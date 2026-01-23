"""
Финальный парсер с привязкой 1:1 по порядку появления
"""

import re
from typing import List, Optional, Tuple
from pathlib import Path
from .models import OwnerRecord


class MDParserFinal:
    """Парсер с сортировкой и привязкой 1:1"""
    
    def parse_md_content(self, content: str) -> List[OwnerRecord]:
        """Парсинг с привязкой таблиц по порядку"""
        
        # Пропускаем frontmatter
        content_start = content.find('<!-- Страница')
        if content_start != -1:
            content = content[content_start:]
        
        print("🔍 ПРОХОД 1: Извлечение владельцев и таблиц")
        
        # Извлекаем владельцев (позиция, код)
        code_pattern = r'# Код (01_\d+)\(NADC\)'
        owners = [(m.start(), m.group(1)) for m in re.finditer(code_pattern, content)]
        print(f"   Владельцев: {len(owners)}")
        
        # Извлекаем таблицы (позиция, количество)
        tables = self._extract_all_tables(content)
        print(f"   Таблиц: {len(tables)}")
        print(f"   Сумма таблиц: {sum(q for _, q in tables):,}")
        
        print("\n🔍 ПРОХОД 2: Привязка по БЛИЖАЙШЕЙ таблице ПОСЛЕ владельца")
        
        records = []
        
        for idx, (owner_pos, owner_code) in enumerate(owners):
            # Ищем ПЕРВУЮ таблицу ПОСЛЕ этого владельца
            closest_table = None
            min_distance = float('inf')
            
            for table_pos, table_qty in tables:
                if table_pos > owner_pos:  # ТОЛЬКО ПОСЛЕ
                    distance = table_pos - owner_pos
                    if distance < min_distance:
                        min_distance = distance
                        closest_table = table_qty
                        if distance < 500:  # Оптимизация: если очень близко - берем
                            break
            
            if closest_table:
                # Определяем границы чанка для извлечения остальных полей
                if idx < len(owners) - 1:
                    chunk_end = owners[idx + 1][0]
                else:
                    chunk_end = owner_pos + 5000
                
                chunk = content[owner_pos:chunk_end]
                
                # Извлекаем остальные поля
                fio = self._extract_fio(chunk)
                address = self._extract_address(chunk)
                document_number = self._extract_document(chunk)
                
                record = OwnerRecord(
                    owner_code=owner_code,
                    full_name=fio,
                    address=address,
                    quantity=closest_table,
                    document_number=document_number,
                    page_number=None
                )
                records.append(record)
            
            if (idx + 1) % 100 == 0:
                print(f"   ... обработано {idx + 1}/{len(owners)}")
        
        print(f"✅ Извлечено записей: {len(records)}")
        return records
    
    def _extract_all_tables(self, content: str) -> List[Tuple[int, int]]:
        """Извлекает ВСЕ таблицы (позиция, количество)"""
        pattern_3col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*(\d+)\s*\|'
        pattern_4col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*\|\s*(\d+)\s*\|'
        
        tables = []
        
        for line_match in re.finditer(r'([^\n]*)', content):
            line = line_match.group(0)
            line_stripped = line.strip()
            
            if line_stripped.startswith('|') and '4-01-36484-R' in line_stripped:
                # Пропускаем обремененные
                if 'обременен' in line_stripped.lower():
                    continue
                
                if line_stripped.count('|') >= 3:
                    match = re.search(pattern_3col, line) or re.search(pattern_4col, line)
                    if match:
                        qty = int(match.group(1))
                        if 1 <= qty < 3000000:
                            pos = line_match.start()
                            tables.append((pos, qty))
        
        # Сортируем по позиции
        tables.sort(key=lambda x: x[0])
        return tables
    
    def _extract_fio(self, chunk: str) -> Optional[str]:
        """Извлечение ФИО"""
        patterns = [
            r'# ([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)\s+Полное наименование',
            r'Полное наименование.*?\|\s*([А-ЯЁ][^\n|]{10,}?)\s*\|',
            r'\|\s+([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)\s+\|',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                fio = match.group(1).strip()
                # Очистка
                fio = re.sub(r'\s{2,}', ' ', fio)
                if len(fio) > 5:
                    return fio
        
        return None
    
    def _extract_address(self, chunk: str) -> Optional[str]:
        """Извлечение адреса"""
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
        """Извлечение номера документа"""
        patterns = [
            r'серия\s+(\d{2}\s+\d{2}).*?номер\s+(\d{6})',
            r'номер\s+(\d{6}).*?серия\s+(\d{2}\s+\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                # Формат: серия номер
                if 'серия' in pattern[:10]:
                    doc_num = f"{match.group(2)} {match.group(1)}"
                else:
                    doc_num = f"{match.group(2)} {match.group(1)}"
                return doc_num
        
        return None


