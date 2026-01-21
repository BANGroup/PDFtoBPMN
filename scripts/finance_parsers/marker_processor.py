"""
Marker Processor - использует marker-pdf для конвертации PDF в структурированный Markdown

Преимущества Marker:
- Высокая точность распознавания таблиц
- Понимание структуры документа
- Сохранение форматирования
- Быстрая работа (10x быстрее Nougat)
"""

from pathlib import Path
from typing import Optional, Dict
import subprocess
import json


class MarkerProcessor:
    """Процессор на базе Marker CLI для конвертации PDF"""
    
    def __init__(self):
        """Инициализация процессора"""
        self.check_marker_available()
    
    def check_marker_available(self) -> bool:
        """Проверяет доступность marker_single в PATH"""
        try:
            result = subprocess.run(
                ["which", "marker_single"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                print("✅ Marker доступен")
                return True
            else:
                raise RuntimeError("marker_single не работает")
        except FileNotFoundError:
            raise RuntimeError(
                "❌ marker_single не найден.\n"
                "Установите: pip install marker-pdf"
            )
        except Exception as e:
            raise RuntimeError(f"❌ Ошибка проверки Marker: {e}")
    
    def process_pdf(
        self,
        pdf_path: Path,
        output_dir: Path,
        page_range: Optional[str] = None,
        disable_ocr: bool = False,
        verbose: bool = False
    ) -> Dict:
        """
        Конвертирует PDF в Markdown через CLI
        
        Args:
            pdf_path: Путь к PDF файлу
            output_dir: Папка для сохранения результата
            page_range: Диапазон страниц (например: "0,1,2" или "0-10")
            disable_ocr: Отключить OCR (для текстовых PDF)
            verbose: Подробный вывод
            
        Returns:
            Dict с путями к созданным файлам и метаданными
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF не найден: {pdf_path}")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Формируем команду
        cmd = [
            "marker_single",
            str(pdf_path),
            "--output_dir", str(output_dir)
        ]
        
        if page_range:
            cmd.extend(["--page_range", page_range])
        
        if disable_ocr:
            cmd.append("--disable_ocr")
        
        if verbose:
            print(f"🔄 Запуск Marker: {' '.join(cmd)}")
        
        # Запускаем
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 минут максимум
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Marker завершился с ошибкой:\n{result.stderr}")
            
            if verbose:
                print(result.stdout)
            
            # Ищем созданные файлы
            base_name = pdf_path.stem
            md_file = output_dir / base_name / f"{base_name}.md"
            meta_file = output_dir / base_name / f"{base_name}_meta.json"
            
            if not md_file.exists():
                raise FileNotFoundError(f"Marker не создал MD файл: {md_file}")
            
            # Читаем метаданные
            metadata = {}
            if meta_file.exists():
                with open(meta_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            
            return {
                'success': True,
                'md_file': md_file,
                'meta_file': meta_file if meta_file.exists() else None,
                'metadata': metadata
            }
        
        except subprocess.TimeoutExpired:
            raise TimeoutError("Marker превысил лимит времени (5 минут)")
        except Exception as e:
            raise RuntimeError(f"Ошибка выполнения Marker: {e}")
    
    def process_and_read(
        self,
        pdf_path: Path,
        output_dir: Path,
        **kwargs
    ) -> str:
        """
        Конвертирует PDF и возвращает содержимое MD
        
        Args:
            pdf_path: Путь к PDF
            output_dir: Папка для сохранения
            **kwargs: Аргументы для process_pdf
            
        Returns:
            Содержимое MD файла
        """
        result = self.process_pdf(pdf_path, output_dir, **kwargs)
        
        with open(result['md_file'], 'r', encoding='utf-8') as f:
            return f.read()


# Пример использования
if __name__ == "__main__":
    # Тест
    processor = MarkerProcessor()
    
    test_pdf = Path("input/Finance/Выпуск 4-02 на 16.06.2020.pdf")
    output = Path("output/finance/marker_test")
    
    if test_pdf.exists():
        print("🧪 Тестируем Marker на первых 3 страницах...")
        result = processor.process_pdf(
            test_pdf,
            output,
            page_range="0,1,2",
            disable_ocr=False,  # Включить OCR
            verbose=True
        )
        
        print("\n✅ РЕЗУЛЬТАТ:")
        print(f"   MD файл: {result['md_file']}")
        print(f"   Размер: {result['md_file'].stat().st_size:,} байт")
        
        if result['metadata']:
            print(f"\n📊 МЕТАДАННЫЕ:")
            if 'table_of_contents' in result['metadata']:
                toc = result['metadata']['table_of_contents']
                print(f"   Разделов в оглавлении: {len(toc)}")
    else:
        print(f"❌ Тестовый PDF не найден: {test_pdf}")

