"""
Модели данных для графа документов
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class ProcessGroup(Enum):
    """Группы процессов СМК"""
    M = "Процессы менеджмента"
    B = "Процессы жизненного цикла"  # Б в латинице для совместимости
    V = "Процессы обеспечения"       # В в латинице для совместимости
    UNKNOWN = "Неклассифицированные"


class DocumentType(Enum):
    """Типы документов СМК"""
    DP = "Документация процесса"      # ДП
    RD = "Руководство по деятельности"  # РД
    ST = "Стандарт"                    # СТ
    KD = "Корпоративный документ"      # КД
    RG = "Регламент"                   # РГ
    RK = "Руководство по качеству"     # РК
    IOT = "Инструкция по охране труда" # ИОТ
    TPM = "Technical Procedures Manual" # TPM
    UNKNOWN = "Неизвестный тип"


@dataclass
class Process:
    """Бизнес-процесс СМК"""
    code: str              # Код процесса (М1, Б7, В4)
    group: ProcessGroup    # Группа процессов
    name: str              # Название процесса
    subprocesses: List[str] = field(default_factory=list)
    responsible: Optional[str] = None
    
    @property
    def full_code(self) -> str:
        """Полный код с группой"""
        return self.code


@dataclass
class Document:
    """Документ СМК"""
    code: str               # Код документа (ДП-М1.020-06)
    doc_type: DocumentType  # Тип документа
    process_code: str       # Код процесса (М1.020)
    version: str            # Версия (06)
    name: Optional[str] = None      # Название документа
    file_path: Optional[str] = None # Путь к файлу
    
    @property
    def process_group(self) -> ProcessGroup:
        """Определить группу процесса из кода"""
        if not self.process_code:
            return ProcessGroup.UNKNOWN
        
        first_char = self.process_code[0].upper()
        
        # Русские буквы → латинские
        mapping = {
            'М': ProcessGroup.M, 'M': ProcessGroup.M,
            'Б': ProcessGroup.B, 'B': ProcessGroup.B,
            'В': ProcessGroup.V, 'V': ProcessGroup.V,
        }
        
        return mapping.get(first_char, ProcessGroup.UNKNOWN)
    
    @property
    def process_id(self) -> str:
        """ID процесса (например М1 из М1.020)"""
        if not self.process_code:
            return ""
        parts = self.process_code.split('.')
        return parts[0] if parts else ""


@dataclass
class GraphNode:
    """Узел графа"""
    id: str
    label: str
    node_type: str  # 'process_group', 'process', 'document'
    data: Dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """Связь в графе"""
    source: str
    target: str
    edge_type: str  # 'hierarchy', 'reference', 'responsibility'
    data: Dict = field(default_factory=dict)


@dataclass 
class DocumentGraph:
    """Граф документов"""
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
    def add_node(self, node: GraphNode):
        """Добавить узел"""
        if not any(n.id == node.id for n in self.nodes):
            self.nodes.append(node)
    
    def add_edge(self, edge: GraphEdge):
        """Добавить связь"""
        self.edges.append(edge)
    
    def to_cytoscape_json(self) -> Dict:
        """Конвертировать в формат Cytoscape.js"""
        elements = []
        
        # Nodes
        for node in self.nodes:
            elements.append({
                "data": {
                    "id": node.id,
                    "label": node.label,
                    "type": node.node_type,
                    **node.data
                }
            })
        
        # Edges
        for edge in self.edges:
            elements.append({
                "data": {
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.edge_type,
                    **edge.data
                }
            })
        
        return {
            "elements": elements,
            "metadata": self.metadata
        }
