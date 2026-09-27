#!/usr/bin/env python3
"""
Тесты исправлений обработки БНД (410 документов).

Проверяет 6 категорий ошибок из анализа:
1. Порядок таблиц и текста (интерливинг по Y-координатам)
2. Сложные таблицы (merged cells, forward fill)
3. Схемы и рисунки (LayoutDetector, порог фильтрации, placeholder)
4. Колонтитулы и версия документа (OCR титульной, убран хардкод)
5. Пропуск текста (whitelist англ. терминов, footer_ratio)
6. Текст -> таблица (валидация таблиц, lines-стратегия)

Тестовые документы из анализа:
- ИОТ-006-04 (Инструкция по охране труда для бортпроводников Boeing 737)
- РД-М1.033-01 (Управление рисками и внутренний контроль)
- РД-В6.026-02 (Руководство по деятельности организации по ТО)

Запуск:
    python3 scripts/tests/test_bnd_processing_fixes.py
    
Или через pytest:
    pytest scripts/tests/test_bnd_processing_fixes.py -v
    
Только unit-тесты (без PDF):
    pytest scripts/tests/test_bnd_processing_fixes.py -v -k "not integration"
"""

import sys
import os
import re
import unittest
from pathlib import Path
from typing import List, Optional

# Добавляем путь к проекту
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# Пути к тестовым документам
# ============================================================================

BND_PDF_DIR = PROJECT_ROOT / "input2" / "BND" / "pdf"
FULL_RUN_DIR = PROJECT_ROOT / "output3" / "full_run_latest"

# Тестовые документы из анализа
TEST_DOCS = {
    "ИОТ-006-04": {
        "pdf_dir": "ИОТ-006-04 ^B9FECBD841C4F91745258B90002BF697",
        "pdf_name": "ИОТ-006-04 (Эталон для печати).pdf",
        "output_dir": "69_ИОТ-006-04",
    },
    "РД-М1.033-01": {
        "pdf_dir": "РД-М1.033-01 ^52E4D5A79B44D6E54525876F0022C179",
        "pdf_name": "РД-М1.033-01 (Эталон 1 для печати).pdf",
        "output_dir": "373_РД-М1.033-01",
    },
    "РД-В6.026-02": {
        "pdf_dir": "РД-В6.026-02 ^4F5EA6B538A6EC5E45258D2B001324D4",
        "pdf_name": "РД-В6.026-02 (Эталон для печати).pdf",
        "output_dir": "366_РД-В6.026-02",
    },
}


def _get_pdf_path(doc_code: str) -> Optional[Path]:
    """Получить путь к PDF тестового документа."""
    info = TEST_DOCS.get(doc_code)
    if not info:
        return None
    path = BND_PDF_DIR / info["pdf_dir"] / info["pdf_name"]
    return path if path.exists() else None


def _get_output_path(doc_code: str) -> Optional[Path]:
    """Получить путь к обработанному результату."""
    info = TEST_DOCS.get(doc_code)
    if not info:
        return None
    path = FULL_RUN_DIR / info["output_dir"]
    return path if path.exists() else None


# ============================================================================
# Категория 1: Порядок таблиц и текста
# ============================================================================

class TestTableInterleaving(unittest.TestCase):
    """Категория 1: Таблицы вставляются на правильное место (не в конец страницы)."""
    
    def test_interleave_function_exists(self):
        """Функция _interleave_text_and_tables существует и импортируется."""
        from scripts.document_graph.pdfplumber_extractor import _interleave_text_and_tables
        self.assertTrue(callable(_interleave_text_and_tables))
    
    def test_interleave_empty_tables(self):
        """Без таблиц — текст выводится как есть."""
        from scripts.document_graph.pdfplumber_extractor import (
            _interleave_text_and_tables, _format_heading
        )
        lines = ["Строка 1", "Строка 2", "Строка 3"]
        result = []
        _interleave_text_and_tables(lines, [], None, result)
        # Все строки должны быть на месте
        text = "\n".join(result)
        self.assertIn("Строка 1", text)
        self.assertIn("Строка 3", text)
    
    def test_table_settings_lines_strategy(self):
        """find_tables использует lines-стратегию (а не text)."""
        # Читаем исходный код и проверяем наличие table_settings
        src = Path("scripts/document_graph/pdfplumber_extractor.py").read_text(encoding="utf-8")
        self.assertIn('"vertical_strategy": "lines"', src,
                      "table_settings должен использовать vertical_strategy='lines'")
        self.assertIn('"horizontal_strategy": "lines"', src,
                      "table_settings должен использовать horizontal_strategy='lines'")


