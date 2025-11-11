#!/usr/bin/env python3
"""
Проверка окружения для PDFtoBPMN проекта

Проверяет:
- Операционную систему (Linux/Windows/macOS)
- Версию Python (≥3.8)
- Кодировку системы (UTF-8)
- Наличие обязательных зависимостей
- Права на запись в output/
- Виртуальное окружение (опционально)

Использование:
    python3 scripts/utils/check_environment.py
    python3 scripts/utils/check_environment.py --strict  # Остановить при warnings

Автор: PDFtoBPMN Project
Дата: 11.11.2025
"""

import sys
import platform
import locale
import os
from pathlib import Path
from typing import List, Tuple, Optional
import subprocess


class EnvironmentChecker:
    """Проверка окружения проекта"""
    
    def __init__(self, strict: bool = False):
        """
        Args:
            strict: Если True, warnings тоже считаются ошибками
        """
        self.strict = strict
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        
        # Определить корень проекта
        self.project_root = Path(__file__).resolve().parent.parent.parent
        
    def check_all(self) -> bool:
        """
        Запуск всех проверок
        
        Returns:
            True если все проверки прошли (или только warnings)
        """
        print("=" * 70)
        print("🔍 ПРОВЕРКА ОКРУЖЕНИЯ PDFtoBPMN")
        print("=" * 70)
        print()
        
        # Запуск всех проверок
        self.check_os()
        self.check_python_version()
        self.check_encoding()
        self.check_dependencies()
        self.check_write_permissions()
        self.check_venv()
        self.check_optional()
        
        # Вывод результатов
        self._print_results()
        
        # Определить успех
        has_errors = len(self.errors) > 0
        has_warnings = len(self.warnings) > 0
        
        if has_errors:
            return False
        elif has_warnings and self.strict:
            return False
        else:
            return True
    
    def check_os(self):
        """Проверка операционной системы"""
        os_name = platform.system()
        os_version = platform.release()
        
        print(f"📟 Операционная система: {os_name} {os_version}")
        
        if os_name == "Linux":
            self.info.append(f"✅ Linux обнаружен ({os_version}) - основная платформа")
        elif os_name == "Windows":
            self.warnings.append(
                f"⚠️ Windows обнаружен ({os_version}). "
                "Проект разработан на Linux. Возможны проблемы с кодировками. "
                "Рекомендация: используйте WSL2 или настройте UTF-8 в терминале."
            )
        elif os_name == "Darwin":  # macOS
            self.warnings.append(
                f"⚠️ macOS обнаружен ({os_version}). "
                "Платформа не тестировалась. Теоретически работает (похож на Linux)."
            )
        else:
            self.errors.append(
                f"❌ Неизвестная ОС: {os_name}. "
                "Поддерживаются: Linux, Windows (с настройкой), macOS."
            )
        
        print()
    
    def check_python_version(self):
        """Проверка версии Python"""
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"
        
        print(f"🐍 Python: {version_str}")
        
        if version.major < 3:
            self.errors.append("❌ Python 2.x не поддерживается. Требуется Python ≥3.8")
        elif version.major == 3 and version.minor < 8:
            self.errors.append(
                f"❌ Python {version_str} слишком старый. "
                "Требуется Python ≥3.8 (для новых фич: f-strings, typing, pathlib)"
            )
        else:
            self.info.append(f"✅ Python {version_str} - поддерживается")
        
        print()
    
    def check_encoding(self):
        """Проверка кодировки системы"""
        try:
            preferred_encoding = locale.getpreferredencoding()
            filesystem_encoding = sys.getfilesystemencoding()
            stdout_encoding = sys.stdout.encoding if hasattr(sys.stdout, 'encoding') else 'unknown'
            
            print(f"📝 Кодировки:")
            print(f"   Предпочитаемая: {preferred_encoding}")
            print(f"   Файловая система: {filesystem_encoding}")
            print(f"   Stdout: {stdout_encoding}")
            
            # Проверка UTF-8
            encodings_ok = True
            problematic = []
            
            if not preferred_encoding.upper().startswith('UTF'):
                problematic.append(f"Предпочитаемая ({preferred_encoding})")
                encodings_ok = False
            
            if not filesystem_encoding.upper().startswith('UTF'):
                problematic.append(f"Файловая система ({filesystem_encoding})")
                encodings_ok = False
            
            if stdout_encoding != 'unknown' and not stdout_encoding.upper().startswith('UTF'):
                problematic.append(f"Stdout ({stdout_encoding})")
                encodings_ok = False
            
            if encodings_ok:
                self.info.append("✅ Кодировки: все UTF-8")
            else:
                os_name = platform.system()
                if os_name == "Windows":
                    self.warnings.append(
                        f"⚠️ Обнаружены не-UTF-8 кодировки: {', '.join(problematic)}.\n"
                        "   Windows fix:\n"
                        "   PowerShell: chcp 65001\n"
                        "   CMD: chcp 65001\n"
                        "   Или установите переменную окружения: PYTHONIOENCODING=utf-8"
                    )
                else:
                    self.warnings.append(
                        f"⚠️ Обнаружены не-UTF-8 кодировки: {', '.join(problematic)}.\n"
                        "   Установите UTF-8 локаль:\n"
                        "   export LANG=en_US.UTF-8\n"
                        "   export LC_ALL=en_US.UTF-8"
                    )
        
        except Exception as e:
            self.warnings.append(f"⚠️ Не удалось определить кодировку: {e}")
        
        print()
    
    def check_dependencies(self):
        """Проверка обязательных зависимостей"""
        print("📦 Зависимости:")
        
        required_packages = [
            ('fitz', 'PyMuPDF', 'Обработка PDF'),
            ('docx', 'python-docx', 'Обработка DOCX'),
            ('openpyxl', 'openpyxl', 'Обработка XLSX'),
            ('requests', 'requests', 'HTTP запросы (OCR)'),
            ('PIL', 'Pillow', 'Обработка изображений'),
        ]
        
        missing = []
        installed = []
        
        for import_name, package_name, description in required_packages:
            try:
                __import__(import_name)
                installed.append((package_name, description))
                print(f"   ✅ {package_name} - установлен")
            except ImportError:
                missing.append((package_name, description))
                print(f"   ❌ {package_name} - НЕ установлен ({description})")
        
        print()
        
        if missing:
            packages_str = ' '.join([pkg for pkg, _ in missing])
            self.errors.append(
                f"❌ Отсутствуют обязательные зависимости: {packages_str}\n"
                f"   Установка:\n"
                f"   pip install {packages_str}"
            )
        else:
            self.info.append(f"✅ Все обязательные зависимости установлены ({len(installed)})")
    
    def check_write_permissions(self):
        """Проверка прав на запись"""
        print("🔐 Права доступа:")
        
        directories_to_check = [
            (self.project_root / "output", "Результаты обработки"),
            (self.project_root / "archive", "Архив старых версий"),
        ]
        
        all_ok = True
        
        for directory, description in directories_to_check:
            # Создать если не существует
            directory.mkdir(parents=True, exist_ok=True)
            
            # Проверить запись
            test_file = directory / ".write_test"
            try:
                test_file.write_text("test", encoding='utf-8')
                test_file.unlink()
                print(f"   ✅ {directory.name}/ - запись разрешена")
            except (PermissionError, OSError) as e:
                print(f"   ❌ {directory.name}/ - НЕТ прав на запись")
                self.errors.append(
                    f"❌ Нет прав на запись в {directory}\n"
                    f"   Описание: {description}\n"
                    f"   Ошибка: {e}"
                )
                all_ok = False
        
        print()
        
        if all_ok:
            self.info.append("✅ Права на запись: все директории доступны")
    
    def check_venv(self):
        """Проверка виртуального окружения (опционально)"""
        print("🌐 Виртуальное окружение:")
        
        # Проверить активацию venv
        in_venv = (
            hasattr(sys, 'real_prefix') or 
            (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
        )
        
        python_path = sys.executable
        
        if in_venv:
            print(f"   ✅ Виртуальное окружение активировано")
            print(f"   📍 Python: {python_path}")
            self.info.append("✅ Виртуальное окружение активировано")
        else:
            print(f"   ⚠️ Виртуальное окружение НЕ активировано")
            print(f"   📍 Используется системный Python: {python_path}")
            
            os_name = platform.system()
            if os_name == "Windows":
                activate_cmd = "venv\\Scripts\\activate.bat"
            else:
                activate_cmd = "source venv/bin/activate"
            
            self.warnings.append(
                f"⚠️ Виртуальное окружение не активировано.\n"
                f"   Рекомендуется использовать venv для изоляции зависимостей.\n"
                f"   Активация: {activate_cmd}\n"
                f"   (Ищите окружение с DeepSeek-OCR для OCR функций)"
            )
        
        print()
    
    def check_optional(self):
        """Проверка опциональных компонентов"""
        print("🔧 Опциональные компоненты:")
        
        # Проверка pandoc (для DOCX генерации)
        try:
            result = subprocess.run(
                ['pandoc', '--version'], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.split('\n')[0]
                print(f"   ✅ pandoc - установлен ({version})")
                self.info.append("✅ pandoc доступен (для генерации DOCX)")
            else:
                print(f"   ⚠️ pandoc - ошибка при запуске")
                self.warnings.append("⚠️ pandoc установлен, но есть проблемы с запуском")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print(f"   ℹ️ pandoc - не установлен")
            self.info.append(
                "ℹ️ pandoc не установлен (опционально для генерации DOCX).\n"
                "   Установка: sudo apt install pandoc (Linux) или скачайте с pandoc.org"
            )
        
        # Проверка GPU/CUDA (для OCR)
        try:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                print(f"   ✅ CUDA - доступен ({gpu_name})")
                self.info.append(f"✅ GPU/CUDA доступен для OCR: {gpu_name}")
            else:
                print(f"   ℹ️ CUDA - не доступен")
                self.info.append(
                    "ℹ️ GPU/CUDA не доступен (опционально для OCR).\n"
                    "   OCR будет работать в режиме 'Native only' (без графики)"
                )
        except ImportError:
            print(f"   ℹ️ PyTorch - не установлен")
            self.info.append("ℹ️ PyTorch не установлен (опционально для OCR)")
        
        print()
    
    def _print_results(self):
        """Вывод итоговых результатов"""
        print("=" * 70)
        print("📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ")
        print("=" * 70)
        print()
        
        # Errors
        if self.errors:
            print(f"❌ КРИТИЧЕСКИЕ ОШИБКИ ({len(self.errors)}):")
            for i, error in enumerate(self.errors, 1):
                print(f"\n{i}. {error}")
            print()
        
        # Warnings
        if self.warnings:
            print(f"⚠️ ПРЕДУПРЕЖДЕНИЯ ({len(self.warnings)}):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"\n{i}. {warning}")
            print()
        
        # Info
        if self.info and not self.errors:
            print(f"✅ ВСЁ ХОРОШО:")
            for info in self.info:
                print(f"   {info}")
            print()
        
        # Итог
        print("=" * 70)
        if self.errors:
            print("❌ ПРОВЕРКА НЕ ПРОЙДЕНА")
            print("   Исправьте критические ошибки перед использованием проекта.")
        elif self.warnings and self.strict:
            print("⚠️ ПРОВЕРКА НЕ ПРОЙДЕНА (strict mode)")
            print("   Устраните предупреждения или запустите без --strict")
        elif self.warnings:
            print("⚠️ ПРОВЕРКА ПРОЙДЕНА С ПРЕДУПРЕЖДЕНИЯМИ")
            print("   Проект будет работать, но рекомендуется устранить предупреждения.")
        else:
            print("✅ ПРОВЕРКА ПРОЙДЕНА УСПЕШНО")
            print("   Окружение настроено корректно. Можно работать!")
        print("=" * 70)


def main():
    """Точка входа"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Проверка окружения для PDFtoBPMN проекта",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Обычная проверка (warnings не блокируют)
  python3 scripts/utils/check_environment.py
  
  # Строгая проверка (warnings = errors)
  python3 scripts/utils/check_environment.py --strict
  
  # Для интеграции в CI/CD используйте --strict

Exit codes:
  0 - всё ок (или только warnings в обычном режиме)
  1 - есть критические ошибки (или warnings в strict режиме)
        """
    )
    
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Строгий режим: warnings тоже считаются ошибками'
    )
    
    args = parser.parse_args()
    
    # Запуск проверки
    checker = EnvironmentChecker(strict=args.strict)
    success = checker.check_all()
    
    # Exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

