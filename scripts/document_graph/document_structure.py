"""
Типовая структура документов СМК (Система Менеджмента Качества)

Определяет:
- Стандартные разделы документов
- Мусорные паттерны (колонтитулы, повторяющиеся элементы)
- Типы документов и их специфику
"""

from dataclasses import dataclass, field
from typing import List, Set, Dict, Optional
from enum import Enum
import re


class DocumentType(Enum):
    """Типы документов СМК"""
    KD = "КД"      # Корпоративные документы
    DP = "ДП"      # Документированные процедуры
    IOT = "ИОТ"    # Инструкции по охране труда
    RD = "РД"      # Руководящие документы
    RI = "РИ"      # Рабочие инструкции
    ST = "СТ"      # Стандарты
    RG = "РГ"      # Регламенты
    PR = "ПР"      # Правила
    TPM = "TPM"    # TPM документы
    UNKNOWN = "UNKNOWN"


@dataclass
class StandardSection:
    """Стандартный раздел документа"""
    number: int
    title_ru: str
    title_en: Optional[str] = None
    is_mandatory: bool = True
    description: str = ""


# Стандартные разделы документов СМК
STANDARD_SECTIONS = [
    StandardSection(1, "ЦЕЛЬ И ОБЛАСТЬ ПРИМЕНЕНИЯ", "PURPOSE AND SCOPE", True, 
                    "Определяет назначение и область действия документа"),
    StandardSection(2, "НОРМАТИВНЫЕ ДОКУМЕНТЫ", "NORMATIVE REFERENCES", True,
                    "Ссылки на связанные документы"),
    StandardSection(3, "ОПРЕДЕЛЕНИЯ", "DEFINITIONS", True,
                    "Термины и определения"),
    StandardSection(4, "ОБОЗНАЧЕНИЯ И СОКРАЩЕНИЯ", "ABBREVIATIONS", True,
                    "Аббревиатуры и сокращения"),
    StandardSection(5, "ОБЩИЕ ПОЛОЖЕНИЯ", "GENERAL PROVISIONS", True,
                    "Общая информация о процессе"),
    StandardSection(6, "ОТВЕТСТВЕННОСТЬ", "RESPONSIBILITY", True,
                    "Распределение ответственности"),
]

# Специфичные разделы для ИОТ
IOT_SECTIONS = [
    StandardSection(1, "ОБЩИЕ ТРЕБОВАНИЯ ОХРАНЫ ТРУДА", None, True),
    StandardSection(2, "ТРЕБОВАНИЯ ОХРАНЫ ТРУДА ПЕРЕД НАЧАЛОМ РАБОТЫ", None, True),
    StandardSection(3, "ТРЕБОВАНИЯ ОХРАНЫ ТРУДА ВО ВРЕМЯ РАБОТЫ", None, True),
    StandardSection(4, "ТРЕБОВАНИЯ ОХРАНЫ ТРУДА В АВАРИЙНЫХ СИТУАЦИЯХ", None, True),
    StandardSection(5, "ТРЕБОВАНИЯ ОХРАНЫ ТРУДА ПО ОКОНЧАНИИ РАБОТЫ", None, True),
    StandardSection(6, "ПЕРЕЧЕНЬ НОРМАТИВНЫХ ДОКУМЕНТОВ", None, False),
]


# =============================================================================
# МУСОРНЫЕ ПАТТЕРНЫ (колонтитулы, повторяющиеся элементы)
# =============================================================================

# Паттерны для фильтрации (точное совпадение, case-insensitive)
GARBAGE_EXACT_PATTERNS = {
    # Английские колонтитулы КД
    "PROCEDURES",
    "СOLLECTION OF CONTINUING AIRWORTHINESS",
    "COLLECTION OF CONTINUING AIRWORTHINESS",
    
    # Русские колонтитулы
    "СБОРНИК ПРОЦЕДУР ПО ПОДДЕРЖАНИЮ ЛЕТНОЙ",
    "ГОДНОСТИ",
    
    # Шапки таблиц
    "Наименование",
    "№ р. т.",
    "№ экз./ № к.т.",
    "№  экз./ №  к.т.",
    "№ к.т.",
    "№ р.т.",
    
    # Колонтитулы с номерами страниц
    "Стр.",
    "Page",
    "стр.",
    "page",
}

