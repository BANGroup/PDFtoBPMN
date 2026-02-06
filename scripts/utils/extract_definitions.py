#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Извлечение определений (секция 3) и сокращений (секция 4) из 410 документов БНД.

Входные данные: output3/full_run_latest/*/full_content.md
Выходные данные:
  - output3/definitions.json   (определения из секции 3)
  - output3/abbreviations.json (сокращения из секции 4)

Использование:
    python3 scripts/utils/extract_definitions.py
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


# ─── Конфигурация ───────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # корень проекта
INPUT_DIR = BASE_DIR / "output3" / "full_run_latest"
OUTPUT_DIR = BASE_DIR / "output3"

# Паттерны начала секции 3 (определения)
# Покрывают варианты: "# 3 ОПРЕДЕЛЕНИЯ", "# 3 Определения", "# 3 ОПРЕДЕЛЕНИЯ/ DEFINITIONS"
SEC3_START_PATTERNS = [
    re.compile(r'^#\s+3\s+ОПРЕДЕЛЕНИЯ', re.IGNORECASE),
    re.compile(r'^#\s+3\s+Определения', re.IGNORECASE),
    re.compile(r'^#\s+3\s+DEFINITIONS', re.IGNORECASE),
    re.compile(r'^#\s+3\.?\s+ОПРЕДЕЛЕНИЯ', re.IGNORECASE),
    re.compile(r'^#\s+3\.?\s+Определения', re.IGNORECASE),
]

# Паттерны начала секции 4 (сокращения)
# Покрывают: "# 4 ОБОЗНАЧЕНИЯ И СОКРАЩЕНИЯ", OCR-ошибки "СОКРАЩЕЕННИИЯЯ"
SEC4_START_PATTERNS = [
    re.compile(r'^#\s+4\s+ОБОЗНАЧЕНИЯ\s+И\s+СОКРАЩ', re.IGNORECASE),
    re.compile(r'^#\s+4\s+Обозначения\s+и\s+сокращ', re.IGNORECASE),
    re.compile(r'^#\s+4\s+TERMS\s+AND\s+ABBREVIATIONS', re.IGNORECASE),
    re.compile(r'^#\s+4\s+СОКРАЩЕНИЯ', re.IGNORECASE),
    re.compile(r'^#\s+4\.?\s+ОБОЗНАЧЕНИЯ', re.IGNORECASE),
    re.compile(r'^#\s+4\.?\s+Обозначения', re.IGNORECASE),
    re.compile(r'^#\s+4\.?\s+СОКРАЩЕНИЯ', re.IGNORECASE),
]

# Паттерн для обнаружения подсекции 4.2 СОКРАЩЕНИЯ (внутри секции 4)
SEC4_2_PATTERNS = [
    re.compile(r'^#+\s+4\.2\s+СОКРАЩЕНИЯ', re.IGNORECASE),
    re.compile(r'^#+\s+4\.2\s+Сокращения', re.IGNORECASE),
    re.compile(r'^#+\s+4\.2\s+ABBREVIATIONS', re.IGNORECASE),
    re.compile(r'^#+\s+СОКРАЩЕНИЯ\s*/\s*ABBREVIATIONS', re.IGNORECASE),
]

# Паттерн следующей секции верхнего уровня (конец текущей секции)
NEXT_SECTION_PATTERN = re.compile(r'^#\s+\d+[\.\s]')

# Паттерн для мусорных строк
JUNK_PATTERNS = [
    re.compile(r'^<!--\s*Страница\s+\d+\s*-->'),         # page breaks
    re.compile(r'^Изменение/Revision'),                    # revision marks
    re.compile(r'^\s*$'),                                  # пустые строки
    re.compile(r'^---+$'),                                 # горизонтальные линии
    re.compile(r'^\|\s*-+\s*\|'),                          # markdown table separators
]

# Паттерн для определения/сокращения: «Термин – расшифровка»
# Тире может быть: – (em-dash), — (em-dash), - (hyphen)
TERM_DASH_PATTERN = re.compile(
    r'^(.+?)\s+[–—\-]\s+(.+)',
    re.DOTALL
)

