# 🏗️ АРХИТЕКТУРА SMART MERGE ДЛЯ DEEPSEEK-OCR

**Дата:** 31.10.2025  
**Задача:** Объединение результатов от промптов `ocr_simple` и `parse_figure` для построения BPMN

---

## 📋 ВХОДНЫЕ ДАННЫЕ

### Вход A: Результат `ocr_simple`
```python
{
  "raw_output": """
    <|ref|>npoecc2<|/ref|><|det|>[[595, 350, 649, 370]]<|/det|>
    <|ref|>C6bITHe1<|/ref|><|det|>[[500, 380, 560, 400]]<|/det|>
    <|ref|>npoecc1<|/ref|><|det|>[[355, 410, 409, 431]]<|/det|>
    <|ref|>npoecc3<|/ref|><|det|>[[595, 479, 649, 499]]<|/det|>
    <|ref|>C6bITHe2<|/ref|><|det|>[[500, 510, 560, 530]]<|/det|>
  """,
  "blocks": []  # Пусто, так как парсер не понимает искаженный текст
}
```

**Что имеем:**
- ✅ Точные координаты каждого элемента (bbox)
- ⚠️ Искаженный текст (latin транслитерация cyrillic)
- ❌ Нет типов элементов
- ❌ Нет связей между элементами

### Вход B: Результат `parse_figure`
```python
{
  "raw_output": """
    The main body of the document contains a diagram with three 
    interconnected boxes, each labeled "Процесс 1," "Процесс 2," 
    and "Процесс 3," respectively. These boxes are connected by 
    arrows, indicating a flow or sequence of processes. The diagram 
    is labeled "Событие 1," "Событие 2," and "Событие 3," which 
    translates to "Event 1," "Event 2," and "Event 3," respectively. 
    The boxes and arrows are colored in yellow, with the exception 
    of the "Событие 1" box, which is in black.
  """,
  "blocks": []  # Пусто, так как это режим describe
}
```

**Что имеем:**
- ✅ Правильные названия элементов ("Процесс 1", "Событие 1")
- ✅ Описание связей ("connected by arrows")
- ✅ Типы элементов ("boxes" = Task, может быть "circles" = Event)
- ✅ Визуальные характеристики (цвета)
- ❌ НЕТ координат

---

## 🎯 ТРЕБУЕМЫЙ ВЫХОД

```python
{
  "elements": [
    {
      "id": "element_1",
      "type": "bpmn:Task",           # Определен из описания "boxes"
      "name": "Процесс 1",           # Правильное имя из parse_figure
      "bbox": [355, 410, 409, 431],  # Точные координаты из ocr_simple
      "visual": {
        "color": "yellow",
        "shape": "box"
      }
    },
    {
      "id": "element_2",
      "type": "bpmn:Event",           # Определен из описания или цвета
      "name": "Событие 1",
      "bbox": [500, 380, 560, 400],
      "visual": {
        "color": "black",
        "shape": "circle"
      }
    },
    # ...
  ],
  "connections": [
    {
      "id": "flow_1",
      "type": "bpmn:SequenceFlow",
      "source": "element_1",
      "target": "element_2"
    },
    # ...
  ]
}
```

---

## 🧩 КОМПОНЕНТЫ СИСТЕМЫ

### 1. TextNormalizer
**Задача:** Исправить искаженную кириллицу из `ocr_simple`

```python
class TextNormalizer:
    """
    Преобразует искаженный текст в правильный русский.
    
    Методы:
    - cyrillic_from_latin_mangled() - обратная транслитерация
    - fuzzy_match() - нечеткое сопоставление с эталонами
    """
    
    TRANSLITERATION_MAP = {
        'n': 'п',
        'p': 'р',
        'o': 'о',
        'e': 'е',
        'c': 'с',
        'C': 'С',
        'b': 'ы',
        'I': 'И',
        'T': 'Т',
        'H': 'Н',
        'e': 'е',
        # ... полная таблица
    }
    
    def normalize(self, mangled_text: str) -> List[str]:
        """
        Возвращает список возможных вариантов нормализации.
        
        Пример:
        "npoecc1" → ["процесс1", "Процесс 1", "процесс 1"]
        "C6bITHe1" → ["событие1", "Событие 1", "событие 1"]
        """
        # 1. Прямая транслитерация
        direct = self._apply_transliteration(mangled_text)
        
        # 2. Добавление пробелов перед цифрами
        spaced = self._add_spaces_before_digits(direct)
        
        # 3. Капитализация
        variants = [
            spaced,
            spaced.lower(),
            spaced.capitalize(),
            spaced.title()
        ]
        
        return variants
```

