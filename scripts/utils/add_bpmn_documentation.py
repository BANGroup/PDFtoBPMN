#!/usr/bin/env python3
"""
Скрипт для добавления <bpmn:documentation> во все элементы BPMN файла.
Использует данные из traceability.json и названия элементов.
"""

import re
import json
import sys
from pathlib import Path

def extract_section_from_id(element_id: str) -> str:
    """Извлекает номер раздела из ID элемента."""
    # Task_51_ProverkaDok -> 5.1
    # Task_711_TOrder -> 7.1.1
    # SubProcess_5_Priemka -> 5
    
    match = re.search(r'(?:Task|SubProcess)_(\d+)_?(\d*)_?(\d*)', element_id)
    if match:
        parts = [p for p in match.groups() if p]
        if len(parts) == 1:
            return parts[0]
        elif len(parts) >= 2:
            # Формируем раздел: 51 -> 5.1, 711 -> 7.1.1
            first = parts[0]
            if len(first) == 1:
                return first
            elif len(first) == 2:
                return f"{first[0]}.{first[1]}"
            elif len(first) == 3:
                return f"{first[0]}.{first[1]}.{first[2]}"
    return ""

def extract_section_from_name(name: str) -> str:
    """Извлекает номер раздела из названия элемента."""
    # "5.1.1 Проверка документов" -> 5.1.1
    # "5. Приемка ТМЦ" -> 5
    match = re.match(r'^(\d+(?:\.\d+)*)', name)
    if match:
        return match.group(1)
    return ""

def get_element_type_name(tag: str) -> str:
    """Возвращает читаемое название типа элемента."""
    types = {
        'manualTask': 'Ручная задача',
        'userTask': 'Пользовательская задача',
        'serviceTask': 'Сервисная задача',
        'task': 'Задача',
        'subProcess': 'Подпроцесс',
        'exclusiveGateway': 'Шлюз (XOR)',
        'parallelGateway': 'Шлюз (AND)',
        'inclusiveGateway': 'Шлюз (OR)',
        'startEvent': 'Начало',
        'endEvent': 'Завершение',
    }
    return types.get(tag, tag)

def create_documentation(element_id: str, name: str, element_type: str, trace_data: dict) -> str:
    """Создает текст documentation для элемента."""
    
    # Получаем данные из traceability если есть
    trace = trace_data.get('elements', {}).get(element_id, {})
    
    # Определяем раздел
    section = trace.get('section') or extract_section_from_name(name) or extract_section_from_id(element_id)
    page = trace.get('page', '')
    quote = trace.get('quote', '')
    responsible = trace.get('responsible', '')
    duration = trace.get('duration', '')
    system = trace.get('system', '')
    
    # Формируем documentation
    doc_parts = []
    
    # Заголовок с источником
    document = trace.get('document', 'Документ')
    if section:
        header = f"📄 {document}, п.{section}"
        if page:
            header += f", стр.{page}"
        doc_parts.append(header)
        doc_parts.append("")
    
    # Цитата или описание
    if quote:
        doc_parts.append(quote)
    elif name:
        # Убираем номер раздела из названия для описания
        clean_name = re.sub(r'^\d+(?:\.\d+)*\s*', '', name)
        if clean_name:
            doc_parts.append(clean_name)
    
    # Метаданные
    metadata = []
    if duration:
        metadata.append(f"⏱️ Длительность: {duration}")
    if system:
        metadata.append(f"💻 Система: {system}")
    if responsible:
        metadata.append(f"👤 Ответственный: {responsible}")
    
    if metadata:
        doc_parts.append("")
        doc_parts.extend(metadata)
    
    return "\n".join(doc_parts)

def add_documentation_to_bpmn(bpmn_content: str, trace_data: dict) -> str:
    """Добавляет documentation во все элементы BPMN."""
    
    # Паттерн для поиска элементов без documentation
    # Ищем: <bpmn:XXX id="..." name="...">
    #   <bpmn:incoming>...</bpmn:incoming>  (или outgoing, или ничего)
    # НЕ содержит <bpmn:documentation>
    
    element_types = [
        'manualTask', 'userTask', 'serviceTask', 'task',
        'subProcess', 'exclusiveGateway', 'parallelGateway', 'inclusiveGateway',
        'startEvent', 'endEvent'
    ]
    
    added_count = 0
    
    for elem_type in element_types:
        # Паттерн для элемента с id и name, без существующей documentation
        pattern = rf'(<bpmn:{elem_type}\s+id="([^"]+)"(?:\s+name="([^"]*)")?[^>]*>)\s*\n(\s*)(<bpmn:(?:incoming|outgoing|laneSet|lane))'
        
        def replace_func(match):
            nonlocal added_count
            opening_tag = match.group(1)
            element_id = match.group(2)
            name = match.group(3) or ''
            indent = match.group(4)
            next_tag = match.group(5)
            
            # Проверяем, что documentation ещё нет
            if '<bpmn:documentation>' in opening_tag:
                return match.group(0)
            
            # Создаем documentation
            doc_text = create_documentation(element_id, name, elem_type, trace_data)
            
            if doc_text.strip():
                added_count += 1
                # Формируем XML с documentation
                doc_xml = f"{indent}<bpmn:documentation>{doc_text}</bpmn:documentation>\n"
                return f"{opening_tag}\n{doc_xml}{indent}{next_tag}"
            
            return match.group(0)
        
        bpmn_content = re.sub(pattern, replace_func, bpmn_content)
    
    print(f"✅ Добавлено documentation: {added_count} элементов")
    return bpmn_content

def main():
    if len(sys.argv) < 2:
        print("Использование: python add_bpmn_documentation.py <bpmn_file> [traceability.json]")
        sys.exit(1)
    
    bpmn_path = Path(sys.argv[1])
    trace_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    
    if not bpmn_path.exists():
        print(f"❌ Файл не найден: {bpmn_path}")
        sys.exit(1)
    
    # Загружаем traceability если есть
    trace_data = {}
    if trace_path and trace_path.exists():
        with open(trace_path, 'r', encoding='utf-8') as f:
            trace_data = json.load(f)
        print(f"📎 Загружена трассировка: {len(trace_data.get('elements', {}))} элементов")
    
    # Читаем BPMN
    with open(bpmn_path, 'r', encoding='utf-8') as f:
        bpmn_content = f.read()
    
    # Считаем существующие documentation
    existing = bpmn_content.count('<bpmn:documentation>')
    print(f"📊 Существующие documentation: {existing}")
    
    # Добавляем documentation
    new_content = add_documentation_to_bpmn(bpmn_content, trace_data)
    
    # Создаем бэкап
    backup_path = bpmn_path.with_suffix('.bpmn.backup')
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(bpmn_content)
    print(f"💾 Бэкап создан: {backup_path}")
    
    # Сохраняем обновленный файл
    with open(bpmn_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    # Итоговая статистика
    final = new_content.count('<bpmn:documentation>')
    print(f"📊 Итого documentation: {final}")

if __name__ == '__main__':
    main()