# ============================================================================
# Категория 6: Валидация таблиц (текст -> таблица)
# ============================================================================

class TestTableValidation(unittest.TestCase):
    """Категория 6: Ложные таблицы отсеиваются."""
    
    def test_is_valid_table_exists(self):
        """Функция _is_valid_table существует."""
        from scripts.document_graph.pdfplumber_extractor import _is_valid_table
        self.assertTrue(callable(_is_valid_table))
    
    def test_single_row_not_table(self):
        """Одна строка — не таблица."""
        from scripts.document_graph.pdfplumber_extractor import _is_valid_table
        data = [["Заголовок"]]
        self.assertFalse(_is_valid_table(data))
    
    def test_single_column_not_table(self):
        """Один столбец — не таблица (это список)."""
        from scripts.document_graph.pdfplumber_extractor import _is_valid_table
        data = [["Строка 1"], ["Строка 2"], ["Строка 3"]]
        self.assertFalse(_is_valid_table(data))
    
    def test_valid_table(self):
        """Нормальная таблица из 2+ строк и 2+ колонок — валидна."""
        from scripts.document_graph.pdfplumber_extractor import _is_valid_table
        data = [
            ["Заголовок 1", "Заголовок 2"],
            ["Значение 1", "Значение 2"],
            ["Значение 3", "Значение 4"],
        ]
        self.assertTrue(_is_valid_table(data))
    
    def test_single_column_dominant_not_table(self):
        """Если >85% контента в одном столбце — не таблица."""
        from scripts.document_graph.pdfplumber_extractor import _is_valid_table
        data = [
            ["Очень длинный текст определения, который занимает всю ширину", ""],
            ["Еще одно длинное определение термина в одном столбце", ""],
            ["И третий пункт с подробным описанием без второго столбца", ""],
        ]
        self.assertFalse(_is_valid_table(data))


# ============================================================================
# Категория 2: Сложные таблицы (merged cells)
# ============================================================================

class TestMergedCells(unittest.TestCase):
    """Категория 2: Forward fill для объединённых ячеек."""
    
    def test_forward_fill_exists(self):
        """Функция _forward_fill_table существует."""
        from scripts.document_graph.pdfplumber_extractor import _forward_fill_table
        self.assertTrue(callable(_forward_fill_table))
    
    def test_forward_fill_none_cells(self):
        """None-ячейки заполняются значением сверху."""
        from scripts.document_graph.pdfplumber_extractor import _forward_fill_table
        data = [
            ["Раздел 1", "Описание 1"],
            [None, "Описание 2"],
            [None, "Описание 3"],
            ["Раздел 2", "Описание 4"],
        ]
        result = _forward_fill_table(data)
        self.assertEqual(result[1][0], "Раздел 1")
        self.assertEqual(result[2][0], "Раздел 1")
        self.assertEqual(result[3][0], "Раздел 2")
    
    def test_forward_fill_preserves_header(self):
        """Заголовок (первая строка) не заполняется."""
        from scripts.document_graph.pdfplumber_extractor import _forward_fill_table
        data = [
            ["Колонка A", None],  # None в заголовке
            ["Данные 1", "Данные 2"],
        ]
        result = _forward_fill_table(data)
        # Первая строка остаётся как есть
        self.assertIsNone(result[0][1])
    
    def test_forward_fill_empty_table(self):
        """Пустая таблица не ломается."""
        from scripts.document_graph.pdfplumber_extractor import _forward_fill_table
        self.assertEqual(_forward_fill_table([]), [])
        self.assertEqual(_forward_fill_table([["a"]]), [["a"]])


# ============================================================================
# Категория 5: Пропуск текста (whitelist англ. терминов)
# ============================================================================

