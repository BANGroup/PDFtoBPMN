#!/usr/bin/env python3
"""
Тестирование vLLM 0.8.5 на странице 23 документа ДП-М1.020-06
Сравнение с результатами Transformers+flash_attn
"""

import asyncio
import os
import sys
import time
import torch
from pathlib import Path

# Настройки окружения для vLLM 0.8.5
if torch.version.cuda == '11.8':
    os.environ["TRITON_PTXAS_PATH"] = "/usr/local/cuda-12.8/bin/ptxas"

os.environ['VLLM_USE_V1'] = '0'  # vLLM 0.8.5 uses V0 API
os.environ["CUDA_VISIBLE_DEVICES"] = '0'
os.environ["TORCH_CUDA_ARCH_LIST"] = "9.0"  # RTX 5080 (sm_120) использует sm_90 в режиме совместимости

# Добавляем путь к DeepSeek-OCR модулям
sys.path.insert(0, str(Path("/home/budnik_an/Obligations/DeepSeek-OCR/DeepSeek-OCR-master/DeepSeek-OCR-vllm")))

from vllm import AsyncLLMEngine, SamplingParams
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.model_executor.models.registry import ModelRegistry
from PIL import Image, ImageOps
from process.ngram_norepeat import NoRepeatNGramLogitsProcessor
from process.image_process import DeepseekOCRProcessor

# Импортируем модель
try:
    from deepseek_ocr import DeepseekOCRForCausalLM
    ModelRegistry.register_model("DeepseekOCRForCausalLM", DeepseekOCRForCausalLM)
    print("✅ DeepseekOCRForCausalLM зарегистрирована")
except Exception as e:
    print(f"⚠️ Ошибка регистрации модели: {e}")


def load_image(image_path):
    """Загрузить изображение с коррекцией EXIF"""
    try:
        image = Image.open(image_path)
        corrected_image = ImageOps.exif_transpose(image)
        return corrected_image
    except Exception as e:
        print(f"⚠️ Ошибка загрузки изображения: {e}")
        return Image.open(image_path)


async def stream_generate(image_features, prompt):
    """Генерация с использованием vLLM"""
    
    # Конфигурация движка
    engine_args = AsyncEngineArgs(
        model="deepseek-ai/DeepSeek-OCR",  # Используем модель из HuggingFace cache
        hf_overrides={"architectures": ["DeepseekOCRForCausalLM"]},
        block_size=256,
        max_model_len=8192,
        enforce_eager=False,
        trust_remote_code=True,
        tensor_parallel_size=1,
        gpu_memory_utilization=0.75,
    )
    
    print("📦 Инициализация vLLM движка...")
    engine = AsyncLLMEngine.from_engine_args(engine_args)
    print("✅ vLLM движок готов")
    
    # Логит процессор для предотвращения повторов
    logits_processors = [
        NoRepeatNGramLogitsProcessor(
            ngram_size=30, 
            window_size=90, 
            whitelist_token_ids={128821, 128822}  # <td>, </td>
        )
    ]
    
    sampling_params = SamplingParams(
        temperature=0.0,
        max_tokens=8192,
        logits_processors=logits_processors,
        skip_special_tokens=False,
    )
    
    request_id = f"request-{int(time.time())}"
    
    # Формируем запрос
    if image_features and '<image>' in prompt:
        request = {
            "prompt": prompt,
            "multi_modal_data": {"image": image_features}
        }
    else:
        request = {"prompt": prompt}
    
    print(f"\n{'='*80}")
    print(f"🔄 ГЕНЕРАЦИЯ (vLLM 0.8.5)")
    print(f"{'='*80}\n")
    
    printed_length = 0
    start_time = time.time()
    
    async for request_output in engine.generate(request, sampling_params, request_id):
        if request_output.outputs:
            full_text = request_output.outputs[0].text
            new_text = full_text[printed_length:]
            print(new_text, end='', flush=True)
            printed_length = len(full_text)
            final_output = full_text
    
    elapsed_time = time.time() - start_time
    print(f"\n\n⏱️ Время генерации: {elapsed_time:.2f} сек")
    
    return final_output


async def main():
    """Основная функция тестирования"""
    
    print(f"\n{'='*80}")
    print(f"🧪 ТЕСТИРОВАНИЕ vLLM 0.8.5 НА СТРАНИЦЕ 23")
    print(f"{'='*80}\n")
    
    # Пути
    image_path = Path("/home/budnik_an/Obligations/output/vllm_test/page_23.png")
    output_dir = Path("/home/budnik_an/Obligations/output/vllm_test")
    output_file = output_dir / "vllm_result.txt"
    
    # Проверка изображения
    if not image_path.exists():
        print(f"❌ Изображение не найдено: {image_path}")
        return
    
    print(f"✅ Изображение: {image_path}")
    print(f"   Размер файла: {image_path.stat().st_size / 1024:.1f} KB")
    
    # Загрузка изображения
    print("\n📥 Загружаем изображение...")
    image = load_image(str(image_path)).convert('RGB')
    print(f"✅ Размер: {image.size[0]}x{image.size[1]} пикселей")
    
    # Промпт ocr_simple (лучший результат на тестах)
    prompt = '<image>\n<|grounding|>OCR this image.'
    print(f"\n📝 Промпт: ocr_simple")
    print(f"   '{prompt}'")
    
    # Предобработка изображения
    print("\n🔄 Предобработка изображения...")
    processor = DeepseekOCRProcessor()
    image_features = processor.tokenize_with_images(
        images=[image],
        bos=True,
        eos=True,
        cropping=False  # Base mode: 1024x1024, no cropping
    )
    print(f"✅ Предобработка завершена")
    
    # Генерация с vLLM
    result = await stream_generate(image_features, prompt)
    
    # Сохранение результата
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(result)
    
    print(f"\n{'='*80}")
    print(f"✅ РЕЗУЛЬТАТ СОХРАНЕН: {output_file}")
    print(f"{'='*80}\n")
    
    # Статистика
    lines = result.split('\n')
    print(f"📊 Статистика:")
    print(f"   Строк: {len(lines)}")
    print(f"   Символов: {len(result)}")
    print(f"   Размер файла: {output_file.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