# Паттерны для фильтрации (regex)
GARBAGE_REGEX_PATTERNS = [
    # Номера документов в колонтитулах (повторяются на каждой странице)
    r"^(КД|ДП|РД|РИ|СТ|РГ|ИОТ)-[А-ЯA-Z0-9\.\-]+\s*(KD|DP|RD|RI|ST|RG)?-?[A-Z0-9\.\-]*$",
    
    # Английские эквиваленты названий
    r"^[A-Z][a-z]+.*Manual$",
    r"^[A-Z][a-z]+.*Procedures?$",
    r"^[A-Z][a-z]+.*Program$",
    
    # Номера страниц в разных форматах
    r"^Page/Страница\s+\d+",
    r"^Стр\.\s*/\s*page\s+\d+",
    r"^\d+-\d+-\d+$",  # Формат страницы типа "12-4-22"
    
    # Даты введения
    r"^Effect\./Дата введ\.\s+\d+\.\d+\.\d+",
    r"^Дата введения",
    
    # Ревизии
    r"^Rev\./Ревизия\s+\d+",
    r"^Issue/Издание\s+\d+",
    
    # Разбитые колонтитулы (фрагменты слов)
    r"^судов$",
    r"^обслуживанию$",
    r"^техники$",
    r"^экипажами$",
    r"^воздушных перевозок$",
    r"^технического имущества$",
    r"^складского учета авиационно-$",
    r"^\(транспортных средств\)$",
    
    # Пустые якоря markdown
    r"^\{#[a-z0-9\-]+\}$",
    r"^`\s*$",  # Пустые блоки кода
    
    # Шапки таблиц и форм
    r"^Выполняется\s*/\s*Implemented",
    r"^Check list of",
    r"^FORM\s+UT\d+",
    r"^Form\s+UT\d+",
    r"^№\s*[–-]\s*[¬_]+",  # Пустые поля форм (№ – ¬___.__/__)
    r"^Используются формы",
    r"^Вовлеченные подразделения",
    r"^Ответственное подразделение",
    r"^Ссылки на документы",
    r"^Основываясь на",
    r"^Ссылка на РД",
    r"^Ссылка на документ",
    
    # Продолжения колонтитулов
    r"^ЛЕТНОЙ ГОДНОСТИ$",
    r"^CONTINUING AIRWORTHINESS$",
    r"^AIRWORTHINESS$",
    
    # Сокращения подразделений
    r"^ЦУТО$",
    r"^УПЛГ$",
    r"^НЕТ$",
    r"^N/A$",
    
    # Рисунки без описания
    r"^Рис\.\s*\d+$",
    r"^Fig\.\s*\d+$",
    
    # Шапки таблиц авиационной документации
    r"^REGISTRATION",
    r"^PART NUMBER$",
    r"^СЕРИЙНЫЙ НОМЕР",
    r"^ТИП ВС",
    r"^AIRCRAFT TYPE",
    r"^ЧЕРТЕЖНЫЙ НОМЕР",
    r"^ЦИКЛЫ$",
    
    # until Status % of completed... (фрагменты таблиц)
    r"^until\s+Status",
]


# =============================================================================
# ВАЖНЫЕ ПАТТЕРНЫ (системные разделы, которые нужно сохранять)
# =============================================================================

IMPORTANT_PATTERNS = [
    # Стандартные разделы СМК
    r"^\d+\s+(ЦЕЛЬ|ОБЛАСТЬ|НОРМАТИВНЫЕ|ОПРЕДЕЛЕНИЯ|ОБОЗНАЧЕНИЯ|ОБЩИЕ|ОТВЕТСТВЕННОСТЬ|ЗАПИСИ)",
    
    # Разделы ИОТ
    r"^\d+\s+ТРЕБОВАНИЯ ОХРАНЫ ТРУДА",
    r"^\d+\s+ОБЩИЕ ТРЕБОВАНИЯ",
    r"^\d+\s+ПЕРЕЧЕНЬ НОРМАТИВНЫХ",
    
    # Служебные разделы
    r"^ПРЕДИСЛОВИЕ",
    r"^ПЕРЕЧЕНЬ РАССЫЛКИ",
    r"^СОДЕРЖАНИЕ$",
    r"^ОГЛАВЛЕНИЕ$",
    r"^ВВЕДЕНИЕ$",
    
    # Приложения
    r"^ПРИЛОЖЕНИЕ\s+[А-ЯA-Z0-9]",
    r"^Приложение\s+[А-ЯA-Z0-9]",
]


