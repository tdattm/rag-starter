from typing import Dict, List, Tuple
import re

def clean_text(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n\n", s)
    return s.strip()

def split_paragraphs(text: str) -> List[str]:
    """
    Tách đoạn bền hơn:
    - Ưu tiên ngắt theo 2 xuống dòng.
    - Nếu không có, fallback ngắt theo dấu câu.
    """
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paras) <= 1:
        # Fallback: cắt theo dấu câu (., !, ?, …) + khoảng trắng
        parts = re.split(r"(?<=[\.\!\?\…])\s+", text)
        paras = [p.strip() for p in parts if p.strip()]
    return paras

# --------- HỖ TRỢ CẮT ĐOẠN DÀI ---------
def split_long_paragraph(p: str, max_tokens: int = 300) -> List[str]:
    """
    Nếu một 'đoạn' quá dài (> max_tokens), cắt tiếp theo câu để giữ mạch.
    """
    sents = re.split(r"(?<=[\.\!\?\…])\s+", p)
    chunks, buf, count = [], [], 0
    for s in sents:
        n = len(s.split())
        if count + n <= max_tokens:
            buf.append(s)
            count += n
        else:
            if buf:
                chunks.append(" ".join(buf))
            buf, count = [s], n
    if buf:
        chunks.append(" ".join(buf))
    return chunks

# --------- CHUNK XUYÊN TRANG ---------
def chunk_across_pages(
    page_paragraphs: List[Tuple[int, str]],
    max_tokens: int = 600,
    overlap: int = 100
) -> List[Dict]:
    """
    Tạo chunk xuyên trang.
    Input: list[(page, paragraph_text)], đã clean & tách đoạn.
    Output: list[{"text": ..., "start_page": int, "end_page": int}]
    """
    chunks = []
    buf: List[Tuple[int, str]] = []
    count = 0

    def flush_chunk():
        nonlocal buf, count
        if not buf:
            return None
        text = "\n\n".join([p for _, p in buf]).strip()
        start_page = min(pg for pg, _ in buf)
        end_page = max(pg for pg, _ in buf)
        chunk = {"text": text, "start_page": start_page, "end_page": end_page}
        # Chuẩn bị overlap cho chunk sau
        if overlap > 0:
            tail_words = " ".join(text.split()[-overlap:])
            buf = [(end_page, tail_words)] if tail_words else []
            count = len(tail_words.split())
        else:
            buf, count = [], 0
        return chunk

    for page, para in page_paragraphs:
        # Nếu đoạn quá dài, cắt tiếp theo câu
        tokens = len(para.split())
        if tokens > max_tokens:
            for sub in split_long_paragraph(para, max_tokens=max_tokens):
                n = len(sub.split())
                if count + n <= max_tokens:
                    buf.append((page, sub))
                    count += n
                else:
                    ch = flush_chunk()
                    if ch: chunks.append(ch)
                    buf, count = [(page, sub)], n
        else:
            if count + tokens <= max_tokens:
                buf.append((page, para))
                count += tokens
            else:
                ch = flush_chunk()
                if ch: chunks.append(ch)
                buf, count = [(page, para)], tokens

    ch = flush_chunk()
    if ch: chunks.append(ch)
    return chunks
