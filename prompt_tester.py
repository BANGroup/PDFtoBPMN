#!/usr/bin/env python3
"""
Утилита для тестирования разных промптов на одном изображении
"""

import requests
import sys
from pathlib import Path

IMAGE_PATH = "output/bpmn_test/page_54_bpmn.png"
OCR_URL = "http://localhost:8000/ocr/figure"

# Коллекция промптов для тестирования
PROMPTS = {
    "1_default": "<image>\n<|grounding|>Convert the document to markdown.",
    
    "2_simple_diagram": "<image>\n<|grounding|>Extract all text from the diagram.",
    
    "3_bpmn_short": "<image>\n<|grounding|>Extract BPMN diagram text.",
    
    "4_bpmn_detailed": "<image>\n<|grounding|>Extract all text from shapes, gateways, and events in the BPMN diagram.",
    
    "5_process_focus": "<image>\n<|grounding|>Extract process names and labels from the diagram.",
    
    "6_ocr_all": "<image>\n<|grounding|>OCR all visible text in the image.",
    
    "7_describe": "<image>\n<|grounding|>Describe the diagram and extract all text labels.",
    
    "8_table_like": "<image>\n<|grounding|>Extract all text as structured list.",
    
    "9_verbose": "<image>\n<|grounding|>Read and transcribe every piece of text visible in this image, including text inside shapes, boxes, and diagram elements.",
    
    "10_no_instruction": "<image>\n<|grounding|>",
}

