# Phát triển

Yêu cầu Python 3.12+, Node.js 22+ và Docker Desktop. Chạy tại root, trừ các lệnh frontend.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
docker compose up -d ollama models
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Mở terminal thứ hai:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

UI: http://localhost:5173. Vite chuyển tiếp `/api` sang backend; không cần mở CORS.
API docs: http://localhost:8000/docs. Linux/macOS sử dụng `python3 -m venv .venv`, `.venv/bin/python` và `npm`.

## Cấu hình

`.env.example` liệt kê các biến của Compose. Có thể sao chép thành `.env` nếu cần đổi cổng hoặc model.
Backend local đọc biến môi trường của shell; không tự đọc `.env` và không sử dụng API key cũ.

```powershell
$env:OLLAMA_BASE_URL = 'http://localhost:11434'
$env:DATABASE_PATH = 'data/atlas.db'
```

Khi thay embedding model, xóa và nhập lại tài liệu. Backend chặn truy xuất nếu tên model hoặc số chiều vector không khớp.
Tùy chỉnh số nguồn, ngưỡng ngữ nghĩa và temperature trong UI được lưu riêng trên trình duyệt.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check backend tests scripts
cd frontend
npm.cmd run build
npm.cmd exec playwright install chromium
```

Browser tests gọi FastAPI và SQLite thật với model giả có kiểm soát, kiểm tra desktop/mobile, nhập tài liệu,
streaming, trích dẫn, lưu hội thoại và dừng câu trả lời. Không gọi Docker, WSL hoặc model thật.
Khởi động server kiểm thử riêng ở root trước khi chạy Playwright:

```powershell
.\.venv\Scripts\python.exe -m uvicorn tests.browser_app:app --host 127.0.0.1 --port 8001
# Terminal frontend:
$env:ATLAS_BASE_URL = 'http://127.0.0.1:8001'
npm.cmd run test:e2e
```

Database kiểm thử nằm trong `test-results/browser-tests.db`, tách biệt dữ liệu người dùng.
Backend integration tests cũng dùng model giả; các kết quả này không chứng minh chất lượng model thật.

Kiểm thử model thật là bước tùy chọn, chỉ chạy khi chủ động muốn sử dụng Docker và đã tải model:

```powershell
.\.venv\Scripts\python.exe scripts/smoke.py --url http://localhost:3000
```

Script nhập một tài liệu riêng, kiểm tra tìm kiếm, streaming, lịch sử, xuất hội thoại rồi xóa dữ liệu do chính nó tạo.
CI chạy backend tests, lint, build và browser tests; không tải các model lớn.
