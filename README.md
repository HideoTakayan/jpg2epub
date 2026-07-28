# 📚 Images to ePub, PDF & CBZ Converter (Advanced AI Edition)

Một công cụ siêu cấp, mạnh mẽ giúp bạn dễ dàng chuyển đổi các thư mục chứa hình ảnh (ảnh chụp, truyện tranh, manga, album ảnh...) thành sách điện tử định dạng **ePub**, **PDF** hoặc **CBZ** chất lượng cao. Công cụ được trang bị kiến trúc đa luồng siêu tốc và các công nghệ **Trí Tuệ Nhân Tạo (AI)** cùng Computer Vision tiên tiến để tối ưu hóa hình ảnh.

## ✨ Các Nâng Cấp Công Nghệ Cốt Lõi Mới
- ⚡ **Kiến trúc Đa luồng (Multiprocessing)**: Sử dụng toàn bộ sức mạnh nhân CPU để xử lý hàng loạt ảnh (Resize, Binarize, Crop) nhanh gấp nhiều lần.
- 🤖 **AI Upscale x2 (Super Resolution)**: Tích hợp mạng nơ-ron sâu (`FSRCNN`) của OpenCV để phục chế và nhân đôi độ phân giải cho truyện scan cũ bị mờ mà không gây vỡ hạt.
- 📐 **Nắn thẳng ảnh & Xén viền thông minh**: Tự động phát hiện góc nghiêng của trang giấy scan, nắn thẳng lại và xén sát viền nội dung (Deskew & Smart Crop) bằng Computer Vision.
- 📱 **Cắt Khung Truyện (Guided View)**: Thuật toán nhận diện và bóc tách từng khung thoại trong trang truyện (Panel Detection), tối ưu cho trải nghiệm đọc lướt trên di động.
- 🔍 **Nhận dạng văn bản OCR**: Tạo Text Layer tàng hình đè lên PDF, giúp PDF có khả năng tìm kiếm và bôi đen chữ (cần cài đặt Tesseract).
- 🗜️ **Nén WebP Tiên Tiến**: Chuyển đổi định dạng sang WebP trong lúc xuất ePub để giảm dung lượng file xuống 50% mà vẫn giữ nguyên chất lượng.
- ✨ **Khử nhiễu nét chữ (Binarize)**: Tẩy trắng nền giấy ố vàng và làm đậm chữ đen, biến bản scan thành bản digital nét căng.
- 🌍 **Tích hợp OPDS Catalog Server**: Kho truyện tự động phát sóng qua Wifi nội bộ. Dễ dàng dùng App đọc sách (Moon+ Reader, KyBook) để duyệt và tải không dây!

## 📁 Cấu Trúc Dự Án Chuyên Nghiệp
Dự án được phân chia gọn gàng theo chuẩn mã nguồn mở:
- `core/`: Chứa toàn bộ lõi thuật toán AI (Upscale, Deskew), Computer Vision và các class xử lý PDF/ePub/CBZ đa luồng.
- `web/`: Chứa giao diện Web UI và máy chủ OPDS.
- `Images_To_ePub.py`: File thực thi trực tiếp bằng giao diện dòng lệnh (CLI).

## 🌟 Các Tính Năng Kế Thừa Hữu Ích
- 📖 **Trình bày cấu trúc thông minh**: Tự động nhận diện mỗi thư mục con là một chương (chapter) và tạo Mục lục (Table of Contents).
- 🎨 **Tự động nhận diện ảnh bìa**: Hình ảnh có chứa từ `cover` trong tên sẽ làm ảnh bìa.
- ✂️ **Cắt trang đôi (Split Spreads)**: Cắt các trang truyện đôi (kích thước ngang lớn) thành hai trang dọc.
- 🇯🇵 **Manga Mode**: Hỗ trợ lật trang từ phải sang trái (RTL).

## ⚙️ Cài Đặt

Yêu cầu máy tính đã cài đặt **Python 3.10** trở lên.

1. Clone thư mục dự án này về máy của bạn.
2. Cài đặt các thư viện phụ thuộc bằng lệnh:
   ```bash
   pip install -r requirements.txt
   ```

## 🚀 Hướng Dẫn Sử Dụng

### Dùng Giao Diện Web Trực Quan
Mở terminal tại thư mục dự án và chạy:
```bash
python web/server.py
```
Giao diện sẽ khởi động tại địa chỉ `http://127.0.0.1:5000`. 
- Tại đây bạn chỉ cần kéo thả thư mục/ảnh và ấn nút chuyển đổi.
- Để sử dụng **OPDS Server**, hãy điền địa chỉ `http://127.0.0.1:5000/opds` (thay 127.0.0.1 bằng IP mạng LAN của máy bạn) vào phần mềm đọc sách trên điện thoại/iPad.

---
*Chúc bạn có những trải nghiệm tuyệt vời và tạo ra được những cuốn truyện ưng ý nhất với sức mạnh của AI!*