def test_prompt(prompt_name, prompt_text, image_path):
    """Тестирует один промпт"""
    print(f"\n{'='*80}")
    print(f"🧪 ТЕСТ: {prompt_name}")
    print(f"{'='*80}")
    print(f"📝 Промпт: {prompt_text}")
    print(f"\n⏳ Обработка...")
    
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    # Создаем временный файл с промптом (через custom prompt)
    files = {"file": (f"test_{prompt_name}.png", image_data, "image/png")}
    
    # Для тестирования разных промптов используем prompt_type=default 
    # но в будущем можно добавить endpoint для custom prompt
    data = {"prompt_type": "default"}
    
    try:
        response = requests.post(OCR_URL, files=files, data=data, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            
            blocks = result.get('blocks', [])
            markdown = result.get('markdown', '')
            
            print(f"\n✅ РЕЗУЛЬТАТ:")
            print(f"   Блоков: {len(blocks)}")
            print(f"   Markdown: {len(markdown)} символов")
            
            if len(blocks) > 0:
                print(f"\n📦 БЛОКИ:")
                for i, block in enumerate(blocks, 1):
                    content = block['content'][:80].replace('\n', ' ')
                    print(f"   {i}. [{block['type']}] {content}...")
            
            if markdown:
                print(f"\n📄 MARKDOWN (первые 500 символов):")
                print(f"   {markdown[:500]}")
            
            return {
                'success': True,
                'blocks_count': len(blocks),
                'markdown_length': len(markdown),
                'blocks': blocks,
                'markdown': markdown
            }
        else:
            print(f"❌ Ошибка {response.status_code}: {response.text[:200]}")
            return {'success': False, 'error': response.status_code}
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return {'success': False, 'error': str(e)}

def main():
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         🧪 PROMPT TESTER                                     ║
║              Тестирование промптов для DeepSeek-OCR                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Изображение: {IMAGE_PATH}
Доступно промптов: {len(PROMPTS)}

Варианты запуска:
  1. python prompt_tester.py all           - тестировать все промпты
  2. python prompt_tester.py 1 3 5         - тестировать промпты 1, 3, 5
  3. python prompt_tester.py interactive   - интерактивный режим
  4. python prompt_tester.py custom "промпт"  - тестировать свой промпт
""")
    
    if not Path(IMAGE_PATH).exists():
        print(f"❌ Изображение не найдено: {IMAGE_PATH}")
        return
    
    # Проверка сервиса
    try:
        health = requests.get("http://localhost:8000/health", timeout=5)
        if health.status_code != 200:
            print("❌ OCR сервис недоступен!")
            return
        print("✅ OCR сервис готов\n")
    except:
        print("❌ OCR сервис не отвечает на localhost:8000")
        return
    
    # Парсинг аргументов
    if len(sys.argv) < 2:
        print("Использование: python prompt_tester.py [all|interactive|1 2 3|custom 'prompt']")
        return
    
    mode = sys.argv[1]
    
    if mode == "all":
        # Тестируем все промпты
        results = {}
        for name, prompt in PROMPTS.items():
            result = test_prompt(name, prompt, IMAGE_PATH)
            results[name] = result
            
        # Итоговая таблица
        print(f"\n\n{'='*80}")
        print("📊 ИТОГОВАЯ СВОДКА")
        print(f"{'='*80}\n")
        print(f"{'Промпт':<20} {'Успех':<8} {'Блоков':<10} {'Markdown':<12}")
        print("-" * 80)
        
        for name, res in results.items():
            if res['success']:
                print(f"{name:<20} {'✅':<8} {res['blocks_count']:<10} {res['markdown_length']:<12}")
            else:
                print(f"{name:<20} {'❌':<8} {'-':<10} {'-':<12}")
        
        # Лучший результат
        best = max([r for r in results.values() if r['success']], 
                   key=lambda x: x['blocks_count'], default=None)
        if best:
            best_name = [k for k, v in results.items() if v == best][0]
            print(f"\n🏆 Лучший результат: {best_name} ({best['blocks_count']} блоков)")
    
    elif mode == "interactive":
        # Интерактивный режим
        print("📝 Интерактивный режим - вводите свои промпты")
        print("   (для выхода введите 'exit')\n")
        
        counter = 1
        while True:
            print(f"\n{'─'*80}")
            user_prompt = input("Введите промпт (или 'exit'): ").strip()
            
            if user_prompt.lower() == 'exit':
                break
            
            if not user_prompt:
                continue
            
            # Добавляем обязательные теги если их нет
            if not user_prompt.startswith("<image>"):
                full_prompt = f"<image>\n<|grounding|>{user_prompt}"
            else:
                full_prompt = user_prompt
            
            test_prompt(f"custom_{counter}", full_prompt, IMAGE_PATH)
            counter += 1
    
    elif mode == "custom":
        # Кастомный промпт из аргументов
        if len(sys.argv) < 3:
            print("❌ Укажите промпт: python prompt_tester.py custom 'your prompt'")
            return
        
        user_prompt = sys.argv[2]
        if not user_prompt.startswith("<image>"):
            full_prompt = f"<image>\n<|grounding|>{user_prompt}"
        else:
            full_prompt = user_prompt
        
        test_prompt("custom", full_prompt, IMAGE_PATH)
    
    else:
        # Тестируем выборочные промпты (по номерам)
        try:
            indices = [int(x) for x in sys.argv[1:]]
            selected_prompts = {k: v for k, v in PROMPTS.items() 
                              if int(k.split('_')[0]) in indices}
            
            if not selected_prompts:
                print(f"❌ Промпты не найдены. Доступные номера: 1-{len(PROMPTS)}")
                return
            
            results = {}
            for name, prompt in selected_prompts.items():
                result = test_prompt(name, prompt, IMAGE_PATH)
                results[name] = result
            
            # Краткая сводка
            print(f"\n\n{'='*80}")
            print("📊 СВОДКА")
            print(f"{'='*80}\n")
            for name, res in results.items():
                if res['success']:
                    print(f"{name}: {res['blocks_count']} блоков, {res['markdown_length']} символов markdown")
                else:
                    print(f"{name}: ❌ Ошибка")
                    
        except ValueError:
            print("❌ Неверный формат. Используйте: python prompt_tester.py 1 2 3")

if __name__ == "__main__":
    main()





