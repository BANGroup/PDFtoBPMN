"""
Парсер кодов документов СМК
Извлекает код процесса, тип документа, версию из имени файла
"""

import re
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

from .models import Document, DocumentType, ProcessGroup


# Паттерны для разбора кодов документов
DOCUMENT_PATTERNS = [
    # КД-ДП-Б1.002-04 - Корпоративный документ (документация процесса)
    r'^(КД)-(ДП|РД|РГ|СТ)-([МБВMВB][0-9]+)\.(\d+)-(\d+)',
    
    # ДП-М1.020-06 - Документация процесса
    r'^(ДП|РД|СТ|РГ)-([МБВMВB][0-9]+)\.(\d+)-(\d+)',
    
    # РК01-2017-07 - Руководство по качеству
    r'^(РК)(\d+)-(\d+)-(\d+)',
    
    # ИОТ-001-02 - Инструкция по охране труда
    r'^(ИОТ)-(\d+)-(\d+)',
    
    # TPM-UTA-UTG-002-03 - Technical Procedures Manual
    r'^(TPM)-([A-Z]+)-([A-Z]+)-(\d+)-(\d+)',
    
    # СТ-166-01 - Стандарт (без кода процесса)
    r'^(СТ)-(\d+)-(\d+)',
]


# Справочник процессов СМК (из РК01-2017-07)
PROCESS_REGISTRY = {
    # Группа М - Процессы менеджмента
    'М1': {'name': 'Анализ и оценка', 'group': ProcessGroup.M},
    'М2': {'name': 'Планирование качества', 'group': ProcessGroup.M},
    'M1': {'name': 'Анализ и оценка', 'group': ProcessGroup.M},
    'M2': {'name': 'Планирование качества', 'group': ProcessGroup.M},
    
    # Группа Б - Процессы жизненного цикла
    'Б1': {'name': 'Организация коммерческих воздушных перевозок', 'group': ProcessGroup.B},
    'Б5': {'name': 'Взаимодействие с потребителями', 'group': ProcessGroup.B},
    'Б6': {'name': 'Планирование и бюджетирование', 'group': ProcessGroup.B},
    'Б7': {'name': 'Управление закупками', 'group': ProcessGroup.B},
    'Б8': {'name': 'Управление полетами', 'group': ProcessGroup.B},
    'B1': {'name': 'Организация коммерческих воздушных перевозок', 'group': ProcessGroup.B},
    'B5': {'name': 'Взаимодействие с потребителями', 'group': ProcessGroup.B},
    'B6': {'name': 'Планирование и бюджетирование', 'group': ProcessGroup.B},
    'B7': {'name': 'Управление закупками', 'group': ProcessGroup.B},
    'B8': {'name': 'Управление полетами', 'group': ProcessGroup.B},
    
    # Группа В - Процессы обеспечения
    'В1': {'name': 'Управление авиационной безопасностью', 'group': ProcessGroup.V},
    'В2': {'name': 'Управление безопасностью полетов', 'group': ProcessGroup.V},
    'В4': {'name': 'Менеджмент персонала', 'group': ProcessGroup.V},
    'В5': {'name': 'Управление инфраструктурой', 'group': ProcessGroup.V},
    'В6': {'name': 'Поддержание летной годности, организация ТО ВС', 'group': ProcessGroup.V},
    'В7': {'name': 'Управление охраной труда', 'group': ProcessGroup.V},
    'В8': {'name': 'Экологический менеджмент', 'group': ProcessGroup.V},
    'V1': {'name': 'Управление авиационной безопасностью', 'group': ProcessGroup.V},
    'V2': {'name': 'Управление безопасностью полетов', 'group': ProcessGroup.V},
    'V4': {'name': 'Менеджмент персонала', 'group': ProcessGroup.V},
    'V5': {'name': 'Управление инфраструктурой', 'group': ProcessGroup.V},
    'V6': {'name': 'Поддержание летной годности, организация ТО ВС', 'group': ProcessGroup.V},
    'V7': {'name': 'Управление охраной труда', 'group': ProcessGroup.V},
    'V8': {'name': 'Экологический менеджмент', 'group': ProcessGroup.V},
}


