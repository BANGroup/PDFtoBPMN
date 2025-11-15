"""
Парсер для прямого извлечения данных из табличных PDF
Для документов типа "Выпуск 4-01 на 29.07.19" с четкой табличной структурой
"""

import re
import fitz  # PyMuPDF
from typing import List, Optional, Tuple
from pathlib import Path
from .models import OwnerRecord


class PDFTableParser:
    """Прямое извлечение из табличных PDF"""
    
    def __init__(self):
        # Паттерн для маркера начала записи владельца
        self.pattern_owner = r'Код\s+(01_\d{10})\(NADC\)'
        
        # Паттерн для таблицы с количеством
        self.pattern_qty_table = r'4-01-36484-R.*?RU\w+\s+\(NADC\).*?(\d{1,7})'
        
    def parse_pdf(self, pdf_path: Path) -> List[OwnerRecord]:
        """Парсинг табличного PDF"""
        print(f"🔍 Открываем PDF: {pdf_path.name}")
        doc = fitz.open(pdf_path)
        
        all_text = []
        print(f"📄 Извлечение текста из {len(doc)} страниц...")
        
        # Извлекаем весь текст
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            all_text.append(text)
            
            if (page_num + 1) % 50 == 0:
                print(f"   ... страница {page_num + 1}/{len(doc)}")
        
        doc.close()
        
        # Объединяем весь текст
        full_text = '\n'.join(all_text)
        
        # Ищем все записи владельцев
        print(f"\n🔍 Поиск записей владельцев...")
        owner_matches = list(re.finditer(self.pattern_owner, full_text, re.IGNORECASE))
        print(f"   Найдено маркеров: {len(owner_matches)}")
        
        records = []
        
        for idx, match in enumerate(owner_matches):
            owner_code = match.group(1)
            
            # Определяем границы чанка для этой записи
            start_pos = match.start()
            
            # До следующего владельца или +5000 символов
            if idx < len(owner_matches) - 1:
                end_pos = owner_matches[idx + 1].start()
            else:
                end_pos = start_pos + 5000
            
            chunk = full_text[start_pos:end_pos]
            
            # Извлекаем данные
            quantity = self._extract_quantity(chunk)
            
            # Только если нашли количество - создаем запись
            if quantity:
                full_name = self._extract_fio(chunk)
                address = self._extract_address(chunk)
                document_number = self._extract_document(chunk)
                
                record = OwnerRecord(
                    owner_code=owner_code,
                    full_name=full_name,
                    address=address,
                    quantity=quantity,
                    document_number=document_number,
                    page_number=None
                )
                records.append(record)
            
            if (idx + 1) % 100 == 0:
                print(f"   ... обработано {idx + 1}/{len(owner_matches)}")
        
        print(f"\n✅ Извлечено записей: {len(records)}")
        return records
    
    def _extract_quantity(self, chunk: str) -> Optional[int]:
        """Извлечение количества облигаций"""
        # Ищем строку с регистрационным номером и количеством
        # Формат: 4-01-36484-R RU000A0JVZF7 (NADC) 3924
        
        lines = chunk.split('\n')
        
        for line in lines:
            if '4-01-36484-R' in line and '(NADC)' in line:
                # Пропускаем строки с "обременен"
                if 'обременен' in line.lower():
                    continue
                
                # Ищем число в конце строки
                match = re.search(r'4-01-36484-R.*?RU\w+\s+\(NADC\).*?(\d{1,7})', line)
                if match:
                    qty = int(match.group(1))
                    if 1 <= qty < 3000000:
                        return qty
        
        return None
    
    def _extract_fio(self, chunk: str) -> Optional[str]:
        """Извлечение ФИО / Наименования"""
        patterns = [
            r'Полное наименование/\s*Ф\.?И\.?О\.?\s+\(юр\./физ\. лица\)\s+([^\n]+)',
            r'Наименование[:\s]+([^\n]{10,})',
            r'Ф\.?И\.?О\.?[:\s]+([^\n]{10,})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                fio = match.group(1).strip()
                # Очистка от лишнего
                fio = re.sub(r'\s{2,}', ' ', fio)
                if len(fio) > 3:
                    return fio
        
        return None
    
    def _extract_address(self, chunk: str) -> Optional[str]:
        """Извлечение адреса"""
        patterns = [
            r'Адрес регистрации \(полный\)[:\s]*([^\n]+(?:\n[^\n]+)?)',
            r'Адрес[:\s]+RU\s+РОССИЯ\s+(\d{6}[^\n]+)',
            r'RU\s+РОССИЯ\s+(\d{6}[^\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                address = match.group(1).strip()
                # Очистка
                address = re.sub(r'\s{2,}', ' ', address)
                if len(address) > 10:
                    return f"RU РОССИЯ {address}" if not address.startswith('RU') else address
        
        return None
    
    def _extract_document(self, chunk: str) -> Optional[str]:
        """Извлечение номера документа"""
        # Паттерн для паспорта
        patterns = [
            r'Паспорт.*?номер\s+(\d{6})\s+серия\s+(\d{2}\s+\d{2})',
            r'серия\s+(\d{2}\s+\d{2}).*?номер\s+(\d{6})',
            r'Документ[:\s]+([^\n]{5,30})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    # Паспорт: серия + номер
                    if 'номер' in pattern:
                        doc_num = f"{match.group(2)} {match.group(1)}"
                    else:
                        doc_num = f"{match.group(1)} {match.group(2)}"
                else:
                    doc_num = match.group(1).strip()
                
                if doc_num:
                    return doc_num
        
        return None


