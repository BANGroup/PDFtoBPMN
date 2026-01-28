#!/usr/bin/env python3
"""
Модуль построения иерархической структуры документа.

Преобразует плоский список заголовков в дерево на основе нумерации пунктов.
Поддерживает форматы: 1, 1.1, 1.1.1, 1.1.1.1, Приложение N
"""

import re
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class RACIEntry:
    """RACI запись для пункта (заполняется на этапе 2)"""
    responsible: List[str] = field(default_factory=list)  # R - исполнители
    accountable: Optional[str] = None                      # A - ответственный
    consulted: List[str] = field(default_factory=list)    # C - консультанты
    informed: List[str] = field(default_factory=list)     # I - информируемые
    confidence: str = "pending"                            # high/medium/low/needs_review/pending
    extracted_by: Optional[str] = None                     # llm/manual/rule


@dataclass
class SectionNode:
    """Узел дерева структуры документа"""
    id: str                                    # "5.1.2" или "app_1"
    num: str                                   # "5.1.2" или "Приложение 1"
    title: str                                 # Текст заголовка
    level: int                                 # Глубина в иерархии (1, 2, 3...)
    parent_id: Optional[str] = None            # ID родительского узла
    children: List['SectionNode'] = field(default_factory=list)
    content: str = ""                          # Полный текст пункта (включая OCR картинок)
    is_actionable: bool = False                # Содержит действие (не просто определение)
    raci: Optional[RACIEntry] = None           # RACI (заполняется позже)
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для JSON"""
        return {
            "id": self.id,
            "num": self.num,
            "title": self.title,
            "level": self.level,
            "parent_id": self.parent_id,
            "content": self.content,
            "is_actionable": self.is_actionable,
            "raci": asdict(self.raci) if self.raci else None,
            "children": [child.to_dict() for child in self.children]
        }


@dataclass
class DocumentTree:
    """Полная структура документа"""
    doc_code: str
    source: str                                # "pdf" или "docx"
    total_sections: int = 0
    max_depth: int = 0
    actionable_sections: int = 0
    raci_status: str = "pending"               # pending/in_progress/completed
    root: SectionNode = field(default_factory=lambda: SectionNode(
        id="root", num="", title="ROOT", level=0
    ))
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для JSON"""
        return {
            "doc_code": self.doc_code,
            "source": self.source,
            "total_sections": self.total_sections,
            "max_depth": self.max_depth,
            "actionable_sections": self.actionable_sections,
            "raci_status": self.raci_status,
            "tree": self.root.to_dict()
        }


# =============================================================================
# Parsing Functions
# =============================================================================

# Паттерны для распознавания нумерации
SECTION_PATTERNS = [
    # Числовая нумерация: 1, 1.1, 1.1.1, 1.1.1.1
    (r'^(\d+(?:\.\d+)*)\s+(.+)$', 'numeric'),
    # Только номер: 1.1 (без текста)
    (r'^(\d+(?:\.\d+)*)$', 'numeric_only'),
    # Приложение: Приложение 1, Приложение А
    (r'^(Приложение\s+\d+|Приложение\s+[А-Яа-яA-Za-z])\.?\s*(.*)$', 'appendix'),
]

# Служебные разделы (level 0)
SERVICE_SECTIONS = {
    'ПРЕДИСЛОВИЕ', 'ПЕРЕЧЕНЬ РАССЫЛКИ', 'СОДЕРЖАНИЕ', 
    'ЛИСТ РЕГИСТРАЦИИ ИЗМЕНЕНИЙ', 'ОГЛАВЛЕНИЕ',
    'ВВЕДЕНИЕ', 'АННОТАЦИЯ'
}

# Паттерны мусора (игнорируем)
GARBAGE_PATTERNS = [
    r'^Стр\.\s*\d+\s*из\s*\d+',           # Стр. 5 из 29
    r'^\d+$',                              # Просто число
    r'^\.{3,}',                            # Точки (оглавление)
    r'^\s*$',                              # Пустые строки
    r'^[А-Яа-я]{1,3}$',                   # Одиночные буквы
]


def is_garbage(text: str) -> bool:
    """Проверка на мусорный заголовок"""
    text = text.strip()
    for pattern in GARBAGE_PATTERNS:
        if re.match(pattern, text):
            return True
    # Слишком короткий текст без нумерации
    if len(text) < 3 and not re.match(r'^\d', text):
        return True
    return False


