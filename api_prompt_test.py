#!/usr/bin/env python3
"""
Тестер промптов через API (БЕЗ загрузки второй модели)
Использует уже работающий OCR сервис на localhost:8000
Автоматически запускает сервис если его нет
"""

import requests
from pathlib import Path
import sys
import time
import re
import socket
import subprocess
import threading
import os

IMAGE_PATH = "output/bpmn_test/page_54_bpmn.png"
OCR_URL = "http://localhost:8000/ocr/figure"
OCR_PORT = 8000

# Тестовые промпты (используем встроенные типы + ОФИЦИАЛЬНЫЕ)
BUILTIN_PROMPTS = {
    # Наши текущие промпты:
    "1_default": "default",
    "2_bpmn": "bpmn",
    "3_complex_diagram": "complex_diagram",
    "4_table": "table",
    "5_text_graphics": "text_graphics",
}

# ОФИЦИАЛЬНЫЕ промпты из DeepSeek-OCR config.py
OFFICIAL_PROMPTS = {
    "6_parse_figure": "parse_figure",           # ⭐⭐⭐ Для графиков/диаграмм
    "7_free_ocr": "free_ocr",                   # Свободный OCR
    "8_describe": "describe",                   # Описание изображения
}

# Объединяем все промпты
ALL_PROMPTS = {**BUILTIN_PROMPTS, **OFFICIAL_PROMPTS}

def is_port_in_use(port):
    """Проверяет занят ли порт"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def check_ocr_service():
    """Проверяет работает ли OCR сервис"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        return response.status_code == 200
    except:
        return False

def stream_output(pipe, prefix=""):
    """Читает и дублирует вывод процесса в реальном времени"""
    for line in iter(pipe.readline, ''):
        if line:
            print(f"{prefix}{line}", end='', flush=True)
    pipe.close()

def start_ocr_service():
    """Запускает OCR сервис и ждёт его готовности"""
    print(f"\n🚀 Запускаем OCR сервис...")
    print(f"{'='*80}\n")
    
    # Команда запуска
    cmd = [
        "python", "-m", "uvicorn",
        "pdf_to_context.ocr_service.app:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--log-level", "info"
    ]
    
    # Активируем venv
    venv_python = "DeepSeek-OCR/venv/bin/python"
    if os.path.exists(venv_python):
        cmd[0] = venv_python
    
    # Запускаем процесс
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd="/home/budnik_an/Obligations"
    )
    
    # Создаём поток для вывода
    output_thread = threading.Thread(
        target=stream_output,
        args=(process.stdout, "   │ "),
        daemon=True
    )
    output_thread.start()
    
    # Ждём готовности (проверяем /health каждые 2 секунды)
    print(f"\n⏳ Ожидание загрузки модели (это займёт ~30-60 секунд)...\n")
    
    max_wait = 120  # максимум 2 минуты
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        time.sleep(2)
        
        if check_ocr_service():
            elapsed = time.time() - start_time
            print(f"\n{'='*80}")
            print(f"✅ OCR сервис готов! (загрузка заняла {elapsed:.1f}s)")
            print(f"{'='*80}\n")
            return process
        
        # Проверяем жив ли процесс
        if process.poll() is not None:
            print(f"\n❌ Процесс OCR сервиса завершился с кодом {process.returncode}")
            return None
    
    print(f"\n❌ Превышено время ожидания запуска сервиса ({max_wait}s)")
    process.terminate()
    return None

def ensure_ocr_service():
    """Проверяет и при необходимости запускает OCR сервис"""
    # Проверка 1: Работает ли сервис?
    if check_ocr_service():
        print(f"✅ OCR сервис уже работает")
        return True
    
    # Проверка 2: Порт занят?
    if is_port_in_use(OCR_PORT):
        print(f"❌ ОШИБКА: Порт {OCR_PORT} занят, но OCR сервис не отвечает!")
        print(f"\n💡 Решение:")
        print(f"   1. Убейте процесс: pkill -f 'uvicorn pdf_to_context.ocr_service.app'")
        print(f"   2. Проверьте: lsof -i :{OCR_PORT}")
        return False
    
    # Проверка 3: Запускаем сервис
    process = start_ocr_service()
    return process is not None

