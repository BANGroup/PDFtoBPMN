#!/usr/bin/env python3
"""
Быстрый тест OCR на одной странице без перезапуска сервиса
"""

import fitz
import requests
import json

# Рендерим страницу 54
pdf_path = "input_data/КД-СТ-161-01 (Эталон для ознакомления).pdf"
doc = fitz.open(pdf_path)
page = doc[53]  # страница 54 (0-based)

# Рендер в PNG
zoom = 300 / 72.0
mat = fitz.Matrix(zoom, zoom)
pix = page.get_pixmap(matrix=mat)
img_data = pix.tobytes("png")

doc.close()

print(f"✅ Отрендерена страница 54: {pix.width}x{pix.height} пикселей")
print(f"📤 Отправляем в OCR сервис (prompt_type=bpmn)...\n")

# Отправляем в OCR
files = {"file": ("page_54.png", img_data, "image/png")}
data = {"prompt_type": "bpmn"}

response = requests.post(
    "http://localhost:8000/ocr/figure",
    files=files,
    data=data,
    timeout=120
)

if response.status_code == 200:
    result = response.json()
    
    print(f"✅ Ответ получен!")
    print(f"   Блоков: {len(result['blocks'])}")
    print(f"   Markdown длина: {len(result['markdown'])} символов")
    print(f"\n{'='*80}")
    print("📝 РАСПОЗНАННЫЙ MARKDOWN:")
    print(f"{'='*80}\n")
    print(result['markdown'])
    print(f"\n{'='*80}")
    
    if result['blocks']:
        print(f"\n📦 БЛОКИ ({len(result['blocks'])}):\n")
        for i, block in enumerate(result['blocks'][:5], 1):  # первые 5
            print(f"{i}. [{block['type']}] {block['content'][:80]}...")
else:
    print(f"❌ Ошибка: {response.status_code}")
    print(response.text)