# Паттерн для определения в табличном формате: | Термин – расшифровка |
TABLE_TERM_PATTERN = re.compile(
    r'^\|\s*(.+?)\s+[–—\-]\s+(.+?)\s*\|?\s*$'
)


# ─── Утилиты ────────────────────────────────────────────────────────────────

def extract_doc_code(dirname: str) -> str:
    """Извлекает код документа из имени папки.
    '02_ДП-Б1.004-06' -> 'ДП-Б1.004-06'
    """
    parts = dirname.split('_', 1)
    if len(parts) == 2:
        return parts[1]
    return dirname


def is_junk_line(line: str) -> bool:
    """Проверяет, является ли строка мусорной."""
    for p in JUNK_PATTERNS:
        if p.match(line):
            return True
    return False


def is_document_header(line: str, doc_code: str) -> bool:
    """Проверяет, является ли строка колонтитулом документа.
    Пример: 'Обновление бортовых навигационных баз данных ДП-Б1.004-06'
    """
    if doc_code and doc_code in line and len(line.strip()) < 200:
        # Строка содержит код документа — скорее всего колонтитул
        return True
    return False


def clean_table_line(line: str) -> str:
    """Убирает маркеры markdown-таблицы из строки."""
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    # Убираем  (bullet) в начале
    line = line.strip()
    if line.startswith(''):
        line = line[1:].strip()
    return line.strip()


def is_toc_line(line: str) -> bool:
    """Проверяет, является ли строка элементом оглавления (TOC).
    
    Примеры TOC:
      # 3 Определения .................................................................................................................... 8
      # 4 Обозначения и сокращения ......................................................................................... 10
      # 3 Определения……………………………………………………………………………………9
    """
    # Многоточие (обычные точки)
    if '...' in line:
        return True
    # Многоточие (символ …)
    if '…' in line:
        return True
    # Заканчивается на номер страницы (число) — TOC паттерн
    stripped = line.rstrip()
    if re.search(r'\s+\d{1,3}\s*$', stripped) and len(stripped) > 40:
        return True
    return False


def find_section(lines: list, start_patterns: list, start_idx: int = 0) -> int:
    """Находит номер строки, с которой начинается секция (пропуская TOC)."""
    for i in range(start_idx, len(lines)):
        line = lines[i].strip()
        for p in start_patterns:
            if p.match(line):
                # Пропускаем TOC-записи
                if is_toc_line(line):
                    continue
                return i
    return -1


def find_section_end(lines: list, start_idx: int) -> int:
    """Находит конец секции — начало следующей секции # N или конец файла."""
    for i in range(start_idx + 1, len(lines)):
        line = lines[i].strip()
        if NEXT_SECTION_PATTERN.match(line):
            # Проверяем, что это не та же секция (подсекция ##)
            if line.startswith('# ') and not line.startswith('## '):
                return i
    return len(lines)


def merge_continuation_lines(raw_lines: list, doc_code: str) -> list:
    """Склеивает многострочные строки в логические блоки.
    
    Определения часто разбиты на несколько строк из-за переносов PDF.
    Нужно склеить строки-продолжения в один блок.
    """
    blocks = []
    current_block = ""

    for line in raw_lines:
        line = line.rstrip()

        # Пропускаем мусор
        if is_junk_line(line):
            continue
        if is_document_header(line, doc_code):
            continue
        # Подсекции (## 4.1 ОБОЗНАЧЕНИЯ) — пропускаем как заголовки
        if line.strip().startswith('## ') or line.strip().startswith('### '):
            if current_block:
                blocks.append(current_block.strip())
                current_block = ""
            # Добавляем подзаголовок как маркер
            blocks.append("__SUBSECTION__:" + line.strip())
            continue

        stripped = line.strip()
        if not stripped:
            continue

        # Табличный формат: | ... |
        if stripped.startswith('|'):
            cleaned = clean_table_line(stripped)
            if not cleaned or cleaned.startswith('-'):
                continue
            # Проверяем, начинается ли с нового термина
            if TERM_DASH_PATTERN.match(cleaned):
                if current_block:
                    blocks.append(current_block.strip())
                current_block = cleaned
            else:
                # Продолжение предыдущего
                current_block += " " + cleaned
            continue

        # Обычный текстовый формат
        # Новый термин начинается с заглавной буквы + тире
        if TERM_DASH_PATTERN.match(stripped) and not stripped[0].islower():
            if current_block:
                blocks.append(current_block.strip())
            current_block = stripped
        else:
            # Продолжение предыдущего блока
            if current_block:
                current_block += " " + stripped
            else:
                current_block = stripped

    if current_block:
        blocks.append(current_block.strip())

    return blocks