# Маппинг типов документов
DOC_TYPE_MAP = {
    'ДП': DocumentType.DP,
    'РД': DocumentType.RD,
    'СТ': DocumentType.ST,
    'КД': DocumentType.KD,
    'РГ': DocumentType.RG,
    'РК': DocumentType.RK,
    'ИОТ': DocumentType.IOT,
    'TPM': DocumentType.TPM,
}


def normalize_process_code(code: str) -> str:
    """Нормализация кода процесса (латиница → кириллица)"""
    mapping = {
        'M': 'М',
        'B': 'Б',
        'V': 'В',
    }
    
    if code and len(code) >= 1:
        first_char = code[0].upper()
        if first_char in mapping:
            return mapping[first_char] + code[1:]
    return code


def normalize_document_code(code: str) -> str:
    """Нормализация кода документа для сопоставления"""
    if not code:
        return ""
    mapping = str.maketrans({
        'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н',
        'K': 'К', 'M': 'М', 'O': 'О', 'P': 'Р', 'T': 'Т',
        'X': 'Х', 'Y': 'У',
    })
    normalized = code.strip().upper().translate(mapping)
    return normalized


def parse_document_code(filename: str) -> Optional[Document]:
    """
    Разобрать код документа из имени файла/папки
    
    Args:
        filename: Имя файла или папки (например "ДП-М1.020-06 ^692386...")
        
    Returns:
        Document или None если не удалось распарсить
    """
    # Убираем хэш и расширение
    clean_name = filename.split('^')[0].strip()
    clean_name = clean_name.replace('.pdf', '').replace('.PDF', '').strip()
    
    # Убираем суффиксы вроде "(Эталон № 13 для печати)"
    clean_name = re.sub(r'\s*\([^)]+\)\s*$', '', clean_name).strip()
    
    # Пробуем разные паттерны
    
    # 1. КД-ДП-Б1.002-04 (корпоративный документ с вложенным типом)
    match = re.match(r'^(КД)-(ДП|РД|РГ|СТ)-([МБВMВBмбв]\d+)\.(\d+)-(\d+)', clean_name, re.IGNORECASE)
    if match:
        kd, inner_type, process_group, process_num, version = match.groups()
        process_code = normalize_process_code(process_group.upper()) + '.' + process_num
        return Document(
            code=clean_name,
            doc_type=DOC_TYPE_MAP.get(inner_type.upper(), DocumentType.KD),
            process_code=process_code,
            version=version,
        )
    
    # 2. ДП-М1.020-06 (стандартный формат)
    match = re.match(r'^(ДП|РД|СТ|РГ)-([МБВMВBмбв]\d+)\.(\d+)-(\d+)', clean_name, re.IGNORECASE)
    if match:
        doc_type, process_group, process_num, version = match.groups()
        process_code = normalize_process_code(process_group.upper()) + '.' + process_num
        return Document(
            code=clean_name,
            doc_type=DOC_TYPE_MAP.get(doc_type.upper(), DocumentType.UNKNOWN),
            process_code=process_code,
            version=version,
        )
    
    # 3. РК01-2017-07 (руководство по качеству)
    match = re.match(r'^(РК)(\d+)-(\d+)-(\d+)', clean_name, re.IGNORECASE)
    if match:
        rk, num, year, version = match.groups()
        return Document(
            code=clean_name,
            doc_type=DocumentType.RK,
            process_code='',  # РК - корневой документ
            version=version,
        )
    
    # 4. ИОТ-001-02 (инструкция по охране труда)
    match = re.match(r'^(ИОТ)-(\d+)-(\d+)', clean_name, re.IGNORECASE)
    if match:
        iot, num, version = match.groups()
        return Document(
            code=clean_name,
            doc_type=DocumentType.IOT,
            process_code='В7',  # ИОТ относятся к процессу В7 (охрана труда)
            version=version,
        )
    
    # 5. СТ-166-01 (стандарт без кода процесса)
    match = re.match(r'^(СТ)-(\d+)-(\d+)', clean_name, re.IGNORECASE)
    if match:
        st, num, version = match.groups()
        return Document(
            code=clean_name,
            doc_type=DocumentType.ST,
            process_code='',
            version=version,
        )
    
    # 6. TPM-UTA-UTG-002-03 (Technical Procedures Manual)
    match = re.match(r'^(TPM)-([A-Z]+)-([A-Z]+)-(\d+)-(\d+)', clean_name, re.IGNORECASE)
    if match:
        tpm, org1, org2, num, version = match.groups()
        return Document(
            code=clean_name,
            doc_type=DocumentType.TPM,
            process_code='',
            version=version,
        )
    
    # 7. КД-РГ-039-05 (корпоративный регламент без процесса)
    match = re.match(r'^(КД)-(РГ)-(\d+)-(\d+)', clean_name, re.IGNORECASE)
    if match:
        kd, rg, num, version = match.groups()
        return Document(
            code=clean_name,
            doc_type=DocumentType.RG,
            process_code='',
            version=version,
        )
    
    return None


