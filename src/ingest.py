import argparse, os, json
from typing import Dict, List, Tuple
from utils.pdf_loader import extract_text_by_page
from utils.text_preprocess import clean_text, split_paragraphs, chunk_across_pages
from utils.chroma_client import get_chroma_collection

def load_chapter_map(path: str) -> Dict[str, str]:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def resolve_chapter_for_span(start_page: int, end_page: int, chapter_map: Dict[str, str]) -> str:
    """
    chapter_map ví dụ: {"1-16": "Lời mở đầu"}
    Ưu tiên chương chứa start_page; nếu span bắc qua 2 chương, lấy chương của start_page.
    """
    for rng, name in chapter_map.items():
        a, b = rng.split("-")
        try:
            a, b = int(a), int(b)
        except ValueError:
            continue
        if a <= start_page <= b:
            return name
    return ""

def main(pdf_path: str, collection_name: str, max_tokens: int, overlap: int, chapter_map_path: str):
    pages = extract_text_by_page(pdf_path)
    cmap = load_chapter_map(chapter_map_path) if chapter_map_path else {}

    # 1) Gom toàn bộ "đoạn" (có thể là đoạn hoặc câu, tuỳ split_paragraphs)
    page_paragraphs: List[Tuple[int, str]] = []
    for p in pages:
        text = clean_text(p["text"])
        paras = split_paragraphs(text)
        for para in paras:
            page_paragraphs.append((p["page"], para))

    # 2) Chunk xuyên trang
    book_chunks = chunk_across_pages(page_paragraphs, max_tokens=max_tokens, overlap=overlap)

    # 3) Gán metadata & nạp vào Chroma
    all_docs, metadatas, ids = [], [], []
    for idx, ch in enumerate(book_chunks):
        all_docs.append(ch["text"])
        chap = resolve_chapter_for_span(ch["start_page"], ch["end_page"], cmap) if cmap else ""
        metadatas.append({
            "start_page": ch["start_page"],
            "end_page": ch["end_page"],
            "chapter": chap,
            "source": os.path.basename(pdf_path),
        })
        ids.append(f"{ch['start_page']}-{ch['end_page']}-{idx}")

    col = get_chroma_collection(collection_name)
    if all_docs:
        col.add(documents=all_docs, metadatas=metadatas, ids=ids)
        print(f"Ingested {len(all_docs)} chunks into collection '{collection_name}'.")
    else:
        print("No chunks to ingest.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, help="Path to PDF")
    parser.add_argument("--collection", default="prisoners_of_geography")
    parser.add_argument("--max_tokens", type=int, default=600)
    parser.add_argument("--overlap", type=int, default=100)
    parser.add_argument("--chapter_map", default="eval/chapter_map.json")
    args = parser.parse_args()
    main(args.pdf, args.collection, args.max_tokens, args.overlap, args.chapter_map)