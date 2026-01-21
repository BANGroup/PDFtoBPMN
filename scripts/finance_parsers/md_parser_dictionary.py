"""
Парсер с двухпроходным алгоритмом:
1. Извлечение всех таблиц в словарь
2. Привязка к владельцам по близости
"""

import re
from typing import List, Optional, Dict
from pathlib import Path
from .models import OwnerRecord


class MDParserDictionary:
    """Парсер с предварительным созданием словаря таблиц"""
    
    def parse_md_content(self, content: str) -> List[OwnerRecord]:
        """Парсинг в два прохода"""
        
        # Пропускаем frontmatter
        content_start = content.find('<!-- Страница')
        if content_start != -1:
            content = content[content_start:]
        
        print("🔍 ПРОХОД 1: Извлечение всех таблиц с количествами")
        
        # Извлекаем ВСЕ таблицы (позиция → количество)
        tables = self._extract_all_tables(content)
        print(f"   Найдено таблиц: {len(tables)}")
        print(f"   Сумма: {sum(tables.values()):,}")
        
        print("\n🔍 ПРОХОД 2: Привязка таблиц к владельцам")
        
        # Находим всех владельцев
        code_pattern = r'# Код (01_\d+)\(NADC\)'
        code_matches = list(re.finditer(code_pattern, content))
        print(f"   Найдено владельцев: {len(code_matches)}")
        
        records = []
        
        for idx, match in enumerate(code_matches):
            owner_code = match.group(1)
            marker_pos = match.start()
            
            # Определяем границы: prev, current, next маркеры
            prev_marker_pos = code_matches[idx - 1].start() if idx > 0 else None
            next_marker_pos = code_matches[idx + 1].start() if idx < len(code_matches) - 1 else None
            
            chunk_end = next_marker_pos if next_marker_pos else (marker_pos + 5000)
            chunk = content[marker_pos:chunk_end]
            
            # Находим таблицу (приоритет: после маркера, fallback: перед)
            quantity = self._find_closest_table(marker_pos, next_marker_pos, prev_marker_pos, tables)
            
            if quantity:
                # Извлекаем остальные поля
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
            
            if (idx + 1) % 100 == 0:
                print(f"   ... обработано {idx + 1}/{len(code_matches)}")
        
        print(f"✅ Извлечено записей: {len(records)}")
        return records
    
    def _extract_all_tables(self, content: str) -> Dict[int, int]:
        """Извлекает ВСЕ таблицы с количествами (позиция → количество)"""
        pattern_3col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*(\d+)\s*\|'
        pattern_4col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*\|\s*(\d+)\s*\|'
        
        tables = {}
        
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
                            # Позиция таблицы в контенте
                            pos = line_match.start()
                            tables[pos] = qty
        
        return tables
    
    def _find_closest_table(self, marker_pos: int, next_marker_pos: Optional[int], prev_marker_pos: Optional[int], tables: Dict[int, int]) -> Optional[int]:
        """
        Находит таблицу, принадлежащую владельцу
        1. Приоритет: ПОСЛЕ маркера и ПЕРЕД следующим
        2. Fallback: ПЕРЕД маркером (для границ страниц)
        """
        if not tables:
            return None
        
        # 1. Ищем ПОСЛЕ маркера (до следующего владельца)
        search_end = next_marker_pos if next_marker_pos else (marker_pos + 5000)
        
        forward_candidates = []
        for table_pos, qty in tables.items():
            if marker_pos < table_pos < search_end:
                forward_candidates.append((table_pos, qty))
        
        if forward_candidates:
            # Берем ПЕРВУЮ (ближайшую к маркеру)
            forward_candidates.sort(key=lambda x: x[0])
            return forward_candidates[0][1]
        
        # 2. Fallback: Ищем ПЕРЕД маркером (граница страницы)
        search_start = prev_marker_pos if prev_marker_pos else (marker_pos - 3000)
        
        backward_candidates = []
        for table_pos, qty in tables.items():
            if search_start < table_pos < marker_pos:
                backward_candidates.append((table_pos, qty))
        
        if backward_candidates:
            # Берем ПОСЛЕДНЮЮ (ближайшую к маркеру с конца)
            backward_candidates.sort(key=lambda x: x[0], reverse=True)
            return backward_candidates[0][1]
        
        return None
    
    def _extract_fio(self, chunk: str) -> Optional[str]:
        """Извлечение ФИО"""
        patterns = [
            r'# ([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)\s+Полное наименование',
            r'Полное наименование.*?\|\s*([А-ЯЁ][^\n|]{10,}?)\s*\|',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_address(self, chunk: str) -> Optional[str]:
        """Извлечение адреса"""
        patterns = [
            r'# (RU РОССИЯ \d{6}[^\n{]+?) Адрес',
            r'Адрес.*?\|\s*(RU РОССИЯ \d{6}[^\n|]{20,}?)\s*\|',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_document(self, chunk: str) -> Optional[str]:
        """Извлечение номера документа"""
        # Паспорт РФ: серия XX XX номер XXXXXX
        patterns = [
            r'серия\s+(\d{2}\s+\d{2}).*?номер\s+(\d{6})',
            r'номер\s+(\d{6}).*?серия\s+(\d{2}\s+\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, chunk, re.IGNORECASE)
            if match:
                if 'номер' in pattern.split()[0]:
                    return f"{match.group(2)} {match.group(1)}"
                else:
                    return f"{match.group(2)} {match.group(1)}"
        
        return None