**Принципы:**
- **KISS:** Простая таблица замены символов
- **DRY:** Единый метод для всех искажений
- **SOLID (S):** Только нормализация текста, ничего больше

---

### 2. LabelExtractor
**Задача:** Извлечь список меток из описания `parse_figure`

```python
class LabelExtractor:
    """
    Извлекает названия элементов из текстового описания.
    
    Использует regex + NLP для поиска паттернов вида:
    - "labeled 'Процесс 1'"
    - "each labeled 'X', 'Y', and 'Z'"
    - "'Событие 1' ('Event 1')"
    """
    
    def extract_labels(self, description: str) -> List[dict]:
        """
        Возвращает список найденных меток с метаданными.
        
        Пример:
        [
          {"text": "Процесс 1", "type_hint": "box", "color": "yellow"},
          {"text": "Процесс 2", "type_hint": "box", "color": "yellow"},
          {"text": "Событие 1", "type_hint": "circle", "color": "black"},
          ...
        ]
        """
        labels = []
        
        # Паттерн 1: "labeled 'X', 'Y', and 'Z'"
        pattern1 = r"labeled \"([^\"]+)\""
        matches1 = re.findall(pattern1, description)
        
        # Паттерн 2: "'X' ('Y')" - русское и английское
        pattern2 = r"\"([^\"]+)\"\s*\(\"([^\"]+)\"\)"
        matches2 = re.findall(pattern2, description)
        
        # Паттерн 3: Контекстный анализ
        # "boxes labeled X" → X это Task
        # "circles representing Y" → Y это Event
        
        # Извлечение типов из контекста
        type_hints = self._extract_type_hints(description)
        color_info = self._extract_color_info(description)
        
        # Объединение всех данных
        for label_text in all_matches:
            labels.append({
                "text": label_text,
                "type_hint": type_hints.get(label_text),
                "color": color_info.get(label_text),
                "context": self._get_context(description, label_text)
            })
        
        return labels
    
    def _extract_type_hints(self, description: str) -> dict:
        """
        Анализирует описание для определения типов элементов.
        
        Ключевые слова:
        - "boxes", "rectangles" → Task
        - "circles", "ovals" → Event
        - "diamonds", "gateway" → Gateway
        - "arrows", "connected" → SequenceFlow
        """
        type_map = {}
        
        # Найти все упоминания элементов с типами
        # "three interconnected boxes, each labeled 'A', 'B', 'C'"
        # → A, B, C = Task
        
        return type_map
```

**Принципы:**
- **SOLID (S):** Только извлечение меток, не парсинг координат
- **KISS:** Простые regex паттерны
- **DRY:** Переиспользуемые паттерны

---

### 3. CoordinateParser
**Задача:** Распарсить `<|ref|>...<|det|>[[x,y,x,y]]<|/det|>` из `ocr_simple`

```python
class CoordinateParser:
    """
    Парсит raw output от ocr_simple и извлекает элементы с координатами.
    """
    
    def parse(self, raw_output: str) -> List[dict]:
        """
        Возвращает список элементов с координатами.
        
        Пример:
        [
          {"text": "npoecc1", "bbox": [355, 410, 409, 431]},
          {"text": "C6bITHe1", "bbox": [500, 380, 560, 400]},
          ...
        ]
        """
        elements = []
        
        # Паттерн: <|ref|>TEXT<|/ref|><|det|>[[x1,y1,x2,y2]]<|/det|>
        pattern = r'<\|ref\|>([^<]+)<\|/ref\|><\|det\|>\[\[([^\]]+)\]\]<\|/det\|>'
        
        for match in re.finditer(pattern, raw_output):
            text = match.group(1)
            coords_str = match.group(2)
            
            # Парсинг координат
            coords = [float(x.strip()) for x in coords_str.split(',')]
            
            if len(coords) == 4:
                elements.append({
                    "text": text,
                    "bbox": coords,
                    "bbox_dict": {
                        "x0": coords[0],
                        "y0": coords[1],
                        "x1": coords[2],
                        "y1": coords[3]
                    }
                })
        
        return elements
```