def parse_section_number(text: str) -> Tuple[Optional[str], int, str, str]:
    """
    Парсинг нумерации из текста заголовка.
    
    Returns:
        (num, level, title, section_type)
        - num: "5.1.2" или "Приложение 1" или None
        - level: глубина (1, 2, 3...) или 0 для служебных
        - title: текст без номера
        - section_type: "numeric", "appendix", "service", "unknown"
    """
    text = text.strip()
    
    # Убираем trailing dots (из оглавления)
    text = re.sub(r'\.{2,}\s*\d*\s*$', '', text).strip()
    
    # Проверка на служебный раздел
    text_upper = text.upper()
    for service in SERVICE_SECTIONS:
        if text_upper.startswith(service):
            return (None, 0, text, "service")
    
    # Попытка распознать нумерацию
    for pattern, section_type in SECTION_PATTERNS:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            num = match.group(1)
            title = match.group(2) if len(match.groups()) > 1 else ""
            
            if section_type == 'numeric' or section_type == 'numeric_only':
                # Определяем level по количеству точек
                level = len(num.split('.'))
                return (num, level, title.strip() if title else num, "numeric")
            
            elif section_type == 'appendix':
                # Приложения на level 1
                return (num, 1, title.strip() if title else num, "appendix")
    
    return (None, 0, text, "unknown")


def normalize_section_id(num: str, section_type: str) -> str:
    """Нормализация ID секции"""
    if section_type == "appendix":
        # Приложение 1 -> app_1
        match = re.search(r'(\d+|[А-Яа-яA-Za-z])$', num)
        if match:
            return f"app_{match.group(1).lower()}"
    return num


# =============================================================================
# Hierarchy Building
# =============================================================================

def build_hierarchy(headings: List[Dict[str, Any]], doc_code: str = "", source: str = "pdf") -> DocumentTree:
    """
    Построение иерархического дерева из плоского списка заголовков.
    
    Args:
        headings: список {"text": "...", "level": N}
        doc_code: код документа
        source: источник (pdf/docx)
    
    Returns:
        DocumentTree с иерархической структурой
    """
    tree = DocumentTree(doc_code=doc_code, source=source)
    
    # Стек для отслеживания текущей позиции в иерархии
    # {level: SectionNode}
    level_stack: Dict[int, SectionNode] = {0: tree.root}
    
    seen_nums = set()  # Для дедупликации
    
    for heading in headings:
        text = heading.get("text", "").strip()
        
        # Пропускаем мусор
        if is_garbage(text):
            continue
        
        # Парсим нумерацию
        num, level, title, section_type = parse_section_number(text)
        
        # Пропускаем unknown без нумерации (кроме служебных)
        if section_type == "unknown" and level == 0:
            continue
        
        # Дедупликация (пропускаем повторы)
        section_id = normalize_section_id(num, section_type) if num else f"service_{len(seen_nums)}"
        if section_id in seen_nums and section_type != "service":
            continue
        seen_nums.add(section_id)
        
        # Создаем узел
        node = SectionNode(
            id=section_id,
            num=num or "",
            title=title,
            level=level,
            content="",  # Будет заполнено позже
            is_actionable=False  # Будет определено позже
        )
        
        # Находим родителя
        if level == 0:
            # Служебные разделы - дети root
            parent = tree.root
        elif level == 1:
            # Верхний уровень - дети root
            parent = tree.root
        else:
            # Ищем родителя на уровень выше
            parent_level = level - 1
            while parent_level >= 0 and parent_level not in level_stack:
                parent_level -= 1
            parent = level_stack.get(parent_level, tree.root)
        
        node.parent_id = parent.id if parent.id != "root" else None
        parent.children.append(node)
        
        # Обновляем стек
        level_stack[level] = node
        # Очищаем более глубокие уровни
        for l in list(level_stack.keys()):
            if l > level:
                del level_stack[l]
        
        # Обновляем статистику
        tree.total_sections += 1
        tree.max_depth = max(tree.max_depth, level)
    
    return tree


def count_nodes(node: SectionNode) -> int:
    """Подсчет общего количества узлов"""
    count = 1
    for child in node.children:
        count += count_nodes(child)
    return count


def get_nodes_by_level(node: SectionNode, level: int) -> List[SectionNode]:
    """Получение всех узлов определенного уровня"""
    result = []
    if node.level == level:
        result.append(node)
    for child in node.children:
        result.extend(get_nodes_by_level(child, level))
    return result


def flatten_tree(node: SectionNode) -> List[SectionNode]:
    """Преобразование дерева в плоский список (в порядке обхода)"""
    result = []
    if node.id != "root":
        result.append(node)
    for child in node.children:
        result.extend(flatten_tree(child))
    return result


# =============================================================================
# Content Assignment
# =============================================================================

