"""
Извлечение данных из PDF документов СМК
- Название документа (с титульной страницы)
- Дата утверждения
- Ссылки на другие документы
"""

import re
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class DocumentMetadata:
    """Метаданные документа из PDF"""
    title: Optional[str] = None
    approval_date: Optional[str] = None
    effective_date: Optional[str] = None
    version: Optional[str] = None
    pages: int = 0
    references: List[str] = field(default_factory=list)  # Коды документов
    text_preview: str = ""  # Первые N символов


# Паттерны для извлечения ссылок на документы
REFERENCE_PATTERNS = [
    # ДП-М1.020-06, РД-Б7.004-05
    r'(?:ДП|РД|СТ|РГ|КД)-[МБВMВBмбв]\d+\.\d+-\d+',
    # КД-ДП-Б1.002-04, КД-РГ-039-05
    r'КД-(?:ДП|РД|РГ|СТ)-[МБВMВBмбв]\d+\.\d+-\d+',
    r'КД-(?:РГ|СТ)-\d+-\d+',
    # РК01-2017-07
    r'РК\d+-\d+-\d+',
    # ИОТ-001-02
    r'ИОТ-\d+-\d+',
    # СТ-166-01
    r'СТ-\d+-\d+',
    # TPM/ТРМ-UTA-UTG-002-03
    r'(?:TPM|ТРМ)-[A-ZА-Я]+-[A-ZА-Я]+-\d+-\d+',
]

# Паттерны для даты
DATE_PATTERNS = [
    # "01.01.2024", "01/01/2024"
    r'(\d{2}[./]\d{2}[./]\d{4})',
    # "01 января 2024", "01 янв 2024"
    r'(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|дек)\.?\s+\d{4})',
    # "2024-01-01"
    r'(\d{4}-\d{2}-\d{2})',
]

