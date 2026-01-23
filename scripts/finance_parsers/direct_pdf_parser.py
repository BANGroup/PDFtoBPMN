"""
Парсер для прямого извлечения данных из PDF (без MD слоя).
Цель: 100% точность по количеству облигаций.
"""

import re
import fitz  # PyMuPDF
from typing import List, Optional, Tuple
from pathlib import Path
from .models import OwnerRecord


class DirectPDFParser:
    """Прямое извлечение из PDF текста"""
    
    def __init__(self):
        self.pattern_owner_code = r'# Код\s+(01_\d+)\(NADC\)'
        self.pattern_quantity = r'4-01-36484-R.*?(\d+)(?:\s*\|)?'
        
    def parse_pdf(self, pdf_path: Path) -> List[OwnerRecord]:
        """Основной метод парсинга PDF"""
        doc = fitz.open(pdf_path)
        
        all_records = []
        
        # Проход по каждой странице
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Извлекаем ВЕСЬ текст страницы
            page_text = page.get_text()
            
            # Ищем все записи владельцев на странице
            records = self._extract_records_from_page(page_text, page_num + 1)
            all_records.extend(records)
            
            if (page_num + 1) % 100 == 0:
                print(f"   ... обработано страниц {page_num + 1}/{len(doc)}")
        
        doc.close()
        
        print(f"✅ Извлечено записей: {len(all_records)}")
        return all_records
    
    def _extract_records_from_page(self, page_text: str, page_num: int) -> List[OwnerRecord]:
        """Извлечение всех записей с одной страницы"""
        records = []
        
        # Ищем все маркеры владельцев
        for match in re.finditer(self.pattern_owner_code, page_text):
            owner_code = match.group(1)
            
            # Извлекаем чанк текста ПОСЛЕ маркера (для количества)
            start_pos = match.end()
            # Берем до следующего маркера или до конца
            next_match = re.search(self.pattern_owner_code, page_text[start_pos:])
            if next_match:
                end_pos = start_pos + next_match.start()
            else:
                end_pos = len(page_text)
            
            chunk = page_text[start_pos:end_pos]
            
            # Извлекаем поля
            quantity = self._extract_quantity(chunk)
            full_name = self._extract_fio(chunk)
            address = self._extract_address(chunk)
            document_number = self._extract_document_number(chunk)
            
            # Создаем запись только если есть ключевые поля
            if quantity:
                record = OwnerRecord(
                    owner_code=owner_code,
                    full_name=full_name,
                    address=address,
                    quantity=quantity,
                    document_number=document_number,
                    page_number=page_num
                )
                records.append(record)
        
        return records
    
    def _extract_quantity(self, chunk: str) -> Optional[int]:
        """Извлечение количества облигаций"""
        # Ищем строки с регистрационным номером
        lines = chunk.split('\n')
        
        for line in lines:
            if '4-01-36484-R' in line:
                # Ищем число после номера
                match = re.search(r'4-01-36484-R.*?(\d+)', line)
                if match:
                    qty = int(match.group(1))
                    if 1 <= qty < 3000000:
                        return qty
        
        return None
    
    def _extract_fio(self, chunk: str) -> Optional[str]:
        """Извлечение ФИО"""
        # Ищем строку с ключевыми словами
        patterns = [
            r'Наименование:\s*([^\n]+)',
            r'Ф\.?И\.?О\.?:\s*([^\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                fio = match.group(1).strip()
                if fio and len(fio) > 3:
                    return fio
        
        return None
    
    def _extract_address(self, chunk: str) -> Optional[str]:
        """Извлечение адреса"""
        # Ищем строки с адресом
        patterns = [
            r'Адрес регистрации \(полный\):\s*([^\n]+(?:\n[^\n]+)*?)(?=\n[A-Z]|$)',
            r'RU\s+РОССИЯ\s+\d{6}\s+([^\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE | re.MULTILINE)
            if match:
                address = match.group(1).strip()
                if address and len(address) > 10:
                    return address
        
        return None
    
    def _extract_document_number(self, chunk: str) -> Optional[str]:
        """Извлечение номера документа"""
        patterns = [
            r'Документ:\s*([^\n]+)',
            r'паспорт.*?(\d{2}\s+\d{2}\s+\d{6})',
            r'№\s*(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                doc_num = match.group(1).strip()
                if doc_num:
                    return doc_num
        
        return None