def parse_term_definition(block: str) -> tuple:
    """Парсит блок 'Термин – определение' в кортеж (term, definition).
    
    Returns:
        (term, definition) или None если не удалось распарсить
    """
    if block.startswith("__SUBSECTION__:"):
        return None

    m = TERM_DASH_PATTERN.match(block)
    if m:
        term = m.group(1).strip()
        definition = m.group(2).strip()

        # Очистка термина
        term = re.sub(r'\s+', ' ', term)
        # Убираем начальные спецсимволы
        term = term.lstrip('•·▪►●■○◆★☆✓✔ ')

        # Очистка определения
        definition = re.sub(r'\s+', ' ', definition)

        # Фильтрация мусорных записей
        if len(term) < 2 or len(definition) < 15:
            return None
        # Фильтрация нумерованных строк (не определения)
        if re.match(r'^\d+[\.\)]\s', term):
            return None
        # Термин начинается с тире — обрывок строки
        if term.startswith('–') or term.startswith('—'):
            return None
        # Термин начинается со скобки — обрывок из середины предыдущего определения
        if term.startswith('('):
            return None
        # Термин — это просто число или страница
        if re.match(r'^\d+\.?\s*$', term):
            return None
        # Определение — просто число (утечка из TOC)
        if re.match(r'^\d+\.?\s*$', definition):
            return None

        # OCR-каша: буквы утроены/удвоены (ааа, ббб) или слова слиплись (> 25 кириллицы подряд)
        if re.search(r'([а-яА-ЯёЁ])\1{2,}', term) or re.search(r'([а-яА-ЯёЁ])\1{2,}', definition):
            return None
        if re.search(r'[а-яА-ЯёЁ]{25,}', term):
            return None
        # Определение — каша: слишком мало пробелов для длинного текста
        if len(definition) > 50 and definition.count(' ') / len(definition) < 0.05:
            return None

        return (term, definition)
    
    return None


def has_cyrillic(text: str) -> bool:
    """Проверяет наличие кириллических символов."""
    return bool(re.search(r'[а-яА-ЯёЁ]', text))


def extract_en_term(en_text: str) -> str:
    """Извлекает английский термин из английской части определения/расшифровки.
    
    Паттерны:
      "Aeronautical information - information obtained..."  → "Aeronautical information"
      "Database - collection of..."                         → "Database"
      "(International Air Transport Association)"           → "International Air Transport Association"
      "ANI - aeronautical information"                      → "ANI"
      "Company – UTair Aviation, Public Joint Stock..."     → "Company"
      "(Flight management system)"                          → "Flight management system"
    """
    if not en_text:
        return ""

    text = en_text.strip()

    # Если весь текст в скобках: "(International Air Transport Association)"
    if text.startswith('(') and ')' in text:
        inner = text[1:text.index(')')]
        return inner.strip()

    # Разделяем по тире: " - " или " – " или "– "
    for sep in [' - ', ' – ', '– ', '— ']:
        if sep in text:
            term = text.split(sep, 1)[0].strip()
            # Если термин разумной длины
            if 1 < len(term) < 100:
                return term

    # Если нет тире, но текст короткий — весь текст и есть термин
    if len(text) < 60:
        return text.rstrip('.,;: ')

    return ""


