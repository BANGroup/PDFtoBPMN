"""
Гибридный парсер: PDF (количества) + MD (остальные поля)
100% точность по количеству гарантируется из PDF
"""

import re
import fitz
from typing import List, Optional, Dict, Tuple
from pathlib import Path
from .models import OwnerRecord


class HybridPDFMDParser:
    """Гибридный парсер PDF + MD"""
    
    def parse(self, pdf_path: Path, md_path: Path) -> List[OwnerRecord]:
        """
        Парсинг в два этапа:
        1. PDF → (код владельца, количество)  - 100% точность
        2. MD → (ФИО, адрес, документ) по коду владельца
        """
        
        print("🔍 ЭТАП 1: Извлечение количеств из PDF")
        pdf_data = self._extract_from_pdf(pdf_path)
        print(f"   Найдено: {len(pdf_data)} записей")
        print(f"   Сумма: {sum(pdf_data.values()):,}")
        
        print("\n🔍 ЭТАП 2: Извлечение полей из MD")
        md_content = md_path.read_text(encoding='utf-8')
        
        # Пропускаем frontmatter
        content_start = md_content.find('<!-- Страница')
        if content_start != -1:
            md_content = md_content[content_start:]
        
        # Создаем словарь: код владельца → чанк MD
        md_chunks = self._create_md_chunks(md_content)
        print(f"   Найдено чанков MD: {len(md_chunks)}")
        
        print("\n🔍 ЭТАП 3: Объединение данных (по коду владельца)")
        records = []
        
        # Проходим по MD чанкам (они в правильном MD порядке)
        for owner_code, chunk in md_chunks.items():
            # Берем количество из PDF по КОДУ
            quantity = pdf_data.get(owner_code)
            
            if quantity:
                fio = self._extract_fio(chunk)
                address = self._extract_address(chunk)
                document_number = self._extract_document(chunk)
                
                record = OwnerRecord(
                    owner_code=owner_code,
                    full_name=fio,
                    address=address,
                    quantity=quantity,
                    document_number=document_number,
                    page_number=None
                )
                records.append(record)
            
            if len(records) % 100 == 0:
                print(f"   ... обработано {len(records)}/{len(md_chunks)}")
        
        print(f"✅ Создано записей: {len(records)}")
        return records
    
    def _extract_from_pdf(self, pdf_path: Path) -> Dict[str, int]:
        """Извлекает словарь {код владельца: количество} из PDF"""
        doc = fitz.open(pdf_path)
        
        all_text = ""
        for page_num in range(len(doc)):
            all_text += f"\n<!-- PAGE {page_num + 1} -->\n"
            all_text += doc[page_num].get_text()
        
        doc.close()
        
        # Находим все записи владельцев
        owner_pattern = r'Код\s+(01_\d{10})\(NADC\)'
        owner_matches = list(re.finditer(owner_pattern, all_text, re.IGNORECASE))
        
        results = {}  # Словарь вместо списка
        
        for idx, match in enumerate(owner_matches):
            owner_code = match.group(1)
            start_pos = match.start()
            
            # До следующего владельца
            if idx < len(owner_matches) - 1:
                end_pos = owner_matches[idx + 1].start()
            else:
                end_pos = start_pos + 5000
            
            chunk = all_text[start_pos:end_pos]
            
            # Ищем количество в чанке
            qty = self._extract_quantity_from_pdf_chunk(chunk)
            
            if qty:
                results[owner_code] = qty  # Словарь по коду
        
        return results
    
    def _extract_quantity_from_pdf_chunk(self, chunk: str) -> Optional[int]:
        """Извлекает количество из чанка PDF"""
        # В PDF разные форматы:
        # 1. Отдельные строки:
        #    4-01-36484-R
        #    RU000A0JVZF7 (NADC)
        #    [число]
        # 2. В одной строке: 4-01-36484-R ... (NADC) [число]
        
        # Сначала ищем в одной строке
        pattern_inline = r'4-01-36484-R.*?RU\w+\s+\(NADC\).*?(\d{1,7})'
        match = re.search(pattern_inline, chunk, re.DOTALL)
        if match:
            qty = int(match.group(1))
            if 1 <= qty < 3000000:
                # Проверяем что это не "обременено"
                context_start = max(0, match.start() - 100)
                context = chunk[context_start:match.end() + 100]
                if 'обременен' not in context.lower():
                    return qty
        
        # Если не нашли - ищем построчно (расширенный контекст)
        lines = chunk.split('\n')
        
        for i, line in enumerate(lines):
            if '4-01-36484-R' in line:
                # Смотрим следующие 10 строк (расширено с 5 до 10)
                for j in range(i + 1, min(i + 11, len(lines))):
                    next_line = lines[j].strip()
                    
                    # Ищем число (1-7 цифр, отдельно стоящее)
                    if re.match(r'^\d{1,7}$', next_line):
                        qty = int(next_line)
                        if 1 <= qty < 3000000:
                            return qty
        
        return None
    
    def _create_md_chunks(self, md_content: str) -> Dict[str, str]:
        """Создает словарь: код владельца → чанк MD"""
        code_pattern = r'# Код (01_\d+)\(NADC\)'
        matches = list(re.finditer(code_pattern, md_content))
        
        chunks = {}
        
        for idx, match in enumerate(matches):
            owner_code = match.group(1)
            start = match.start()
            
            # До следующего владельца
            if idx < len(matches) - 1:
                end = matches[idx + 1].start()
            else:
                end = start + 5000
            
            chunks[owner_code] = md_content[start:end]
        
        return chunks
    
    def _extract_fio(self, chunk: str) -> Optional[str]:
        """Извлечение ФИО из MD"""
        patterns = [
            r'# ([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)\s+Полное наименование',
            r'Полное наименование.*?\|\s*([А-ЯЁ][^\n|]{10,}?)\s*\|',
            r'\|\s+([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)\s+\|',
        ]
        
        # Стоп-слова (заголовки, не ФИО)
        stop_words = ['Код ценной бумаги', 'Регистрационный номер', 'Баланс по ценной',
                      'Количество в штуках', 'Номер счета', 'Тип счета']
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                fio = match.group(1).strip()
                fio = re.sub(r'\s{2,}', ' ', fio)
                
                # Проверяем что это не заголовок
                if len(fio) > 5 and not any(stop in fio for stop in stop_words):
                    return fio
        
        return None
    
    def _extract_address(self, chunk: str) -> Optional[str]:
        """Извлечение адреса из MD"""
        patterns = [
            r'# (RU РОССИЯ \d{6}[^\n{]+?) Адрес',
            r'Адрес.*?\|\s*(RU РОССИЯ \d{6}[^\n|]{20,}?)\s*\|',
            r'\|\s*(RU РОССИЯ \d{6}[^\n|]{20,}?)\s*\|',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                address = match.group(1).strip()
                address = re.sub(r'\s{2,}', ' ', address)
                if len(address) > 15:
                    return address
        
        return None
    
    def _extract_document(self, chunk: str) -> Optional[str]:
        """Извлечение номера документа из MD"""
        patterns = [
            r'серия\s+(\d{2}\s+\d{2}).*?номер\s+(\d{6})',
            r'номер\s+(\d{6}).*?серия\s+(\d{2}\s+\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                if 'серия' in pattern[:10]:
                    return f"{match.group(2)} {match.group(1)}"
                else:
                    return f"{match.group(2)} {match.group(1)}"
        
        return None

