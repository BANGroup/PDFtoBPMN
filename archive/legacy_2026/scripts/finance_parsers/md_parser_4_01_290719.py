"""
MD Parser для документа "Выпуск 4-01 на 29.07.19" - ТАБЛИЧНЫЙ ФОРМАТ

Отличия от базового парсера (md_parser.py):
- Данные в MD таблицах (не plain text)  
- Маркер: # Код 01_XXXXXXXX(NADC)
- Количество в маленькой таблице (3 столбца)
- Адрес, ФИО, ОГРН в большой таблице владельца
"""

import re
from typing import List, Optional
from .models import OwnerRecord


class MDParser_4_01_290719:
    """Парсер MD файла для табличного формата (29.07.19)"""
    
    def parse_md_file(self, md_path: str) -> List[OwnerRecord]:
        """Парсит MD файл и извлекает записи владельцев"""
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return self.parse_md_content(content)
    
    def parse_md_content(self, content: str) -> List[OwnerRecord]:
        """Парсит содержимое MD (табличный формат)"""
        records = []
        
        # КРИТИЧНО: Пропускаем frontmatter и оглавление
        # Ищем начало основного контента (маркер страницы)
        content_start = content.find('<!-- Страница')
        if content_start == -1:
            content_start = 50000  # Fallback
        
        # Работаем только с основным контентом
        content = content[content_start:]  # Заменяем content на очищенный
        
        # Находим все маркеры владельцев: # Код 01_XXXXXXXX(NADC)
        code_pattern = r'# Код (01_\d+)\(NADC\)'
        code_matches = list(re.finditer(code_pattern, content))
        
        print(f"🔍 Найдено владельцев: {len(code_matches)}")
        
        for match_idx, code_match in enumerate(code_matches, 1):
            owner_code = code_match.group(1)
            start_pos = code_match.start()
            
            # === СТРУКТУРА ЗАПИСИ (СМЕШАННАЯ!) ===
            # Вариант 1:
            #   | Таблица QTY | ← ПЕРЕД маркером
            #   # Код 01_XXX(NADC)  ← МАРКЕР
            #   | Большая таблица с адресом, ФИО | ← ПОСЛЕ маркера
            #
            # Вариант 2:
            #   # Код 01_XXX(NADC)  ← МАРКЕР
            #   | Большая таблица с адресом, ФИО |  ← ПОСЛЕ маркера
            #   | Таблица QTY | ← ПОСЛЕ маркера
            
            # Чанк ВПЕРЕД (всегда ищем адрес/ФИО/ОГРН здесь)
            if match_idx < len(code_matches):
                next_match = code_matches[match_idx]
                chunk_end = next_match.start()
            else:
                chunk_end = start_pos + 5000
            
            chunk_forward = content[start_pos:chunk_end]
            
            # Чанк НАЗАД (расширенный для захвата таблиц на разрывах страниц)
            if match_idx > 1:
                prev_match = code_matches[match_idx - 2]
                chunk_start = prev_match.start()
            else:
                chunk_start = max(0, start_pos - 20000)  # Расширен для первых записей
            
            chunk_back = content[chunk_start:start_pos]
            
            # === 1. ИЗВЛЕЧЕНИЕ КОЛИЧЕСТВА (ТОЛЬКО ВПЕРЕД!) ===
            # КРИТИЧНО: MD перемешивает порядок, backward дает дубли!
            # Пример: Юшкова Наталья (01_4866071304) не имеет таблицы, 
            # backward берет 73,930 от предыдущего счета (01_4866071306) - это ДУБЛЬ!
            quantity = self._extract_quantity_forward_only(chunk_forward)
            
            # === 2. ИЗВЛЕЧЕНИЕ ФИО (сначала вперед, потом назад) ===
            fio = self._extract_fio_from_table(chunk_forward)
            if fio is None:
                fio = self._extract_fio_from_table(chunk_back)
            
            # === 3. ИЗВЛЕЧЕНИЕ АДРЕСА (сначала вперед, потом назад) ===
            address = self._extract_address_from_table(chunk_forward)
            if address is None:
                address = self._extract_address_from_table(chunk_back)
            
            # === 4. ИЗВЛЕЧЕНИЕ ОГРН/НОМЕРА ДОКУМЕНТА (сначала вперед, потом назад) ===
            document_number = self._extract_document_number(chunk_forward)
            if document_number is None:
                document_number = self._extract_document_number(chunk_back)
            
            # Создаем запись
            if address and quantity:
                record = OwnerRecord(
                    owner_code=owner_code,
                    full_name=fio,
                    address=address,
                    quantity=quantity,
                    document_number=document_number,
                    page_number=None  # В табличном формате номера страниц нет
                )
                
                if record.validate():
                    records.append(record)
                    if match_idx % 100 == 0:
                        print(f"   ... обработано {match_idx}/{len(code_matches)}")
            else:
                # Отладка: почему запись не прошла
                if match_idx <= 10 or (not address) or (not quantity):
                    reason = []
                    if not address:
                        reason.append("НЕТ АДРЕСА")
                    if not quantity:
                        reason.append("НЕТ КОЛИЧЕСТВА")
                    if match_idx <= 10:
                        print(f"   ⚠️  Запись {match_idx} ({owner_code}): {', '.join(reason)}")
        
        print(f"✅ Извлечено записей: {len(records)}")
        return records
    
    def _extract_quantity_forward_only(self, chunk_forward: str) -> Optional[int]:
        """
        Извлекает количество ТОЛЬКО из chunk_forward
        Backward НЕ используется - дает дубли из-за перемешанного порядка MD
        """
        pattern_3col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*(\d+)\s*\|'
        pattern_4col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*\|\s*(\d+)\s*\|'
        
        for line in chunk_forward.split('\n'):
            line_stripped = line.strip()
            
            if line_stripped.startswith('|') and '4-01-36484-R' in line_stripped:
                if 'обременен' in line_stripped.lower():
                    continue
                
                if line_stripped.count('|') >= 3:
                    match = re.search(pattern_3col, line) or re.search(pattern_4col, line)
                    if match:
                        qty = int(match.group(1))
                        if 1 <= qty < 3000000:
                            return qty
        
        return None
    
    def _extract_quantity_smart(self, chunk_forward: str, chunk_back: str) -> Optional[int]:
        """
        Умное извлечение количества с учетом перемешанного порядка MD
        1. Приоритет: chunk_forward (свой чанк)
        2. Fallback: chunk_back ПОСЛЕДНЯЯ таблица (для границ страниц)
        """
        pattern_3col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*(\d+)\s*\|'
        pattern_4col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*\|\s*(\d+)\s*\|'
        
        # 1. Ищем ВПЕРЕД (приоритет - 95% случаев)
        for line in chunk_forward.split('\n'):
            line_stripped = line.strip()
            
            if line_stripped.startswith('|') and '4-01-36484-R' in line_stripped:
                if 'обременен' in line_stripped.lower():
                    continue
                
                if line_stripped.count('|') >= 3:
                    match = re.search(pattern_3col, line) or re.search(pattern_4col, line)
                    if match:
                        qty = int(match.group(1))
                        if 1 <= qty < 3000000:
                            return qty
        
        # 2. Fallback: Ищем НАЗАД (граница страницы - 5% случаев)
        # Берем ПОСЛЕДНЮЮ таблицу (ближайшую к маркеру)
        backward_quantities = []
        
        for line in chunk_back.split('\n'):
            line_stripped = line.strip()
            
            if line_stripped.startswith('|') and '4-01-36484-R' in line_stripped:
                if 'обременен' in line_stripped.lower():
                    continue
                
                if line_stripped.count('|') >= 3:
                    match = re.search(pattern_3col, line) or re.search(pattern_4col, line)
                    if match:
                        qty = int(match.group(1))
                        if 1 <= qty < 3000000:
                            backward_quantities.append(qty)
        
        # Берем ПОСЛЕДНЮЮ (ближайшую к маркеру с конца chunk_back)
        if backward_quantities:
            return backward_quantities[-1]
        
        return None
    
    def _extract_quantity_closest_to_marker(self, chunk_forward: str, chunk_back: str, marker_pos: int) -> Optional[int]:
        """
        Извлекает количество с приоритетом направления
        
        ВАЖНО: 95% таблиц находятся ПОСЛЕ маркера (+269 симв)
        Поиск НАЗАД нужен только для записей на границах страниц
        
        Приоритет:
        1. Ищем ПОСЛЕ маркера (chunk_forward) - берем ПЕРВОЕ найденное
        2. Только если НЕ НАШЛИ - ищем ПЕРЕД маркером (chunk_back) - берем ПОСЛЕДНЕЕ
        """
        # КРИТИЧНО: Ищем ТОЛЬКО в строках таблиц, НЕ в заголовках
        # Используем фильтрацию по строкам вместо regex
        pattern_3col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*(\d+)\s*\|'
        pattern_4col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*\|\s*(\d+)\s*\|'
        
        # 1. ПРИОРИТЕТ: Ищем ПОСЛЕ маркера (chunk_forward)
        # Берем ПЕРВОЕ найденное (ближайшее к маркеру)
        # ФИЛЬТРАЦИЯ: ТОЛЬКО строки, начинающиеся с "|" (таблицы)
        
        forward_candidates = []
        lines_forward = chunk_forward.split('\n')
        cumulative_pos = 0
        
        for line in lines_forward:
            line_stripped = line.strip()
            
            # СТРОГАЯ ФИЛЬТРАЦИЯ: ТОЛЬКО строки таблиц
            if line_stripped.startswith('|') and '4-01-36484-R' in line_stripped:
                # КРИТИЧНО: Пропускаем строки с обремененными облигациями
                if 'обременен' in line_stripped.lower():
                    continue
                
                # Дополнительная проверка: НЕ заголовок (в заголовках нет второго "|")
                if line_stripped.count('|') >= 3:  # Таблица имеет минимум 3 разделителя
                    # Ищем паттерн в этой строке
                    match_3 = re.search(pattern_3col, line)
                    match_4 = re.search(pattern_4col, line)
                    
                    if match_3:
                        qty = int(match_3.group(1))
                        if 1 <= qty < 3000000:
                            forward_candidates.append((cumulative_pos + match_3.start(), qty))
                            break  # Берем ПЕРВОЕ
                    
                    if match_4:
                        qty = int(match_4.group(1))
                        if 1 <= qty < 3000000:
                            forward_candidates.append((cumulative_pos + match_4.start(), qty))
                            break  # Берем ПЕРВОЕ
            
            cumulative_pos += len(line) + 1  # +1 для '\n'
        
        if forward_candidates:
            # Берем таблицу ближайшую к маркеру (минимальная позиция)
            forward_candidates.sort(key=lambda x: x[0])
            return forward_candidates[0][1]
        
        # 2. Только если НЕ НАШЛИ вперед - ищем ПЕРЕД маркером (chunk_back)
        # Берем ПОСЛЕДНЕЕ найденное (ближайшее к маркеру с конца)
        # ФИЛЬТРАЦИЯ: ТОЛЬКО строки таблиц
        
        back_candidates = []
        lines_back = chunk_back.split('\n')
        cumulative_pos_back = 0
        
        for line in lines_back:
            line_stripped = line.strip()
            
            # СТРОГАЯ ФИЛЬТРАЦИЯ: ТОЛЬКО строки таблиц
            if line_stripped.startswith('|') and '4-01-36484-R' in line_stripped:
                # КРИТИЧНО: Пропускаем строки с обремененными облигациями
                if 'обременен' in line_stripped.lower():
                    continue
                
                if line_stripped.count('|') >= 3:  # Полноценная строка таблицы
                    # Ищем паттерны в этой строке
                    for match in re.finditer(pattern_3col, line):
                        qty = int(match.group(1))
                        if 1 <= qty < 3000000:
                            back_candidates.append((cumulative_pos_back + match.end(), qty))
                    
                    for match in re.finditer(pattern_4col, line):
                        qty = int(match.group(1))
                        if 1 <= qty < 3000000:
                            back_candidates.append((cumulative_pos_back + match.end(), qty))
            
            cumulative_pos_back += len(line) + 1
        
        if back_candidates:
            # Берем ПОСЛЕДНЕЕ (максимальная позиция = ближе к концу чанка = ближе к маркеру)
            back_candidates.sort(key=lambda x: -x[0])
            return back_candidates[0][1]
        
        return None
    
    def _extract_quantity_from_table(self, chunk: str) -> Optional[int]:
        """
        Извлекает количество из таблицы (ТОЛЬКО основное, БЕЗ обременений)
        
        Формат 1 (3 столбца):
        | 4-01-36484-R | RU000A0JVZF7 (NADC) | 3924 |
        
        Формат 2 (4 столбца):
        | 4-01-36484-R | RU000A0JVZF7 (NADC) |  | 121255 |
        | Из них |  |  |  |
        | обременено обязательствами... |  | 121255 | ← НЕ БРАТЬ (дубликат)!
        
        ВАЖНО: Обремененное количество = часть основного, НЕ дополнительное!
        """
        # Паттерн 1: 3 столбца (количество в 3-й ячейке)
        pattern_3col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*(\d+)\s*\|'
        match = re.search(pattern_3col, chunk)
        
        if match:
            qty = int(match.group(1))
            if 1 <= qty < 3000000:
                return qty
        
        # Паттерн 2: 4 столбца (количество в 4-й ячейке, 3-я пустая)
        # ВАЖНО: Строка с "4-01-36484-R" - это ОСНОВНОЕ количество (брать)
        # Строка с "обременено" БЕЗ "4-01-36484-R" - это дубликат (не брать)
        pattern_4col = r'\|\s*4-01-36484-R\s*\|\s*RU\w+\s+\(NADC\)\s*\|\s*\|\s*(\d+)\s*\|'
        match_4col = re.search(pattern_4col, chunk)
        
        if match_4col:
            qty = int(match_4col.group(1))
            
            # ПРОВЕРКА: Строка содержит "4-01-36484-R" => это ОСНОВНОЕ количество
            # Даже если рядом есть слово "обременено", это не страшно - главное что в ЭТОЙ строке есть регномер
            if 1 <= qty < 3000000:
                return qty
        
        return None
    
    def _extract_fio_from_table(self, chunk: str) -> Optional[str]:
        """
        Извлекает ФИО из большой таблицы владельца
        
        Формат:
        | Полное наименование/
        Ф.И.О. (юр./физ. лица) | Открытое акционерное общество "Спецмонтажмеханизация" |
        """
        # Ищем строку таблицы с ФИО
        fio_pattern = r'\|\s*Полное наименование.*?\|\s*([^|]+?)\s*\|'
        
        match = re.search(fio_pattern, chunk, re.DOTALL)
        if match:
            fio_raw = match.group(1).strip()
            # Убираем переносы строк и лишние пробелы
            fio = ' '.join(fio_raw.split())
            # Ограничиваем длину
            if len(fio) > 200:
                fio = fio[:197] + '...'
            return fio
        
        return None
    
    def _extract_address_from_table(self, chunk: str) -> Optional[str]:
        """
        Извлекает адрес из большой таблицы владельца (3 варианта)
        
        Вариант 1:
        | Адрес | RU РОССИЯ 115230... |
        
        Вариант 2:
        | Адрес для направления корреспонденции | ФИО\nRU РОССИЯ адрес |
        
        Вариант 3:
        |  | RU РОССИЯ 450092... | (без заголовка, просто адрес с кодом страны)
        """
        # Вариант 1: прямая ячейка "Адрес"
        addr_pattern = r'\|\s*Адрес\s*\|\s*([A-Z]{2}\s+[^|]+?)\s*\|'
        match = re.search(addr_pattern, chunk)
        
        if match:
            addr_raw = match.group(1).strip()
            address = ' '.join(addr_raw.split())
            return address
        
        # Вариант 2: "Адрес для направления корреспонденции" (адрес после ФИО)
        addr_corr_pattern = r'Адрес\s+для направления\s+корреспонденции.*?([A-Z]{2}\s+[А-ЯA-Z][^|]{20,200})'
        match_corr = re.search(addr_corr_pattern, chunk, re.DOTALL)
        
        if match_corr:
            addr_raw = match_corr.group(1).strip()
            # Извлекаем адрес (начинается с кода страны RU/CY/etc)
            addr_lines = addr_raw.split('\n')
            for line in addr_lines:
                if re.match(r'^[A-Z]{2}\s+', line):
                    address = ' '.join(line.split())
                    return address
        
        # Вариант 3: любая ячейка таблицы с адресом (начинается с кода страны)
        # Ищем строку таблицы с кодом страны и длинным адресом
        addr_any_pattern = r'\|\s*\|\s*([A-Z]{2}\s+[А-ЯA-Z][^|]{30,}?)\s*\|'
        match_any = re.search(addr_any_pattern, chunk)
        
        if match_any:
            addr_raw = match_any.group(1).strip()
            # Проверяем что это действительно адрес (содержит слова типа "город", "улица", "дом")
            if any(word in addr_raw.lower() for word in ['город', 'г ', 'ул ', 'улица', 'дом', 'респ', 'область', 'край']):
                address = ' '.join(addr_raw.split())
                return address
        
        return None
    
    def _extract_document_number(self, chunk: str) -> Optional[str]:
        """
        Извлекает номер документа (ОГРН для юрлиц, паспорт для физлиц)
        
        Формат юрлиц в таблице:
        | ОГРН
        1027700070310 | Код ИНН ... |
        
        Формат физлиц в тексте:
        номер 057362 серия 45 02
        """
        # 1. Сначала пробуем найти ОГРН в таблице (юрлица)
        ogrn_pattern = r'\|\s*ОГРН\s+(\d+)\s*\|'
        ogrn_match = re.search(ogrn_pattern, chunk)
        
        if ogrn_match:
            return ogrn_match.group(1)
        
        # 2. Если нет ОГРН - ищем паспорт (физлица)
        # Паттерн: "номер XXXXXX серия XX XX" (в курсивном тексте)
        passport_pattern = r'номер\s+(\d+)\s+серия\s+([\d\s]+)'
        passport_match = re.search(passport_pattern, chunk)
        
        if passport_match:
            number = passport_match.group(1)
            series_raw = passport_match.group(2).strip()
            # Нормализуем серию (может быть "45 02" или "4502")
            series = series_raw.replace(' ', '')
            if len(series) == 4:
                # Разделяем на 2 части: "4502" → "45 02"
                series = f"{series[:2]} {series[2:]}"
            return f"{series} {number}"
        
        # 3. Альтернативный паттерн (ОГРН в строке "Код ОКВЭД ОГРН XXXX")
        ogrn_inline_pattern = r'ОГРН\s+(\d{13,15})'
        ogrn_inline_match = re.search(ogrn_inline_pattern, chunk)
        
        if ogrn_inline_match:
            return ogrn_inline_match.group(1)
        
        return None
