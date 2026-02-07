#!/usr/bin/env python3
"""
Fine-tuning YOLO12 для детекции элементов диаграмм/схем.

YOLO12 использует Area Attention (гибрид CNN + Transformer),
что критически важно для диаграмм:
- Захватывает long-range dependencies (стрелки между далёкими блоками)
- Семантический контекст (ромб=решение, прямоугольник=задача)
- Пространственные связи между элементами схемы

Датасеты:
1. Roboflow flow-chart-detection (1.1k изображений, 19 классов)
   https://universe.roboflow.com/object-detection-gol2i/flow-chart-detection
   Экспорт: YOLOv8 формат

2. hdBPMN (502 hand-drawn BPMN, COCO формат)
   https://github.com/dwslab/hdBPMN
   Требует конвертации COCO -> YOLO

Использование:
    # 1. Скачать датасет с Roboflow в YOLOv8 формат:
    #    -> Export -> YOLOv8 -> Download zip
    #    -> Распаковать в datasets/flowchart/
    
    # 2. Запустить обучение:
    python3 scripts/utils/train_diagram_detector.py \\
        --data datasets/flowchart/data.yaml \\
        --epochs 50 \\
        --imgsz 640
    
    # 3. Модель сохранится в models/diagram_detector.pt
    
    # 4. Для проверки:
    python3 scripts/utils/train_diagram_detector.py --test path/to/diagram.png
"""

import argparse
import sys
from pathlib import Path

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def check_prerequisites():
    """Проверка зависимостей перед обучением."""
    errors = []
    
    try:
        import torch
        print(f"PyTorch: {torch.__version__}")
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_mem / 1024**3
            print(f"GPU: {gpu_name} ({vram:.1f} GB VRAM)")
        else:
            print("GPU: не доступен (обучение на CPU будет медленным)")
    except ImportError:
        errors.append("PyTorch не установлен: pip install torch")
    
    try:
        import ultralytics
        print(f"Ultralytics: {ultralytics.__version__}")
    except ImportError:
        errors.append("Ultralytics не установлен: pip install ultralytics")
    
    if errors:
        print("\nОшибки:")
        for e in errors:
            print(f"  - {e}")
        return False
    
    return True


def train(
    data_yaml: str,
    epochs: int = 50,
    imgsz: int = 640,
    batch: int = 16,
    base_model: str = "yolo12n.pt",
    output_dir: str = "models",
    project: str = "runs/diagram_train",
    name: str = "yolo12_flowchart"
):
    """
    Fine-tuning YOLO12 на датасете диаграмм.
    
    Args:
        data_yaml: Путь к data.yaml датасета (YOLO формат)
        epochs: Количество эпох
        imgsz: Размер изображения
        batch: Размер батча
        base_model: Базовая модель YOLO12 (nano по умолчанию)
        output_dir: Папка для сохранения итоговой модели
        project: Папка для логов обучения
        name: Имя эксперимента
    """
    from ultralytics import YOLO
    
    print(f"\n{'='*60}")
    print(f"Fine-tuning YOLO12 для детекции элементов диаграмм")
    print(f"{'='*60}")
    print(f"  Base model: {base_model}")
    print(f"  Dataset: {data_yaml}")
    print(f"  Epochs: {epochs}")
    print(f"  Image size: {imgsz}")
    print(f"  Batch size: {batch}")
    print(f"  Output: {output_dir}/diagram_detector.pt")
    print(f"{'='*60}\n")
    
    # Загрузка базовой модели
    print("Загрузка базовой модели YOLO12...")
    model = YOLO(base_model)
    
    # Обучение
    print("Начало обучения...\n")
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project=project,
        name=name,
        patience=10,  # Early stopping
        save=True,
        save_period=10,  # Сохранять каждые 10 эпох
        plots=True,  # Графики обучения
        verbose=True,
    )
    
    # Копируем лучшую модель
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    best_model_path = Path(project) / name / "weights" / "best.pt"
    target_path = output_path / "diagram_detector.pt"
    
    if best_model_path.exists():
        import shutil
        shutil.copy2(best_model_path, target_path)
        print(f"\nЛучшая модель сохранена: {target_path}")
    else:
        print(f"\nФайл лучшей модели не найден: {best_model_path}")
        # Попробуем last.pt
        last_model_path = Path(project) / name / "weights" / "last.pt"
        if last_model_path.exists():
            import shutil
            shutil.copy2(last_model_path, target_path)
            print(f"Последняя модель сохранена: {target_path}")
    
    # Валидация
    print("\nВалидация модели...")
    val_results = model.val()
    
    print(f"\n{'='*60}")
    print(f"Обучение завершено!")
    print(f"  mAP50: {val_results.box.map50:.4f}")
    print(f"  mAP50-95: {val_results.box.map:.4f}")
    print(f"  Модель: {target_path}")
    print(f"  Логи: {project}/{name}/")
    print(f"{'='*60}")
    
    return target_path


def test_model(model_path: str, image_path: str, imgsz: int = 640):
    """
    Тестирование обученной модели на изображении.
    
    Args:
        model_path: Путь к модели (.pt)
        image_path: Путь к изображению
        imgsz: Размер для инференса
    """
    from ultralytics import YOLO
    
    print(f"Тестирование модели: {model_path}")
    print(f"Изображение: {image_path}")
    
    model = YOLO(model_path)
    results = model.predict(
        source=image_path,
        imgsz=imgsz,
        conf=0.3,
        save=True,
        verbose=True,
    )
    
    for result in results:
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            print("Элементы не обнаружены")
            continue
        
        print(f"\nОбнаружено {len(boxes)} элементов:")
        for i in range(len(boxes)):
            bbox = boxes.xyxy[i].cpu().numpy()
            conf = float(boxes.conf[i].cpu().numpy())
            cls_id = int(boxes.cls[i].cpu().numpy())
            class_name = result.names.get(cls_id, "unknown")
            print(f"  [{class_name}] conf={conf:.2f} bbox=({bbox[0]:.0f}, {bbox[1]:.0f}, {bbox[2]:.0f}, {bbox[3]:.0f})")
    
    print(f"\nРезультаты сохранены в runs/detect/predict/")


