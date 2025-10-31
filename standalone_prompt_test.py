#!/usr/bin/env python3
"""
Standalone тестер промптов для DeepSeek-OCR
Работает НАПРЯМУЮ с моделью, без API сервиса
"""

import torch
from transformers import AutoModel, AutoTokenizer
from pathlib import Path
import sys
import time

# Коллекция промптов для тестирования
PROMPTS = {
    "1_default": "<image>\n<|grounding|>Convert the document to markdown.",
    
    "2_simple": "<image>\n<|grounding|>Extract all text.",
    
    "3_diagram": "<image>\n<|grounding|>Extract text from the diagram.",
    
    "4_bpmn": "<image>\n<|grounding|>Extract BPMN diagram with process names, gateways, and events.",
    
    "5_detailed": "<image>\n<|grounding|>Extract all text from shapes, boxes, and labels.",
    
    "6_ocr": "<image>\n<|grounding|>OCR all visible text.",
    
    "7_transcribe": "<image>\n<|grounding|>Transcribe every text element in the image.",
    
    "8_list": "<image>\n<|grounding|>List all text elements.",
    
    "9_describe_extract": "<image>\n<|grounding|>Describe the image and extract all text.",
    
    "10_shapes": "<image>\n<|grounding|>Extract text from all shapes and diagram elements.",
}

def load_model():
    """Загрузка модели DeepSeek-OCR"""
    print("🔄 Загрузка DeepSeek-OCR...")
    
    model_name = 'deepseek-ai/DeepSeek-OCR'
    
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_name,
        _attn_implementation='eager',
        trust_remote_code=True,
        use_safetensors=True
    )
    model = model.eval().cuda().to(torch.bfloat16)
    
    print("✅ Модель загружена!\n")
    
    return model, tokenizer

def test_prompt(model, tokenizer, image_path, prompt_name, prompt_text):
    """Тестирует один промпт"""
    print(f"{'='*80}")
    print(f"🧪 ТЕСТ: {prompt_name}")
    print(f"{'='*80}")
    print(f"📝 Промпт: {prompt_text}\n")
    
    # Захват stdout
    from io import StringIO
    import sys as system
    
    old_stdout = system.stdout
    system.stdout = captured_output = StringIO()
    
    start_time = time.time()
    
    try:
        res = model.infer(
            tokenizer,
            prompt=prompt_text,
            image_file=str(image_path),
            output_path="/tmp/deepseek_output",
            base_size=1024,
            image_size=1024,
            crop_mode=False,
            save_results=False,
            test_compress=False
        )
    finally:
        system.stdout = old_stdout
        output = captured_output.getvalue()
    
    elapsed = time.time() - start_time
    
    print(f"⏱️  Время: {elapsed:.2f}s")
    print(f"📏 Вывод: {len(output)} символов\n")
    
    # Парсим вывод
    lines = output.split('\n')
    
    # Считаем теги
    text_blocks = output.count('<|ref|>text<|/ref|>')
    image_blocks = output.count('<|ref|>image<|/ref|>')
    
    print(f"📊 Найдено тегов:")
    print(f"   - text блоков: {text_blocks}")
    print(f"   - image блоков: {image_blocks}")
    print()
    
    # Показываем результат
    if len(output) > 200:
        # Убираем технические сообщения
        clean_output = '\n'.join([line for line in lines 
                                  if not line.startswith('=====') 
                                  and 'BASE:' not in line 
                                  and 'NO PATCHES' not in line
                                  and line.strip()])
        
        print(f"📄 РАСПОЗНАННЫЙ ТЕКСТ:")
        print(f"{'-'*80}")
        
        # Извлекаем текст между тегами
        import re
        pattern = r'<\|ref\|>(.*?)<\|/ref\|><\|det\|>.*?<\|/det\|>\s*(.*?)(?=\n<\|ref\||$)'
        matches = re.findall(pattern, output, re.DOTALL)
        
        if matches:
            for i, (tag_type, text_content) in enumerate(matches, 1):
                text_clean = text_content.strip()
                if text_clean:
                    print(f"{i}. [{tag_type}] {text_clean}")
            print()
        else:
            # Просто показываем чистый вывод
            print(clean_output[:800])
            if len(clean_output) > 800:
                print("\n... (обрезано)")
        print(f"{'-'*80}")
    else:
        print(f"⚠️  Пустой или короткий результат")
    
    print()
    return {
        'prompt': prompt_text,
        'output_length': len(output),
        'text_blocks': text_blocks,
        'image_blocks': image_blocks,
        'elapsed': elapsed
    }

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Standalone тестер промптов DeepSeek-OCR')
    parser.add_argument('image', help='Путь к изображению')
    parser.add_argument('prompts', nargs='*', help='Номера промптов (1-10) или "all"')
    parser.add_argument('--custom', help='Кастомный промпт')
    
    args = parser.parse_args()
    
    image_path = Path(args.image)
    
    if not image_path.exists():
        print(f"❌ Изображение не найдено: {image_path}")
        return
    
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    🧪 STANDALONE PROMPT TESTER                               ║
║                   Прямое тестирование DeepSeek-OCR                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Изображение: {image_path}
Размер файла: {image_path.stat().st_size / 1024:.1f} KB