def test_prompt(image_path, prompt_name, prompt_type):
    """Тестирует один промпт через API"""
    print(f"\n{'='*80}")
    print(f"🧪 ТЕСТ: {prompt_name} (prompt_type={prompt_type})")
    print(f"{'='*80}")
    
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    files = {"file": (f"{prompt_name}.png", image_data, "image/png")}
    data = {"prompt_type": prompt_type}
    
    print(f"📤 Отправка запроса...")
    
    start_time = time.time()
    
    try:
        response = requests.post(OCR_URL, files=files, data=data, timeout=120)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            
            blocks = result.get('blocks', [])
            markdown = result.get('markdown', '')
            raw = result.get('raw_output', '')
            
            print(f"✅ Успех ({elapsed:.2f}s)")
            print(f"\n📊 Статистика:")
            print(f"   Блоков: {len(blocks)}")
            print(f"   Markdown: {len(markdown)} символов")
            print(f"   Raw output: {len(raw)} символов")
            
            # Анализ типов блоков
            if blocks:
                types = {}
                for block in blocks:
                    t = block['type']
                    types[t] = types.get(t, 0) + 1
                
                print(f"\n📦 Типы блоков:")
                for t, count in types.items():
                    print(f"   - {t}: {count}")
            
            # Показываем содержимое
            if len(blocks) > 0:
                print(f"\n📄 СОДЕРЖИМОЕ БЛОКОВ:")
                print(f"{'-'*80}")
                for i, block in enumerate(blocks, 1):
                    content = block['content'][:100].replace('\n', ' ')
                    print(f"{i}. [{block['type']}] {content}...")
                print(f"{'-'*80}")
            
            # Показываем markdown если есть
            if markdown:
                print(f"\n📝 MARKDOWN (первые 400 символов):")
                print(f"{'-'*80}")
                print(markdown[:400])
                if len(markdown) > 400:
                    print("... (обрезано)")
                print(f"{'-'*80}")
            
            return {
                'success': True,
                'blocks_count': len(blocks),
                'markdown_length': len(markdown),
                'raw_length': len(raw),
                'elapsed': elapsed,
                'blocks': blocks,
                'markdown': markdown
            }
        else:
            print(f"❌ Ошибка {response.status_code}")
            print(f"   {response.text[:200]}")
            return {
                'success': False,
                'error': response.status_code,
                'elapsed': time.time() - start_time
            }
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return {
            'success': False,
            'error': str(e),
            'elapsed': time.time() - start_time
        }

def main():
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                      🧪 API PROMPT TESTER                                    ║
║            Тестирование через работающий OCR сервис                          ║
║                  (БЕЗ загрузки второй модели)                                ║
╚══════════════════════════════════════════════════════════════════════════════╝

Использует: API на localhost:8000
Изображение: {IMAGE_PATH}

