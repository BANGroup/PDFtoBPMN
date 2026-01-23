"""
Модели данных для Finance Parser
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class OwnerRecord:
    """Запись о владельце облигаций"""
    
    # Ключевые поля (обязательные)
    address: Optional[str] = None           # Адрес регистрации (полный)
    quantity: Optional[int] = None          # Количество в штуках
    
    # Дополнительные поля (для справки)
    owner_code: Optional[str] = None        # Код владельца (01_17395424797)
    full_name: Optional[str] = None         # ФИО
    document_number: Optional[str] = None   # Номер и/или серия документа (паспорт)
    account_number: Optional[str] = None    # Номер счета
    
    # Метаданные
    page_number: Optional[int] = None       # Номер страницы (начало записи)
    is_complete: bool = False               # Все ключевые поля заполнены?
    
    def validate(self) -> bool:
        """Проверка обязательных полей"""
        return all([
            self.address is not None and self.address.strip(),
            self.quantity is not None and self.quantity > 0
        ])
    
    def mark_complete(self):
        """Пометить запись как завершенную"""
        self.is_complete = self.validate()
    
    def to_dict(self) -> dict:
        """Конвертация в словарь для XLSX"""
        return {
            'Адрес регистрации': self.address or '',
            'Количество в штуках': self.quantity or 0,
            'Код владельца': self.owner_code or '',
            'ФИО': self.full_name or '',
            'Номер документа': self.document_number or '',
            'Номер счета': self.account_number or '',
            'Страница': self.page_number or 0
        }


@dataclass
class ParsedPage:
    """Результат парсинга одной страницы"""
    
    page_number: int
    blocks: List[dict] = field(default_factory=list)
    
    def has_start_record(self) -> bool:
        """Есть ли начало записи на странице?"""
        return any(b['type'] == 'start_record' for b in self.blocks)
    
    def has_quantity(self) -> bool:
        """Есть ли блок количества на странице?"""
        return any(b['type'] == 'quantity' for b in self.blocks)


@dataclass
class ValidationReport:
    """Отчет валидации результата"""
    
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    
    total_quantity: int = 0
    
    missing_address: int = 0
    missing_quantity: int = 0
    
    def add_record(self, record: OwnerRecord):
        """Добавить запись в отчет"""
        self.total_records += 1
        
        if record.validate():
            self.valid_records += 1
            if record.quantity:
                self.total_quantity += record.quantity
        else:
            self.invalid_records += 1
            
            if not record.address or not record.address.strip():
                self.missing_address += 1
            if record.quantity is None or record.quantity <= 0:
                self.missing_quantity += 1
    
    def print_report(self):
        """Вывести отчет в консоль"""
        print("="*80)
        print("📊 ОТЧЕТ ВАЛИДАЦИИ")
        print("="*80)
        print()
        
        print(f"📝 Всего записей: {self.total_records}")
        print(f"   ✅ Валидных: {self.valid_records}")
        print(f"   ❌ Невалидных: {self.invalid_records}")
        print()
        
        print(f"💰 Всего бумаг: {self.total_quantity:,} шт.".replace(',', ' '))
        print()
        
        if self.invalid_records > 0:
            print("⚠️  Проблемы:")
            if self.missing_address > 0:
                print(f"   • Отсутствует адрес: {self.missing_address} записей")
            if self.missing_quantity > 0:
                print(f"   • Отсутствует количество: {self.missing_quantity} записей")
            print()
        
        quality = (self.valid_records / self.total_records * 100) if self.total_records > 0 else 0
        print(f"✨ Качество данных: {quality:.1f}%")
        print()