# Ключевые слова для поиска даты утверждения
APPROVAL_KEYWORDS = [
    'утвержд', 'введен в действие', 'вступает в силу', 'дата введения',
    'approved', 'effective date', 'дата утверждения'
]


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 10) -> Tuple[str, int]:
    """
    Извлечь текст из PDF (первые N страниц)
    
    Returns:
        (text, total_pages)
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        text_parts = []
        pages_to_read = min(max_pages, total_pages)
        
        for page_num in range(pages_to_read):
            page = doc[page_num]
            text = page.get_text()
            text_parts.append(text)
        
        doc.close()
        return "\n\n".join(text_parts), total_pages
        
    except Exception as e:
        print(f"⚠️ Ошибка чтения {pdf_path}: {e}")
        return "", 0


def extract_title(text: str, filename: str) -> Optional[str]:
    """Извлечь название документа из текста"""
    
    # Паттерны для поиска названия
    title_patterns = [
        # После кода документа часто идёт название
        r'(?:ДП|РД|СТ|РГ|КД|РК|ИОТ)[^\n]+\n+([А-ЯA-Z][^\n]{10,100})',
        # "НАИМЕНОВАНИЕ" или заголовок капсом
        r'\n([А-ЯA-Z][А-ЯA-Z\s]{20,100})\n',
        # После "Название:" или "Title:"
        r'(?:название|наименование|title)[:\s]+([^\n]{10,100})',
    ]
    
    for pattern in title_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # Очистка
            title = re.sub(r'\s+', ' ', title)
            if len(title) > 10 and len(title) < 200:
                return title
    
    return None


def extract_dates(text: str) -> Dict[str, Optional[str]]:
    """Извлечь даты из текста"""
    result = {
        'approval_date': None,
        'effective_date': None
    }
    
    text_lower = text.lower()
    
    # Ищем даты рядом с ключевыми словами
    for keyword in APPROVAL_KEYWORDS:
        if keyword in text_lower:
            # Найти позицию ключевого слова
            pos = text_lower.find(keyword)
            # Взять контекст вокруг (±200 символов)
            context = text[max(0, pos-50):pos+200]
            
            # Искать дату в контексте
            for pattern in DATE_PATTERNS:
                match = re.search(pattern, context, re.IGNORECASE)
                if match:
                    result['approval_date'] = match.group(1)
                    break
            
            if result['approval_date']:
                break
    
    # Если не нашли по ключевым словам, берём первую дату на первой странице
    if not result['approval_date']:
        first_page = text[:2000]  # Примерно первая страница
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, first_page, re.IGNORECASE)
            if match:
                result['effective_date'] = match.group(1)
                break
    
    return result


def extract_references(text: str, self_code: str = "") -> List[str]:
    """Извлечь ссылки на другие документы"""
    references = set()
    
    for pattern in REFERENCE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Нормализуем код
            code = match.upper().replace('М', 'М').replace('Б', 'Б').replace('В', 'В')
            # Не добавляем ссылку на себя
            if code != self_code.upper():
                references.add(code)
    
    return sorted(list(references))


def extract_document_metadata(
    pdf_path: Path, 
    doc_code: str = "",
    docx_path: Path = None,
    catalog_entry = None
) -> DocumentMetadata:
    """
    Извлечь все метаданные из PDF документа
    
    Приоритет источников:
    1. DOCX файл (если есть) - для названия
    2. XLSX каталог (если есть) - для даты и типа
    3. PDF файл - для ссылок и fallback
    
    Args:
        pdf_path: Путь к PDF файлу
        doc_code: Код документа (для исключения самоссылок)
        docx_path: Путь к соответствующему DOCX (опционально)
        catalog_entry: Запись из xlsx каталога (опционально)
        
    Returns:
        DocumentMetadata
    """
    metadata = DocumentMetadata()
    
    # 1. Пробуем извлечь из DOCX (лучший источник для названия)
    if docx_path and docx_path.exists():
        try:
            from .docx_extractor import extract_from_docx
            docx_meta = extract_from_docx(docx_path)
            if docx_meta.title:
                metadata.title = docx_meta.title
            if docx_meta.effective_date:
                metadata.effective_date = docx_meta.effective_date
        except Exception:
            pass
    
    # 2. Используем данные из каталога xlsx
    if catalog_entry:
        if catalog_entry.reg_date:
            if hasattr(catalog_entry.reg_date, 'strftime'):
                metadata.approval_date = catalog_entry.reg_date.strftime('%d.%m.%Y')
            else:
                metadata.approval_date = str(catalog_entry.reg_date)
    
    # 3. Извлекаем текст из PDF
    text, total_pages = extract_text_from_pdf(pdf_path, max_pages=5)
    metadata.pages = total_pages
    metadata.text_preview = text[:500] if text else ""
    
    # 4. Если название не найдено в DOCX, пробуем из PDF
    if not metadata.title and text:
        metadata.title = extract_title(text, pdf_path.name)
    
    # 5. Если дата не найдена в каталоге, пробуем из PDF
    if not metadata.approval_date and text:
        dates = extract_dates(text)
        metadata.approval_date = dates['approval_date']
        if not metadata.effective_date:
            metadata.effective_date = dates['effective_date']
    
    # 6. Извлекаем ссылки из PDF (это PDF-специфичная задача)
    if text:
        # Для ссылок читаем больше страниц
        full_text, _ = extract_text_from_pdf(pdf_path, max_pages=50)
        metadata.references = extract_references(full_text, doc_code)
    
    return metadata


def batch_extract_metadata(pdf_paths: List[Path], progress_callback=None) -> Dict[str, DocumentMetadata]:
    """
    Пакетное извлечение метаданных из списка PDF
    
    Args:
        pdf_paths: Список путей к PDF файлам
        progress_callback: Функция обратного вызова (current, total, filename)
        
    Returns:
        Dict[doc_code -> DocumentMetadata]
    """
    results = {}
    total = len(pdf_paths)
    
    for i, pdf_path in enumerate(pdf_paths):
        if progress_callback:
            progress_callback(i + 1, total, pdf_path.name)
        
        # Извлекаем код из имени файла
        from .parser import parse_document_code
        doc = parse_document_code(pdf_path.parent.name if pdf_path.parent.name != 'pdf' else pdf_path.name)
        doc_code = doc.code if doc else pdf_path.stem
        
        metadata = extract_document_metadata(pdf_path, doc_code)
        results[doc_code] = metadata
    
    return results


if __name__ == "__main__":
    # Тест
    import sys
    
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1])
    else:
        # Тестовый файл
        pdf_path = Path("/home/budnik_an/Obligations/input2/BND/pdf/РД-М1.014-16 ^C2C689454B27066945258C91001D57CE")
        pdf_files = list(pdf_path.glob("*.pdf"))
        if pdf_files:
            pdf_path = pdf_files[0]
    
    if pdf_path.exists():
        print(f"📄 Анализ: {pdf_path.name}")
        print("=" * 60)
        
        metadata = extract_document_metadata(pdf_path)
        
        print(f"📖 Название: {metadata.title or 'Не найдено'}")
        print(f"📅 Дата утверждения: {metadata.approval_date or 'Не найдена'}")
        print(f"📅 Дата введения: {metadata.effective_date or 'Не найдена'}")
        print(f"📑 Страниц: {metadata.pages}")
        print(f"🔗 Ссылки ({len(metadata.references)}):")
        for ref in metadata.references[:10]:
            print(f"   → {ref}")
        if len(metadata.references) > 10:
            print(f"   ... и ещё {len(metadata.references) - 10}")
    else:
        print(f"❌ Файл не найден: {pdf_path}")
