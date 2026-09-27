#!/usr/bin/env python3
"""
Тест Qwen2.5-VL на реальных изображениях.
Требования: RTX 5080 (16GB VRAM), PyTorch 2.10+cu129

Использование:
    source venv/bin/activate
    python3 scripts/utils/test_qwen_vlm.py output2/test_vlm/page22_img1.jpeg
"""

import sys
import torch
import warnings
warnings.filterwarnings("ignore")

def main():
    if len(sys.argv) < 2:
        print("Использование: python3 test_qwen_vlm.py <путь_к_изображению>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    print("=" * 60)
    print("🧪 ТЕСТ QWEN2.5-VL НА ЛОКАЛЬНОМ GPU")
    print("=" * 60)
    
    # Проверка GPU
    if not torch.cuda.is_available():
        print("❌ CUDA недоступна!")
        sys.exit(1)
    
    torch.cuda.empty_cache()
    free_vram = torch.cuda.mem_get_info()[0] / 1024**3
    total_vram = torch.cuda.mem_get_info()[1] / 1024**3
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {free_vram:.1f} / {total_vram:.1f} GB свободно")
    
    if free_vram < 10:
        print("⚠️ Недостаточно VRAM! Нужно минимум 10GB свободно.")
        sys.exit(1)
    
    # Импорт после проверки
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    from qwen_vl_utils import process_vision_info
    from PIL import Image
    import io
    
    print("\n⏳ Загрузка модели Qwen2.5-VL-7B...")
    print("   (первая загрузка скачивает ~16GB, подождите)")
    
    # Загрузка модели
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        "Qwen/Qwen2.5-VL-7B-Instruct",
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
        device_map="auto",
    )
    
    # Процессор с ограничением разрешения для экономии VRAM
    processor = AutoProcessor.from_pretrained(
        "Qwen/Qwen2.5-VL-7B-Instruct",
        min_pixels=256*28*28,
        max_pixels=512*28*28
    )
    
    print(f"✅ Модель загружена")
    print(f"VRAM после загрузки: {torch.cuda.mem_get_info()[0] / 1024**3:.1f} GB свободно")
    
    # Загрузка изображения
    print(f"\n📷 Обработка: {image_path}")
    
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    image = Image.open(io.BytesIO(image_data))
    print(f"   Размер: {image.size[0]}x{image.size[1]}")
    
    # Подготовка запроса
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "Извлеките весь текст с изображения. Формат: Markdown."}
            ],
        }
    ]
    
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    inputs = inputs.to("cuda")
    
    # Генерация
    print("⏳ Генерация ответа...")
    generated_ids = model.generate(**inputs, max_new_tokens=2048)
    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]
    
    # Результат
    print("\n" + "=" * 60)
    print("📝 РЕЗУЛЬТАТ OCR:")
    print("=" * 60)
    print(output_text)
    print("=" * 60)
    print(f"\n📊 Длина результата: {len(output_text)} символов")
    print(f"VRAM после inference: {torch.cuda.mem_get_info()[0] / 1024**3:.1f} GB свободно")
    
    return output_text

if __name__ == "__main__":
    main()
