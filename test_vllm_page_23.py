#!/usr/bin/env python3
"""
Тестовый скрипт для сравнения vLLM и Transformers на странице 23
Страница 23 содержит BPMN диаграмму
"""
import os
import sys
import time
import asyncio
from pathlib import Path

# Настройка путей
PROJECT_ROOT = Path("/home/budnik_an/Obligations")
sys.path.insert(0, str(PROJECT_ROOT / "DeepSeek-OCR/DeepSeek-OCR-master/DeepSeek-OCR-vllm"))

import torch
import fitz  # PyMuPDF
from PIL import Image
import io

# Настройка CUDA
os.environ["CUDA_VISIBLE_DEVICES"] = '0'
os.environ['VLLM_USE_V1'] = '1'

# Пути
PDF_PATH = PROJECT_ROOT / "input/ДП-М1.020-06 (Эталон №14 для ознакомления).pdf"
OUTPUT_DIR = PROJECT_ROOT / "output/vllm_test"
PAGE_23_IMAGE = OUTPUT_DIR / "page_23_test.png"

# Создать директорию для результатов
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def extract_page_23_as_image():
    """Извлечь страницу 23 как изображение"""
    print("\n" + "="*80)
    print("📄 ИЗВЛЕЧЕНИЕ СТРАНИЦЫ 23 КАК ИЗОБРАЖЕНИЕ")
    print("="*80)
    
    doc = fitz.open(PDF_PATH)
    page = doc[22]  # Страница 23 (индекс 22)
    
    # Рендерим с высоким разрешением для OCR
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    
    # Сохраняем как PNG
    pix.save(PAGE_23_IMAGE)
    
    print(f"✅ Страница 23 сохранена: {PAGE_23_IMAGE}")
    print(f"   Размер: {pix.width}x{pix.height} px")
    
    doc.close()
    return PAGE_23_IMAGE


def test_transformers_api():
    """Тест через текущий Transformers API (FastAPI сервис)"""
    import requests
    
    print("\n" + "="*80)
    print("🔬 ТЕСТ 1: TRANSFORMERS API (текущий подход)")
    print("="*80)
    
    # Проверить, запущен ли сервис
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code != 200:
            print("❌ OCR сервис не запущен!")
            print("   Запустите: cd scripts/pdf_to_context/ocr_service && python app.py")
            return None
    except Exception as e:
        print(f"❌ OCR сервис недоступен: {e}")
        print("   Запустите: cd scripts/pdf_to_context/ocr_service && python app.py")
        return None
    
    print("✅ OCR сервис запущен")
    
    # Отправить запрос
    print(f"\n📤 Отправляем страницу 23 на OCR (Transformers)...")
    start_time = time.time()
    
    with open(PAGE_23_IMAGE, 'rb') as f:
        files = {'file': ('page_23.png', f, 'image/png')}
        data = {'prompt_type': 'ocr_simple'}
        
        response = requests.post(
            "http://localhost:8000/ocr/figure",
            files=files,
            data=data,
            timeout=120
        )
    
    elapsed = time.time() - start_time
    
    if response.status_code == 200:
        result = response.json()
        blocks = result.get('blocks', [])
        markdown = result.get('markdown', '')
        
        print(f"\n✅ Transformers API - РЕЗУЛЬТАТЫ:")
        print(f"   ⏱️  Время: {elapsed:.2f} сек")
        print(f"   📦 Блоков: {len(blocks)}")
        print(f"   📝 Markdown: {len(markdown)} символов")
        
        # Сохранить результат
        output_file = OUTPUT_DIR / "transformers_result.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Время: {elapsed:.2f} сек\n")
            f.write(f"Блоков: {len(blocks)}\n\n")
            f.write(markdown)
        
        return {
            'time': elapsed,
            'blocks': len(blocks),
            'markdown_length': len(markdown),
            'markdown': markdown
        }
    else:
        print(f"❌ Ошибка: {response.status_code}")
        return None


