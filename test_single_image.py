#!/usr/bin/env python3
"""
Тестирование DeepSeek-OCR на одном изображении с разными промптами
"""

import os
import sys
import time
import subprocess
import requests
from pathlib import Path

# Путь к изображению для тестирования
IMAGE_PATH = "output/bpmn_test/page_54_bpmn.png"
OCR_URL = "http://localhost:8000/ocr/figure"
HEALTH_URL = "http://localhost:8000/health"

# Официальные промпты из DeepSeek-OCR
OFFICIAL_PROMPTS = {
    "1_default": "default",              # <image>\n<|grounding|>Convert the document to markdown
    "2_ocr_simple": "ocr_simple",        # <image>\n<|grounding|>OCR this image
    "3_free_ocr": "free_ocr",            # <image>\nFree OCR
    "4_parse_figure": "parse_figure",    # ⭐ <image>\nParse the figure
    "5_describe": "describe",            # <image>\nDescribe this image in detail
    "6_bpmn": "bpmn",                    # Наш кастомный для BPMN
}

def check_ocr_service():
    """Проверить доступность OCR сервиса"""
    try:
        response = requests.get(HEALTH_URL, timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "healthy":
                print("✅ OCR сервис работает")
                print(f"   Model loaded: {data.get('model_loaded')}")
                print(f"   CUDA available: {data.get('cuda_available')}")
                return True
    except requests.exceptions.RequestException:
        pass
    
    print("❌ OCR сервис недоступен")
    return False

def start_ocr_service():
    """Запустить OCR сервис"""
    print("\n🚀 Запуск OCR сервиса...")
    
    venv_python = "/home/budnik_an/Obligations/DeepSeek-OCR/venv/bin/python"
    cmd = [
        venv_python, "-m", "uvicorn",
        "pdf_to_context.ocr_service.app:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--log-level", "warning"
    ]
    
    process = subprocess.Popen(
        cmd,
        cwd="/home/budnik_an/Obligations",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONUNBUFFERED": "1"}
    )
    
    # Ждем запуска (до 60 секунд)
    print("⏳ Ожидание загрузки модели (до 60 сек)...")
    for i in range(60):
        time.sleep(1)
        if check_ocr_service():
            print(f"✅ Сервис запущен за {i+1} секунд")
            return process
        if i % 10 == 0 and i > 0:
            print(f"   ... {i} секунд прошло...")
    
    print("❌ Не удалось дождаться запуска сервиса")
    process.kill()
    return None

def test_single_prompt(image_path: str, prompt_type: str, prompt_name: str):
    """
    Протестировать один промпт
    
    Args:
        image_path: Путь к изображению
        prompt_type: Тип промпта (для API)
        prompt_name: Название для вывода
    
    Returns:
        dict: Результаты теста
    """
    print(f"\n{'='*80}")
    print(f"📝 Тестируем: {prompt_name} ({prompt_type})")
    print(f"{'='*80}")
    
    if not os.path.exists(image_path):
        print(f"❌ Файл не найден: {image_path}")
        return None
    
    # Отправляем запрос
    start_time = time.time()
    
    with open(image_path, 'rb') as f:
        files = {'file': ('image.png', f, 'image/png')}
        data = {'prompt_type': prompt_type}
        
        try:
            response = requests.post(OCR_URL, files=files, data=data, timeout=120)
            elapsed = time.time() - start_time
            
            if response.status_code != 200:
                print(f"❌ Ошибка HTTP {response.status_code}")
                print(f"   {response.text[:200]}")
                return None
            
            result = response.json()
            
            # Статистика
            blocks = result.get('blocks', [])
            markdown = result.get('markdown', '')
            raw_output = result.get('raw_output', '')
            
            print(f"\n⏱️  Время обработки: {elapsed:.2f} сек")
            print(f"📊 Блоков распознано: {len(blocks)}")
            print(f"📄 Длина markdown: {len(markdown)} символов")
            print(f"🔤 Длина raw output: {len(raw_output)} символов")
            
            # Показываем первые 500 символов markdown
            if markdown:
                print(f"\n📝 Markdown (первые 500 символов):")
                print("-" * 80)
                print(markdown[:500])
                if len(markdown) > 500:
                    print("...")
                print("-" * 80)
            
            # Показываем первые 500 символов raw output
            if raw_output and len(raw_output) > 100:
                print(f"\n🔍 Raw Output (первые 500 символов):")
                print("-" * 80)
                print(raw_output[:500])
                if len(raw_output) > 500:
                    print("...")
                print("-" * 80)
            
            # Если есть блоки, показываем их
            if blocks:
                print(f"\n🧩 Блоки (детально):")
                for i, block in enumerate(blocks[:5], 1):
                    text = block.get('text', block.get('content', ''))
                    bbox = block.get('bbox', {})
                    block_type = block.get('type', 'unknown')
                    print(f"\n   📦 Блок {i}:")
                    print(f"      Тип: {block_type}")
                    print(f"      BBox: {bbox}")
                    print(f"      Текст: {text[:200]}{'...' if len(text) > 200 else ''}")
                if len(blocks) > 5:
                    print(f"\n   ... и еще {len(blocks) - 5} блоков")
            
            return {
                'prompt_type': prompt_type,
                'prompt_name': prompt_name,
                'elapsed': elapsed,
                'blocks_count': len(blocks),
                'markdown_length': len(markdown),
                'raw_output_length': len(raw_output),
                'success': True
            }
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return None

def main():
    """Главная функция"""
    print("\n" + "="*80)
    print("🧪 ТЕСТИРОВАНИЕ DEEPSEEK-OCR НА ОДНОМ ИЗОБРАЖЕНИИ")
    print("="*80)
    
    # Проверяем наличие изображения
    if not os.path.exists(IMAGE_PATH):
        print(f"❌ Изображение не найдено: {IMAGE_PATH}")
        sys.exit(1)
    
    print(f"📷 Изображение: {IMAGE_PATH}")
    print(f"📊 Промптов для теста: {len(OFFICIAL_PROMPTS)}")
    
    # Проверяем сервис
    service_process = None
    if not check_ocr_service():
        service_process = start_ocr_service()
        if service_process is None:
            print("❌ Не удалось запустить OCR сервис")
            sys.exit(1)
    
    # Тестируем все промпты
    results = []
    for prompt_key, prompt_type in OFFICIAL_PROMPTS.items():
        result = test_single_prompt(IMAGE_PATH, prompt_type, prompt_key)
        if result:
            results.append(result)
        time.sleep(1)  # Небольшая пауза между запросами
    
    # Итоговая таблица
    print("\n" + "="*80)
    print("📊 ИТОГОВАЯ ТАБЛИЦА РЕЗУЛЬТАТОВ")
    print("="*80)
    print(f"{'Промпт':<25} {'Время, сек':<12} {'Блоков':<10} {'MD, симв':<12} {'Raw, симв':<12}")
    print("-"*80)
    
    for r in results:
        print(f"{r['prompt_name']:<25} {r['elapsed']:>10.2f}  {r['blocks_count']:>8}  {r['markdown_length']:>10}  {r['raw_output_length']:>10}")
    
    # Рекомендации
    print("\n" + "="*80)
    print("💡 АНАЛИЗ И РЕКОМЕНДАЦИИ")
    print("="*80)
    
    # Найдем лучший промпт по количеству распознанного текста
    best_by_markdown = max(results, key=lambda x: x['markdown_length']) if results else None
    best_by_raw = max(results, key=lambda x: x['raw_output_length']) if results else None
    fastest = min(results, key=lambda x: x['elapsed']) if results else None
    
    if best_by_markdown:
        print(f"\n✅ Лучший по Markdown: {best_by_markdown['prompt_name']}")
        print(f"   Распознано: {best_by_markdown['markdown_length']} символов")
    
    if best_by_raw:
        print(f"\n✅ Лучший по Raw Output: {best_by_raw['prompt_name']}")
        print(f"   Распознано: {best_by_raw['raw_output_length']} символов")
    
    if fastest:
        print(f"\n⚡ Самый быстрый: {fastest['prompt_name']}")
        print(f"   Время: {fastest['elapsed']:.2f} сек")
    
    print("\n📝 ВЫВОДЫ:")
    print("   - Для BPMN диаграмм лучше всего подходит: parse_figure или bpmn")
    print("   - Для точного распознавания текста: ocr_simple или default")
    print("   - Для описания содержимого: describe")
    
    print("\n🎯 ДООБУЧЕНИЕ:")
    print("   - DeepSeek-OCR обучена на 30M PDF страниц + синтетических диаграммах")
    print("   - Точность до 97% на стандартных документах")
    print("   - Для BPMN: если точность >90% → дообучение НЕ требуется")
    print("   - Если точность <80% → собрать датасет 50-100 BPMN + fine-tune")
    
    # Останавливаем сервис (если запускали сами)
    if service_process:
        print("\n🛑 Останавливаем OCR сервис...")
        subprocess.run(["pkill", "-f", "uvicorn.*ocr_service"], check=False)
        time.sleep(2)
    
    print("\n✅ Тестирование завершено!")

if __name__ == "__main__":
    main()