def clean_ocr_artifacts(text: str) -> str:
    """Убирает OCR-артефакты из текста определений/сокращений.
    
    - Пайп-символы | (остатки таблиц/чекбоксов)
    - Множественные пробелы
    - Обрезанные слова с переносами (вклю- ающий → включающий)
    """
    if not text:
        return text
    # Убираем пайп-символы (одиночные и с пробелами вокруг)
    text = re.sub(r'\s*\|\s*', ' ', text)
    # Убираем переносы слов: "вклю- ающий" → "включающий"
    text = re.sub(r'(\w)- (\w)', r'\1\2', text)
    # Множественные пробелы → один
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def split_ru_en(text: str) -> tuple:
    """Разделяет смешанный ru+en текст на русскую и английскую части.
    
    Алгоритм: каждый токен (слово) классифицируется по алфавиту символов.
    Нейтральные токены (цифры, пунктуация, скобки) добавляются к обоим потокам.
    
    Returns:
        (ru_text, en_text) — русская и английская части.
        Если текст одноязычный, второе поле будет пустой строкой.
    """
    if not text:
        return ("", "")

    tokens = re.findall(r'\S+', text)

    ru_parts = []
    en_parts = []

    for token in tokens:
        has_cyr = bool(re.search(r'[а-яА-ЯёЁ]', token))
        has_lat = bool(re.search(r'[a-zA-Z]', token))

        if has_cyr and not has_lat:
            ru_parts.append(token)
        elif has_lat and not has_cyr:
            en_parts.append(token)
        elif has_cyr and has_lat:
            # Смешанный токен (ЮТэйр, SAP-система) — в обе части
            ru_parts.append(token)
            en_parts.append(token)
        else:
            # Нейтральный (цифры, пунктуация, скобки) — в обе части
            if ru_parts:
                ru_parts.append(token)
            if en_parts:
                en_parts.append(token)

    ru_text = ' '.join(ru_parts).strip()
    en_text = ' '.join(en_parts).strip()

    # Очистка: убираем дубликаты пробелов и висящую пунктуацию
    ru_text = re.sub(r'\s+', ' ', ru_text).strip()
    en_text = re.sub(r'\s+', ' ', en_text).strip()
    # Убираем висящие тире/запятые на краях
    ru_text = re.sub(r'^[\s,;.\-–—]+|[\s,;\-–—]+$', '', ru_text).strip()
    en_text = re.sub(r'^[\s,;.\-–—]+|[\s,;\-–—]+$', '', en_text).strip()

    # Если английская часть слишком короткая (< 20 символов), 
    # это скорее всего просто аббревиатура в русском тексте (SAP, IATA, ISO),
    # а не полноценный английский перевод
    if len(en_text) < 20:
        # Возвращаем оригинал как русский, английский — пустой
        cleaned_original = re.sub(r'\s+', ' ', text).strip()
        return (cleaned_original, "")

    return (ru_text, en_text)


# ─── Основные функции извлечения ─────────────────────────────────────────────

def extract_definitions_from_file(filepath: Path, dirname: str) -> list:
    """Извлекает определения из секции 3 файла full_content.md."""
    doc_code = extract_doc_code(dirname)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  [ОШИБКА] Не удалось прочитать {filepath}: {e}")
        return []

    # Ищем секцию 3 (find_section автоматически пропускает TOC-записи)
    sec3_idx = find_section(lines, SEC3_START_PATTERNS)
    if sec3_idx == -1:
        return []

    # Находим конец секции 3
    sec3_end = find_section_end(lines, sec3_idx)

    # Извлекаем строки секции 3 (без заголовка)
    section_lines = [l.rstrip('\n') for l in lines[sec3_idx + 1:sec3_end]]

    # Склеиваем многострочные определения
    blocks = merge_continuation_lines(section_lines, doc_code)

    # Парсим определения
    results = []
    for block in blocks:
        parsed = parse_term_definition(block)
        if parsed:
            term, definition = parsed
            # Пропускаем чисто английские определения (без кириллицы в термине)
            if not has_cyrillic(term):
                continue
            # Очистка OCR-артефактов и разделение ru/en
            definition = clean_ocr_artifacts(definition)
            def_ru, def_en = split_ru_en(definition)
            def_ru = clean_ocr_artifacts(def_ru)
            def_en = clean_ocr_artifacts(def_en)
            term_en = extract_en_term(def_en)
            results.append({
                "term": term,
                "term_en": term_en,
                "definition_ru": def_ru,
                "definition_en": def_en,
                "source": doc_code,
                "source_dir": dirname,
            })

    return results