def get_process_info(process_id: str) -> Optional[dict]:
    """
    Получить информацию о процессе по его коду
    
    Args:
        process_id: Код процесса (М1, Б7, В4)
        
    Returns:
        Dict с name и group или None
    """
    # Нормализуем код
    normalized = normalize_process_code(process_id)
    return PROCESS_REGISTRY.get(normalized) or PROCESS_REGISTRY.get(process_id)


def scan_documents_folder(folder_path: Path) -> List[Document]:
    """
    Сканировать папку с документами и извлечь информацию
    
    Args:
        folder_path: Путь к папке с документами
        
    Returns:
        Список Document
    """
    documents = []
    
    if not folder_path.exists():
        return documents
    
    for item in folder_path.iterdir():
        if item.is_dir():
            # Папка с документом (формат: "ДП-М1.020-06 ^692386...")
            doc = parse_document_code(item.name)
            if doc:
                # Ищем PDF внутри папки
                pdf_files = list(item.glob('*.pdf')) + list(item.glob('*.PDF'))
                if pdf_files:
                    doc.file_path = str(pdf_files[0])
                documents.append(doc)
        elif item.suffix.lower() == '.pdf':
            # PDF файл напрямую
            doc = parse_document_code(item.name)
            if doc:
                doc.file_path = str(item)
                documents.append(doc)
    
    return documents


if __name__ == "__main__":
    # Тест парсера
    test_names = [
        "ДП-М1.020-06 ^692386276D6DDE30452584F50038090F",
        "КД-ДП-Б1.002-04 ^7B1A2943B36B17A346257BDA003FB1BA",
        "РК01-2017-07 (Эталон № 13 для печати).pdf",
        "ИОТ-001-02 ^0E02046716E6B8434525880F004081C1",
        "СТ-166-01 ^4B692AD146B4319845258C65003C450D",
        "TPM-UTA-UTG-002-03 ^CDA7C0F2C002F20A4525896300299CDE",
        "КД-РГ-039-05 ^98922A5C1D13C8AF45258B0400287F5F",
        "РД-М1.014-16",
        "РД-Б7.004-05",
    ]
    
    print("Тест парсера документов:")
    print("=" * 80)
    
    for name in test_names:
        doc = parse_document_code(name)
        if doc:
            print(f"\n{name}")
            print(f"  → Код: {doc.code}")
            print(f"  → Тип: {doc.doc_type.value}")
            print(f"  → Процесс: {doc.process_code}")
            print(f"  → Версия: {doc.version}")
            print(f"  → Группа: {doc.process_group.value}")
            
            process_info = get_process_info(doc.process_id)
            if process_info:
                print(f"  → Название процесса: {process_info['name']}")
        else:
            print(f"\n{name}")
            print(f"  → НЕ РАСПОЗНАН")
