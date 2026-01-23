"""
Record Merger - склейка записей владельцев между страницами

State Machine для обработки разрывов записей:
- IDLE: ожидание начала записи
- IN_RECORD: внутри записи (после Блока 1)
- WAITING_QUANTITY: ждем Блок 5 (после нашли Блок 2)
- COMPLETE: запись завершена
"""

from typing import List
from .models import OwnerRecord, ParsedPage
from .html_parser import TableType


class RecordState:
    """Состояния state machine"""
    IDLE = "idle"
    IN_RECORD = "in_record"
    WAITING_QUANTITY = "waiting_quantity"
    COMPLETE = "complete"


class RecordMerger:
    """Склейка записей владельцев между страницами"""
    
    def __init__(self):
        self.state = RecordState.IDLE
        self.current_record = None
        self.completed_records = []
    
    def process_pages(self, pages: List[ParsedPage]) -> List[OwnerRecord]:
        """
        Обработка списка страниц и извлечение записей
        
        Args:
            pages: Список ParsedPage с блоками данных
            
        Returns:
            Список завершенных OwnerRecord
        """
        self.state = RecordState.IDLE
        self.current_record = None
        self.completed_records = []
        
        for page in pages:
            self._process_page(page)
        
        # Если осталась незавершенная запись - добавляем её
        if self.current_record is not None:
            self.current_record.mark_complete()
            self.completed_records.append(self.current_record)
        
        return self.completed_records
    
    def _process_page(self, page: ParsedPage):
        """Обработка одной страницы"""
        for block in page.blocks:
            block_type = block['type']
            fields = block.get('fields', {})
            
            if block_type == TableType.START_RECORD:
                self._handle_start_record(fields, page.page_number)
            
            elif block_type == TableType.PERSONAL:
                self._handle_personal(fields)
            
            elif block_type == TableType.QUANTITY:
                self._handle_quantity(fields)
    
    def _handle_start_record(self, fields: dict, page_number: int):
        """Обработка Блока 1: начало записи"""
        # Если уже есть текущая запись - завершаем её
        if self.current_record is not None:
            self.current_record.mark_complete()
            self.completed_records.append(self.current_record)
        
        # Начинаем новую запись
        self.current_record = OwnerRecord(page_number=page_number)
        
        # Извлекаем поля
        self.current_record.owner_code = fields.get('Код, присвоенный номинальным держателем, предоставляющим данные')
        self.current_record.full_name = fields.get('Почтовое наименование')
        self.current_record.account_number = fields.get('Номер счета')
        
        self.state = RecordState.IN_RECORD
    
    def _handle_personal(self, fields: dict):
        """Обработка Блока 2: персональные данные (АДРЕС)"""
        if self.current_record is None:
            return
        
        # Извлекаем адрес регистрации (ключевое поле!)
        address = fields.get('Адрес')
        if address:
            self.current_record.address = address
            self.state = RecordState.WAITING_QUANTITY
    
    def _handle_quantity(self, fields: dict):
        """Обработка Блока 5: количество (КЛЮЧЕВОЕ ПОЛЕ!)"""
        if self.current_record is None:
            return
        
        # Извлекаем количество в штуках
        quantity = fields.get('Количество в штуках')
        if quantity is not None:
            self.current_record.quantity = quantity
            
            # Запись завершена (есть адрес и количество)
            self.current_record.mark_complete()
            self.completed_records.append(self.current_record)
            self.current_record = None
            self.state = RecordState.IDLE

