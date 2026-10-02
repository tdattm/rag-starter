from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv("DATABASE_PATH", "data/atlas.db"))
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "qwen2.5:3b")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "bge-m3")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    chunk_size: int = 1100
    chunk_overlap: int = 160
    max_chunks_per_document: int = 1500
    max_total_chunks: int = 15000
    frontend_path: Path = Path("frontend/dist")

    def __post_init__(self):
        if not 1 <= self.max_upload_mb <= 100:
            raise ValueError("MAX_UPLOAD_MB phải nằm trong khoảng 1–100.")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap phải nhỏ hơn chunk_size và không âm.")
        if self.chunk_size < 100 or self.max_chunks_per_document < 1 or self.max_total_chunks < 1:
            raise ValueError("Cấu hình giới hạn tài liệu không hợp lệ.")
