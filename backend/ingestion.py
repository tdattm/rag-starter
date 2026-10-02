from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import http.client
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from pypdf import PdfReader


@dataclass
class Passage:
    text: str
    page: int | None = None


def parse_file(name: str, content: bytes) -> tuple[list[Passage], str]:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError("PDF có mật khẩu. Hãy mở khóa trước khi tải lên.")
            if len(reader.pages) > 500:
                raise ValueError("Mỗi PDF tối đa 500 trang.")
            passages = [Passage(page.extract_text() or "", i + 1) for i, page in enumerate(reader.pages)]
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Không đọc được PDF. Hãy kiểm tra lại tệp.") from exc
        mime = "application/pdf"
    elif suffix in {".txt", ".md", ".json"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Tệp văn bản phải sử dụng UTF-8.") from exc
        mime = {".txt": "text/plain", ".md": "text/markdown", ".json": "application/json"}[suffix]
        if suffix == ".json":
            try:
                rows = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("JSON không hợp lệ.") from exc
            if (
                not isinstance(rows, list)
                or not rows
                or any(
                    not isinstance(row, dict)
                    or not isinstance(row.get("page_content"), str)
                    or not isinstance(row.get("metadata", {}), dict)
                    for row in rows
                )
            ):
                raise ValueError("JSON cần là danh sách {page_content, metadata}; tương thích src/data.")
            passages = []
            for row in rows:
                metadata = row.get("metadata", {})
                page = metadata.get("page")
                match = re.fullmatch(r"page_(\d+)", str(metadata.get("source", "")))
                if match:
                    page = int(match[1])
                passages.append(
                    Passage(row["page_content"], page if isinstance(page, int) and page > 0 else None)
                )
        else:
            passages = [Passage(text)]
    else:
        raise ValueError("Hỗ trợ PDF, TXT, Markdown và JSON.")
    if not any(p.text.strip() for p in passages):
        raise ValueError("Tệp không có văn bản. PDF dạng ảnh cần OCR trước khi tải lên.")
    return passages, mime


def split_passages(passages: list[Passage], size: int, overlap: int) -> list[Passage]:
    result = []
    for passage in passages:
        text = re.sub(r"\n{3,}", "\n\n", passage.text.replace("\x00", "")).strip()
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                breaks = [
                    text.rfind(separator, start + size // 2, end) for separator in ("\n\n", "\n", ". ", " ")
                ]
                boundary = next((b for b in breaks if b > start), -1)
                if boundary > start:
                    end = boundary + 1
            chunk = text[start:end].strip()
            if chunk:
                result.append(Passage(chunk, passage.page))
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    return result


def fingerprint(passages: list[Passage], model: str) -> str:
    payload = json.dumps([[p.text, p.page] for p in passages], ensure_ascii=False)
    return sha256((model + "\0" + payload).encode()).hexdigest()


def public_address(url: str) -> tuple[object, str]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Nhập URL HTTP/HTTPS công khai, không chứa thông tin đăng nhập.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if port not in {80, 443}:
            raise ValueError("Chỉ hỗ trợ cổng HTTP/HTTPS tiêu chuẩn.")
        addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise ValueError("Không phân giải được địa chỉ trang web hoặc cổng không hợp lệ.") from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Chỉ nhập trang web công khai; địa chỉ nội bộ bị chặn.")
    return parts, addresses[0][4][0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, port: int):
        super().__init__(host, port=port, timeout=20, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def fetch_web(url: str, max_bytes: int) -> tuple[list[Passage], str, str, int]:
    # Pin the validated IP for each hop while retaining TLS hostname verification.
    for _ in range(5):
        parts, address = public_address(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        conn = (
            PinnedHTTPSConnection(parts.hostname, address, port)
            if parts.scheme == "https"
            else http.client.HTTPConnection(address, port, timeout=20)
        )
        try:
            target = parts.path or "/"
            if parts.query:
                target += "?" + parts.query
            conn.request(
                "GET",
                target,
                headers={
                    "Host": parts.netloc,
                    "User-Agent": "AtlasKnowledge/1.0",
                    "Accept-Encoding": "identity",
                },
            )
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Trang web chuyển hướng không hợp lệ.")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f"Trang web trả về HTTP {response.status}.")
            if "text/html" not in response.getheader("Content-Type", ""):
                raise ValueError("URL cần trỏ đến một trang HTML.")
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise ValueError("Trang web vượt giới hạn kích thước.")
            soup = BeautifulSoup(content, "html.parser")
            title = soup.title.get_text(strip=True)[:200] if soup.title else parts.hostname
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()
            root = soup.find("main") or soup.find("article") or soup
            text = root.get_text("\n", strip=True)
            if not text:
                raise ValueError("Trang web không có văn bản đọc được.")
            return [Passage(text)], title, url, len(content)
        except (OSError, UnicodeError, http.client.HTTPException) as exc:
            raise ValueError("Không tải được trang web. Kiểm tra URL hoặc tải lên tệp thay thế.") from exc
        finally:
            conn.close()
    raise ValueError("Trang web chuyển hướng quá nhiều lần.")