**Принципы:**
- **SOLID (S):** Только парсинг, не нормализация
- **KISS:** Прямой regex, без сложных FSM
- **DRY:** Один паттерн для всех элементов

---

### 4. ElementMatcher (🔥 ЯДРО СИСТЕМЫ)
**Задача:** Сопоставить элементы из двух источников

```python
class ElementMatcher:
    """
    Сопоставляет искаженный текст с координатами (ocr_simple) 
    с правильными метками (parse_figure).
    
    Стратегии matching:
    1. Fuzzy string matching (Levenshtein distance)
    2. Semantic matching (после нормализации)
    3. Positional matching (по относительному расположению)
    4. Count matching (если количество совпадает)
    """
    
    def __init__(self, normalizer: TextNormalizer):
        self.normalizer = normalizer
    
    def match(
        self, 
        coord_elements: List[dict],  # Из ocr_simple
        label_elements: List[dict]   # Из parse_figure
    ) -> List[dict]:
        """
        Возвращает объединенный список элементов.
        
        Алгоритм:
        1. Нормализовать искаженный текст
        2. Для каждого элемента с координатами найти лучший match по метке
        3. Если match найден - объединить данные
        4. Если не найден - оставить как есть с предупреждением
        """
        matched = []
        unmatched_coords = []
        unmatched_labels = list(label_elements)
        
        # ЭТАП 1: Прямой matching (после нормализации)
        for coord_elem in coord_elements:
            mangled = coord_elem['text']
            bbox = coord_elem['bbox']
            
            # Нормализуем искаженный текст
            normalized_variants = self.normalizer.normalize(mangled)
            
            # Ищем лучший match среди меток
            best_match = None
            best_score = 0
            
            for label_elem in unmatched_labels:
                label_text = label_elem['text']
                
                # Сравниваем с каждым вариантом нормализации
                for variant in normalized_variants:
                    score = self._fuzzy_match_score(variant, label_text)
                    
                    if score > best_score:
                        best_score = score
                        best_match = label_elem
            
            # Если нашли хороший match (score > 0.7)
            if best_score > 0.7 and best_match:
                matched.append({
                    "name": best_match['text'],           # Правильное имя
                    "bbox": bbox,                         # Точные координаты
                    "type_hint": best_match.get('type_hint'),
                    "color": best_match.get('color'),
                    "confidence": best_score,
                    "original_text": mangled              # Для отладки
                })
                unmatched_labels.remove(best_match)
            else:
                unmatched_coords.append(coord_elem)
        
        # ЭТАП 2: Positional matching для неспаренных элементов
        if unmatched_coords and unmatched_labels:
            # Если количество элементов совпадает, используем позиционный анализ
            if len(unmatched_coords) == len(unmatched_labels):
                # Сортируем оба списка по Y-координате (сверху вниз)
                sorted_coords = sorted(
                    unmatched_coords, 
                    key=lambda x: x['bbox'][1]  # y0
                )
                sorted_labels = sorted(
                    unmatched_labels,
                    key=lambda x: self._infer_position(x, label_elements)
                )
                
                # Спариваем по порядку
                for coord, label in zip(sorted_coords, sorted_labels):
                    matched.append({
                        "name": label['text'],
                        "bbox": coord['bbox'],
                        "type_hint": label.get('type_hint'),
                        "color": label.get('color'),
                        "confidence": 0.5,  # Низкая уверенность
                        "matching_method": "positional",
                        "original_text": coord['text']
                    })
                
                unmatched_coords = []
                unmatched_labels = []
        
        # ЭТАП 3: Обработка несопоставленных элементов
        # Оставляем с предупреждениями
        for coord in unmatched_coords:
            matched.append({
                "name": f"UNKNOWN_{coord['text']}",
                "bbox": coord['bbox'],
                "confidence": 0.1,
                "warning": "No matching label found",
                "original_text": coord['text']
            })
        
        return matched
    
    def _fuzzy_match_score(self, str1: str, str2: str) -> float:
        """
        Вычисляет similarity score между строками.
        
        Использует:
        - Levenshtein distance
        - Normalized similarity (0.0 - 1.0)
        """
        from difflib import SequenceMatcher
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
    
    def _infer_position(self, label: dict, all_labels: List[dict]) -> float:
        """
        Пытается определить относительную позицию метки
        на основе описания порядка в parse_figure.
        
        Пример: "Процесс 1" → 1, "Процесс 2" → 2, "Процесс 3" → 3
        """
        text = label['text']
        
        # Извлекаем числа из текста
        numbers = re.findall(r'\d+', text)
        if numbers:
            return float(numbers[0])
        
        # Или по порядку упоминания в контексте
        if 'context' in label:
            # Анализ позиции в тексте описания
            pass
        
        return 0.0
```

