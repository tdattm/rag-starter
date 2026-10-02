import json
import math
import httpx

from .config import Settings


class ModelUnavailable(RuntimeError):
    pass


class Ollama:
    def __init__(self, settings: Settings):
        self.settings = settings

    def models(self) -> dict:
        try:
            response = httpx.get(f"{self.settings.ollama_base_url}/api/tags", timeout=4)
            response.raise_for_status()
            names = {item["name"] for item in response.json()["models"]}

            def available(name):
                return name in names or f"{name}:latest" in names

            return {
                "connected": True,
                "llm_ready": available(self.settings.llm_model),
                "embedding_ready": available(self.settings.embedding_model),
            }
        except (httpx.HTTPError, ValueError, KeyError):
            return {"connected": False, "llm_ready": False, "embedding_ready": False}

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            with httpx.Client(timeout=httpx.Timeout(600, connect=10)) as client:
                response = client.post(
                    f"{self.settings.ollama_base_url}/api/embed",
                    json={
                        "model": self.settings.embedding_model,
                        "input": texts,
                        "truncate": False,
                        "keep_alive": "5m",
                    },
                )
                response.raise_for_status()
                vectors = response.json()["embeddings"]
                if (
                    len(vectors) != len(texts)
                    or not vectors
                    or any(
                        not v
                        or len(v) != len(vectors[0])
                        or any(not math.isfinite(x) for x in v)
                        or not any(v)
                        for v in vectors
                    )
                ):
                    raise ValueError("Invalid embedding response")
                return vectors
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ModelUnavailable("Không tạo được embedding. Kiểm tra Ollama và model bge-m3.") from exc

    async def chat(self, messages: list[dict], temperature: float):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as client:
                async with client.stream(
                    "POST",
                    f"{self.settings.ollama_base_url}/api/chat",
                    json={
                        "model": self.settings.llm_model,
                        "messages": messages,
                        "stream": True,
                        "options": {"temperature": temperature, "num_ctx": 8192, "num_predict": 1400},
                        "keep_alive": "5m",
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        item = json.loads(line)
                        if item.get("error"):
                            raise ModelUnavailable("Model không thể hoàn thành câu trả lời.")
                        yield item
                        if item.get("done"):
                            return
                    raise ModelUnavailable("Kết nối model kết thúc trước khi trả lời hoàn tất.")
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelUnavailable(
                "Không nhận được câu trả lời. Kiểm tra Ollama và model Qwen2.5:3b."
            ) from exc
