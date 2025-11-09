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
    
    @staticmethod
    def _preprocess_markdown(content: str) -> str:
        """
        Препроцессинг MD для лучшей конвертации в PDF/DOCX
        
        Исправления:
        - Удаляет emoji (не поддерживаются в PDF/DOCX)
        - Заменяет <br> на двойной перенос строки  
        - Добавляет пробелы после ** (жирный текст)
        - Добавляет пробелы после ) перед ЗАГЛАВНЫМИ буквами
        
        Args:
            content: Исходный MD контент
        
        Returns:
            str: Обработанный контент
        """
        import re
        
        # 0a. Заменить специальные Unicode символы на ASCII аналоги
        replacements = {
            '✓': '[+]',      # галочка → [+]
            '✅': '[OK]',    # зеленая галочка → [OK]
            '❌': '[X]',     # красный крест → [X]
            '⚠️': '[!]',     # предупреждение → [!]
            '→': '->',       # стрелка вправо → ->
            '←': '<-',       # стрелка влево → <-
            '↑': '^',        # стрелка вверх → ^
            '↓': 'v',        # стрелка вниз → v
            '•': '-',        # bullet point → -
            '§': 'S',        # параграф → S
            '№': 'N',        # номер → N
        }
        
        for unicode_char, ascii_char in replacements.items():
            content = content.replace(unicode_char, ascii_char)
        
        # 0b. Удалить оставшиеся emoji (они отображаются как квадратики в PDF/DOCX)
        # Regex для всех emoji Unicode блоков
        emoji_pattern = re.compile(
            "["
            "\U0001F1E0-\U0001F1FF"  # флаги (iOS)
            "\U0001F300-\U0001F5FF"  # символы и пиктограммы
            "\U0001F600-\U0001F64F"  # эмоции
            "\U0001F680-\U0001F6FF"  # транспорт и карты
            "\U0001F700-\U0001F77F"  # алхимические символы
            "\U0001F780-\U0001F7FF"  # геометрические фигуры
            "\U0001F800-\U0001F8FF"  # стрелки
            "\U0001F900-\U0001F9FF"  # дополнительные символы
            "\U0001FA00-\U0001FA6F"  # расширенные символы
            "\U0001FA70-\U0001FAFF"  # символы и пиктограммы
            "\U00002702-\U000027B0"  # Dingbats
            "\U000024C2-\U0001F251" 
            "\U0000FE0F"  # variation selector
            "]+",
            flags=re.UNICODE
        )
        content = emoji_pattern.sub('', content)
        
        # 1. Заменить <br> на двойной перенос строки (лучше работает в таблицах)
        content = re.sub(r'<br>\s*', r'  \n', content)
        
        # 2. Добавить пробел после закрывающего ** (жирный текст)
        content = re.sub(r'\*\*([^*]+)\*\*([А-ЯЁA-Z])', r'**\1** \2', content)
        
        # 3. Добавить пробел после ) перед ЗАГЛАВНЫМИ буквами
        content = re.sub(r'\)([А-ЯЁ]{2,}:)', r') \1', content)
        
        return content
    
    def convert_to_docx(self,
                        md_path: str,
                        docx_path: Optional[str] = None,
                        add_toc: bool = False) -> bool:
        """
        Конвертировать MD файл в DOCX (Word)
        
        DOCX лучше обрабатывает сложные таблицы, чем PDF
        
        Args:
            md_path: Путь к входному MD файлу
            docx_path: Путь к выходному DOCX файлу (по умолчанию: заменить .md на .docx)
            add_toc: Добавить оглавление
        
        Returns:
            bool: True если конвертация успешна
        """
        if not self.pandoc_available:
            print(f"   ⚠️  pandoc не установлен - пропускаем генерацию DOCX")
            return False
        
        # Определяем путь к DOCX
        md_file = Path(md_path)
        if not md_file.exists():
            print(f"   ❌ Файл не найден: {md_path}")
            return False
        
        if docx_path is None:
            docx_path = md_file.with_suffix('.docx')
        
        docx_file = Path(docx_path)
        
        # Читаем и препроцессим MD файл
        tmp_md_path = None
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Применяем препроцессинг
            content = self._preprocess_markdown(content)
            
            # Создаем временный файл с обработанным контентом
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.md', delete=False) as tmp:
                tmp.write(content)
                tmp_md_path = tmp.name
            
        except Exception as e:
            print(f"   ❌ Ошибка препроцессинга: {e}")
            return False
        
        # Формируем команду pandoc для DOCX
        cmd = [
            "pandoc",
            tmp_md_path,
            "-o", str(docx_file),
            "-f", "markdown",
            "-t", "docx",
        ]
        
        # Добавляем оглавление
        if add_toc:
            cmd.append("--toc")
        
        # Выполняем конвертацию
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Очищаем временный файл
            if tmp_md_path and Path(tmp_md_path).exists():
                Path(tmp_md_path).unlink()
            
            if result.returncode == 0:
                print(f"   ✓ DOCX создан: {docx_file.name}")
                return True
            else:
                print(f"   ❌ Ошибка pandoc: {result.stderr[:200]}")
                return False
        
        except subprocess.TimeoutExpired:
            print(f"   ❌ Timeout при конвертации {md_file.name}")
            if tmp_md_path and Path(tmp_md_path).exists():
                Path(tmp_md_path).unlink()
            return False
        
        except Exception as e:
            print(f"   ❌ Ошибка конвертации: {e}")
            if tmp_md_path and Path(tmp_md_path).exists():
                Path(tmp_md_path).unlink()
            return False
    
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
        
        # Читаем и препроцессим MD файл
        tmp_md_path = None
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Применяем препроцессинг
            content = self._preprocess_markdown(content)
            
            # Создаем временный файл с обработанным контентом
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.md', delete=False) as tmp:
                tmp.write(content)
                tmp_md_path = tmp.name
            
        except Exception as e:
            print(f"   ❌ Ошибка препроцессинга: {e}")
            return False
        
        # Формируем команду pandoc (используем временный файл)
        cmd = [
            "pandoc",
            tmp_md_path,
            "-o", str(pdf_file),
            "--pdf-engine=xelatex",
            "-V", "mainfont=DejaVu Sans",
            "--wrap=preserve",  # Сохранять пробелы и переносы
            "--columns=200",     # Широкие колонки для таблиц
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
            
            # Очищаем временный файл
            if tmp_md_path and Path(tmp_md_path).exists():
                Path(tmp_md_path).unlink()
            
            if result.returncode == 0:
                print(f"   ✓ PDF создан: {pdf_file.name}")
                return True
            else:
                print(f"   ❌ Ошибка pandoc: {result.stderr[:200]}")
                return False
        
        except subprocess.TimeoutExpired:
            print(f"   ❌ Timeout при конвертации {md_file.name}")
            # Очищаем временный файл
            if tmp_md_path and Path(tmp_md_path).exists():
                Path(tmp_md_path).unlink()
            return False
        
        except Exception as e:
            print(f"   ❌ Ошибка конвертации: {e}")
            # Очищаем временный файл
            if tmp_md_path and Path(tmp_md_path).exists():
                Path(tmp_md_path).unlink()
            return False
    
    def convert_process_files(self, output_dir: str, base_name: str, format: str = 'docx') -> dict:
        """
        Конвертировать все MD файлы процесса в DOCX или PDF
        
        Создает DOCX/PDF версии для:
        - [base_name]_OCR.md → [base_name]_OCR.docx/.pdf
        - [base_name]_RACI.md → [base_name]_RACI.docx/.pdf
        - [base_name]_Pipeline.md → [base_name]_Pipeline.docx/.pdf (с TOC)
        - [base_name].md → [base_name].docx/.pdf (с TOC)
        
        Args:
            output_dir: Путь к директории output/[process_name]/
            base_name: Базовое имя процесса
            format: Формат вывода ('docx' или 'pdf'). По умолчанию 'docx'
                   DOCX рекомендуется для сложных таблиц
        
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
            
            # Выбор метода конвертации в зависимости от формата
            if format.lower() == 'docx':
                success = self.convert_to_docx(
                    md_path=str(md_file),
                    add_toc=conversion["toc"]
                )
            else:  # PDF
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
                      output_path: Optional[str] = None,  # Alias для pdf_path
                      landscape: bool = False,
                      add_toc: bool = False,
                      format: str = 'docx') -> bool:
    """
    Быстрая функция для конвертации MD → DOCX/PDF
    
    ПРИМЕЧАНИЕ: Несмотря на название функции, по умолчанию конвертирует в DOCX.
    Название - историческое наследие.
    
    Args:
        md_path: Путь к MD файлу
        pdf_path: Путь к выходному файлу (опционально, устаревший параметр)
        output_path: Путь к выходному файлу (опционально, предпочтительный параметр)
        landscape: Альбомная ориентация
        add_toc: Добавить оглавление
        format: Формат вывода ('docx' или 'pdf'). По умолчанию 'docx'
    
    Returns:
        bool: True если успешно
    """
    # Поддержка обоих параметров (output_path имеет приоритет)
    final_path = output_path if output_path else pdf_path
    
    converter = get_converter()
    
    # Если указан format='docx', автоматически изменить расширение
    if format == 'docx' and final_path and not final_path.endswith('.docx'):
        final_path = final_path.replace('.pdf', '.docx')
    
    return converter.convert(md_path, final_path, landscape, add_toc)


def convert_process_files(output_dir: str, base_name: str, format: str = 'docx') -> dict:
    """
    Конвертировать все MD файлы процесса в DOCX или PDF
    
    Args:
        output_dir: Директория output/[process_name]/
        base_name: Базовое имя процесса
        format: Формат вывода ('docx' или 'pdf'). По умолчанию 'docx'
    
    Returns:
        dict: Статистика
    """
    converter = get_converter()
    return converter.convert_process_files(output_dir, base_name, format)