**Принципы:**
- **SOLID (S):** Только matching, не извлечение или нормализация
- **SOLID (O):** Можно добавить новые стратегии matching без изменения кода
- **SOLID (D):** Зависит от абстракции TextNormalizer
- **KISS:** Простые эвристики, не ML
- **DRY:** Переиспользуемые функции сравнения

---

### 5. ConnectionExtractor
**Задача:** Извлечь связи из описания `parse_figure`

```python
class ConnectionExtractor:
    """
    Извлекает информацию о связях между элементами из текстового описания.
    
    Ключевые фразы:
    - "connected by arrows"
    - "flow from X to Y"
    - "interconnected boxes"
    - "sequence of processes"
    """
    
    def extract_connections(
        self, 
        description: str,
        elements: List[dict]
    ) -> List[dict]:
        """
        Возвращает список связей.
        
        Алгоритм:
        1. Найти упоминания связей ("connected", "arrows", "flow")
        2. Определить направление (if specified)
        3. Если явного направления нет - вывести по геометрии (слева направо, сверху вниз)
        """
        connections = []
        
        # Анализируем описание на предмет явных связей
        # "A connected to B by arrow" → A → B
        explicit_connections = self._extract_explicit_connections(description)
        
        if explicit_connections:
            return explicit_connections
        
        # Если явных связей нет, делаем геометрический анализ
        # Предполагаем последовательный flow слева направо
        if "sequence" in description.lower() or "flow" in description.lower():
            # Сортируем элементы по X-координате
            sorted_elements = sorted(elements, key=lambda e: e['bbox'][0])
            
            # Создаем последовательные связи
            for i in range(len(sorted_elements) - 1):
                connections.append({
                    "type": "bpmn:SequenceFlow",
                    "source": sorted_elements[i]['name'],
                    "target": sorted_elements[i + 1]['name'],
                    "confidence": 0.6,
                    "inferred": True
                })
        
        return connections
    
    def _extract_explicit_connections(self, description: str) -> List[dict]:
        """
        Ищет явные описания связей в тексте.
        
        Паттерны:
        - "'X' connected to 'Y'"
        - "'X' flows to 'Y'"
        - "from 'X' to 'Y'"
        """
        connections = []
        
        # Паттерн: "from X to Y"
        pattern = r"from\s+['\"]([^'\"]+)['\"]\s+to\s+['\"]([^'\"]+)['\"]"
        matches = re.findall(pattern, description, re.IGNORECASE)
        
        for source, target in matches:
            connections.append({
                "type": "bpmn:SequenceFlow",
                "source": source,
                "target": target,
                "confidence": 0.9,
                "inferred": False
            })
        
        return connections
```

**Принципы:**
- **SOLID (S):** Только извлечение связей
- **KISS:** Простые эвристики и паттерны
- **DRY:** Переиспользуемые паттерны

---

### 6. TypeInferencer
**Задача:** Определить тип BPMN элемента

