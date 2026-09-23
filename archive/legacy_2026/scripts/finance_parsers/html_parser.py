"""
HTML Table Parser - извлечение данных из HTML таблиц DeepSeek OCR

Распознает 5 типов блоков записи владельца:
1. Блок начала записи (код владельца + ФИО)
2. Персональные данные (ФИО + адрес + дата рождения)
3. Паспортные данные
4. Баланс по ценной бумаге (ISIN)
5. Количество в штуках
"""

from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import re


class TableType:
    """Типы таблиц в записи владельца"""
    START_RECORD = "start_record"  # Блок 1: начало записи
    PERSONAL = "personal"          # Блок 2: персональные данные
    PASSPORT = "passport"          # Блок 3: паспорт
    BALANCE = "balance"            # Блок 4: баланс (ISIN)
    QUANTITY = "quantity"          # Блок 5: количество
    UNKNOWN = "unknown"


class HTMLTableParser:
    """Парсер HTML таблиц от DeepSeek OCR"""
    
    def __init__(self):
        # Маркеры для определения типа таблицы
        self.markers = {
            TableType.START_RECORD: [
                "Код, присвоенный номинальным держателем",
                "Почтовое наименование"
            ],
            TableType.PERSONAL: [
                "Наименование",
                "Адрес",
                "Дата рождения"
            ],
            TableType.PASSPORT: [
                "Код типа документа",
                "Паспорт гражданина",
                "Номер и/или серия"
            ],
            TableType.BALANCE: [
                "ISIN"  # Единственный надежный маркер
            ],
            TableType.QUANTITY: [
                "Количество в штуках",
                "(прописью)"
            ]
        }
    
    def parse_raw_output(self, raw_output: str) -> List[Dict]:
        """
        Парсит raw_output от DeepSeek OCR
        
        Args:
            raw_output: HTML строка с таблицами и маркерами
            
        Returns:
            Список блоков данных с типом и полями
        """
        blocks = []
        
        # Разделяем по маркерам <|ref|>table<|/ref|>
        table_parts = re.split(r'<\|ref\|>table<\|/ref\|>', raw_output)
        
        for part in table_parts:
            if '<table>' not in part:
                continue
            
            # Извлекаем HTML таблицу
            table_html = self._extract_table_html(part)
            if not table_html:
                continue
            
            # Определяем тип и парсим
            block = self._parse_table(table_html)
            if block:
                blocks.append(block)
        
        return blocks
    
    def _extract_table_html(self, text: str) -> Optional[str]:
        """Извлекает HTML таблицу из текста"""
        match = re.search(r'<table>.*?</table>', text, re.DOTALL)
        if match:
            return match.group(0)
        return None
    
    def _parse_table(self, table_html: str) -> Optional[Dict]:
        """Парсит одну таблицу и возвращает блок данных"""
        soup = BeautifulSoup(table_html, 'html.parser')
        
        # Определяем тип таблицы
        table_type = self._detect_table_type(table_html)
        
        # Парсим в зависимости от типа
        if table_type == TableType.START_RECORD:
            return self._parse_start_record(soup)
        elif table_type == TableType.PERSONAL:
            return self._parse_personal(soup)
        elif table_type == TableType.PASSPORT:
            return self._parse_passport(soup)
        elif table_type == TableType.BALANCE:
            return self._parse_balance(soup)
        elif table_type == TableType.QUANTITY:
            return self._parse_quantity(soup)
        
        return None
    
    def _detect_table_type(self, table_html: str) -> str:
        """Определяет тип таблицы по маркерам"""
        for table_type, markers in self.markers.items():
            if all(marker in table_html for marker in markers):
                return table_type
        return TableType.UNKNOWN
    
    def _parse_start_record(self, soup: BeautifulSoup) -> Dict:
        """Парсит Блок 1: начало записи"""
        data = {
            'type': TableType.START_RECORD,
            'fields': {}
        }
        
        rows = soup.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                data['fields'][key] = value
        
        return data
    
    def _parse_personal(self, soup: BeautifulSoup) -> Dict:
        """Парсит Блок 2: персональные данные"""
        data = {
            'type': TableType.PERSONAL,
            'fields': {}
        }
        
        rows = soup.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                data['fields'][key] = value
        
        return data
    
    def _parse_passport(self, soup: BeautifulSoup) -> Dict:
        """Парсит Блок 3: паспортные данные"""
        data = {
            'type': TableType.PASSPORT,
            'fields': {}
        }
        
        # Заголовки
        headers = []
        header_row = soup.find('tr')
        if header_row:
            headers = [cell.get_text(strip=True) for cell in header_row.find_all('td')]
        
        # Значения
        rows = soup.find_all('tr')
        if len(rows) > 1:
            value_row = rows[1]
            values = [cell.get_text(strip=True) for cell in value_row.find_all('td')]
            
            for i, header in enumerate(headers):
                if i < len(values):
                    data['fields'][header] = values[i]
        
        return data
    
    def _parse_balance(self, soup: BeautifulSoup) -> Dict:
        """
        Парсит Блок 4: баланс (информация о ценной бумаге)
        
        Примечание: используется только для идентификации структуры записи,
        конкретные поля не извлекаются (не требуются)
        """
        data = {
            'type': TableType.BALANCE,
            'fields': {}
        }
        
        # Блок нужен только как маркер структуры записи
        # Конкретные данные не извлекаются
        
        return data
    
    def _parse_quantity(self, soup: BeautifulSoup) -> Dict:
        """
        Парсит Блок 5: количество в штуках ⭐⭐
        
        Извлекает:
        - Количество в штуках (число)
        - Количество прописью (текст)
        """
        data = {
            'type': TableType.QUANTITY,
            'fields': {}
        }
        
        rows = soup.find_all('tr')
        
        # Первая строка - заголовок
        # Вторая строка - значения
        if len(rows) >= 2:
            value_row = rows[1]
            cells = value_row.find_all('td')
            
            if len(cells) >= 1:
                # Первая ячейка - количество в штуках
                quantity_text = cells[0].get_text(strip=True)
                if quantity_text.isdigit():
                    data['fields']['Количество в штуках'] = int(quantity_text)
            
            if len(cells) >= 3:
                # Третья ячейка - прописью
                words_text = cells[2].get_text(strip=True)
                # Убираем "(прописью)" из текста
                words_clean = re.sub(r'\(прописью\)', '', words_text).strip()
                if words_clean:
                    data['fields']['Количество прописью'] = words_clean
        
        return data

