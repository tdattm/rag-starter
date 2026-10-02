from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL,
                    mime TEXT NOT NULL, size INTEGER NOT NULL, fingerprint TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL, embedding_model TEXT NOT NULL, dimension INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    text TEXT NOT NULL, page INTEGER, embedding BLOB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'complete'
                );
                CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id, sequence);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def documents(self) -> list[dict]:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute("""
                SELECT d.*, COUNT(c.id) AS chunk_count FROM documents d
                LEFT JOIN chunks c ON c.document_id=d.id GROUP BY d.id ORDER BY d.created_at DESC
            """)
            ]

    def conversations(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM conversations ORDER BY updated_at DESC")]

    def create_conversation(self) -> dict:
        item = {"id": str(uuid4()), "title": "Cuộc trò chuyện mới", "created_at": now(), "updated_at": now()}
        with self.connect() as db:
            db.execute("INSERT INTO conversations VALUES (:id,:title,:created_at,:updated_at)", item)
        return item

    def conversation(self, conversation_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["messages"] = []
            for message in db.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY sequence", (conversation_id,)
            ):
                item = dict(message)
                item["sources"] = json.loads(item["sources"])
                result["messages"].append(item)
            return result

    def message(self, conversation_id: str, role: str, content: str, sources=None, status="complete") -> dict:
        item = {
            "id": str(uuid4()),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "sources": sources or [],
            "created_at": now(),
            "status": status,
        }
        with self.connect() as db:
            db.execute(
                """INSERT INTO messages (id,conversation_id,role,content,sources,created_at,status)
                VALUES (?,?,?,?,?,?,?)""",
                (
                    item["id"],
                    conversation_id,
                    role,
                    content,
                    json.dumps(item["sources"], ensure_ascii=False),
                    item["created_at"],
                    status,
                ),
            )
            db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), conversation_id))
            if role == "user":
                count = db.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id=? AND role='user'",
                    (conversation_id,),
                ).fetchone()[0]
                if count == 1:
                    db.execute("UPDATE conversations SET title=? WHERE id=?", (content[:64], conversation_id))
        return item