def assign_content_from_text(tree: DocumentTree, full_text: str) -> None:
    """
    Присвоение контента пунктам на основе полного текста документа.
    
    Разбивает full_text на части по нумерации пунктов и присваивает
    соответствующим узлам дерева.
    
    Args:
        tree: дерево структуры
        full_text: полный текст документа (с OCR картинок)
    """
    # Получаем плоский список узлов
    nodes = flatten_tree(tree.root)
    if not nodes:
        return
    
    # Создаем паттерн для поиска начала пунктов
    # Ищем: "5.1 " или "5.1.2 " в начале строки
    section_pattern = r'^(\d+(?:\.\d+)*)\s+'
    
    # Разбиваем текст на строки
    lines = full_text.split('\n')
    
    # Собираем контент для каждого пункта
    current_num = None
    current_content = []
    section_contents: Dict[str, str] = {}
    
    for line in lines:
        match = re.match(section_pattern, line)
        if match:
            # Сохраняем предыдущий контент
            if current_num:
                section_contents[current_num] = '\n'.join(current_content).strip()
            # Начинаем новый пункт
            current_num = match.group(1)
            current_content = [line]
        else:
            current_content.append(line)
    
    # Сохраняем последний пункт
    if current_num:
        section_contents[current_num] = '\n'.join(current_content).strip()
    
    # Присваиваем контент узлам
    for node in nodes:
        if node.num in section_contents:
            node.content = section_contents[node.num]
            # Определяем is_actionable (простая эвристика)
            node.is_actionable = _is_actionable_content(node.content)
            if node.is_actionable:
                tree.actionable_sections += 1


def _is_actionable_content(content: str) -> bool:
    """Определение, содержит ли пункт действие"""
    # Ключевые слова действий
    action_keywords = [
        r'несет ответственность',
        r'обязан',
        r'должен',
        r'выполняет',
        r'осуществляет',
        r'проводит',
        r'обеспечивает',
        r'контролирует',
        r'согласовывает',
        r'утверждает',
        r'направляет',
        r'представляет',
        r'информирует',
    ]
    
    content_lower = content.lower()
    for keyword in action_keywords:
        if re.search(keyword, content_lower):
            return True
    return False


# =============================================================================
# Export Functions
# =============================================================================

def export_tree_json(tree: DocumentTree, output_path: Path) -> None:
    """Сохранение дерева в JSON"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(tree.to_dict(), f, ensure_ascii=False, indent=2)


def export_tree_markdown(tree: DocumentTree, output_path: Path) -> None:
    """Сохранение дерева в Markdown"""
    lines = [
        f"# Структура документа: {tree.doc_code}",
        "",
        f"**Источник:** {tree.source}",
        f"**Разделов:** {tree.total_sections}",
        f"**Макс. глубина:** {tree.max_depth}",
        f"**Actionable разделов:** {tree.actionable_sections}",
        "",
        "## Иерархия",
        "",
    ]
    
    def _render_node(node: SectionNode, indent: int = 0):
        prefix = "  " * indent
        marker = "📌" if node.is_actionable else "📄"
        if node.id != "root":
            lines.append(f"{prefix}- {marker} **{node.num}** {node.title[:50]}{'...' if len(node.title) > 50 else ''}")
        for child in node.children:
            _render_node(child, indent + 1)
    
    _render_node(tree.root)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def print_tree_stats(tree: DocumentTree) -> None:
    """Вывод статистики дерева"""
    print(f"\n📊 Статистика: {tree.doc_code}")
    print(f"   Источник: {tree.source}")
    print(f"   Всего разделов: {tree.total_sections}")
    print(f"   Макс. глубина: {tree.max_depth}")
    print(f"   Actionable: {tree.actionable_sections}")
    
    # Статистика по уровням
    print("\n   По уровням:")
    for level in range(tree.max_depth + 1):
        nodes = get_nodes_by_level(tree.root, level)
        if nodes:
            print(f"     Level {level}: {len(nodes)} узлов")


# =============================================================================
# Main (for testing)
# =============================================================================

if __name__ == "__main__":
    # Тест на примере
    test_headings = [
        {"text": "ПРЕДИСЛОВИЕ", "level": 1},
        {"text": "1 Цель и область применения", "level": 1},
        {"text": "2 Нормативные документы", "level": 1},
        {"text": "5 Общие положения", "level": 1},
        {"text": "5.1 Настоящий документ устанавливает порядок", "level": 1},
        {"text": "5.2 В настоящем документе определен порядок", "level": 1},
        {"text": "6 Ответственность", "level": 1},
        {"text": "6.1 Начальник УИФ несет ответственность", "level": 1},
        {"text": "6.2 Начальник УИФ несет ответственность за актуализацию", "level": 1},
        {"text": "7 Порядок ведения реестров", "level": 1},
        {"text": "7.1 Информационный ресурс", "level": 1},
        {"text": "7.1.1 Детализация первого подпункта", "level": 1},
        {"text": "Приложение 1. Форма отчета", "level": 1},
    ]
    
    tree = build_hierarchy(test_headings, doc_code="TEST-001", source="pdf")
    print_tree_stats(tree)
    
    # Выводим дерево
    def print_tree(node, indent=0):
        if node.id != "root":
            print("  " * indent + f"[{node.level}] {node.num} - {node.title[:40]}")
        for child in node.children:
            print_tree(child, indent + 1)
    
    print("\n📂 Дерево:")
    print_tree(tree.root)
