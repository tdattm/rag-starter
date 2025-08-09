from typing import List
import re

def clean_text(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n\n", s)
    return s.strip()

def split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

def chunk_by_tokens(paragraphs: List[str], max_tokens: int = 600, overlap: int = 100) -> List[str]:
    chunks, buf, count = [], [], 0
    for p in paragraphs:
        n = len(p.split())
        if count + n <= max_tokens:
            buf.append(p)
            count += n
        else:
            if buf:
                chunk = "\n\n".join(buf)
                chunks.append(chunk)
                if overlap > 0:
                    tail = " ".join(chunk.split()[-overlap:])
                    buf = [tail, p]
                    count = len(tail.split()) + n
                else:
                    buf, count = [p], n
            else:
                buf, count = [p], n
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks
