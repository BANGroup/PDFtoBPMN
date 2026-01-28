# Document Graph System
# Система построения графа документов по бизнес-процессам СМК

__version__ = "1.1.0"

from .document_structure import (
    DocumentType,
    analyzer,
    detect_headers_footers,
    normalize_text,
    filter_with_report,
    filter_garbage_headings,
    analyze_document_structure,
)

from .docx_parser import (
    Heading,
    ValidationResult,
    extract_structure_docx,
    validate_docx_vs_pdf,
    find_docx_for_pdf,
    extract_doc_code,
)

from .hybrid_parser import (
    ParseResult,
    FilterReport,
    parse_document,
    format_parse_report,
    parse_documents_batch,
    extract_structure_pdf,
)

from .hierarchy_builder import (
    SectionNode,
    RACIEntry,
    DocumentTree,
    build_hierarchy,
    parse_section_number,
    flatten_tree,
    get_nodes_by_level,
    assign_content_from_text,
    export_tree_json,
    export_tree_markdown,
)
