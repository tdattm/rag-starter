from typing import List, Dict, Any
import fitz  # PyMuPDF

def extract_text_by_page(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Trả về danh sách dict: {page (1-based), text}
    - Yêu cầu: PDF có lớp văn bản (không phải ảnh/scan). Nếu là scan, cần OCR trước.
    """
    out = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            out.append({"page": i + 1, "text": text})
    return out
