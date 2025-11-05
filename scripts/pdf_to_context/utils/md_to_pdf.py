"""
Утилита для конвертации Markdown в PDF

Использует pandoc для генерации качественных PDF файлов с поддержкой:
- Русского языка
- Таблиц
- Форматирования
- Оглавления (TOC)

Принципы:
- KISS: Простой вызов pandoc через subprocess
- Автоматическая проверка доступности pandoc
- Graceful degradation: если pandoc нет - пропускаем без ошибок
"""

import subprocess
import shutil
from pathlib import Path
from typing import Optional


class MarkdownToPDFConverter:
    """
    Конвертер Markdown → PDF через pandoc
    
    Особенности:
    - Поддержка русского языка (DejaVu Sans)
    - Правильное отображение таблиц
    - Автоматическое оглавление для длинных документов
    - Landscape для широких таблиц (RACI)
    """
    
    def __init__(self):
        """Инициализация конвертера"""
        self.pandoc_available = self._check_pandoc()
    
    @staticmethod
    def _check_pandoc() -> bool:
        """
        Проверка доступности pandoc
        
        Returns:
            bool: True если pandoc установлен
        """
        return shutil.which("pandoc") is not None
    
    def convert(self, 
                md_path: str, 
                pdf_path: Optional[str] = None,
                landscape: bool = False,
                add_toc: bool = False) -> bool:
        """
        Конвертировать MD файл в PDF
        
        Args:
            md_path: Путь к входному MD файлу
            pdf_path: Путь к выходному PDF файлу (по умолчанию: заменить .md на .pdf)
            landscape: Использовать альбомную ориентацию (для широких таблиц)
            add_toc: Добавить оглавление
        
        Returns:
            bool: True если конвертация успешна
        """
        if not self.pandoc_available:
            print(f"   ⚠️  pandoc не установлен - пропускаем генерацию PDF")
            return False
        
        # Определяем путь к PDF
        md_file = Path(md_path)
        if not md_file.exists():
            print(f"   ❌ Файл не найден: {md_path}")
            return False
        
        if pdf_path is None:
            pdf_path = md_file.with_suffix('.pdf')
        
        pdf_file = Path(pdf_path)
        
        # Формируем команду pandoc
        cmd = [
            "pandoc",
            str(md_file),
            "-o", str(pdf_file),
            "--pdf-engine=xelatex",
            "-V", "mainfont=DejaVu Sans",
        ]
        
        # Добавляем параметры ориентации
        if landscape:
            cmd.extend(["-V", "geometry:margin=1.5cm,landscape"])
        else:
            cmd.extend(["-V", "geometry:margin=2cm"])
        
        # Добавляем оглавление для длинных документов
        if add_toc:
            cmd.append("--toc")
        
        # Выполняем конвертацию
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # 60 секунд максимум
            )
            
            if result.returncode == 0:
                print(f"   ✓ PDF создан: {pdf_file.name}")
                return True
            else:
                print(f"   ❌ Ошибка pandoc: {result.stderr[:200]}")
                return False
        
        except subprocess.TimeoutExpired:
            print(f"   ❌ Timeout при конвертации {md_file.name}")
            return False
        
        except Exception as e:
            print(f"   ❌ Ошибка конвертации: {e}")
            return False
    
    def convert_process_files(self, output_dir: str, base_name: str) -> dict:
        """
        Конвертировать все MD файлы процесса в PDF
        
        Создает PDF версии для:
        - [base_name]_OCR.md → [base_name]_OCR.pdf
        - [base_name]_RACI.md → [base_name]_RACI.pdf (landscape)
        - [base_name]_Pipeline.md → [base_name]_Pipeline.pdf (с TOC)
        - [base_name].md → [base_name].pdf (с TOC)
        
        Args:
            output_dir: Путь к директории output/[process_name]/
            base_name: Базовое имя процесса
        
        Returns:
            dict: Статистика конвертации
        """
        output_path = Path(output_dir)
        stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
        
        # Список файлов для конвертации
        conversions = [
            {
                "md": f"{base_name}_OCR.md",
                "landscape": False,
                "toc": False
            },
            {
                "md": f"{base_name}_RACI.md",
                "landscape": True,  # Широкие таблицы
                "toc": False
            },
            {
                "md": f"{base_name}_Pipeline.md",
                "landscape": False,
                "toc": True  # Длинный документ
            },
            {
                "md": f"{base_name}.md",
                "landscape": False,
                "toc": True  # Документация процесса
            }
        ]
        
        for conversion in conversions:
            md_file = output_path / conversion["md"]
            
            if not md_file.exists():
                continue
            
            stats["total"] += 1
            
            success = self.convert(
                md_path=str(md_file),
                landscape=conversion["landscape"],
                add_toc=conversion["toc"]
            )
            
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1
        
        # Если pandoc не установлен
        if not self.pandoc_available:
            stats["skipped"] = stats["total"]
            stats["total"] = 0
            stats["success"] = 0
            stats["failed"] = 0
        
        return stats


# Глобальный экземпляр конвертера
_converter = None


def get_converter() -> MarkdownToPDFConverter:
    """
    Получить глобальный экземпляр конвертера
    
    Returns:
        MarkdownToPDFConverter
    """
    global _converter
    if _converter is None:
        _converter = MarkdownToPDFConverter()
    return _converter


def convert_md_to_pdf(md_path: str, 
                      pdf_path: Optional[str] = None,
                      landscape: bool = False,
                      add_toc: bool = False) -> bool:
    """
    Быстрая функция для конвертации MD → PDF
    
    Args:
        md_path: Путь к MD файлу
        pdf_path: Путь к PDF файлу (опционально)
        landscape: Альбомная ориентация
        add_toc: Добавить оглавление
    
    Returns:
        bool: True если успешно
    """
    converter = get_converter()
    return converter.convert(md_path, pdf_path, landscape, add_toc)


def convert_process_files(output_dir: str, base_name: str) -> dict:
    """
    Конвертировать все MD файлы процесса в PDF
    
    Args:
        output_dir: Директория output/[process_name]/
        base_name: Базовое имя процесса
    
    Returns:
        dict: Статистика
    """
    converter = get_converter()
    return converter.convert_process_files(output_dir, base_name)