class DocumentStructureAnalyzer:
    """
    Анализатор структуры документов
    
    Определяет:
    - Тип документа по коду
    - Мусорные элементы для фильтрации
    - Важные разделы
    """
    
    def __init__(self):
        self._garbage_exact = {p.upper() for p in GARBAGE_EXACT_PATTERNS}
        self._garbage_regex = [re.compile(p, re.IGNORECASE) for p in GARBAGE_REGEX_PATTERNS]
        self._important_regex = [re.compile(p, re.IGNORECASE) for p in IMPORTANT_PATTERNS]
    
    def get_document_type(self, doc_code: str) -> DocumentType:
        """Определить тип документа по коду"""
        if not doc_code:
            return DocumentType.UNKNOWN
            
        # Извлекаем префикс
        parts = doc_code.split("-")
        if not parts:
            return DocumentType.UNKNOWN
            
        prefix = parts[0].upper()
        
        type_map = {
            "КД": DocumentType.KD,
            "ДП": DocumentType.DP,
            "ИОТ": DocumentType.IOT,
            "РД": DocumentType.RD,
            "РИ": DocumentType.RI,
            "СТ": DocumentType.ST,
            "РГ": DocumentType.RG,
            "ПР": DocumentType.PR,
            "TPM": DocumentType.TPM,
        }
        
        return type_map.get(prefix, DocumentType.UNKNOWN)
    
    def is_garbage(self, text: str) -> bool:
        """
        Проверить, является ли текст мусором (колонтитул, повторяющийся элемент)
        
        Args:
            text: Текст для проверки (заголовок или параграф)
            
        Returns:
            True если это мусор
        """
        if not text:
            return True
            
        # Очищаем от markdown якорей
        clean_text = re.sub(r'\s*\{#[^}]+\}\s*$', '', text).strip()
        
        # Слишком короткий текст (обычно артефакт)
        if len(clean_text) < 3:
            return True
        
        # Точное совпадение
        if clean_text.upper() in self._garbage_exact:
            return True
        
        # Regex паттерны
        for pattern in self._garbage_regex:
            if pattern.search(clean_text):
                return True
        
        return False
    
    def is_important(self, text: str) -> bool:
        """
        Проверить, является ли текст важным разделом
        
        Args:
            text: Текст для проверки
            
        Returns:
            True если это важный раздел
        """
        if not text:
            return False
            
        clean_text = re.sub(r'\s*\{#[^}]+\}\s*$', '', text).strip()
        
        for pattern in self._important_regex:
            if pattern.search(clean_text):
                return True
        
        return False
    
    def classify_heading(self, text: str) -> str:
        """
        Классифицировать заголовок
        
        Returns:
            "garbage" - мусор (колонтитул)
            "important" - важный раздел
            "content" - контент (нужно проверить)
        """
        if self.is_garbage(text):
            return "garbage"
        if self.is_important(text):
            return "important"
        return "content"
    
    def get_standard_sections(self, doc_type: DocumentType) -> List[StandardSection]:
        """Получить список стандартных разделов для типа документа"""
        if doc_type == DocumentType.IOT:
            return IOT_SECTIONS
        return STANDARD_SECTIONS


# Создаём глобальный экземпляр для удобства
analyzer = DocumentStructureAnalyzer()


def filter_garbage_headings(headings: List[str]) -> List[str]:
    """
    Отфильтровать мусорные заголовки
    
    Args:
        headings: Список заголовков
        
    Returns:
        Отфильтрованный список
    """
    return [h for h in headings if not analyzer.is_garbage(h)]


def detect_headers_footers(pages_text: List[List[str]], threshold_percent: float = 50.0) -> Set[str]:
    """
    Находит тексты, повторяющиеся на >50% страниц (колонтитулы)
    
    Args:
        pages_text: Список страниц, каждая страница - список текстовых блоков
        threshold_percent: Порог в процентах (по умолчанию 50%)
        
    Returns:
        Множество текстов-колонтитулов
    """
    if not pages_text:
        return set()
    
    total_pages = len(pages_text)
    threshold = total_pages * (threshold_percent / 100.0)
    
    # Считаем на скольких страницах встречается каждый блок
    from collections import defaultdict
    text_page_count = defaultdict(int)
    
    for page_blocks in pages_text:
        # Уникальные блоки на странице (чтобы не считать дважды)
        seen_on_page = set()
        for block in page_blocks:
            normalized = normalize_text(block)
            if normalized and normalized not in seen_on_page:
                text_page_count[normalized] += 1
                seen_on_page.add(normalized)
    
    # Фильтруем колонтитулы
    garbage = {text for text, count in text_page_count.items() 
               if count > threshold}
    
    return garbage