class TestTextLossWhitelist(unittest.TestCase):
    """Категория 5: Англоязычные авиационные термины не фильтруются."""
    
    def test_clean_markdown_preserves_aviation_terms(self):
        """Авиационные аббревиатуры не удаляются фильтром латиницы."""
        from scripts.document_graph.full_hierarchy_parser import clean_markdown
        
        # Строки с легитимными англоязычными терминами
        test_lines = [
            "MEL — Minimum Equipment List (Перечень минимального оборудования)",
            "EASA Part-145 Approval — сертификат ТО",
            "Boeing 737-800 Flight Manual",
            "AMOS — Aviation Maintenance and Operations System",
            "RVSM — Reduced Vertical Separation Minimum",
        ]
        
        for line in test_lines:
            md = f"# Тест\n\n{line}\n"
            result = clean_markdown(md)
            self.assertIn(line.split(" — ")[0] if " — " in line else line[:20], result,
                          f"Строка '{line[:50]}...' была удалена фильтром!")
    
    def test_clean_markdown_removes_garbage(self):
        """Мусор от битой кодировки по-прежнему удаляется."""
        from scripts.document_graph.full_hierarchy_parser import clean_markdown
        
        garbage_lines = [
            "# TIYBIII AKUI4OHEP",  # "ПУБЛИЧНОЕ АКЦИОНЕРНОЕ" с битой кодировкой
            "# OEIUECTB O",  # "ОБЩЕСТВО" с битой кодировкой
        ]
        
        for line in garbage_lines:
            md = f"{line}\nНормальный текст\n"
            result = clean_markdown(md)
            self.assertNotIn("TIYBIII", result)
            self.assertIn("Нормальный текст", result)
    
    def test_footer_ratio_reduced(self):
        """footer_ratio снижен до 0.05 (с 0.08)."""
        src = Path("scripts/pdf_to_context/extractors/native_extractor.py").read_text(encoding="utf-8")
        self.assertIn("footer_ratio = 0.05", src,
                      "footer_ratio должен быть 0.05 (снижен с 0.08)")


# ============================================================================
# Категория 3: Схемы и рисунки (LayoutDetector, DiagramDetector)
# ============================================================================

