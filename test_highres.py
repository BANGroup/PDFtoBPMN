#!/usr/bin/env python3
"""
Тест с увеличенным разрешением для детального распознавания BPMN
"""

import fitz
import requests

# Рендерим страницу 54
pdf_path = "input_data/КД-СТ-161-01 (Эталон для ознакомления).pdf"
doc = fitz.open(pdf_path)
page = doc[53]

zoom = 300 / 72.0
mat = fitz.Matrix(zoom, zoom)
pix = page.get_pixmap(matrix=mat)
img_data = pix.tobytes("png")
doc.close()

print(f"✅ Страница 54: {pix.width}x{pix.height}")
print(f"🔬 Тест с ВЫСОКИМ разрешением:")
print(f"   - base_size: 2048 (вместо 1024)")
print(f"   - image_size: 2048")
print(f"   - crop_mode: True (разбивка на патчи)")
print(f"   - prompt_type: bpmn\n")

files = {"file": ("page_54.png", img_data, "image/png")}
data = {
    "prompt_type": "bpmn",
    "base_size": "2048",      # Увеличено!
    "image_size": "2048",     # Увеличено!
    "crop_mode": "true"       # Включен!
}

print("📤 Отправляем запрос (это займет ~10-20 секунд)...\n")

response = requests.post(
    "http://localhost:8000/ocr/figure",
    files=files,
    data=data,
    timeout=180  # 3 минуты на обработку
)

if response.status_code == 200:
    result = response.json()
    
    print(f"✅ УСПЕХ!")
    print(f"   Блоков: {len(result['blocks'])}")
    print(f"   Markdown: {len(result['markdown'])} символов\n")
    print(f"{'='*80}")
    print("📝 РАСПОЗНАННЫЙ MARKDOWN:")
    print(f"{'='*80}\n")
    print(result['markdown'])
    
    if len(result['blocks']) > 0:
        print(f"\n{'='*80}")
        print(f"📦 ВСЕ БЛОКИ ({len(result['blocks'])}):")
        print(f"{'='*80}\n")
        for i, block in enumerate(result['blocks'], 1):
            content_preview = block['content'][:150].replace('\n', ' ')
            print(f"{i}. [{block['type']}]")
            print(f"   {content_preview}...")
            print()
else:
    print(f"❌ Ошибка: {response.status_code}")
    print(response.text)






