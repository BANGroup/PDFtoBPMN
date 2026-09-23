"""
Парсер для Markdown от Marker - извлечение владельцев облигаций
"""

import re
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd


class MarkerOwnerParser:
    """Парсер владельцев из Markdown от Marker"""
    
    def __init__(self):
        self.records = []
    
    def parse_file(self, md_path: Path) -> List[Dict]:
        """
        Парсит Markdown файл и извлекает записи владельцев
        
        Returns:
            List[Dict]: Список записей с полями:
                - address: адрес регистрации
                - quantity: количество в штуках
                - code: код владельца
                - name: ФИО или наименование
                - document: номер документа
                - account: номер счета
                - page: номер страницы
        """
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return self.parse_content(content)
    
    def parse_content(self, content: str) -> List[Dict]:
        """Парсит содержимое Markdown"""
        self.records = []
        self.content = content  # Сохраняем для валидации
        
        # Разбиваем на записи по коду владельца
        # Ищем все строки с "Код, присвоенный" (может быть обрезано!)
        
        # Паттерн 1: Код в отдельной ячейке таблицы: | Код, присвоенный... | <код>
        pattern1 = r'\| Код, присвоенный[^\n]*?\|([^\n]+)'
        
        # Паттерн 2: Код в той же строке: Код, присвоенный... 01_XXXXXXXXXXX
        pattern2 = r'Код, присвоенный[^\n]*(0[12]_\d{11})'
        
        # Ищем все вхождения обоих паттернов
        matches1 = list(re.finditer(pattern1, content))
        matches2 = list(re.finditer(pattern2, content))
        
        # Объединяем и сортируем по позиции
        code_matches = sorted(matches1 + matches2, key=lambda m: m.start())
        
        print(f"Найдено строк с 'Код, присвоенный...': {len(code_matches)}")
        
        # Извлекаем коды
        valid_codes = []
        for match in code_matches:
            # Проверяем какой паттерн сработал
            if match.re.pattern == pattern2:
                # Паттерн 2: код уже извлечён
                code = match.group(1)
                valid_codes.append((match.start(), code))
                continue
            
            # Паттерн 1: берём всё что после "Код, присвоенный..."
            after_pipe = match.group(1)
            
            # Также смотрим следующие 2 строки (на случай если код в следующей строке)
            pos = match.end()
            next_chunk = content[pos:pos+200]
            combined = after_pipe + " " + next_chunk
            
            # Пытаемся извлечь код в разных форматах
            # Формат 1: 01_XXXXXXXXXXX или 02_XXXXXXXXXXX (полный с подчеркиванием)
            code = re.search(r'\b(0[12]_\d{11})\b', combined)
            if code:
                valid_codes.append((match.start(), code.group(1)))
                continue
            
            # Формат 2: 01 XXXXXXXXXXX или 02 XXXXXXXXXXX (с пробелом вместо подчеркивания)
            code = re.search(r'\b0([12])[\s_]+(\d{11})\b', combined)
            if code:
                valid_codes.append((match.start(), f"0{code.group(1)}_{code.group(2)}"))
                continue
            
            # Формат 3: код разбит на части в таблице
            # Ищем все числа и пытаемся собрать код
            # Примеры: "01 1740" + "01851345" или "02_174" + "01851369"
            parts = re.findall(r'\b(\d+)\b', combined)
            if len(parts) >= 2:
                # Первое число должно быть 01 или 02
                if len(parts) >= 2 and parts[0] in ('01', '02'):
                    # Собираем все остальные числа
                    rest = ''.join(parts[1:])
                    # Берем первые 11 цифр
                    if len(rest) >= 11:
                        full_code = parts[0] + '_' + rest[:11]
                        valid_codes.append((match.start(), full_code))
                        continue
        
        print(f"Извлечено валидных кодов (с дубликатами): {len(valid_codes)}")
        
        # Дедуплицируем по коду (оставляем первое вхождение)
        seen_codes = set()
        unique_codes = []
        for pos, code in valid_codes:
            if code not in seen_codes:
                seen_codes.add(code)
                unique_codes.append((pos, code))
        
        valid_codes = unique_codes
        print(f"Извлечено уникальных кодов: {len(valid_codes)}")
        
        for i, (pos, code) in enumerate(valid_codes):
            try:
                # Определяем границы записи:
                # - Назад на 2000 символов (чтобы захватить данные с предыдущей страницы при разрыве)
                # - Вперед до следующего кода
                start_pos = max(0, pos - 2000)
                if i + 1 < len(valid_codes):
                    end_pos = valid_codes[i + 1][0]  # Позиция следующего кода
                else:
                    end_pos = len(content)
                
                # Извлекаем блок записи (с запасом назад для количества)
                record_block = content[start_pos:end_pos]
                
                # Парсим запись
                record = self._parse_record(record_block, code)
                
                if record:
                    # Валидация: проверяем что код РЕАЛЬНО есть в MD как отдельное слово
                    if self._validate_code(code):
                        self.records.append(record)
                    else:
                        print(f"   ⚠️ Код {code} не найден в MD - пропускаем (ложное извлечение)")
                    
            except Exception as e:
                print(f"Ошибка при парсинге записи {i} (код {code}): {e}")
                continue
        
        print(f"Успешно извлечено записей Типа A (с кодом): {len(self.records)}")
        
        # ========================================================================
        # ТИП B: Записи с заголовком "## Баланс по ценной бумаге лица"
        # ========================================================================
        print("\n🔄 Парсинг записей Типа B (без явного кода)...")
        
        balance_pattern = r'## Баланс по ценной бумаге лица, включаемого в список'
        balance_matches = list(re.finditer(balance_pattern, content))
        
        print(f"Найдено записей Типа B: {len(balance_matches)}")
        
        for i, match in enumerate(balance_matches):
            try:
                # Определяем границы записи:
                # - Назад на 2000 символов (чтобы захватить данные с предыдущей страницы)
                # - Вперед до следующего баланса или конца
                start_pos = max(0, match.start() - 2000)
                if i + 1 < len(balance_matches):
                    end_pos = balance_matches[i + 1].start()
                else:
                    end_pos = min(len(content), match.end() + 2000)
                
                record_block = content[start_pos:end_pos]
                
                # Парсим запись без кода
                record = self._parse_record_type_b(record_block)
                
                if record:
                    self.records.append(record)
                    
            except Exception as e:
                print(f"Ошибка при парсинге записи Типа B {i}: {e}")
                continue
        
        print(f"✅ Всего извлечено записей: {len(self.records)} (Тип A + Тип B)")
        return self.records
    
    def _validate_code(self, code: str) -> bool:
        """Проверяет что код реально существует в MD как отдельное слово"""
        import re
        # Ищем код как отдельное слово (с границами слов)
        pattern = r'\b' + re.escape(code) + r'\b'
        return bool(re.search(pattern, self.content))
    
    def _parse_record_type_b(self, block: str) -> Optional[Dict]:
        """Парсит запись Типа B (без явного кода владельца)"""
        
        record = {
            'code': None,  # У записей Типа B нет явного кода
            'name': None,
            'address': None,
            'quantity': None,
            'document': None,
            'account': None,
            'page': None
        }
        
        # 1. Ищем имя в строке "Наименование"
        name_match = re.search(r'Наименование\s*\|\s*([^\n|]+)', block)
        if name_match:
            name = name_match.group(1).strip()
            record['name'] = name
        
        # 2. Ищем адрес
        address_match = re.search(r'Адрес\s*[|]?\s*(RU[^\n]+)', block)
        if address_match:
            address = address_match.group(1).strip()
            record['address'] = address
        
        # 3. Ищем количество ПЕРЕД заголовком "## Баланс"
        qty_pos = block.find('Количество в штуках')
        if qty_pos != -1:
            qty_chunk = block[qty_pos:qty_pos+500]
            all_numbers = re.findall(r'\b(\d+)\b', qty_chunk)
            
            for num in all_numbers:
                num_len = len(num)
                if 1 <= num_len <= 7:
                    if num_len == 4 and (num.startswith('19') or num.startswith('20')):
                        continue
                    if num.startswith('01') and num_len > 5:
                        continue
                    
                    record['quantity'] = num
                    break
        
        # 4. Ищем документ (ОГРН или паспорт)
        passport_match = re.search(r'\b(\d{4}\s*\d{6})\b', block)
        if passport_match:
            record['document'] = passport_match.group(1).replace(' ', '')
        
        ogrn_match = re.search(r'\b(10\d{11,12}|1\d{12})\b', block)
        if ogrn_match:
            record['document'] = f"ЕГРЮЛ\\n{ogrn_match.group(1)}"
        
        # 5. Генерируем код владельца на основе имени (для уникальности)
        if record['name']:
            # Берём первые 20 символов имени и хешируем
            import hashlib
            name_hash = hashlib.md5(record['name'].encode()).hexdigest()[:11]
            record['code'] = f"TypeB_{name_hash}"
        
        # Проверка валидности
        if not record['name']:
            return None
        
        if not record['quantity']:
            print(f"   ⚠️ Запись Типа B без количества: {record['name'][:30]}")
        
        return record
    
    def _parse_record(self, block: str, code: str) -> Optional[Dict]:
        """Парсит одну запись владельца"""
        
        record = {
            'address': '',
            'quantity': '',
            'code': code,
            'name': '',
            'document': '',
            'account': '',
            'page': ''
        }
        
        # 1. Ищем наименование (ФИО или название организации)
        # Паттерн: "Почтовое наименование | <имя>"
        name_match = re.search(r'Почтовое наименование[^\|]*\|([^\|]+?)(?:\||$)', block)
        if name_match:
            name = name_match.group(1).strip()
            # Очищаем от переносов строк и лишних пробелов
            name = re.sub(r'\s+', ' ', name)
            record['name'] = name
        
        # 2. Ищем адрес
        # Паттерн: "Почтовый адрес | RU<br>индекс<br>адрес"
        addr_match = re.search(r'Почтовый адрес[^\|]*\|([^\|]+?)(?:\||$)', block, re.DOTALL)
        if addr_match:
            addr = addr_match.group(1).strip()
            # Убираем <br>, лишние пробелы
            addr = re.sub(r'<br>|<br\s*/>', ' ', addr)
            addr = re.sub(r'\s+', ' ', addr)
            # Убираем пустые ")" в конце
            addr = re.sub(r'\s*\)\s*$', '', addr)
            record['address'] = addr.strip()
        
        # 3. Ищем номер счета
        # Паттерн: "Номер счета | <номер>"
        account_match = re.search(r'Номер счета[^\|]*\|([^\|]+?)(?:\||$)', block)
        if account_match:
            account = account_match.group(1).strip()
            account = re.sub(r'\s+', ' ', account)
            record['account'] = account
        
        # 4. Ищем количество в штуках
        # Количество ПЕРЕД кодом владельца, может быть на расстоянии нескольких строк
        
        # Сначала находим позицию "Количество в штуках"
        qty_pos = block.find('Количество в штуках')
        if qty_pos != -1:
            # Берём следующие 500 символов после этого места
            qty_chunk = block[qty_pos:qty_pos+500]
            
            # Ищем все числа в этом куске
            all_numbers = re.findall(r'\b(\d+)\b', qty_chunk)
            
            # Фильтруем: берём первое число длиной 1-7 цифр (это скорее всего количество)
            for num in all_numbers:
                num_len = len(num)
                # Количество бумаг: от 1 до 9999999
                if 1 <= num_len <= 7:
                    # Исключаем очевидно неподходящие: годы (4 цифры 19XX, 20XX)
                    if num_len == 4 and (num.startswith('19') or num.startswith('20')):
                        continue
                    # Исключаем коды (начинаются с 01)
                    if num.startswith('01') and num_len > 5:
                        continue
                    
                    record['quantity'] = num
                    break
        
        # 5. Ищем номер документа
        # Для физлиц - паспорт, для юрлиц - ОГРН
        # Паттерн паспорта: 4 цифры пробел 6 цифр
        passport_match = re.search(r'\b(\d{4}\s*\d{6})\b', block)
        if passport_match:
            record['document'] = passport_match.group(1).replace(' ', '')
        else:
            # ОГРН: 13 цифр
            ogrn_match = re.search(r'\b(10\d{11,12}|1\d{12})\b', block)
            if ogrn_match:
                record['document'] = f"ЕГРЮЛ\\n{ogrn_match.group(1)}"
        
        # Проверяем что запись валидна
        # Минимальное требование: есть код владельца
        # Имя или количество могут отсутствовать - это не критично, попытаемся заполнить позже
        if not record['code']:
            return None
        
        # Если нет имени или количества - запись всё равно валидна, но будем логировать
        if not record['name']:
            print(f"   ⚠️ Запись без имени: код {record['code']}")
        if not record['quantity']:
            print(f"   ⚠️ Запись без количества: код {record['code']}, имя: {record['name'][:30] if record['name'] else 'N/A'}")
        
        return record
    
    def to_dataframe(self) -> pd.DataFrame:
        """Конвертирует записи в DataFrame"""
        df = pd.DataFrame(self.records)
        
        # Переименовываем колонки под формат Excel
        df = df.rename(columns={
            'address': 'Адрес регистрации',
            'quantity': 'Количество в штуках',
            'code': 'Код владельца',
            'name': 'ФИО',
            'document': 'Номер документа',
            'account': 'Номер счета',
            'page': 'Страница'
        })
        
        # Порядок колонок как в существующем Excel
        cols = [
            'Адрес регистрации',
            'Количество в штуках',
            'Код владельца',
            'ФИО',
            'Номер документа',
            'Номер счета',
            'Страница'
        ]
        
        return df[cols]
    
    def export_to_excel(self, output_path: Path):
        """Экспортирует в Excel"""
        df = self.to_dataframe()
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(output_path, index=False)
        
        print(f"\n✅ Экспортировано записей: {len(df)}")
        print(f"📁 Файл: {output_path}")
        print(f"📊 Размер: {output_path.stat().st_size:,} байт")