Доступные промпты:
""")
    
    for name, prompt in PROMPTS.items():
        print(f"  {name}: {prompt[:70]}...")
    
    print()
    
    # Загрузка модели
    model, tokenizer = load_model()
    
    # Определяем какие промпты тестировать
    if args.custom:
        # Кастомный промпт
        custom_prompt = args.custom
        if not custom_prompt.startswith("<image>"):
            custom_prompt = f"<image>\n<|grounding|>{custom_prompt}"
        
        results = {
            'custom': test_prompt(model, tokenizer, image_path, 'custom', custom_prompt)
        }
    
    elif not args.prompts or 'all' in args.prompts:
        # Все промпты
        print("🔄 Тестируем ВСЕ промпты...\n")
        results = {}
        for name, prompt in PROMPTS.items():
            result = test_prompt(model, tokenizer, image_path, name, prompt)
            results[name] = result
            print()
    
    else:
        # Выборочные промпты
        selected = {}
        for num_str in args.prompts:
            try:
                num = int(num_str)
                key = f"{num}_{[k for k in PROMPTS.keys() if k.startswith(f'{num}_')][0].split('_')[1]}"
                if key in PROMPTS:
                    selected[key] = PROMPTS[key]
            except:
                print(f"⚠️  Пропущен неверный номер: {num_str}")
        
        if not selected:
            print("❌ Не найдено валидных номеров промптов")
            return
        
        results = {}
        for name, prompt in selected.items():
            result = test_prompt(model, tokenizer, image_path, name, prompt)
            results[name] = result
            print()
    
    # Итоговая таблица
    print(f"\n{'='*80}")
    print("📊 ИТОГОВАЯ СВОДКА")
    print(f"{'='*80}\n")
    print(f"{'Промпт':<20} {'Время':<10} {'Text':<8} {'Image':<8} {'Длина':<10}")
    print("-" * 80)
    
    for name, res in results.items():
        print(f"{name:<20} {res['elapsed']:>6.2f}s   {res['text_blocks']:<8} {res['image_blocks']:<8} {res['output_length']:<10}")
    
    # Лучший результат
    best = max(results.values(), key=lambda x: x['text_blocks'])
    best_name = [k for k, v in results.items() if v == best][0]
    
    print(f"\n🏆 Лучший результат: {best_name}")
    print(f"   Text блоков: {best['text_blocks']}")
    print(f"   Image блоков: {best['image_blocks']}")
    print(f"   Время: {best['elapsed']:.2f}s\n")

if __name__ == "__main__":
    main()