```python
class TypeInferencer:
    """
    Определяет тип BPMN элемента на основе:
    - type_hint из описания ("box", "circle", "diamond")
    - Названия элемента ("Процесс" → Task, "Событие" → Event)
    - Визуальных характеристик (цвет, форма)
    - Геометрии bbox (aspect ratio)
    """
    
    TYPE_KEYWORDS = {
        "bpmn:Task": ["процесс", "задача", "действие", "операция"],
        "bpmn:Event": ["событие", "старт", "конец", "начало"],
        "bpmn:Gateway": ["шлюз", "условие", "развилка", "gateway"]
    }
    
    TYPE_SHAPES = {
        "bpmn:Task": ["box", "rectangle"],
        "bpmn:Event": ["circle", "oval"],
        "bpmn:Gateway": ["diamond", "rhombus"]
    }
    
    def infer_type(self, element: dict) -> str:
        """
        Возвращает тип BPMN элемента.
        
        Алгоритм (по приоритету):
        1. Если есть type_hint в описании - использовать его
        2. Проверить ключевые слова в названии
        3. Анализ геометрии bbox (соотношение сторон)
        4. Default: Task
        """
        # Приоритет 1: type_hint
        if 'type_hint' in element and element['type_hint']:
            hint = element['type_hint'].lower()
            for bpmn_type, shapes in self.TYPE_SHAPES.items():
                if hint in shapes:
                    return bpmn_type
        
        # Приоритет 2: Ключевые слова в названии
        name = element.get('name', '').lower()
        for bpmn_type, keywords in self.TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in name:
                    return bpmn_type
        
        # Приоритет 3: Геометрический анализ
        bbox = element.get('bbox')
        if bbox:
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            aspect_ratio = width / height if height > 0 else 1.0
            
            # Круги имеют aspect_ratio ≈ 1.0
            if 0.8 < aspect_ratio < 1.2:
                return "bpmn:Event"
            
            # Ромбы (Gateway) тоже ≈ 1.0, но меньше по размеру
            if 0.8 < aspect_ratio < 1.2 and width < 40:
                return "bpmn:Gateway"
        
        # Default
        return "bpmn:Task"
```

**Принципы:**
- **SOLID (S):** Только определение типа
- **SOLID (O):** Легко добавить новые эвристики
- **KISS:** Простые правила без ML

---

### 7. BPMNHybridExtractor (ГЛАВНЫЙ ОРКЕСТРАТОР)
**Задача:** Объединить все компоненты в единый pipeline

