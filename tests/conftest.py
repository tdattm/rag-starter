from dataclasses import replace
import re

from fastapi.testclient import TestClient
import pytest

from backend.config import Settings
from backend.main import create_app


class FakeModel:
    def __init__(self):
        self.embed_calls = 0
        self.chat_calls = 0
        self.fail_embed = False
        self.fail_chat = False
        self.ready = True
        self.last_messages = []

    def models(self):
        return {"connected": True, "llm_ready": self.ready, "embedding_ready": True}

    def embed(self, texts):
        from backend.ollama import ModelUnavailable

        self.embed_calls += 1
        if self.fail_embed:
            raise ModelUnavailable("Embedding unavailable")
        return [
            [
                1.0 if re.search(r"atlas|rag", text, re.I) else 0.0,
                1.0 if "toán" in text.casefold() else 0.0,
                0.05,
            ]
            for text in texts
        ]

    async def chat(self, messages, temperature):
        from backend.ollama import ModelUnavailable

        self.chat_calls += 1
        self.last_messages = messages
        yield {"message": {"content": "Atlas chạy "}, "done": False}
        if self.fail_chat:
            raise ModelUnavailable("Generation interrupted")
        yield {"message": {"content": "cục bộ [1]."}, "done": True}


@pytest.fixture
def client(tmp_path):
    settings = replace(
        Settings(), database_path=tmp_path / "test.db", frontend_path=tmp_path / "missing", max_upload_mb=1
    )
    model = FakeModel()
    app = create_app(settings, model)
    with TestClient(app) as test_client:
        test_client.model = model
        test_client.app_state = app.state
        yield test_client
