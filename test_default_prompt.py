#!/usr/bin/env python3
"""
Тест с базовым промптом (default)
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
print(f"📤 Тест с prompt_type='default' (базовый промпт)\n")

files = {"file": ("page_54.png", img_data, "image/png")}
data = {"prompt_type": "default"}  # Базовый промпт!

response = requests.post(
    "http://localhost:8000/ocr/figure",
    files=files,
    data=data,
    timeout=120
)

if response.status_code == 200:
    result = response.json()
    
    print(f"✅ Блоков: {len(result['blocks'])}")
    print(f"📏 Markdown: {len(result['markdown'])} символов\n")
    print(f"{'='*80}")
    print("📝 MARKDOWN:")
    print(f"{'='*80}\n")
    print(result['markdown'])
    
    if len(result['blocks']) > 3:
        print(f"\n{'='*80}")
        print(f"📦 БЛОКИ ({len(result['blocks'])}):")
        print(f"{'='*80}\n")
        for i, block in enumerate(result['blocks'], 1):
            print(f"{i}. [{block['type']}] {block['content'][:100]}...")
else:
    print(f"❌ Ошибка: {response.status_code}")








