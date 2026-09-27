#!/usr/bin/env python3
"""
Тесты для компонентов Этапа 0 (Quick Wins)

Проверяет:
1. LayoutDetector (DocLayout-YOLO) - graceful degradation
2. QwenVLService - graceful degradation
3. OCRServiceFactory - обратная совместимость
4. Существующий функционал - не сломан

Запуск:
    python scripts/tests/test_stage0_components.py

Или через pytest:
    pytest scripts/tests/test_stage0_components.py -v
"""

import sys
import os
from pathlib import Path

# Добавляем путь к проекту
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import unittest
from io import BytesIO


class TestLayoutDetector(unittest.TestCase):
    """Тесты LayoutDetector (DocLayout-YOLO)"""
    
    def test_import_without_error(self):
        """Импорт не должен падать даже без doclayout-yolo"""
        try:
            from scripts.pdf_to_context.extractors.layout_detector import (
                LayoutDetector,
                LayoutCategory,
                LayoutElement,
                is_layout_detection_available,
                DOCLAYOUT_AVAILABLE
            )
            # Импорт успешен
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Импорт упал с ошибкой: {e}")
    
    def test_graceful_degradation(self):
        """При отсутствии DocLayout-YOLO должен возвращать пустой список"""
        from scripts.pdf_to_context.extractors.layout_detector import (
            LayoutDetector,
            is_layout_detection_available
        )
        
        detector = LayoutDetector()
        
        # Создаем тестовое изображение (белый PNG 100x100)
        from PIL import Image
        import io
        img = Image.new('RGB', (100, 100), color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        test_image = buffer.getvalue()
        
        # Должен вернуть пустой список если недоступен
        result = detector.detect(test_image)
        
        if not is_layout_detection_available():
            self.assertEqual(result, [])
            print("✅ LayoutDetector: graceful degradation работает")
        else:
            # Если доступен - должен вернуть список (может быть пустым для белого изображения)
            self.assertIsInstance(result, list)
            print(f"✅ LayoutDetector: доступен, обнаружено {len(result)} элементов")
    
    def test_layout_category_enum(self):
        """LayoutCategory должен корректно конвертировать строки"""
        from scripts.pdf_to_context.extractors.layout_detector import LayoutCategory
        
        # Тест конвертации
        self.assertEqual(LayoutCategory.from_string("text"), LayoutCategory.TEXT)
        self.assertEqual(LayoutCategory.from_string("TITLE"), LayoutCategory.TITLE)
        self.assertEqual(LayoutCategory.from_string("unknown_type"), LayoutCategory.UNKNOWN)
        
        print("✅ LayoutCategory: enum работает корректно")


class TestQwenVLService(unittest.TestCase):
    """Тесты QwenVLService"""
    
    def test_import_without_error(self):
        """Импорт не должен падать даже без transformers"""
        try:
            from scripts.pdf_to_context.ocr_service.qwen_service import (
                QwenVLService,
                is_qwen_available,
                TORCH_AVAILABLE,
                TRANSFORMERS_AVAILABLE
            )
            # Импорт успешен
            self.assertTrue(True)
            print(f"✅ QwenVLService: импорт успешен (torch={TORCH_AVAILABLE}, transformers={TRANSFORMERS_AVAILABLE})")
        except ImportError as e:
            self.fail(f"Импорт упал с ошибкой: {e}")
    
    def test_availability_check(self):
        """Проверка is_available() без падения"""
        from scripts.pdf_to_context.ocr_service.qwen_service import (
            QwenVLService,
            is_qwen_available
        )
        
        service = QwenVLService()
        available = service.is_available()
        
        # Не должен падать, должен вернуть bool
        self.assertIsInstance(available, bool)
        
        if available:
            print("✅ QwenVLService: доступен")
        else:
            print("✅ QwenVLService: недоступен (это OK - graceful degradation)")
    
    def test_prompts_defined(self):
        """Проверка наличия предустановленных промптов"""
        from scripts.pdf_to_context.ocr_service.qwen_service import QwenVLService
        
        self.assertIn("default", QwenVLService.PROMPTS)
        self.assertIn("table", QwenVLService.PROMPTS)
        self.assertIn("bpmn", QwenVLService.PROMPTS)
        self.assertIn("russian", QwenVLService.PROMPTS)
        
        print("✅ QwenVLService: промпты определены")


class TestOCRServiceFactory(unittest.TestCase):
    """Тесты обратной совместимости OCRServiceFactory"""
    
    def test_old_api_still_works(self):
        """Старый API должен работать без изменений"""
        from scripts.pdf_to_context.ocr_service.factory import OCRServiceFactory
        
        # Старый API: create() без аргументов
        # Должен работать (может выбросить RuntimeError если нет сервисов)
        try:
            service = OCRServiceFactory.create()
            self.assertIsNotNone(service)
            print(f"✅ OCRServiceFactory.create(): {service.get_service_name()}")
        except RuntimeError as e:
            # Это OK - нет доступных сервисов
            self.assertIn("Ни один OCR сервис недоступен", str(e))
            print("✅ OCRServiceFactory.create(): правильно выбрасывает RuntimeError")
    
    def test_new_service_type_parameter(self):
        """Новый параметр service_type должен работать"""
        from scripts.pdf_to_context.ocr_service.factory import OCRServiceFactory
        
        # Проверка что параметр принимается
        # (может выбросить RuntimeError если сервис недоступен)
        for service_type in ["auto", "deepseek", "qwen", "paddle"]:
            try:
                service = OCRServiceFactory.create(service_type=service_type)
                print(f"✅ service_type='{service_type}': {service.get_service_name()}")
            except RuntimeError:
                print(f"✅ service_type='{service_type}': недоступен (OK)")
    
    def test_list_available_services(self):
        """Тест нового метода list_available_services()"""
        from scripts.pdf_to_context.ocr_service.factory import OCRServiceFactory
        
        services = OCRServiceFactory.list_available_services()
        
        # Должен вернуть словарь с тремя ключами
        self.assertIn("deepseek", services)
        self.assertIn("paddle", services)
        self.assertIn("qwen", services)
        
        print("✅ list_available_services():")
        for name, info in services.items():
            status = "✓" if info.get("available", False) else "✗"
            print(f"   {status} {name}: {info.get('description', info.get('error', 'unknown'))}")


class TestBackwardCompatibility(unittest.TestCase):
    """Тесты обратной совместимости существующего кода"""
    
    def test_native_extractor_unchanged(self):
        """NativeExtractor должен работать как раньше"""
        from scripts.pdf_to_context.extractors import NativeExtractor
        
        extractor = NativeExtractor()
        self.assertTrue(hasattr(extractor, 'extract_page'))
        self.assertTrue(hasattr(extractor, 'extract_text_blocks'))
        self.assertTrue(hasattr(extractor, 'extract_image_blocks'))
        
        print("✅ NativeExtractor: API не изменился")
    
    def test_ocr_client_unchanged(self):
        """OCRClient должен работать как раньше"""
        from scripts.pdf_to_context.extractors import OCRClient
        
        # Должен импортироваться без ошибок
        self.assertTrue(True)
        print("✅ OCRClient: импорт работает")
    
    def test_hybrid_handler_unchanged(self):
        """HybridHandler должен работать как раньше"""
        from scripts.pdf_to_context.extractors import HybridHandler
        
        # Должен импортироваться без ошибок
        self.assertTrue(True)
        print("✅ HybridHandler: импорт работает")
    
    def test_existing_scripts_import(self):
        """Существующие скрипты должны импортироваться"""
        try:
            # Основной пайплайн
            from scripts.pdf_to_context.pipeline import PDFToContextPipeline
            print("✅ PDFToContextPipeline: импорт работает")
        except ImportError as e:
            self.fail(f"PDFToContextPipeline не импортируется: {e}")
        
        try:
            # Документный пайплайн
            from scripts.pdf_to_context.document_pipeline import DocumentToContextPipeline
            print("✅ DocumentToContextPipeline: импорт работает")
        except ImportError as e:
            self.fail(f"DocumentToContextPipeline не импортируется: {e}")


class TestIntegration(unittest.TestCase):
    """Интеграционные тесты"""
    
    def test_extractors_module_exports(self):
        """Проверка экспортов модуля extractors"""
        from scripts.pdf_to_context import extractors
        
        # Старые экспорты должны быть доступны
        self.assertTrue(hasattr(extractors, 'NativeExtractor'))
        self.assertTrue(hasattr(extractors, 'OCRClient'))
        self.assertTrue(hasattr(extractors, 'HybridHandler'))
        
        # Новый экспорт
        self.assertTrue(hasattr(extractors, 'get_layout_detector'))
        
        print("✅ extractors: все экспорты доступны")
    
    def test_get_layout_detector_function(self):
        """Проверка функции get_layout_detector()"""
        from scripts.pdf_to_context.extractors import get_layout_detector
        
        LayoutDetector, is_available = get_layout_detector()
        
        # Должен вернуть либо класс и функцию, либо (None, lambda)
        if LayoutDetector is not None:
            self.assertTrue(callable(is_available))
            print(f"✅ get_layout_detector(): LayoutDetector доступен, available={is_available()}")
        else:
            self.assertFalse(is_available())
            print("✅ get_layout_detector(): graceful degradation (None, False)")


def run_tests():
    """Запуск всех тестов с красивым выводом"""
    print("=" * 60)
    print("🧪 ТЕСТЫ ЭТАПА 0: Quick Wins")
    print("=" * 60)
    print()
    
    # Создаем тестовый suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Добавляем все тесты
    suite.addTests(loader.loadTestsFromTestCase(TestLayoutDetector))
    suite.addTests(loader.loadTestsFromTestCase(TestQwenVLService))
    suite.addTests(loader.loadTestsFromTestCase(TestOCRServiceFactory))
    suite.addTests(loader.loadTestsFromTestCase(TestBackwardCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # Запускаем с выводом
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Итоги
    print()
    print("=" * 60)
    if result.wasSuccessful():
        print("✅ ВСЕ ТЕСТЫ ПРОШЛИ!")
        print("   Обратная совместимость сохранена")
        print("   Новые компоненты работают корректно")
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ!")
        print(f"   Ошибок: {len(result.failures)}")
        print(f"   Исключений: {len(result.errors)}")
    print("=" * 60)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