def normalize_text(text: str) -> str:
    """
    Нормализует текст для сравнения
    
    - Убирает markdown якоря
    - Приводит к нижнему регистру
    - Убирает лишние пробелы
    """
    if not text:
        return ""
    
    # Убираем markdown якоря
    clean = re.sub(r'\s*\{#[^}]+\}\s*$', '', text)
    # Убираем лишние пробелы
    clean = ' '.join(clean.split())
    # Нижний регистр
    clean = clean.lower().strip()
    
    return clean


def filter_with_report(headings: List[str], repeat_garbage: Set[str] = None) -> Dict:
    """
    Фильтрует заголовки с детальным отчётом по каждому фильтру
    
    Args:
        headings: Список заголовков
        repeat_garbage: Множество колонтитулов (из detect_headers_footers)
        
    Returns:
        Словарь с результатами фильтрации:
        - filtered_by_repeat: выкинуто по фильтру повторов
        - filtered_by_blacklist: выкинуто по чёрному списку
        - filtered_by_pattern: выкинуто по паттернам
        - kept_important: сохранено (важные разделы)
        - kept_content: сохранено (контент)
    """
    from collections import Counter
    
    repeat_garbage = repeat_garbage or set()
    
    result = {
        "filtered_by_repeat": [],
        "filtered_by_blacklist": [],
        "filtered_by_pattern": [],
        "kept_important": [],
        "kept_content": [],
    }
    
    for heading in headings:
        normalized = normalize_text(heading)
        clean_text = re.sub(r'\s*\{#[^}]+\}\s*$', '', heading).strip()
        
        # 1. Проверка на повторы (>50% страниц)
        if normalized in repeat_garbage:
            result["filtered_by_repeat"].append(heading)
            continue
        
        # 2. Проверка на чёрный список (точные совпадения)
        if clean_text.upper() in analyzer._garbage_exact:
            result["filtered_by_blacklist"].append(heading)
            continue
        
        # 3. Проверка на паттерны мусора (regex)
        is_pattern_garbage = False
        for pattern in analyzer._garbage_regex:
            if pattern.search(clean_text):
                result["filtered_by_pattern"].append(heading)
                is_pattern_garbage = True
                break
        
        if is_pattern_garbage:
            continue
        
        # 4. Если прошёл все фильтры - классифицируем
        if analyzer.is_important(heading):
            result["kept_important"].append(heading)
        else:
            result["kept_content"].append(heading)
    
    return result


def analyze_document_structure(md_content: str) -> Dict:
    """
    Анализировать структуру документа
    
    Args:
        md_content: Markdown контент
        
    Returns:
        Статистика по структуре
    """
    lines = md_content.split('\n')
    
    stats = {
        "total_headings": 0,
        "garbage_headings": 0,
        "important_headings": 0,
        "content_headings": 0,
        "garbage_examples": [],
        "important_examples": [],
    }
    
    for line in lines:
        if line.startswith('# '):
            heading = line[2:].strip()
            stats["total_headings"] += 1
            
            classification = analyzer.classify_heading(heading)
            
            if classification == "garbage":
                stats["garbage_headings"] += 1
                if len(stats["garbage_examples"]) < 5:
                    stats["garbage_examples"].append(heading)
                    
            elif classification == "important":
                stats["important_headings"] += 1
                if len(stats["important_examples"]) < 5:
                    stats["important_examples"].append(heading)
                    
            else:
                stats["content_headings"] += 1
    
    return stats


if __name__ == "__main__":
    # Тест на примерах
    test_headings = [
        "# PROCEDURES",
        "# СOLLECTION OF CONTINUING AIRWORTHINESS",
        "# 1 ЦЕЛЬ И ОБЛАСТЬ ПРИМЕНЕНИЯ",
        "# 3 ОПРЕДЕЛЕНИЯ",
        "# КД-РД-Б1.043-02  KD-RD-B1.043-02",
        "# судов",
        "# ПРЕДИСЛОВИЕ",
        "# 4 ТРЕБОВАНИЯ ОХРАНЫ ТРУДА В АВАРИЙНЫХ СИТУАЦИЯХ",
        "# Наименование",
    ]
    
    print("=== ТЕСТ КЛАССИФИКАЦИИ ===\n")
    
    for h in test_headings:
        text = h[2:]  # Убираем "# "
        classification = analyzer.classify_heading(text)
        emoji = {"garbage": "🗑️", "important": "✅", "content": "📄"}[classification]
        print(f"{emoji} [{classification:10}] {text[:50]}")