```python
class BPMNHybridExtractor:
    """
    Главный класс для гибридного извлечения BPMN из изображения.
    
    Pipeline:
    1. Запрос к OCR с промптом "ocr_simple" → координаты
    2. Запрос к OCR с промптом "parse_figure" → метки и связи
    3. Парсинг обоих результатов
    4. Нормализация искаженного текста
    5. Matching элементов
    6. Извлечение связей
    7. Определение типов
    8. Формирование финального BPMN IR
    """
    
    def __init__(self, ocr_service_url: str):
        self.ocr_url = ocr_service_url
        
        # Инициализация компонентов
        self.coord_parser = CoordinateParser()
        self.label_extractor = LabelExtractor()
        self.normalizer = TextNormalizer()
        self.matcher = ElementMatcher(self.normalizer)
        self.connection_extractor = ConnectionExtractor()
        self.type_inferencer = TypeInferencer()
    
    def extract(self, image_path: str) -> dict:
        """
        Главный метод извлечения BPMN.
        
        Returns: BPMN Intermediate Representation
        """
        logger.info(f"Извлечение BPMN из {image_path}")
        
        # ШАГ 1: OCR с ocr_simple (координаты)
        logger.info("  [1/7] Запрос ocr_simple...")
        coord_result = self._ocr_request(image_path, "ocr_simple")
        coord_elements = self.coord_parser.parse(coord_result['raw_output'])
        logger.info(f"  Найдено {len(coord_elements)} элементов с координатами")
        
        # ШАГ 2: OCR с parse_figure (метки и связи)
        logger.info("  [2/7] Запрос parse_figure...")
        label_result = self._ocr_request(image_path, "parse_figure")
        label_elements = self.label_extractor.extract_labels(
            label_result['raw_output']
        )
        logger.info(f"  Найдено {len(label_elements)} меток")
        
        # ШАГ 3: Matching
        logger.info("  [3/7] Matching элементов...")
        matched_elements = self.matcher.match(coord_elements, label_elements)
        logger.info(f"  Сопоставлено {len(matched_elements)} элементов")
        
        # ШАГ 4: Определение типов
        logger.info("  [4/7] Определение типов элементов...")
        for elem in matched_elements:
            elem['type'] = self.type_inferencer.infer_type(elem)
        
        # ШАГ 5: Извлечение связей
        logger.info("  [5/7] Извлечение связей...")
        connections = self.connection_extractor.extract_connections(
            label_result['raw_output'],
            matched_elements
        )
        logger.info(f"  Найдено {len(connections)} связей")
        
        # ШАГ 6: Присвоение ID
        logger.info("  [6/7] Присвоение ID...")
        for i, elem in enumerate(matched_elements):
            elem['id'] = f"element_{i+1}"
        
        for i, conn in enumerate(connections):
            conn['id'] = f"flow_{i+1}"
        
        # ШАГ 7: Формирование финального IR
        logger.info("  [7/7] Формирование BPMN IR...")
        bpmn_ir = {
            "elements": matched_elements,
            "connections": connections,
            "metadata": {
                "source_image": image_path,
                "extraction_method": "hybrid_deepseek_ocr",
                "timestamp": datetime.now().isoformat(),
                "ocr_simple_elements": len(coord_elements),
                "parse_figure_labels": len(label_elements),
                "matched_elements": len(matched_elements),
                "confidence_avg": self._calc_avg_confidence(matched_elements)
            }
        }
        
        logger.info("✅ Извлечение завершено")
        return bpmn_ir
    
    def _ocr_request(self, image_path: str, prompt_type: str) -> dict:
        """Запрос к OCR сервису"""
        with open(image_path, 'rb') as f:
            files = {"file": f}
            data = {"prompt_type": prompt_type}
            response = requests.post(
                f"{self.ocr_url}/ocr/figure",
                files=files,
                data=data,
                timeout=120
            )
            response.raise_for_status()
            return response.json()
    
    def _calc_avg_confidence(self, elements: List[dict]) -> float:
        """Вычисляет среднюю уверенность matching"""
        confidences = [e.get('confidence', 0.0) for e in elements]
        return sum(confidences) / len(confidences) if confidences else 0.0
```

**Принципы:**
- **SOLID (S):** Оркестрирует компоненты, не делает их работу
- **SOLID (D):** Зависит от абстракций компонентов
- **KISS:** Линейный pipeline без сложной логики
- **DRY:** Переиспользует все компоненты

---

## 📊 ПРИМЕР РАБОТЫ

### Входные данные:

**Изображение:** page_54_bpmn.png

### Промежуточные результаты:

**После CoordinateParser:**
```python
[
  {"text": "npoecc1", "bbox": [355, 410, 409, 431]},
  {"text": "C6bITHe1", "bbox": [500, 380, 560, 400]},
  {"text": "npoecc2", "bbox": [595, 350, 649, 370]},
  {"text": "npoecc3", "bbox": [595, 479, 649, 499]},
  {"text": "C6bITHe2", "bbox": [500, 510, 560, 530]},
]
```

**После LabelExtractor:**
```python
[
  {"text": "Процесс 1", "type_hint": "box", "color": "yellow"},
  {"text": "Процесс 2", "type_hint": "box", "color": "yellow"},
  {"text": "Процесс 3", "type_hint": "box", "color": "yellow"},
  {"text": "Событие 1", "type_hint": "circle", "color": "black"},
  {"text": "Событие 2", "type_hint": "circle", "color": "yellow"},
]
```

**После TextNormalizer (для "npoecc1"):**
```python
[
  "процесс1",
  "Процесс 1",
  "процесс 1",
  "ПРОЦЕСС 1"
]
```

