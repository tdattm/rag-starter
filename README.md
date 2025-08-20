## Hướng dẫn chạy dự án

### Yêu cầu hệ thống

- Python >= 3.8
- Docker Desktop
- Anaconda 
- pip

### Cài đặt môi trường

1. **Clone dự án**
   ```bash
   git clone https://github.com/tdattm/rag-starter.git
   cd rag-starter
   ```

2. **Cài đặt môi trường**
   - Sử dụng conda để setup môi trường: `conda create -n rag-chatbot python=3.10`
   - Active môi trường: `conda activate rag-chatbot`
   - Cài đặt các thư viện cần thiết: `pip install -r requirements.txxt`
  
=> **Lưu ý**: Cài đặt anaconda trước khi thực hiện bước 2 (nếu chưa có)

3. **Cài đặt và chạy database**
    - Khởi động Docker Desktop
    - Mở Terminal/Command Prompt, chạy lệnh: `docker compose up --build`
  
=> **Lưu ý**: Cài đặt anaconda trước khi thực hiện bước 3 (nếu chưa có)

4. **Cấu hình các API cần thiết**
   - Thêm các API cần thiết vào .env (Khuyến nghị sử dụng gemini API để có thể run nhanh dự án)

5. **Chạy ứng dụng**
    1. Crawl data về local Mở Terminal/Command Prompt, di chuyển vào thư mục src `cd src` và chạy:
    ```python
    python crawl.py
    ```
    2. Seed data vào Milvus:
    ```python
    python seed_data.py
    ```
    3. Run ứng dụng:
    ```python
    streamlit run main.py
    ```