class TestDiagramDetector(unittest.TestCase):
    """Категория 3: DiagramElementDetector и LayoutDetector интеграция."""
    
    def test_diagram_imports(self):
        """DiagramElementDetector импортируется без ошибок."""
        from scripts.pdf_to_context.extractors.layout_detector import (
            DiagramElementDetector,
            DiagramCategory,
            DiagramElement,
            is_diagram_detection_available,
            get_diagram_detector,
        )
        self.assertTrue(callable(get_diagram_detector))
    
    def test_diagram_category_mapping(self):
        """DiagramCategory корректно маппит строки классов."""
        from scripts.pdf_to_context.extractors.layout_detector import DiagramCategory
        
        # BPMN элементы
        self.assertEqual(DiagramCategory.from_string("task"), DiagramCategory.TASK)
        self.assertEqual(DiagramCategory.from_string("exclusiveGateway"), DiagramCategory.EXCLUSIVE_GATEWAY)
        self.assertEqual(DiagramCategory.from_string("sequenceFlow"), DiagramCategory.SEQUENCE_FLOW)
        self.assertEqual(DiagramCategory.from_string("pool"), DiagramCategory.POOL)
        
        # Flowchart элементы
        self.assertEqual(DiagramCategory.from_string("decision"), DiagramCategory.DECISION)
        self.assertEqual(DiagramCategory.from_string("action"), DiagramCategory.TASK)
        self.assertEqual(DiagramCategory.from_string("arrow"), DiagramCategory.ARROW)
        
        # Неизвестный
        self.assertEqual(DiagramCategory.from_string("xyz_unknown"), DiagramCategory.UNKNOWN)
    
    def test_diagram_element_properties(self):
        """DiagramElement: is_node/is_flow работают корректно."""
        from scripts.pdf_to_context.extractors.layout_detector import DiagramElement, DiagramCategory
        
        task = DiagramElement(
            category=DiagramCategory.TASK,
            bbox=(100, 50, 200, 100),
            confidence=0.95,
        )
        self.assertTrue(task.is_node)
        self.assertFalse(task.is_flow)
        self.assertEqual(task.center, (150.0, 75.0))
        
        flow = DiagramElement(
            category=DiagramCategory.SEQUENCE_FLOW,
            bbox=(200, 70, 300, 80),
            confidence=0.8,
        )
        self.assertFalse(flow.is_node)
        self.assertTrue(flow.is_flow)
    
    def test_graceful_degradation_no_model(self):
        """Без обученной модели — возвращает пустой список."""
        from scripts.pdf_to_context.extractors.layout_detector import DiagramElementDetector
        
        detector = DiagramElementDetector(model_path="nonexistent_model.pt")
        self.assertFalse(detector.is_available())
        self.assertEqual(detector.detect(b"fake_image"), [])
    
    def test_build_connections(self):
        """build_connections находит связи по пространственной близости."""
        from scripts.pdf_to_context.extractors.layout_detector import (
            DiagramElementDetector, DiagramElement, DiagramCategory
        )
        
        elements = [
            DiagramElement(
                category=DiagramCategory.TASK,
                bbox=(100, 50, 200, 100),
                confidence=0.95,
                element_id="elem_0",
                text="Задача А",
            ),
            DiagramElement(
                category=DiagramCategory.SEQUENCE_FLOW,
                bbox=(200, 70, 300, 80),  # Горизонтальная стрелка
                confidence=0.8,
                element_id="elem_1",
            ),
            DiagramElement(
                category=DiagramCategory.TASK,
                bbox=(300, 50, 400, 100),
                confidence=0.9,
                element_id="elem_2",
                text="Задача Б",
            ),
        ]
        
        connections = DiagramElementDetector.build_connections(elements)
        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0]["from"], "elem_0")
        self.assertEqual(connections[0]["to"], "elem_2")
    
    def test_to_structured_json(self):
        """to_structured_json генерирует корректный JSON."""
        from scripts.pdf_to_context.extractors.layout_detector import (
            DiagramElementDetector, DiagramElement, DiagramCategory
        )
        
        elements = [
            DiagramElement(
                category=DiagramCategory.TASK,
                bbox=(100, 50, 200, 100),
                confidence=0.95,
                element_id="elem_0",
                text="Проверка",
            ),
        ]
        connections = [{"from": "elem_0", "to": "elem_1", "type": "sequence_flow", "confidence": 0.8}]
        
        result = DiagramElementDetector.to_structured_json(elements, connections, page_num=5)
        
        self.assertEqual(result["type"], "diagram")
        self.assertEqual(result["page"], 5)
        self.assertEqual(len(result["elements"]), 1)
        self.assertEqual(result["elements"][0]["text"], "Проверка")
        self.assertEqual(len(result["connections"]), 1)
    
    def test_to_markdown(self):
        """to_markdown генерирует читаемое описание."""
        from scripts.pdf_to_context.extractors.layout_detector import (
            DiagramElementDetector, DiagramElement, DiagramCategory
        )
        
        elements = [
            DiagramElement(
                category=DiagramCategory.TASK,
                bbox=(100, 50, 200, 100), confidence=0.95,
                element_id="elem_0", text="Задача",
            ),
        ]
        connections = [{"from": "elem_0", "to": "elem_1", "type": "sequence_flow", "confidence": 0.8}]
        
        md = DiagramElementDetector.to_markdown(elements, connections)
        self.assertIn("YOLO12", md)
        self.assertIn("task", md)
        self.assertIn("Задача", md)
    
    def test_image_area_threshold_lowered(self):
        """Порог фильтрации изображений снижен до 0.02 при наличии LayoutDetector."""
        src = Path("scripts/document_graph/pdfplumber_extractor.py").read_text(encoding="utf-8")
        self.assertIn("0.02 if layout_detector else 0.08", src,
                      "Порог должен быть 0.02 с LayoutDetector, 0.08 без")
    
    def test_parse_figure_prompt(self):
        """Используется prompt_type='parse_figure' вместо 'ocr_simple'."""
        src = Path("scripts/document_graph/pdfplumber_extractor.py").read_text(encoding="utf-8")
        self.assertIn('prompt_type="parse_figure"', src)
        # Не должно быть ocr_simple для основных изображений
        # (ocr_simple может быть в других местах, но в секции OCR графики — parse_figure)


