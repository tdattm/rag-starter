import json

import pytest


def upload(client, name="notes.md", content=b"Atlas is a local RAG workspace."):
    return client.post("/api/documents", files={"file": (name, content)})


def create_chat(client):
    return client.post("/api/conversations").json()["id"]


def test_upload_deduplicates_and_preserves_existing_documents(client):
    first = upload(client).json()
    assert first["document"]["chunk_count"] == 1
    second = upload(client, "renamed.md").json()
    assert second["duplicate"] is True
    assert first["document"]["id"] == second["document"]["id"]
    assert client.model.embed_calls == 1
    upload(client, "other.txt", "Tài liệu toán học".encode())
    assert len(client.get("/api/documents").json()) == 2


@pytest.mark.parametrize(
    "name,content",
    [
        ("bad.exe", b"x"),
        ("empty.md", b"  "),
        ("bad.txt", b"\xff"),
        ("broken.json", b"{"),
        ("wrong.json", b"{}"),
        ("broken.pdf", b"not pdf"),
    ],
)
def test_invalid_file_rejected_before_embedding(client, name, content):
    assert upload(client, name, content).status_code == 422
    assert client.model.embed_calls == 0
    assert client.get("/api/documents").json() == []


def test_upload_size_limit_before_embedding(client):
    assert upload(client, content=b"x" * (1024 * 1024 + 1)).status_code == 413
    assert client.model.embed_calls == 0


def test_failed_embedding_does_not_leave_partial_document(client):
    client.model.fail_embed = True
    assert upload(client).status_code == 503
    assert client.get("/api/documents").json() == []


def test_old_json_format_keeps_page_numbers(client):
    content = json.dumps([{"page_content": "Atlas uses bge-m3.", "metadata": {"source": "page_7"}}]).encode()
    doc = upload(client, "old.json", content).json()["document"]
    chunks = client.get(f"/api/documents/{doc['id']}/chunks").json()
    assert chunks[0]["page"] == 7


def test_search_filter_and_stale_id(client):
    atlas = upload(client).json()["document"]
    maths = upload(client, "maths.txt", "Toán học".encode()).json()["document"]
    results = client.post("/api/search", json={"query": "Atlas"}).json()["results"]
    assert results[0]["document_id"] == atlas["id"]
    scoped = client.post("/api/search", json={"query": "Atlas", "document_ids": [maths["id"]]}).json()[
        "results"
    ]
    assert all(item["document_id"] == maths["id"] for item in scoped)
    assert client.post("/api/search", json={"query": "Atlas", "document_ids": ["missing"]}).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"query": " "},
        {"query": "x", "top_k": 0},
        {"query": "x", "top_k": 9},
        {"query": "x", "min_score": 1.1},
        {"query": "x", "unknown": True},
    ],
)
def test_invalid_query_never_calls_model(client, payload):
    assert client.post("/api/search", json=payload).status_code == 422
    assert client.model.embed_calls == 0


def test_stream_sources_history_and_export(client):
    doc = upload(client).json()["document"]
    chat_id = create_chat(client)
    response = client.post(f"/api/conversations/{chat_id}/chat", json={"query": "Atlas là gì?"})
    assert response.status_code == 200
    assert (
        "event: sources" in response.text
        and "event: token" in response.text
        and "event: done" in response.text
    )
    history = client.get(f"/api/conversations/{chat_id}").json()
    assert len(history["messages"]) == 2
    assert history["title"] == "Atlas là gì?"
    assert history["messages"][1]["content"] == "Atlas chạy cục bộ [1]."
    assert history["messages"][1]["sources"][0]["document_id"] == doc["id"]
    exported = client.get(f"/api/conversations/{chat_id}/export")
    assert "Atlas chạy cục bộ [1]." in exported.text
    assert "notes.md" in exported.text
    assert "attachment" in exported.headers["content-disposition"]
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}/chunks").status_code == 404
    assert client.get(f"/api/conversations/{chat_id}").json()["messages"][1]["sources"]


def test_no_sources_does_not_invent_answer_or_call_llm(client):
    chat_id = create_chat(client)
    response = client.post(f"/api/conversations/{chat_id}/chat", json={"query": "Atlas?"})
    assert "chưa tìm thấy" in response.text
    assert client.model.chat_calls == client.model.embed_calls == 0


def test_model_failure_streams_error_and_preserves_partial_answer(client):
    upload(client)
    client.model.fail_chat = True
    chat_id = create_chat(client)
    response = client.post(f"/api/conversations/{chat_id}/chat", json={"query": "Atlas?"})
    assert "event: error" in response.text
    assert "event: done" not in response.text
    message = client.get(f"/api/conversations/{chat_id}").json()["messages"][-1]
    assert message["status"] == "error" and message["content"] == "Atlas chạy "
    assert chat_id not in client.app_state.active_chats


def test_missing_model_returns_503_without_saving_user_message(client):
    upload(client)
    client.model.ready = False
    chat_id = create_chat(client)
    assert client.post(f"/api/conversations/{chat_id}/chat", json={"query": "Atlas?"}).status_code == 503
    assert client.get(f"/api/conversations/{chat_id}").json()["messages"] == []
    assert chat_id not in client.app_state.active_chats


def test_generation_lock_and_deletion_conflict(client):
    chat_id = create_chat(client)
    client.app_state.active_chats.add(chat_id)
    assert client.post(f"/api/conversations/{chat_id}/chat", json={"query": "Atlas?"}).status_code == 409
    assert client.delete(f"/api/conversations/{chat_id}").status_code == 409
    client.app_state.active_chats.clear()
    assert client.delete(f"/api/conversations/{chat_id}").status_code == 204
    assert client.get(f"/api/conversations/{chat_id}").status_code == 404


def test_embedding_model_mismatch_fails_explicitly(client):
    upload(client)
    with client.app_state.store.connect() as db:
        db.execute("UPDATE documents SET embedding_model='other-model'")
    response = client.post("/api/search", json={"query": "Atlas?"})
    assert response.status_code == 422
    assert "model embedding khác" in response.json()["detail"]
    assert client.model.embed_calls == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://localhost",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]",
        "http://2130706433",
        "file:///etc/passwd",
        "http://user:password@example.com",
    ],
)
def test_private_urls_rejected_before_embedding(client, url):
    assert client.post("/api/documents/url", json={"url": url}).status_code == 422
    assert client.model.embed_calls == 0
