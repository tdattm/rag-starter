"""Run against the real Docker stack; creates and removes its own isolated fixtures."""

import argparse
import json
import time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:3000")
    args = parser.parse_args()
    document_id = conversation_id = None
    with httpx.Client(base_url=args.url, timeout=600) as client:
        try:
            status = client.get("/api/status").json()
            assert status["llm_ready"] and status["embedding_ready"], status
            content = "Atlas smoke fixture: Mã dự án là ATLAS-742. Ngày bắt đầu là 02/10/2026. Kho dữ liệu là SQLite."
            response = client.post(
                "/api/documents", files={"file": ("atlas-smoke.txt", content.encode(), "text/plain")}
            )
            response.raise_for_status()
            assert not response.json()["duplicate"], (
                "Smoke fixture already exists; remove it before rerunning."
            )
            document_id = response.json()["document"]["id"]
            dimension = response.json()["document"]["dimension"]
            query = {"query": "Mã dự án Atlas là gì?", "document_ids": [document_id]}
            result = client.post("/api/search", json=query)
            result.raise_for_status()
            assert "ATLAS-742" in result.json()["results"][0]["text"]
            conversation_id = client.post("/api/conversations").json()["id"]
            events, answer = [], ""
            start = time.perf_counter()
            with client.stream("POST", f"/api/conversations/{conversation_id}/chat", json=query) as response:
                response.raise_for_status()
                kind = ""
                for line in response.iter_lines():
                    if line.startswith("event: "):
                        kind = line[7:]
                        events.append(kind)
                    if line.startswith("data: ") and kind == "token":
                        answer += json.loads(line[6:])["content"]
            assert "error" not in events and "done" in events, events
            assert "ATLAS-742" in answer, answer
            messages = client.get(f"/api/conversations/{conversation_id}").json()["messages"]
            assert len(messages) == 2 and messages[-1]["sources"][0]["document_id"] == document_id
            assert "ATLAS-742" in client.get(f"/api/conversations/{conversation_id}/export").text
            print(
                json.dumps(
                    {
                        "result": "PASS",
                        "models": [status["llm_model"], status["embedding_model"]],
                        "embedding_dimension": dimension,
                        "chat_seconds": round(time.perf_counter() - start, 1),
                        "answer": answer,
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            if conversation_id:
                client.delete(f"/api/conversations/{conversation_id}").raise_for_status()
            if document_id:
                client.delete(f"/api/documents/{document_id}").raise_for_status()


if __name__ == "__main__":
    main()