**После ElementMatcher:**
```python
[
  {
    "name": "Процесс 1",
    "bbox": [355, 410, 409, 431],
    "type_hint": "box",
    "color": "yellow",
    "confidence": 0.95,
    "original_text": "npoecc1"
  },
  {
    "name": "Событие 1",
    "bbox": [500, 380, 560, 400],
    "type_hint": "circle",
    "color": "black",
    "confidence": 0.92,
    "original_text": "C6bITHe1"
  },
  # ...
]
```

**После TypeInferencer:**
```python
[
  {
    "id": "element_1",
    "type": "bpmn:Task",
    "name": "Процесс 1",
    "bbox": [355, 410, 409, 431],
    # ...
  },
  {
    "id": "element_2",
    "type": "bpmn:Event",
    "name": "Событие 1",
    "bbox": [500, 380, 560, 400],
    # ...
  },
  # ...
]
```

**После ConnectionExtractor:**
```python
[
  {
    "id": "flow_1",
    "type": "bpmn:SequenceFlow",
    "source": "element_1",
    "target": "element_2",
    "confidence": 0.6
  },
  # ...
]
```

### Финальный BPMN IR:

```json
{
  "elements": [
    {
      "id": "element_1",
      "type": "bpmn:Task",
      "name": "Процесс 1",
      "bbox": [355, 410, 409, 431],
      "visual": {"color": "yellow", "shape": "box"},
      "confidence": 0.95
    },
    {
      "id": "element_2",
      "type": "bpmn:Event",
      "name": "Событие 1",
      "bbox": [500, 380, 560, 400],
      "visual": {"color": "black", "shape": "circle"},
      "confidence": 0.92
    }
  ],
  "connections": [
    {
      "id": "flow_1",
      "type": "bpmn:SequenceFlow",
      "source": "element_1",
      "target": "element_2"
    }
  ],
  "metadata": {
    "extraction_method": "hybrid_deepseek_ocr",
    "confidence_avg": 0.89
  }
}
```

---

## ⚖️ ОЦЕНКА ТОЧНОСТИ

### Сценарий 1: Идеальный match
- Искаженный текст хорошо нормализуется
- Количество элементов совпадает
- **Точность:** 90-95%

### Сценарий 2: Частичный match
- Некоторые элементы не удается нормализовать
- Используется positional matching
- **Точность:** 70-80%

### Сценарий 3: Сложная диаграмма
- Много элементов, перекрытия
- Нечеткое описание связей
- **Точность:** 60-70%

---

## 🚀 ПРЕИМУЩЕСТВА ПОДХОДА

1. ✅ **Работает без fine-tuning**
2. ✅ **Использует сильные стороны обоих промптов**
3. ✅ **Прозрачный и отлаживаемый** (каждый шаг явный)
4. ✅ **Расширяемый** (легко добавить новые стратегии)
5. ✅ **Fault-tolerant** (fallback на positional matching)

---

## ⚠️ ОГРАНИЧЕНИЯ

1. ⏱️ **Двойное время** (~19 сек вместо 9 сек)
2. 🎯 **Не 100% точность** (особенно для сложных диаграмм)
3. 🔧 **Требует тонкой настройки** эвристик для разных типов BPMN
4. ⚠️ **Может ошибаться в связях** (если нет явного описания)

---

## 📈 ВОЗМОЖНЫЕ УЛУЧШЕНИЯ

### Фаза 2 (если потребуется):
1. **ML для matching:** Обучить небольшую модель на паттернах искажений
2. **Computer Vision для связей:** Детекция стрелок на изображении
3. **LLM для post-processing:** GPT-4 для валидации и исправления
4. **Feedback loop:** Обучение на ошибках пользователей

---

## 🎯 ИТОГ

**Smart merge - это:**
- 7 специализированных компонентов
- 2 запроса к OCR сервису
- 5 этапов обработки данных
- Множество эвристик и fallback-стратегий
- Прозрачный и расширяемый pipeline

**Результат:**
- BPMN IR с элементами, связями и координатами
- Готов для конвертации в BPMN XML
- Confidence scores для каждого элемента
- Метаданные для отладки