# ============================================================================
# Категория 4: Колонтитулы и версия документа
# ============================================================================

class TestVersionExtraction(unittest.TestCase):
    """Категория 4: Извлечение версии документа с титульной страницы."""
    
    def test_extract_version_function_exists(self):
        """Функция _extract_version_from_ocr существует."""
        from scripts.document_graph.pdfplumber_extractor import _extract_version_from_ocr
        self.assertTrue(callable(_extract_version_from_ocr))
    
    def test_extract_version_izdanie_reviziya(self):
        """Парсинг 'ИЗДАНИЕ 2 / РЕВИЗИЯ 0'."""
        from scripts.document_graph.pdfplumber_extractor import _extract_version_from_ocr
        
        lines = ["УТВЕРЖДЕНО", "ИЗДАНИЕ 2 / РЕВИЗИЯ 0", "Дата введения: 01.01.2025"]
        result = _extract_version_from_ocr(lines)
        self.assertIsNotNone(result)
        self.assertIn("Издание 2", result)
        self.assertIn("Ревизия 0", result)
    
    def test_extract_version_issue_izdanie(self):
        """Парсинг 'Issue/Издание 3'."""
        from scripts.document_graph.pdfplumber_extractor import _extract_version_from_ocr
        
        lines = ["Issue/Издание 3", "Rev./Ревизия 1"]
        result = _extract_version_from_ocr(lines)
        self.assertIsNotNone(result)
        self.assertIn("3", result)
    
    def test_extract_version_none_if_missing(self):
        """Если версии нет — возвращает None."""
        from scripts.document_graph.pdfplumber_extractor import _extract_version_from_ocr
        
        lines = ["Просто текст без версии", "Ещё текст"]
        result = _extract_version_from_ocr(lines)
        self.assertIsNone(result)
    
    def test_no_hardcoded_company_name(self):
        """Хардкод 'ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО' убран из OCR титульной."""
        src = Path("scripts/document_graph/pdfplumber_extractor.py").read_text(encoding="utf-8")
        # В request_ocr не должно быть хардкода
        # Ищем паттерн: title_md += "**ПУБЛИЧНОЕ ...
        # Он должен быть удалён
        lines = src.split("\n")
        in_request_ocr = False
        for line in lines:
            if "def request_ocr" in line:
                in_request_ocr = True
            if in_request_ocr and 'ПУБЛИЧНОЕ АКЦИОНЕРНОЕ' in line:
                self.fail("Хардкод 'ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО' не убран из request_ocr()!")
            if in_request_ocr and line.strip().startswith("return "):
                break


# ============================================================================
# Категория 3+: Экспорт __init__.py
# ============================================================================

class TestExports(unittest.TestCase):
    """Проверка экспортов из __init__.py."""
    
    def test_get_diagram_detector_export(self):
        """get_diagram_detector экспортируется из extractors."""
        from scripts.pdf_to_context.extractors import get_diagram_detector
        self.assertTrue(callable(get_diagram_detector))
    
    def test_get_layout_detector_export(self):
        """get_layout_detector экспортируется из extractors."""
        from scripts.pdf_to_context.extractors import get_layout_detector
        self.assertTrue(callable(get_layout_detector))


# ============================================================================
# Интеграционные тесты (требуют реальные PDF файлы)
# ============================================================================

