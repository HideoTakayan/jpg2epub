import os
import re
import sys
import threading
import traceback
from pathlib import Path
import io

import PIL.Image
from PIL import ImageChops, ImageEnhance
import concurrent.futures

try:
    import pytesseract
    from pypdf import PdfWriter, PdfReader
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from core.ePubMaker import filter_images
from core import cv2_filters


class PdfMaker(threading.Thread):
    def __init__(
            self,
            master,
            input_dir,
            file,
            name,
            grayscale,
            max_width,
            max_height,
            quality=100,
            rtl=False,
            auto_crop=False,
            split_spreads=False,
            cleanup_dir=None,
            progress=None,
            page_size='fit',
            margin=0,
            binarize=False,
            use_ocr=False,
            ai_upscale=False,
            deskew_crop=False,
            guided_view=False):
        threading.Thread.__init__(self)
        self.master = master
        self.progress = None
        if self.master:
            self.progress = master
        elif progress:
            self.progress = progress
        self.dir = input_dir
        self.file = file
        self.name = name
        self.stop_event = False

        self.grayscale = grayscale
        self.max_width = max_width
        self.max_height = max_height
        self.quality = quality
        self.rtl = rtl
        self.auto_crop = auto_crop
        self.split_spreads = split_spreads
        self.cleanup_dir = cleanup_dir
        self.page_size = page_size
        self.margin = margin
        self.binarize = binarize
        self.use_ocr = use_ocr
        self.ai_upscale = ai_upscale
        self.deskew_crop = deskew_crop
        self.guided_view = guided_view
        self.image_files: list[str] = []

    def run(self):
        try:
            self.working = True

            self.working = True

            assert os.path.isdir(
                self.dir), "The given directory does not exist!"
            assert self.name, "No name given!"

            self.make_pdf()

            if self.master is None:
                print("\nPDF created")
            else:
                self.master.generic_queue.put(lambda: self.master.stop(1))

        except Exception as e:
            if not isinstance(e, StopException):
                if self.master is not None:
                    error_msg = str(e)
                    self.master.generic_queue.put(
                        lambda: self.master.showerror(
                            "Error encountered",
                            f"The following error was thrown:\n{error_msg}"))
                    # Reset GUI state so the user can try again
                    self.master.generic_queue.put(lambda: self.master.stop(0))
                else:
                    print("Error encountered:", file=sys.stderr)
                    traceback.print_exc()
            try:
                if os.path.isfile(self.file):
                    os.remove(self.file)
            except OSError:
                pass
        finally:
            if self.cleanup_dir and os.path.exists(self.cleanup_dir):
                import shutil
                shutil.rmtree(self.cleanup_dir, ignore_errors=True)

    def make_pdf(self):
        self.gather_images()
        if not self.image_files:
            raise Exception("No images found in the directory.")
        self.write_pdf()

    def gather_images(self):
        # Lấy toàn bộ ảnh hợp lệ trong thư mục
        for dir_path, dir_names, filenames in os.walk(self.dir):
            dir_names.sort(
                key=lambda text: [
                    (int(c) if c.isdigit() else c)
                    for c in re.split(r'(\d+)', text)])

            for x, _, _ in filter_images(filenames):
                self.image_files.append(str(Path(dir_path) / x))

    def process_image(self, img_path: str) -> list[PIL.Image.Image]:
        image_data = PIL.Image.open(img_path)

        # PDF không hỗ trợ kênh Alpha (trong suốt), ép kiểu về RGB để tránh lỗi khi lưu
        if image_data.mode in ("RGBA", "P"):
            image_data = image_data.convert("RGB")

        # Xén viền trắng (Auto Crop)
        if self.auto_crop:
            bg = PIL.Image.new(image_data.mode, image_data.size, image_data.getpixel((0, 0)))
            diff = ImageChops.difference(image_data, bg)
            bbox = diff.getbbox()
            if bbox:
                image_data = image_data.crop(bbox)

        images = []
        img = image_data
        
        if self.deskew_crop:
            img = cv2_filters.deskew_and_crop(img)
            
        if self.ai_upscale:
            img = cv2_filters.ai_upscale(img)

        # Cắt trang đôi
        width, height = img.size
        img_list = []
        if self.split_spreads and width > height:
            mid = width // 2
            left = img.crop((0, 0, mid, height))
            right = img.crop((mid, 0, width, height))
            if self.rtl:
                img_list = [(img, right), (img, left)]
            else:
                img_list = [(img, left), (img, right)]
        else:
            img_list = [(img, img)]
                
        # Chế độ Guided View (Ghi đè luôn cả cắt trang đôi)
        if self.guided_view:
            panels = cv2_filters.guided_view_panels(img, self.rtl)
            # Đóng gói lại thành format tuple giống split spreads
            img_list = [(img, p) for p in panels]

        processed_images = []
        for orig_img, sub_img in img_list:
            img = sub_img
            w, h = img.size
            should_grayscale = self.grayscale and img.mode != "L"
            
            if self.page_size in ('a4', 'letter'):
                # Kích thước chuẩn 150 DPI cho A4/Letter
                if self.page_size == 'a4':
                    page_w, page_h = 1240, 1754
                else: # letter
                    page_w, page_h = 1275, 1650
                    
                target_w = page_w - 2 * self.margin
                target_h = page_h - 2 * self.margin
                
                # Co giãn ảnh cho vừa trang
                scale = min(target_w / w, target_h / h)
                new_w, new_h = int(w * scale), int(h * scale)
                img = img.resize((new_w, new_h), resample=PIL.Image.Resampling.LANCZOS)
                
                # Tạo nền trắng và dán ảnh vào giữa
                canvas = PIL.Image.new("RGB", (page_w, page_h), (255, 255, 255))
                offset_x = (page_w - new_w) // 2
                offset_y = (page_h - new_h) // 2
                canvas.paste(img, (offset_x, offset_y))
                img = canvas
            else:
                should_resize = (self.max_width and self.max_width < w) or (self.max_height and self.max_height < h)
                if should_resize:
                    width_scale = w / self.max_width if self.max_width else 1.0
                    height_scale = h / self.max_height if self.max_height else 1.0
                    scale = max(width_scale, height_scale)
                    img = img.resize(
                        (int(w / scale), int(h / scale)),
                        resample=PIL.Image.Resampling.LANCZOS
                    )

            if should_grayscale:
                img = img.convert("L")

            if self.binarize:
                if img.mode != "L":
                    img = img.convert("L")
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(2.0)
                img = img.point(lambda p: 255 if p > 128 else 0, mode='1')

            processed_images.append(img)

        return processed_images

    def write_pdf(self):
        if self.progress:
            self.progress.progress_set_maximum(len(self.image_files))
            self.progress.progress_set_value(0)

        # Xử lý ảnh đầu tiên trước để mồi (khởi tạo PDF)
        first_images = self.process_image(self.image_files[0])
        first_image = first_images[0]

        # Generator chạy lười (lazy) cho các ảnh còn lại
        def img_gen():
            # Nếu ảnh mồi bị cắt làm đôi, đẩy nốt nửa kia ra
            for img in first_images[1:]:
                yield img

            # Xử lý đa luồng với cửa sổ trượt (tránh nổ RAM)
            with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
                pending = []
                idx = 1
                total = len(self.image_files)

                while idx < total or pending:
                    # Bơm task liên tục nhưng giới hạn bằng 2 lần số CPU
                    while idx < total and len(pending) < (os.cpu_count() or 1) * 2:
                        self.check_is_stopped()
                        future = executor.submit(self.process_image, self.image_files[idx])
                        pending.append(future)
                        idx += 1

                    if pending:
                        # Đợi task cũ nhất chạy xong
                        oldest = pending.pop(0)
                        results = oldest.result()
                        for img in results:
                            yield img
                        
                        if self.progress:
                            self.progress.progress_set_value(idx - len(pending))

        if self.progress:
            self.progress.progress_set_value(1)

        # Gom tất cả lại xuất ra PDF
        ocr_failed = False
        if self.use_ocr and OCR_AVAILABLE:
            try:
                merger = PdfWriter()
                # Khởi tạo trang bìa
                pdf_bytes = pytesseract.image_to_pdf_or_hocr(first_image, extension='pdf')
                merger.append(PdfReader(io.BytesIO(pdf_bytes)))
                
                # Chạy hết generator và build file
                for img in img_gen():
                    pdf_bytes = pytesseract.image_to_pdf_or_hocr(img, extension='pdf')
                    merger.append(PdfReader(io.BytesIO(pdf_bytes)))
                    
                with open(self.file, "wb") as fp:
                    merger.write(fp)
            except Exception as e:
                print("OCR failed or Tesseract not installed, falling back to standard PDF:", e)
                ocr_failed = True
        else:
            ocr_failed = True

        if ocr_failed:
            # Lưu ý: append_images nhận generator nên RAM sẽ không bị quá tải
            if self.quality < 100:
                first_image.save(
                    self.file,
                    "PDF",
                    resolution=100.0,
                    save_all=True,
                    quality=self.quality,
                    optimize=True,
                    append_images=img_gen()
                )
            else:
                first_image.save(
                    self.file,
                    "PDF",
                    resolution=100.0,
                    save_all=True,
                    append_images=img_gen()
                )

        if self.progress:
            self.progress.progress_set_value(len(self.image_files))

    def stop(self):
        self.stop_event = True

    def check_is_stopped(self):
        if self.stop_event:
            raise StopException()


class StopException(Exception):
    def __str__(self):
        return "The PDF creator has been stopped!"
