#!/usr/bin/env python3
"""
Тест DeepSeek-OCR на страницах с BPMN диаграммами
Проверка разных типов промптов
"""

import fitz
import requests
import json
from PIL import Image
import io
from pathlib import Path
import time

# Конфигурация
PDF_PATH = "input_data/КД-СТ-161-01 (Эталон для ознакомления).pdf"
OCR_SERVICE_URL = "http://localhost:8000"
OUTPUT_DIR = Path("output/bpmn_test")

# Тестовые страницы
TEST_PAGES = [
    {
        "page_num": 54,
        "name": "Эксклюзивный шлюз по событиям",
        "prompt_type": "bpmn",
        "description": "Простая BPMN диаграмма: Процесс 1 → Gateway → События → Процессы 2,3"
    },
    {
        "page_num": 26,
        "name": "Переход от IDEF0 к BPMN",
        "prompt_type": "complex_diagram",
        "description": "Сложная схема с IDEF0 и BPMN элементами"
    }
]

def check_ocr_service():
    """Проверка доступности OCR сервиса"""
    try:
        response = requests.get(f"{OCR_SERVICE_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print("✅ OCR сервис доступен:")
            print(f"   Model loaded: {data['model_loaded']}")
            print(f"   CUDA available: {data['cuda_available']}")
            print(f"   GPU: {data.get('cuda_device', 'N/A')}")
            return True
        else:
            print(f"❌ OCR сервис вернул код {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ OCR сервис недоступен: {e}")
        print(f"\n💡 Запустите сервис:")
        print(f"   cd ~/Obligations")
        print(f"   source DeepSeek-OCR/venv/bin/activate")
        print(f"   python -m uvicorn pdf_to_context.ocr_service.app:app --host 0.0.0.0 --port 8000")
        return False


def render_page_to_image(pdf_path: str, page_num: int, dpi: int = 300) -> bytes:
    """
    Рендер страницы PDF в PNG
    
    Args:
        pdf_path: Путь к PDF
        page_num: Номер страницы (1-based)
        dpi: Разрешение рендеринга
    
    Returns:
        PNG изображение в bytes
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]  # 0-based index
    
    # Рендеринг
    zoom = dpi / 72.0  # 72 DPI - базовое разрешение PDF
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    # Конвертация в PNG bytes
    img_data = pix.tobytes("png")
    
    doc.close()
    
    return img_data


def ocr_page(image_data: bytes, prompt_type: str = "default") -> dict:
    """
    OCR страницы через DeepSeek-OCR
    
    Args:
        image_data: PNG изображение в bytes
        prompt_type: Тип промпта
    
    Returns:
        Результат OCR (blocks + markdown)
    """
    files = {
        "file": ("page.png", image_data, "image/png")
    }
    
    data = {
        "prompt_type": prompt_type
    }
    
    response = requests.post(
        f"{OCR_SERVICE_URL}/ocr/figure",
        files=files,
        data=data,
        timeout=120  # 2 минуты на обработку
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"OCR failed: {response.status_code} - {response.text}")


def save_results(page_info: dict, image_data: bytes, ocr_result: dict):
    """Сохранение результатов теста"""
    page_num = page_info["page_num"]
    prompt_type = page_info["prompt_type"]
    
    # Создаем директорию
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Сохраняем изображение
    img_path = OUTPUT_DIR / f"page_{page_num}_{prompt_type}.png"
    with open(img_path, "wb") as f:
        f.write(image_data)
    
    # Сохраняем markdown
    md_path = OUTPUT_DIR / f"page_{page_num}_{prompt_type}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {page_info['name']}\n\n")
        f.write(f"**Страница:** {page_num}\n\n")
        f.write(f"**Prompt type:** {prompt_type}\n\n")
        f.write(f"**Описание:** {page_info['description']}\n\n")
        f.write("---\n\n")
        f.write("## Распознанный контент\n\n")
        f.write(ocr_result["markdown"])
    
    # Сохраняем JSON с полными данными
    json_path = OUTPUT_DIR / f"page_{page_num}_{prompt_type}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        result_data = {
            "page_info": page_info,
            "ocr_result": ocr_result,
            "stats": {
                "blocks_count": len(ocr_result.get("blocks", [])),
                "markdown_length": len(ocr_result.get("markdown", ""))
            }
        }
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    print(f"   💾 Сохранено:")
    print(f"      - Изображение: {img_path}")
    print(f"      - Markdown: {md_path}")
    print(f"      - JSON: {json_path}")


def main():
    """Главная функция теста"""
    print("="*100)
    print("🧪 ТЕСТ DeepSeek-OCR НА BPMN ДИАГРАММАХ")
    print("="*100)
    print()
    
    # Проверка сервиса
    if not check_ocr_service():
        return
    
    print()
    print(f"📄 Документ: {PDF_PATH}")
    print(f"🎯 Тестовых страниц: {len(TEST_PAGES)}")
    print()
    print("="*100)
    
    # Тестируем каждую страницу
    results = []
    
    for i, page_info in enumerate(TEST_PAGES, 1):
        page_num = page_info["page_num"]
        prompt_type = page_info["prompt_type"]
        
        print()
        print(f"📃 ТЕСТ {i}/{len(TEST_PAGES)}: Страница {page_num}")
        print(f"   Название: {page_info['name']}")
        print(f"   Описание: {page_info['description']}")
        print(f"   Prompt: {prompt_type}")
        print()
        
        try:
            # Рендеринг страницы
            print("   🖼️  Рендеринг страницы (300 DPI)...")
            start_time = time.time()
            image_data = render_page_to_image(PDF_PATH, page_num, dpi=300)
            render_time = time.time() - start_time
            
            # Определяем размер изображения
            img = Image.open(io.BytesIO(image_data))
            print(f"      ✅ Готово ({render_time:.2f}s): {img.size[0]}x{img.size[1]} пикселей")
            
            # OCR обработка
            print(f"   🔍 OCR обработка (prompt_type={prompt_type})...")
            start_time = time.time()
            ocr_result = ocr_page(image_data, prompt_type)
            ocr_time = time.time() - start_time
            
            # Статистика
            blocks = ocr_result.get("blocks", [])
            markdown = ocr_result.get("markdown", "")
            
            print(f"      ✅ Готово ({ocr_time:.2f}s):")
            print(f"         - Блоков распознано: {len(blocks)}")
            print(f"         - Markdown длина: {len(markdown)} символов")
            
            # Превью результата
            if markdown:
                preview = markdown[:200].replace("\n", " ")
                print(f"         - Превью: {preview}...")
            
            # Сохранение результатов
            save_results(page_info, image_data, ocr_result)
            
            results.append({
                "page_info": page_info,
                "success": True,
                "render_time": render_time,
                "ocr_time": ocr_time,
                "blocks_count": len(blocks),
                "markdown_length": len(markdown)
            })
            
            print("   ✅ УСПЕХ")
            
        except Exception as e:
            print(f"   ❌ ОШИБКА: {e}")
            results.append({
                "page_info": page_info,
                "success": False,
                "error": str(e)
            })
    
    # Итоговая статистика
    print()
    print("="*100)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("="*100)
    print()
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print(f"✅ Успешно обработано: {len(successful)}/{len(TEST_PAGES)}")
    print(f"❌ Ошибок: {len(failed)}")
    
    if successful:
        print()
        print("Средние показатели:")
        avg_render = sum(r["render_time"] for r in successful) / len(successful)
        avg_ocr = sum(r["ocr_time"] for r in successful) / len(successful)
        avg_blocks = sum(r["blocks_count"] for r in successful) / len(successful)
        
        print(f"  - Время рендеринга: {avg_render:.2f}s")
        print(f"  - Время OCR: {avg_ocr:.2f}s")
        print(f"  - Блоков на страницу: {avg_blocks:.1f}")
    
    print()
    print(f"📁 Результаты сохранены в: {OUTPUT_DIR}")
    print()
    print("💡 Следующие шаги:")
    print("   1. Откройте markdown файлы в output/bpmn_test/")
    print("   2. Проверьте качество распознавания")
    print("   3. Оцените структурированность вывода")
    print()


if __name__ == "__main__":
    main()