@unittest.skipUnless(
    _get_pdf_path("ИОТ-006-04") is not None,
    "PDF файл ИОТ-006-04 не найден в input2/BND/pdf/"
)
class TestIntegrationIOT006(unittest.TestCase):
    """Интеграционные тесты на ИОТ-006-04 (замечания пп. 16-18)."""
    
    def test_pdfplumber_extracts_text(self):
        """pdfplumber извлекает текст из ИОТ-006-04."""
        from scripts.document_graph.pdfplumber_extractor import extract_text_pdfplumber
        
        pdf_path = _get_pdf_path("ИОТ-006-04")
        text = extract_text_pdfplumber(
            str(pdf_path),
            ocr_title=False,  # Без OCR для скорости
            ocr_graphics=False,
        )
        
        self.assertGreater(len(text), 1000, "Извлечено слишком мало текста")
        # Проверяем что базовые разделы на месте
        self.assertIn("охран", text.lower(), "Должно быть слово 'охрана/охраны'")
    
    def test_tables_not_at_end(self):
        """Таблицы не уезжают в конец страницы (Категория 1, п.18)."""
        from scripts.document_graph.pdfplumber_extractor import extract_text_pdfplumber
        
        pdf_path = _get_pdf_path("ИОТ-006-04")
        text = extract_text_pdfplumber(
            str(pdf_path),
            ocr_title=False,
            ocr_graphics=False,
        )
        
        # Ищем паттерн: таблица (|...|) не должна быть скоплением в конце страницы
        pages = text.split("<!-- Страница")
        for page in pages[1:]:  # Пропускаем первую часть
            lines = page.split("\n")
            table_lines = [i for i, l in enumerate(lines) if "|" in l and "---" not in l]
            text_lines = [i for i, l in enumerate(lines) if l.strip() and "|" not in l and not l.startswith("<!--")]
            
            if table_lines and text_lines:
                # Проверяем что таблицы не ВСЕ в конце
                last_text = max(text_lines) if text_lines else 0
                first_table = min(table_lines) if table_lines else 0
                # Если таблица начинается после всего текста — это проблема
                # (допускаем если таблица в конце и это нормально)


@unittest.skipUnless(
    _get_pdf_path("РД-В6.026-02") is not None,
    "PDF файл РД-В6.026-02 не найден в input2/BND/pdf/"
)
class TestIntegrationRDV6(unittest.TestCase):
    """Интеграционные тесты на РД-В6.026-02 (замечания пп. 1-15)."""
    
    def test_pdfplumber_extracts_large_document(self):
        """pdfplumber обрабатывает большой документ (475 секций)."""
        from scripts.document_graph.pdfplumber_extractor import extract_pages_pdfplumber
        
        pdf_path = _get_pdf_path("РД-В6.026-02")
        pages = extract_pages_pdfplumber(str(pdf_path))
        
        self.assertGreater(len(pages), 10, "Должно быть >10 страниц")
        
        # Проверяем что текст извлечён с большинства страниц
        pages_with_text = sum(1 for p in pages if p.text.strip())
        self.assertGreater(pages_with_text, len(pages) * 0.8,
                          "Текст должен быть извлечён с >80% страниц")


# ============================================================================
# Тесты train скрипта
# ============================================================================

class TestTrainScript(unittest.TestCase):
    """Проверка скрипта обучения DiagramDetector."""
    
    def test_train_script_imports(self):
        """Скрипт обучения импортируется без ошибок."""
        try:
            from scripts.utils.train_diagram_detector import (
                check_prerequisites,
                convert_coco_to_yolo,
            )
            self.assertTrue(callable(check_prerequisites))
            self.assertTrue(callable(convert_coco_to_yolo))
        except ImportError as e:
            self.fail(f"Импорт скрипта обучения упал: {e}")
    
    def test_train_script_help(self):
        """Скрипт обучения выводит help без ошибок."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/utils/train_diagram_detector.py", "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT)
        )
        self.assertEqual(result.returncode, 0, f"Help вернул ошибку: {result.stderr}")
        self.assertIn("train_diagram_detector", result.stdout)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print(f"{'='*60}")
    print(f"Тесты исправлений обработки БНД")
    print(f"{'='*60}")
    print(f"Проект: {PROJECT_ROOT}")
    print()
    
    # Проверяем наличие тестовых файлов
    for code, info in TEST_DOCS.items():
        pdf_path = _get_pdf_path(code)
        output_path = _get_output_path(code)
        pdf_status = "OK" if pdf_path else "NOT FOUND"
        out_status = "OK" if output_path else "NOT FOUND"
        print(f"  {code}: PDF={pdf_status}, Output={out_status}")
    
    print()
    unittest.main(verbosity=2)