Доступные промпты:
""")
    
    for name, ptype in ALL_PROMPTS.items():
        marker = "⭐⭐⭐" if "parse_figure" in name else ""
        print(f"  {name}: prompt_type='{ptype}' {marker}")
    
    # Проверка изображения
    image_path = Path(IMAGE_PATH)
    if not image_path.exists():
        print(f"\n❌ Изображение не найдено: {IMAGE_PATH}")
        return
    
    print(f"\n✅ Изображение найдено: {image_path.stat().st_size / 1024:.1f} KB")
    
    # Проверка и запуск API если нужно
    print(f"\n🔍 Проверка OCR сервиса...")
    if not ensure_ocr_service():
        return
    
    # Получаем инфо о сервисе
    try:
        health = requests.get("http://localhost:8000/health", timeout=5)
        if health.status_code == 200:
            info = health.json()
            print(f"📊 Информация о сервисе:")
            print(f"   GPU: {info.get('cuda_device', 'N/A')}")
            print(f"   Model: {info.get('model_type', 'N/A')}")
    except Exception as e:
        print(f"⚠️ Не удалось получить инфо: {e}")
    
    # Парсим аргументы
    if len(sys.argv) < 2:
        print(f"\n💡 Использование:")
        print(f"   python api_prompt_test.py all              - тестировать все промпты")
        print(f"   python api_prompt_test.py 1 2 3            - тестировать промпты 1, 2, 3")
        print(f"   python api_prompt_test.py compare          - сравнение всех промптов (таблица)")
        return
    
    mode = sys.argv[1]
    
    if mode == "all":
        # Тестируем все
        print(f"\n🔄 Тестируем ВСЕ {len(ALL_PROMPTS)} промптов...")
        results = {}
        
        for name, ptype in ALL_PROMPTS.items():
            result = test_prompt(image_path, name, ptype)
            results[name] = result
            print()
        
        # Итоговая таблица
        print(f"\n{'='*80}")
        print(f"📊 ИТОГОВАЯ СВОДКА")
        print(f"{'='*80}\n")
        print(f"{'Промпт':<25} {'Статус':<8} {'Блоков':<8} {'Markdown':<10} {'Время':<8}")
        print("-" * 80)
        
        for name, res in results.items():
            if res['success']:
                status = "✅"
                blocks = res['blocks_count']
                markdown = res['markdown_length']
                elapsed = f"{res['elapsed']:.2f}s"
            else:
                status = "❌"
                blocks = "-"
                markdown = "-"
                elapsed = f"{res['elapsed']:.2f}s"
            
            print(f"{name:<25} {status:<8} {str(blocks):<8} {str(markdown):<10} {elapsed:<8}")
        
        # Лучший результат
        successful = [r for r in results.values() if r['success']]
        if successful:
            best = max(successful, key=lambda x: x['blocks_count'])
            best_name = [k for k, v in results.items() if v == best][0]
            
            print(f"\n🏆 Лучший результат: {best_name}")
            print(f"   Блоков: {best['blocks_count']}")
            print(f"   Markdown: {best['markdown_length']} символов")
            print(f"   Время: {best['elapsed']:.2f}s")
    
    elif mode == "compare":
        # Быстрое сравнение (без подробного вывода)
        print(f"\n🔄 Быстрое сравнение всех промптов...\n")
        results = {}
        
        for name, ptype in ALL_PROMPTS.items():
            print(f"   Тестируем {name}...", end=" ", flush=True)
            
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            files = {"file": (f"{name}.png", image_data, "image/png")}
            data = {"prompt_type": ptype}
            
            try:
                start = time.time()
                response = requests.post(OCR_URL, files=files, data=data, timeout=120)
                elapsed = time.time() - start
                
                if response.status_code == 200:
                    result = response.json()
                    results[name] = {
                        'success': True,
                        'blocks': len(result.get('blocks', [])),
                        'markdown_len': len(result.get('markdown', '')),
                        'elapsed': elapsed
                    }
                    print(f"✅ ({elapsed:.1f}s)")
                else:
                    results[name] = {'success': False, 'elapsed': elapsed}
                    print(f"❌")
            except Exception as e:
                results[name] = {'success': False, 'error': str(e)}
                print(f"❌ {e}")
        
        # Сравнительная таблица
        print(f"\n{'='*80}")
        print(f"📊 СРАВНИТЕЛЬНАЯ ТАБЛИЦА")
        print(f"{'='*80}\n")
        print(f"{'Промпт':<25} {'Блоков':<10} {'Markdown':<12} {'Время':<10}")
        print("-" * 80)
        
        for name, res in results.items():
            if res['success']:
                print(f"{name:<25} {res['blocks']:<10} {res['markdown_len']:<12} {res['elapsed']:.2f}s")
            else:
                print(f"{name:<25} {'ОШИБКА':<10} {'-':<12} {'-':<10}")
    
    else:
        # Выборочные промпты
        try:
            indices = [int(x) for x in sys.argv[1:]]
            selected = {k: v for k, v in ALL_PROMPTS.items() 
                       if int(k.split('_')[0]) in indices}
            
            if not selected:
                print(f"\n❌ Промпты не найдены. Доступные: 1-{len(ALL_PROMPTS)}")
                return
            
            print(f"\n🔄 Тестируем {len(selected)} промптов...")
            results = {}
            
            for name, ptype in selected.items():
                result = test_prompt(image_path, name, ptype)
                results[name] = result
                print()
            
            # Краткая сводка
            print(f"{'='*80}")
            print(f"📊 СВОДКА")
            print(f"{'='*80}\n")
            
            for name, res in results.items():
                if res['success']:
                    print(f"{name}: {res['blocks_count']} блоков, {res['markdown_length']} символов, {res['elapsed']:.2f}s")
                else:
                    print(f"{name}: ❌ Ошибка")
                    
        except ValueError:
            print(f"\n❌ Неверный формат. Используйте: python api_prompt_test.py 1 2 3")

if __name__ == "__main__":
    main()

