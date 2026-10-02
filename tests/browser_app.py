"""Local browser-test API. All model traffic stays in this deterministic test double."""

import asyncio
from dataclasses import replace
from pathlib import Path

from backend.config import Settings
from backend.main import create_app
from backend.ollama import ModelUnavailable
from .conftest import FakeModel


class BrowserModel(FakeModel):
    async def chat(self, messages, temperature):
        question = messages[-1]["content"].rsplit("Câu hỏi:", 1)[-1]
        if "chậm" in question:
            for _ in range(50):
                await asyncio.sleep(0.1)
                yield {"message": {"content": "Đang trả lời… "}, "done": False}
        else:
            for token in ["Atlas ", "dùng ", "SQLite ", "để lưu dữ liệu ", "[1]."]:
                await asyncio.sleep(0.1)
                yield {"message": {"content": token}, "done": False}
        if "lỗi" in question:
            raise ModelUnavailable("Lỗi model giả trong browser test.")
        yield {"message": {"content": ""}, "done": True}


app = create_app(replace(Settings(), database_path=Path("test-results/browser-tests.db")), BrowserModel())
