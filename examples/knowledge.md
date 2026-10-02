# Chào mừng đến với Atlas

Atlas là không gian làm việc cá nhân để hỏi đáp và tìm kiếm trong tài liệu của bạn.
Dữ liệu tài liệu, vector embedding và hội thoại được lưu trong SQLite trên máy chủ cục bộ.

## Công nghệ

Qwen2.5:3b tạo câu trả lời bằng tiếng Việt. Model bge-m3 tạo vector embedding cho cả tài liệu và câu hỏi.
Hai model chạy qua Ollama trong Docker. Sau lần tải model ban đầu, hỏi đáp tài liệu không cần API key hay kết nối internet.
Nhập tài liệu từ URL vẫn cần internet. Các tệp PDF dạng ảnh cần OCR trước khi nhập.

## Tìm kiếm và nguồn

Atlas chia tài liệu thành các đoạn khoảng 1.100 ký tự với 160 ký tự chồng lấp.
Tìm kiếm kết hợp cosine similarity và BM25 bằng reciprocal rank fusion với trọng số 70% ngữ nghĩa, 30% từ khóa.
Mỗi câu trả lời kèm các đoạn nguồn để bạn đối chiếu. Model có thể mắc lỗi; nên đọc nguồn trước khi sử dụng kết luận.

## Bắt đầu

Tải lên tài liệu PDF, TXT, Markdown hoặc JSON. Mở cuộc trò chuyện mới và đặt câu hỏi cụ thể.
Bạn có thể giới hạn tài liệu được tìm kiếm, xem nguồn, dừng câu trả lời và xuất hội thoại ra Markdown.
Trang Tìm kiếm cho phép kiểm tra các đoạn được truy xuất trước khi dùng chúng để hỏi đáp.

