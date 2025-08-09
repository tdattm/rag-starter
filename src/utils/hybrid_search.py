from typing import List, Dict, Any
from rank_bm25 import BM25Okapi

class BM25Index:
    def __init__(self, docs: List[str]):
        tokenized = [d.split() for d in docs]
        self.bm25 = BM25Okapi(tokenized)
        self.docs = docs

    def search(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        tokenized_query = query.split()
        scores = self.bm25.get_scores(tokenized_query)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:k]
        return [{"doc_id": i, "score": s, "text": self.docs[i]} for i, s in ranked]
