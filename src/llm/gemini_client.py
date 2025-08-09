from typing import List, Dict
import google.generativeai as genai
from src.config import GEMINI_API_KEY

def get_gemini(model_name: str = "gemini-1.5-flash"):
    """
    Khởi tạo client Gemini (ưu tiên model rẻ/nhanh). 
    Lưu ý: đảm bảo bạn đã đặt GEMINI_API_KEY trong .env
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is empty. Set it in your .env before calling Gemini.")
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(model_name)

SYSTEM_PROMPT = (
    "Bạn là trợ lý chỉ trả lời dựa trên các đoạn văn bản được cung cấp từ cuốn sách. "
    "Nếu thông tin không xuất hiện trong tài liệu, hãy nói rõ là không tìm thấy và không suy đoán. "
    "Luôn trích dẫn trang/chapter từ metadata nếu có."
)

def answer_with_context_gemini(query: str, contexts: List[Dict[str, str]], model_name: str = "gemini-1.5-flash") -> str:
    """
    contexts: list of dicts like {"text": ..., "page": ..., "chapter": ...}
    """
    model = get_gemini(model_name)
    # Chuẩn hoá context thành một chuỗi an toàn
    ctx_lines = []
    for c in contexts:
        page = c.get("page", "")
        chap = c.get("chapter", "")
        prefix = f"[tr.{page}{', ' + chap if chap else ''}] "
        ctx_lines.append(prefix + c.get("text", ""))
    ctx_block = "\n\n".join(ctx_lines[:8])  # hạn chế số đoạn để tránh quá dài

    prompt = f"""{SYSTEM_PROMPT}

Câu hỏi: {query}

Ngữ cảnh:
{ctx_block}

Yêu cầu đầu ra:
- Trả lời ngắn gọn, đúng trọng tâm.
- Chèn citation dạng (tr. X, Chương: Y) tương ứng các câu.
- Nếu ngữ cảnh không đủ, nói rõ “Không tìm thấy trong tài liệu.”
"""
    resp = model.generate_content(prompt)
    return resp.text.strip() if hasattr(resp, "text") and resp.text else ""