async def test_vllm_api():
    """Тест через vLLM (новый подход)"""
    from vllm import AsyncLLMEngine, SamplingParams
    from vllm.engine.arg_utils import AsyncEngineArgs
    from vllm.model_executor.models.registry import ModelRegistry
    
    # Импорт DeepSeek-OCR модели для vLLM
    sys.path.insert(0, str(PROJECT_ROOT / "DeepSeek-OCR/DeepSeek-OCR-master/DeepSeek-OCR-vllm"))
    from deepseek_ocr import DeepseekOCRForCausalLM
    from process.image_process import DeepseekOCRProcessor
    
    # Регистрируем модель
    ModelRegistry.register_model("DeepseekOCRForCausalLM", DeepseekOCRForCausalLM)
    
    print("\n" + "="*80)
    print("🚀 ТЕСТ 2: vLLM API (новый подход)")
    print("="*80)
    
    # Настройки модели
    model_path = 'deepseek-ai/DeepSeek-OCR'
    
    print(f"\n⏳ Загрузка модели через vLLM...")
    print(f"   Модель: {model_path}")
    
    # Создать AsyncEngineArgs
    engine_args = AsyncEngineArgs(
        model=model_path,
        trust_remote_code=True,
        dtype='bfloat16',
        gpu_memory_utilization=0.9,
        max_model_len=8192,
        enforce_eager=False,  # Использовать CUDA graphs
        disable_custom_all_reduce=False,
    )
    
    # Создать AsyncLLMEngine
    engine_start = time.time()
    engine = AsyncLLMEngine.from_engine_args(engine_args)
    engine_load_time = time.time() - engine_start
    
    print(f"✅ Модель загружена за {engine_load_time:.2f} сек")
    
    # Загрузить изображение
    image = Image.open(PAGE_23_IMAGE)
    
    # Подготовить промпт
    prompt = '<image>\n<|grounding|>OCR this image.'
    
    # Sampling параметры
    sampling_params = SamplingParams(
        temperature=0.0,
        max_tokens=4096,
        stop_token_ids=[100001],  # DeepSeek-OCR specific
    )
    
    print(f"\n📤 Отправляем страницу 23 на OCR (vLLM)...")
    start_time = time.time()
    
    # Генерация
    outputs = []
    async for output in engine.generate(
        {"prompt": prompt, "multi_modal_data": {"image": image}},
        sampling_params=sampling_params,
        request_id=f"test_page_23"
    ):
        outputs.append(output)
    
    elapsed = time.time() - start_time
    
    # Получить результат
    if outputs:
        final_output = outputs[-1]
        generated_text = final_output.outputs[0].text
        
        print(f"\n✅ vLLM API - РЕЗУЛЬТАТЫ:")
        print(f"   ⏱️  Время: {elapsed:.2f} сек (загрузка модели: {engine_load_time:.2f} сек)")
        print(f"   📝 Сгенерировано: {len(generated_text)} символов")
        print(f"   🎯 Tokens: {len(final_output.outputs[0].token_ids)}")
        
        # Сохранить результат
        output_file = OUTPUT_DIR / "vllm_result.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Время: {elapsed:.2f} сек (загрузка: {engine_load_time:.2f} сек)\n")
            f.write(f"Символов: {len(generated_text)}\n\n")
            f.write(generated_text)
        
        return {
            'time': elapsed,
            'load_time': engine_load_time,
            'text_length': len(generated_text),
            'tokens': len(final_output.outputs[0].token_ids),
            'text': generated_text
        }
    else:
        print("❌ Нет результатов от vLLM")
        return None


def compare_results(transformers_result, vllm_result):
    """Сравнить результаты"""
    print("\n" + "="*80)
    print("📊 СРАВНЕНИЕ РЕЗУЛЬТАТОВ")
    print("="*80)
    
    if not transformers_result or not vllm_result:
        print("⚠️ Не все тесты выполнены успешно")
        return
    
    print(f"\n{'Метрика':<30} {'Transformers':<20} {'vLLM':<20} {'Разница':<20}")
    print("-" * 90)
    
    # Время
    t_time = transformers_result['time']
    v_time = vllm_result['time']
    time_diff = ((t_time - v_time) / t_time * 100) if t_time > 0 else 0
    print(f"{'Время обработки (сек)':<30} {t_time:<20.2f} {v_time:<20.2f} {time_diff:+.1f}%")
    
    # Количество данных
    t_blocks = transformers_result['blocks']
    v_chars = vllm_result['text_length']
    print(f"{'Блоков / Символов':<30} {t_blocks:<20} {v_chars:<20} -")
    
    # Throughput
    t_throughput = t_blocks / t_time if t_time > 0 else 0
    v_throughput = vllm_result['tokens'] / v_time if v_time > 0 else 0
    print(f"{'Throughput (blocks/sec, tok/sec)':<30} {t_throughput:<20.2f} {v_throughput:<20.2f} -")
    
    print("\n" + "="*80)
    print("💡 ВЫВОДЫ:")
    print("="*80)
    
    if time_diff > 10:
        print(f"✅ vLLM быстрее на {abs(time_diff):.1f}%")
    elif time_diff < -10:
        print(f"⚠️ vLLM медленнее на {abs(time_diff):.1f}%")
    else:
        print(f"≈ Примерно одинаковая скорость (разница {abs(time_diff):.1f}%)")
    
    print(f"\n📊 Загрузка модели vLLM: {vllm_result['load_time']:.2f} сек")
    print(f"   (при повторных запусках модель уже в памяти)")


def main():
    """Главная функция"""
    print("\n" + "="*80)
    print("🧪 СРАВНЕНИЕ vLLM vs TRANSFORMERS API")
    print("="*80)
    print(f"📄 Документ: ДП-М1.020-06")
    print(f"📃 Страница: 23 (BPMN диаграмма)")
    print(f"🎯 Цель: Сравнить производительность")
    
    # Шаг 1: Извлечь страницу 23
    if not PAGE_23_IMAGE.exists():
        extract_page_23_as_image()
    else:
        print(f"\n✅ Изображение уже существует: {PAGE_23_IMAGE}")
    
    # Шаг 2: Тест Transformers API
    transformers_result = test_transformers_api()
    
    # Шаг 3: Тест vLLM API
    try:
        vllm_result = asyncio.run(test_vllm_api())
    except Exception as e:
        print(f"❌ Ошибка vLLM: {e}")
        import traceback
        traceback.print_exc()
        vllm_result = None
    
    # Шаг 4: Сравнение
    compare_results(transformers_result, vllm_result)
    
    print("\n" + "="*80)
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("="*80)
    print(f"📁 Результаты сохранены в: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()