def extract_abbreviations_from_file(filepath: Path, dirname: str) -> list:
    """Извлекает сокращения из секции 4 файла full_content.md."""
    doc_code = extract_doc_code(dirname)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  [ОШИБКА] Не удалось прочитать {filepath}: {e}")
        return []

    # Ищем секцию 4 (find_section автоматически пропускает TOC-записи)
    sec4_idx = find_section(lines, SEC4_START_PATTERNS)
    if sec4_idx == -1:
        return []

    # Находим конец секции 4
    sec4_end = find_section_end(lines, sec4_idx)

    # Извлекаем строки секции 4 (без заголовка)
    section_lines = [l.rstrip('\n') for l in lines[sec4_idx + 1:sec4_end]]

    # Склеиваем строки
    blocks = merge_continuation_lines(section_lines, doc_code)

    # Фильтруем: если есть подсекция 4.1 ОБОЗНАЧЕНИЯ — пропускаем до 4.2 СОКРАЩЕНИЯ
    # Подсекция 4.1 содержит графические символы, не сокращения
    in_subsection_41 = False
    in_subsection_42 = False
    filtered_blocks = []

    for block in blocks:
        if block.startswith("__SUBSECTION__:"):
            header = block.split(":", 1)[1].strip().upper()
            if '4.1' in header or 'ОБОЗНАЧЕНИЯ' in header and 'СОКРАЩЕНИЯ' not in header:
                in_subsection_41 = True
                in_subsection_42 = False
                continue
            if '4.2' in header or 'СОКРАЩЕНИЯ' in header or 'ABBREVIATIONS' in header:
                in_subsection_41 = False
                in_subsection_42 = True
                continue
            continue

        # Если нет подсекций — берём всё
        # Если есть подсекция 4.1 — пропускаем её содержимое
        if in_subsection_41 and not in_subsection_42:
            continue

        filtered_blocks.append(block)

    # Если вообще не нашли подсекций — используем все blocks
    if not in_subsection_41 and not in_subsection_42:
        filtered_blocks = [b for b in blocks if not b.startswith("__SUBSECTION__:")]

    # Парсим сокращения
    results = []
    for block in filtered_blocks:
        if block.startswith("__SUBSECTION__:"):
            continue

        parsed = parse_term_definition(block)
        if parsed:
            abbr, expansion = parsed
            # Убираем чисто мусорные строки
            if abbr.lower() in ('обозначения не применяются', 'не применяются'):
                continue
            # Очистка OCR-артефактов и разделение ru/en
            expansion = clean_ocr_artifacts(expansion)
            exp_ru, exp_en = split_ru_en(expansion)
            exp_ru = clean_ocr_artifacts(exp_ru)
            exp_en = clean_ocr_artifacts(exp_en)
            abbr_en = extract_en_term(exp_en)
            results.append({
                "abbreviation": abbr,
                "abbreviation_en": abbr_en,
                "expansion_ru": exp_ru,
                "expansion_en": exp_en,
                "source": doc_code,
                "source_dir": dirname,
            })

    return results


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if not INPUT_DIR.exists():
        print(f"ОШИБКА: Директория не найдена: {INPUT_DIR}")
        sys.exit(1)

    # Собираем все папки
    dirs = sorted([
        d.name for d in INPUT_DIR.iterdir()
        if d.is_dir() and (d / "full_content.md").exists()
    ])

    print(f"📂 Найдено папок с full_content.md: {len(dirs)}")
    print(f"📁 Входная директория: {INPUT_DIR}")
    print(f"📁 Выходная директория: {OUTPUT_DIR}")
    print()

    all_definitions = []
    all_abbreviations = []
    docs_with_defs = 0
    docs_with_abbrs = 0
    docs_without_sec3 = []
    docs_without_sec4 = []

    for i, dirname in enumerate(dirs, 1):
        filepath = INPUT_DIR / dirname / "full_content.md"
        doc_code = extract_doc_code(dirname)

        # Прогресс
        if i % 50 == 0 or i == len(dirs):
            print(f"  [{i}/{len(dirs)}] Обработано...")

        # Извлекаем определения
        defs = extract_definitions_from_file(filepath, dirname)
        if defs:
            all_definitions.extend(defs)
            docs_with_defs += 1
        else:
            docs_without_sec3.append(dirname)

        # Извлекаем сокращения
        abbrs = extract_abbreviations_from_file(filepath, dirname)
        if abbrs:
            all_abbreviations.extend(abbrs)
            docs_with_abbrs += 1
        else:
            docs_without_sec4.append(dirname)

    # ─── Формируем JSON ────────────────────────────────────────────────────

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    definitions_json = {
        "metadata": {
            "generated": now,
            "description": "Определения из секции 3 нормативных документов БНД",
            "total_documents_processed": len(dirs),
            "documents_with_definitions": docs_with_defs,
            "documents_without_definitions": len(docs_without_sec3),
            "total_entries": len(all_definitions),
        },
        "entries": all_definitions,
    }

    abbreviations_json = {
        "metadata": {
            "generated": now,
            "description": "Обозначения и сокращения из секции 4 нормативных документов БНД",
            "total_documents_processed": len(dirs),
            "documents_with_abbreviations": docs_with_abbrs,
            "documents_without_abbreviations": len(docs_without_sec4),
            "total_entries": len(all_abbreviations),
        },
        "entries": all_abbreviations,
    }

    # ─── Сохраняем ──────────────────────────────────────────────────────────

    defs_path = OUTPUT_DIR / "definitions.json"
    abbrs_path = OUTPUT_DIR / "abbreviations.json"

    with open(defs_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(definitions_json, f, ensure_ascii=False, indent=2)

    with open(abbrs_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(abbreviations_json, f, ensure_ascii=False, indent=2)

    # ─── Статистика ─────────────────────────────────────────────────────────

    print()
    print("=" * 60)
    print("📊 РЕЗУЛЬТАТЫ")
    print("=" * 60)
    print()
    print(f"📗 ОПРЕДЕЛЕНИЯ (секция 3):")
    print(f"   Файл: {defs_path}")
    print(f"   Документов обработано: {len(dirs)}")
    print(f"   Документов с определениями: {docs_with_defs}")
    print(f"   Документов без секции 3: {len(docs_without_sec3)}")
    print(f"   Всего определений извлечено: {len(all_definitions)}")
    print()
    print(f"📘 СОКРАЩЕНИЯ (секция 4):")
    print(f"   Файл: {abbrs_path}")
    print(f"   Документов обработано: {len(dirs)}")
    print(f"   Документов с сокращениями: {docs_with_abbrs}")
    print(f"   Документов без секции 4: {len(docs_without_sec4)}")
    print(f"   Всего сокращений извлечено: {len(all_abbreviations)}")
    print()

    # Статистика по языкам
    from collections import Counter
    def_counts = Counter(d["source"] for d in all_definitions)
    abbr_counts = Counter(a["source"] for a in all_abbreviations)

    defs_with_en = sum(1 for d in all_definitions if d["definition_en"])
    defs_with_term_en = sum(1 for d in all_definitions if d["term_en"])
    abbrs_with_en = sum(1 for a in all_abbreviations if a["expansion_en"])
    abbrs_with_abbr_en = sum(1 for a in all_abbreviations if a["abbreviation_en"])

    print(f"   Определений с англ. переводом: {defs_with_en}")
    print(f"   Определений с англ. термином: {defs_with_term_en}")
    print(f"   Определений только на русском: {len(all_definitions) - defs_with_en}")
    print()
    print(f"   Сокращений с англ. переводом: {abbrs_with_en}")
    print(f"   Сокращений с англ. термином: {abbrs_with_abbr_en}")
    print(f"   Сокращений только на русском: {len(all_abbreviations) - abbrs_with_en}")
    print()

    print("📈 Топ-10 документов по определениям:")
    for doc, count in def_counts.most_common(10):
        print(f"   {doc}: {count}")
    print()

    print("📈 Топ-10 документов по сокращениям:")
    for doc, count in abbr_counts.most_common(10):
        print(f"   {doc}: {count}")
    print()

    # Примеры без секции 3
    if docs_without_sec3:
        print(f"⚠️  Примеры документов без секции 3 (первые 10):")
        for d in docs_without_sec3[:10]:
            print(f"   {d}")
        print()

    print("✅ Готово!")


if __name__ == "__main__":
    main()