def convert_coco_to_yolo(coco_json: str, images_dir: str, output_dir: str):
    """
    Конвертация аннотаций из COCO формата в YOLO формат.
    
    Для hdBPMN датасета:
    https://github.com/dwslab/hdBPMN
    
    Args:
        coco_json: Путь к COCO annotations JSON
        images_dir: Папка с изображениями
        output_dir: Выходная папка (YOLO формат)
    """
    import json
    
    with open(coco_json, 'r', encoding='utf-8') as f:
        coco = json.load(f)
    
    # Маппинг category_id -> индекс
    categories = {cat['id']: idx for idx, cat in enumerate(coco['categories'])}
    cat_names = {cat['id']: cat['name'] for cat in coco['categories']}
    
    # Маппинг image_id -> info
    images = {img['id']: img for img in coco['images']}
    
    # Создаём выходные папки
    out_path = Path(output_dir)
    labels_dir = out_path / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    
    # Конвертация аннотаций
    for ann in coco['annotations']:
        img_id = ann['image_id']
        img_info = images[img_id]
        img_w = img_info['width']
        img_h = img_info['height']
        
        # COCO bbox: [x, y, width, height]
        x, y, w, h = ann['bbox']
        
        # YOLO bbox: [class_id, cx, cy, w, h] (нормализованные)
        cx = (x + w / 2) / img_w
        cy = (y + h / 2) / img_h
        nw = w / img_w
        nh = h / img_h
        
        class_idx = categories[ann['category_id']]
        
        # Записываем в файл (имя = имя изображения без расширения)
        img_name = Path(img_info['file_name']).stem
        label_file = labels_dir / f"{img_name}.txt"
        
        with open(label_file, 'a', encoding='utf-8') as f:
            f.write(f"{class_idx} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")
    
    # Создаём data.yaml
    class_names = [cat_names[cid] for cid in sorted(categories.keys(), key=lambda k: categories[k])]
    
    yaml_content = f"""# hdBPMN Dataset (converted from COCO)
path: {out_path.absolute()}
train: images
val: images

nc: {len(class_names)}
names: {class_names}
"""
    
    yaml_path = out_path / "data.yaml"
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write(yaml_content)
    
    print(f"Конвертация завершена:")
    print(f"  Аннотаций: {len(coco['annotations'])}")
    print(f"  Классов: {len(class_names)}")
    print(f"  Классы: {class_names}")
    print(f"  Labels: {labels_dir}")
    print(f"  data.yaml: {yaml_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Fine-tuning YOLO12 для детекции элементов диаграмм",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Обучение на Roboflow датасете:
  python3 scripts/utils/train_diagram_detector.py \\
      --data datasets/flowchart/data.yaml --epochs 50

  # Тестирование модели:
  python3 scripts/utils/train_diagram_detector.py \\
      --test path/to/diagram.png

  # Конвертация hdBPMN из COCO в YOLO:
  python3 scripts/utils/train_diagram_detector.py \\
      --convert-coco hdBPMN/annotations.json \\
      --images-dir hdBPMN/images \\
      --output-dir datasets/hdbpmn
        """
    )
    
    parser.add_argument("--data", type=str, help="Путь к data.yaml датасета")
    parser.add_argument("--epochs", type=int, default=50, help="Количество эпох (default: 50)")
    parser.add_argument("--imgsz", type=int, default=640, help="Размер изображения (default: 640)")
    parser.add_argument("--batch", type=int, default=16, help="Размер батча (default: 16)")
    parser.add_argument("--base-model", type=str, default="yolo12n.pt",
                       help="Базовая модель YOLO12 (default: yolo12n.pt)")
    parser.add_argument("--output-dir", type=str, default="models",
                       help="Папка для итоговой модели (default: models)")
    
    parser.add_argument("--test", type=str, help="Тестировать модель на изображении")
    parser.add_argument("--model", type=str, default="models/diagram_detector.pt",
                       help="Путь к модели для тестирования")
    
    parser.add_argument("--convert-coco", type=str, help="Конвертировать COCO JSON в YOLO формат")
    parser.add_argument("--images-dir", type=str, help="Папка с изображениями (для конвертации)")
    parser.add_argument("--output-dir-coco", type=str, help="Выходная папка (для конвертации)")
    
    parser.add_argument("--check", action="store_true", help="Проверить зависимости")
    
    args = parser.parse_args()
    
    if args.check:
        check_prerequisites()
        return
    
    if args.convert_coco:
        if not args.images_dir or not args.output_dir_coco:
            parser.error("--convert-coco requires --images-dir and --output-dir-coco")
        convert_coco_to_yolo(args.convert_coco, args.images_dir, args.output_dir_coco)
        return
    
    if args.test:
        if not check_prerequisites():
            sys.exit(1)
        test_model(args.model, args.test, args.imgsz)
        return
    
    if args.data:
        if not check_prerequisites():
            sys.exit(1)
        train(
            data_yaml=args.data,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            base_model=args.base_model,
            output_dir=args.output_dir,
        )
        return
    
    parser.print_help()


if __name__ == "__main__":
    main()
