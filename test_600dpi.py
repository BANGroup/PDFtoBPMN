#!/usr/bin/env python3
"""
Тест с увеличенным DPI рендеринга (600 вместо 300)
Параметры модели безопасные (1024x1024)
"""

import fitz
import requests

# Рендерим страницу 54 с ВЫСОКИМ DPI
pdf_path = "input_data/КД-СТ-161-01 (Эталон для ознакомления).pdf"
doc = fitz.open(pdf_path)
page = doc[53]

zoom = 600 / 72.0  # 600 DPI вместо 300!
mat = fitz.Matrix(zoom, zoom)
pix = page.get_pixmap(matrix=mat)
img_data = pix.tobytes("png")
doc.close()

print(f"✅ Страница 54 отрендерена:")
print(f"   Разрешение: {pix.width}x{pix.height} (600 DPI)")
print(f"   Размер: {len(img_data) / 1024 / 1024:.1f} MB\n")
print(f"🎯 Параметры OCR:")
print(f"   - prompt_type: default")
print(f"   - base_size: 1024 (БЕЗОПАСНО)")
print(f"   - image_size: 1024")
print(f"   - crop_mode: False\n")

files = {"file": ("page_54.png", img_data, "image/png")}
data = {
    "prompt_type": "default"
    # Остальные параметры по умолчанию (безопасные)
}

print("📤 Отправляем (это займет ~5-8 секунд)...\n")

response = requests.post(
    "http://localhost:8000/ocr/figure",
    files=files,
    data=data,
    timeout=120
)

if response.status_code == 200:
    result = response.json()
    
    print(f"✅ РЕЗУЛЬТАТ:")
    print(f"   Блоков: {len(result['blocks'])}")
    print(f"   Markdown: {len(result['markdown'])} символов\n")
    print(f"{'='*80}")
    print("📝 MARKDOWN:")
    print(f"{'='*80}\n")
    print(result['markdown'])
    
    if len(result['blocks']) > 3:
        print(f"\n{'='*80}")
        print(f"📦 ДОПОЛНИТЕЛЬНЫЕ БЛОКИ (кроме 3 текстовых):")
        print(f"{'='*80}\n")
        for i, block in enumerate(result['blocks'][3:], 4):
            print(f"{i}. [{block['type']}] {block['content'][:100]}...")
else:
    print(f"❌ Ошибка: {response.status_code}")





