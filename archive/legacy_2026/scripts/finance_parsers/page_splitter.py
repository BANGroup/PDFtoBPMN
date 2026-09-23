"""
Компонент 1: Page Splitter
Разбивает PDF на страницы для обработки
"""

from typing import Iterator, Tuple
import fitz  # PyMuPDF


class PageSplitter:
    """Разбивает PDF на страницы и рендерит в изображения"""
    
    def __init__(self, dpi: int = 300):
        """
        Args:
            dpi: DPI для рендеринга (default: 300)
        """
        self.dpi = dpi
        self.zoom = dpi / 72  # Zoom factor для PyMuPDF
    
    def split_pdf(self, pdf_path: str) -> Iterator[Tuple[int, bytes, dict]]:
        """
        Разбивает PDF на страницы и рендерит в PNG
        
        Args:
            pdf_path: Путь к PDF файлу
        
        Yields:
            tuple: (page_number, image_bytes, metadata)
        """
        doc = fitz.open(pdf_path)
        
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Рендеринг в изображение
                matrix = fitz.Matrix(self.zoom, self.zoom)
                pix = page.get_pixmap(matrix=matrix)
                image_bytes = pix.tobytes("png")
                
                # Метаданные
                metadata = {
                    'page_number': page_num + 1,
                    'width': pix.width,
                    'height': pix.height,
                    'size_bytes': len(image_bytes)
                }
                
                yield (page_num + 1, image_bytes, metadata)
        
        finally:
            doc.close()