if __name__ == "__main__":
    print()
    print("="*80)
    print("🚀 ПАРСИНГ MARKDOWN ОТ MARKER")
    print("="*80)
    print()
    
    # Пути
    md_path = Path("/home/budnik_an/Obligations/output/finance_marker/Выпуск 4-02 на 16.06.2020/Выпуск 4-02 на 16.06.2020.md")
    output_path = Path("/home/budnik_an/Obligations/output/finance_marker/Выпуск_4-02_marker.xlsx")
    
    # Парсинг
    parser = MarkerOwnerParser()
    
    print(f"📄 Входной файл: {md_path.name}")
    print(f"📁 Выходной файл: {output_path.name}")
    print()
    
    print("🔄 Парсинг...")
    records = parser.parse_file(md_path)
    
    if records:
        print()
        print("📋 ПРИМЕРЫ НАЙДЕННЫХ ЗАПИСЕЙ:")
        print("-"*80)
        for i, rec in enumerate(records[:3], 1):
            print(f"\n{i}. {rec['name']}")
            print(f"   Адрес: {rec['address'][:60]}...")
            print(f"   Количество: {rec['quantity']}")
            print(f"   Документ: {rec['document']}")
            print(f"   Счет: {rec['account']}")
        
        # Экспорт
        print()
        print("="*80)
        print("💾 ЭКСПОРТ В EXCEL")
        print("="*80)
        parser.export_to_excel(output_path)
        
        print()
        print("="*80)
        print("✅ ГОТОВО!")
        print("="*80)
        print()
        print("💡 Сравните файлы:")
        print(f"   • Старый: output/finance/Выпуск_4-02_на_16.06.2020.xlsx (291 запись)")
        print(f"   • Новый:  output/finance_marker/Выпуск_4-02_marker.xlsx ({len(records)} записей)")
    else:
        print()
        print("❌ Не удалось извлечь записи")

