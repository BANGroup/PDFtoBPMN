"""
MD Parser - парсинг native text extraction из PDF (без OCR)

Быстрая альтернатива OCR для текстовых PDF.
"""

import re
from typing import List
from .models import OwnerRecord


class MDParser:
    """Парсер MD файла от native text extraction"""
    
    def parse_md_file(self, md_path: str) -> List[OwnerRecord]:
        """
        Парсит MD файл и извлекает записи владельцев
        
        Args:
            md_path: Путь к MD файлу
            
        Returns:
            Список OwnerRecord
        """
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return self.parse_md_content(content)
    
    def parse_md_content(self, content: str) -> List[OwnerRecord]:
        """Парсит содержимое MD"""
        records = []
        
        # НЕ исключаем итог глобально - он может быть в одном чанке с реальной записью!
        
        # Ищем записи по маркеру "Код, присвоенный номинальным держателем"
        # Это надежный маркер НАЧАЛА записи
        # Код находится на следующей строке после "предоставляющим данные"
        
        code_pattern = r'предоставляющим данные\s+(\d+_\d+)'
        
        for code_match in re.finditer(code_pattern, content):
            owner_code = code_match.group(1)
            start_pos = code_match.start()
            
            # Ищем СЛЕДУЮЩИЙ код владельца чтобы ограничить чанк
            next_code_match = re.search(
                r'предоставляющим данные\s+\d+_\d+',
                content[start_pos + 50:]  # Пропускаем текущий код
            )
            
            if next_code_match:
                # Ограничиваем чанк до следующей записи
                chunk_end = start_pos + 50 + next_code_match.start()
                chunk = content[start_pos:chunk_end]
            else:
                # Последняя запись - берем 3000 символов
                chunk = content[start_pos:start_pos + 3000]
            
            # Ищем ФИО/наименование (включая юрлица с кавычками, скобками, латиницей)
            # Захватываем всё между "Почтовое наименование" и "Почтовый адрес"
            fio_match = re.search(
                r'Почтовое наименование\s+(.*?)(?=Почтовый адрес|\d+\s*---)',
                chunk,
                re.DOTALL
            )
            fio = None
            if fio_match:
                fio_raw = fio_match.group(1).strip()
                # Убираем переносы страниц
                fio_raw = re.sub(r'##\s+Страница\s+\d+', '', fio_raw)
                # Убираем множественные пробелы/переносы
                fio = ' '.join(fio_raw.split()).strip()
                # Ограничиваем длину (если > 200 символов - захватили лишнее)
                if len(fio) > 200:
                    fio = fio[:197] + '...'
            
            # Ищем адрес регистрации (любой, включая не-RU: CY, BZ и т.д.)
            # Адрес может быть многострочным и заканчивается перед следующим блоком
            addr_match = re.search(
                r'Адрес\s+([A-Z]{2}[,\s].+?)(?=\s*(?:Код типа документа|Дата рождения|Признак юридического лица))',
                chunk,
                re.DOTALL
            )
            
            address = None
            if addr_match:
                address = addr_match.group(1).strip()
                # Очищаем адрес - убираем лишние переносы
                address = ' '.join(address.split())
            
            # Ищем номер документа (универсальный подход для физлиц и юрлиц)
            # Структура таблицы: "Номер и/или серия документа" → описание типа → НОМЕР → "Дата документа"
            # Номер - это строка с цифрами/буквами после всех описаний и перед датой
            
            document_number = None
            
            # Ищем номер документа: он идет ПОСЛЕ описания типа, прямо перед датой DD.MM.YYYY
            # Паттерн: "Номер и/или серия документа" ... [тип документа] ... НОМЕР ... DD.MM.YYYY
            doc_section_match = re.search(
                r'Номер и/или серия\s+документа(.*?)Баланс по ценной бумаге',
                chunk,
                re.DOTALL
            )
            
            if doc_section_match:
                doc_section = doc_section_match.group(1).strip()
                
                # Ищем строку перед датой в формате DD.MM.YYYY
                # Разбиваем на строки
                lines = [line.strip() for line in doc_section.split('\n') if line.strip()]
                
                # Фильтруем: исключаем заголовки и описания
                exclude_keywords = [
                    'Дата документа', 'Орган', 'осуществивший', 'регистрацию',
                    'Паспорт', 'гражданина', 'действующий', 'территории',
                    'Свидетельство', 'внесении', 'записи', 'ЕГРЮЛ',
                    'Сертификат', 'инкорпорации', 'регистрации',
                    'Другое', 'TXID', 'UKWN', 'Код типа', 'Описание'
                ]
                
                # Находим все строки с датами (DD.MM.YYYY)
                date_indices = []
                for i, line in enumerate(lines):
                    if re.match(r'\d{2}\.\d{2}\.\d{4}', line):
                        date_indices.append(i)
                
                # Если есть даты, ищем номер перед первой датой
                if date_indices:
                    first_date_idx = date_indices[0]
                    # Смотрим строку перед датой
                    for i in range(first_date_idx - 1, -1, -1):
                        line = lines[i]
                        has_keywords = any(kw in line for kw in exclude_keywords)
                        has_content = re.search(r'[\dА-ЯA-Za-z]', line)
                        
                        if not has_keywords and has_content and len(line) >= 3:
                            document_number = line
                            break
            
            # Ищем количество в штуках
            # ВАЖНО: Обрабатываем случаи когда количество разорвано разрывом страницы
            # Паттерн: "Количество в штуках \d+ --- ## Страница N \d+"
            qty_split_match = re.search(
                r'Количество в штуках\s+\d+\s+---\s+##\s+Страница\s+\d+\s+(\d+)',
                chunk
            )
            
            quantity = None
            if qty_split_match:
                # Разорванное количество - берем ВТОРОЕ число (после разрыва)
                quantity = int(qty_split_match.group(1))
            else:
                # Обычное количество
                qty_matches = list(re.finditer(r'Количество в штуках\s+(\d+)', chunk))
                
                if qty_matches:
                    first_match = qty_matches[0]
                    context_before = chunk[max(0, first_match.start()-100):first_match.start()]
                    qty_value = int(first_match.group(1))
                    
                    # Исключаем если это "Из них обременено" ИЛИ если это итог 4121600
                    if 'Из них обременено' not in context_before and qty_value != 4121600:
                        quantity = qty_value
            
            # Создаем запись
            if address and quantity:
                record = OwnerRecord(
                    owner_code=owner_code,
                    full_name=fio,
                    address=address,
                    quantity=quantity,
                    document_number=document_number
                )
                
                if record.validate():
                    records.append(record)
        
        return records

