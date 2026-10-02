import json
from unittest.mock import patch

import httpx
import pytest

from backend.config import Settings
from backend.ollama import ModelUnavailable, Ollama


@pytest.mark.parametrize("vectors", [[[0, 0]], [[float("inf"), 1]], [[1, 0], [1, 2]], [[]]])
def test_corrupt_embeddings_are_rejected(vectors):
    with patch("backend.ollama.httpx.Client") as client:
        response = client.return_value.__enter__.return_value.post.return_value
        response.json.return_value = {"embeddings": vectors}
        with pytest.raises(ModelUnavailable):
            Ollama(Settings()).embed(["Atlas"])


def test_model_health_reports_missing_models_without_fallback():
    with patch("backend.ollama.httpx.get", side_effect=httpx.ConnectError("offline")):
        assert Ollama(Settings()).models() == {
            "connected": False,
            "llm_ready": False,
            "embedding_ready": False,
        }


def test_chat_premature_eof_is_not_success():
    import asyncio

    async def run():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=json.dumps({"message": {"content": "partial"}, "done": False})
            )
        )
        original_client = httpx.AsyncClient
        with patch(
            "backend.ollama.httpx.AsyncClient",
            side_effect=lambda **kwargs: original_client(transport=transport, **kwargs),
        ):
            with pytest.raises(ModelUnavailable, match="kết thúc"):
                async for _ in Ollama(Settings()).chat([], 0.2):
                    pass

    asyncio.run(run())
