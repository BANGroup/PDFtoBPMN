#!/usr/bin/env python3
"""
Тест OCR на BPMN с увеличенным разрешением
"""

import sys
import os

# Добавляем путь к DeepSeek-OCR
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'DeepSeek-OCR'))

from transformers import AutoModel, AutoTokenizer
import torch
from pathlib import Path

model_name = 'deepseek-ai/DeepSeek-OCR'

print("🔄 Загрузка модели...")
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModel.from_pretrained(
    model_name,
    _attn_implementation='eager',
    trust_remote_code=True,
    use_safetensors=True
)
model = model.eval().cuda().to(torch.bfloat16)

print("✅ Модель загружена!")

# Используем отрендеренное изображение
image_path = "output/bpmn_test/page_54_bpmn.png"

# Промпт специально для diagram
prompt = "<image>\n<|grounding|>Extract all text from the BPMN diagram including process names, gateway conditions, and event labels."

print(f"\n📄 Обрабатываем: {image_path}")
print(f"🎯 Промпт: {prompt}")
print(f"📐 Режим: Large (2048x2048) + crop_mode=True\n")

# Вызов с увеличенными параметрами
res = model.infer(
    tokenizer,
    prompt=prompt,
    image_file=image_path,
    output_path="output/temp",
    base_size=2048,  # Увеличено с 1024
    image_size=2048,  # Увеличено с 1024
    crop_mode=True,   # Включен crop для детальной обработки
    save_results=False,
    test_compress=False
)

print(f"\n{'='*80}")
print("📝 РЕЗУЛЬТАТ:")
print(f"{'='*80}\n")

# Результат в stdout, захватываем его визуально








