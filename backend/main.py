import asyncio
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import threading
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .ingestion import fetch_web, parse_file
from .ollama import ModelUnavailable, Ollama
from .rag import RAG, build_prompt
from .store import Store

logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    top_k: int = Field(default=4, ge=1, le=8)
    min_score: float = Field(default=0.3, ge=0, le=1, allow_inf_nan=False)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value):
        if not value.strip():
            raise ValueError("Câu hỏi không được để trống.")
        return value.strip()


class ChatRequest(SearchRequest):
    temperature: float = Field(default=0.2, ge=0, le=1, allow_inf_nan=False)


class URLRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


def create_app(settings: Settings | None = None, model=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings.database_path)
        app.state.model = model or Ollama(settings)
        app.state.rag = RAG(settings, app.state.store, app.state.model)
        app.state.active_chats = set()
        app.state.chat_lock = threading.Lock()
        yield

    app = FastAPI(title="Atlas API", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(ModelUnavailable)
    async def model_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def input_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        with app.state.store.connect() as db:
            db.execute("SELECT 1")
        return {"status": "ok"}

    @app.get("/api/status")
    def status():
        return {
            **app.state.model.models(),
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "max_upload_mb": settings.max_upload_mb,
        }

    @app.get("/api/documents")
    def documents():
        return app.state.store.documents()

    @app.post("/api/documents", status_code=201)
    def upload(file: UploadFile = File(...)):
        try:
            content = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
            if len(content) > settings.max_upload_mb * 1024 * 1024:
                raise HTTPException(413, f"Mỗi tệp tối đa {settings.max_upload_mb} MB.")
            name = Path((file.filename or "document.txt").replace("\\", "/")).name
            passages, mime = parse_file(name, content)
            return app.state.rag.ingest(name, name, mime, len(content), passages)
        finally:
            file.file.close()

    @app.post("/api/documents/url", status_code=201)
    def import_url(payload: URLRequest):
        passages, title, url, size = fetch_web(payload.url, settings.max_upload_mb * 1024 * 1024)
        return app.state.rag.ingest(title, url, "text/html", size, passages)

    @app.delete("/api/documents/{document_id}", status_code=204)
    def delete_document(document_id: str):
        with app.state.rag.library_lock, app.state.store.connect() as db:
            if not db.execute("DELETE FROM documents WHERE id=?", (document_id,)).rowcount:
                raise HTTPException(404, "Không tìm thấy tài liệu.")

    @app.get("/api/documents/{document_id}/chunks")
    def document_chunks(document_id: str, offset: int = 0):
        if offset < 0:
            raise HTTPException(422, "Offset phải không âm.")
        with app.state.store.connect() as db:
            if not db.execute("SELECT id FROM documents WHERE id=?", (document_id,)).fetchone():
                raise HTTPException(404, "Không tìm thấy tài liệu.")
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id, text, page FROM chunks WHERE document_id=? ORDER BY rowid LIMIT 20 OFFSET ?",
                    (document_id, offset),
                )
            ]

    @app.post("/api/search")
    def search(payload: SearchRequest):
        start = time.perf_counter()
        results = app.state.rag.search(payload.query, payload.document_ids, payload.top_k, payload.min_score)
        return {"results": results, "duration_ms": round((time.perf_counter() - start) * 1000)}

    @app.get("/api/conversations")
    def conversations():
        return app.state.store.conversations()

    @app.post("/api/conversations", status_code=201)
    def create_conversation():
        return app.state.store.create_conversation()

    def require_conversation(conversation_id):
        conversation = app.state.store.conversation(conversation_id)
        if conversation is None:
            raise HTTPException(404, "Không tìm thấy cuộc trò chuyện.")
        return conversation

    @app.get("/api/conversations/{conversation_id}")
    def conversation(conversation_id: str):
        return require_conversation(conversation_id)

    @app.patch("/api/conversations/{conversation_id}")
    def rename_conversation(conversation_id: str, payload: RenameRequest):
        require_conversation(conversation_id)
        if not payload.title.strip():
            raise HTTPException(422, "Tiêu đề không được để trống.")
        with app.state.store.connect() as db:
            db.execute(
                "UPDATE conversations SET title=? WHERE id=?", (payload.title.strip(), conversation_id)
            )
        return require_conversation(conversation_id)

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str):
        with app.state.chat_lock:
            if conversation_id in app.state.active_chats:
                raise HTTPException(409, "Hãy dừng câu trả lời trước khi xóa cuộc trò chuyện.")
            require_conversation(conversation_id)
            with app.state.store.connect() as db:
                db.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))

    @app.get("/api/conversations/{conversation_id}/export")
    def export_conversation(conversation_id: str):
        item = require_conversation(conversation_id)
        lines = [f"# {item['title']}", "", f"Xuất từ Atlas · {settings.llm_model}", ""]
        for message in item["messages"]:
            lines.extend(
                ["## " + ("Bạn" if message["role"] == "user" else "Atlas"), "", message["content"], ""]
            )
            if message["status"] != "complete":
                lines.extend([f"_Trạng thái: {message['status']}_", ""])
            for source in message["sources"]:
                lines.append(
                    f"[{source['citation']}] {source['name']} — {source['source']}"
                    + (f" · trang {source['page']}" if source["page"] else "")
                )
            lines.append("")
        from fastapi.responses import Response

        return Response(
            "\n".join(lines),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="atlas-conversation.md"'},
        )

    @app.post("/api/conversations/{conversation_id}/chat")
    async def chat(conversation_id: str, payload: ChatRequest):
        with app.state.chat_lock:
            if conversation_id in app.state.active_chats:
                raise HTTPException(409, "Cuộc trò chuyện đang tạo câu trả lời.")
            previous = require_conversation(conversation_id)
            app.state.active_chats.add(conversation_id)
        try:
            sources = await run_in_threadpool(
                app.state.rag.search, payload.query, payload.document_ids, payload.top_k, payload.min_score
            )
            if sources:
                readiness = await run_in_threadpool(app.state.model.models)
                if not readiness["llm_ready"]:
                    raise ModelUnavailable("Qwen2.5:3b chưa sẵn sàng. Chờ tải model hoàn tất.")
            app.state.store.message(conversation_id, "user", payload.query)
        except BaseException:
            app.state.active_chats.discard(conversation_id)
            raise

        def event(kind, data):
            return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        async def stream():
            content, state = "", "interrupted"
            start = time.perf_counter()
            try:
                yield event("sources", sources)
                if not sources:
                    content = "Mình chưa tìm thấy đoạn tài liệu phù hợp để trả lời. Hãy thêm tài liệu vào thư viện, chọn lại phạm vi hoặc diễn đạt câu hỏi cụ thể hơn."
                    yield event("token", {"content": content})
                else:
                    async for item in app.state.model.chat(
                        build_prompt(payload.query, previous["messages"], sources), payload.temperature
                    ):
                        token = item.get("message", {}).get("content", "")
                        if token:
                            content += token
                            yield event("token", {"content": token})
                if not content.strip():
                    raise ModelUnavailable("Model trả về câu trả lời rỗng. Vui lòng thử lại.")
                state = "complete"
                saved = app.state.store.message(conversation_id, "assistant", content, sources, state)
                yield event(
                    "done",
                    {"message_id": saved["id"], "duration_ms": round((time.perf_counter() - start) * 1000)},
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state = "error"
                logger.exception("Chat generation failed")
                message = (
                    str(exc)
                    if isinstance(exc, ModelUnavailable)
                    else "Có lỗi khi tạo câu trả lời. Vui lòng thử lại."
                )
                yield event("error", {"message": message})
            finally:
                try:
                    if state != "complete":
                        app.state.store.message(
                            conversation_id,
                            "assistant",
                            content or "Câu trả lời đã bị gián đoạn.",
                            sources,
                            state,
                        )
                finally:
                    app.state.active_chats.discard(conversation_id)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if settings.frontend_path.is_dir():
        assets = settings.frontend_path / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "API endpoint không tồn tại.")
            target = (settings.frontend_path / path).resolve()
            if path and target.is_relative_to(settings.frontend_path.resolve()) and target.is_file():
                return FileResponse(target)
            return FileResponse(settings.frontend_path / "index.html")

    return app


app = create_app()
