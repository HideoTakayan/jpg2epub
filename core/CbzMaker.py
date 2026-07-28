import os
import threading
from pathlib import Path
import io

import PIL.Image
from PIL import ImageChops, ImageEnhance
import concurrent.futures
from zipfile import ZipFile, ZIP_DEFLATED

from core.ePubMaker import filter_images
from core import cv2_filters


class CbzMaker(threading.Thread):
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

            self.make_cbz()

            if self.master is None:
                print()
                print("CBZ created")
            else:
                self.master.generic_queue.put(lambda: self.master.stop(1))

        except Exception as e:
            if not isinstance(e, StopException):
                if self.master is not None:
                    error_msg = str(e)
                    self.master.generic_queue.put(
                        lambda: self.master.showerror(
                            "Có lỗi xảy ra",
                            f"Đã gặp lỗi sau:\n{error_msg}"))
                    # Đặt lại trạng thái giao diện để người dùng thử lại
                    self.master.generic_queue.put(lambda: self.master.stop(0))
                else:
                    print("Có lỗi xảy ra:", file=sys.stderr)
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

    def make_cbz(self):
        self.gather_images()
        if not self.image_files:
            raise Exception("Không tìm thấy ảnh trong thư mục.")
        self.write_cbz()

    def gather_images(self):
        # Quét thư mục và lấy danh sách ảnh hợp lệ
        for dir_path, dir_names, filenames in os.walk(self.dir):
            dir_names.sort(
                key=lambda text: [
                    (int(c) if c.isdigit() else c)
                    for c in re.split(r'(\d+)', text)])

            for x, _, _ in filter_images(filenames):
                self.image_files.append(str(Path(dir_path) / x))

    def process_image(self, img_path: str) -> list[PIL.Image.Image]:
        img = PIL.Image.open(img_path)

        # Chuyển đổi sang RGB
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Xén viền trắng (Auto Crop)
        if self.auto_crop:
            bg = PIL.Image.new(img.mode, img.size, img.getpixel((0, 0)))
            diff = ImageChops.difference(img, bg)
            bbox = diff.getbbox()
            if bbox:
                img = img.crop(bbox)
        
        if self.deskew_crop:
            img = cv2_filters.deskew_and_crop(img)
            
        if self.ai_upscale:
            img = cv2_filters.ai_upscale(img)

        # Cắt trang đôi
        img_list = []
        width, height = img.size
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
            
        # Chế độ Guided View
        if self.guided_view:
            panels = cv2_filters.guided_view_panels(img, self.rtl)
            img_list = [(img, p) for p in panels]

        processed_images = []
        for orig_img, sub_img in img_list:
            img = sub_img
            w, h = img.size
            should_grayscale = self.grayscale and img.mode != "L"
            
            if self.page_size in ('a4', 'letter'):
                if self.page_size == 'a4':
                    page_w, page_h = 1240, 1754
                else:
                    page_w, page_h = 1275, 1650
                    
                target_w = page_w - 2 * self.margin
                target_h = page_h - 2 * self.margin
                
                scale = min(target_w / w, target_h / h)
                new_w, new_h = int(w * scale), int(h * scale)
                img = img.resize((new_w, new_h), resample=PIL.Image.Resampling.LANCZOS)
                
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

    def write_cbz(self):
        if self.progress:
            self.progress.progress_set_maximum(len(self.image_files))
            self.progress.progress_set_value(0)

        # Xử lý ảnh đầu tiên để khởi tạo
        first_images = self.process_image(self.image_files[0])

        # Bộ tạo cho phần còn lại
        def img_gen():
            for img in first_images:
                yield img

            with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
                pending = []
                idx = 1
                total = len(self.image_files)

                while idx < total or pending:
                    # Bơm task liên tục nhưng giới hạn số lượng để tránh quá tải RAM
                    while idx < total and len(pending) < (os.cpu_count() or 1) * 2:
                        self.check_is_stopped()
                        future = executor.submit(self.process_image, self.image_files[idx])
                        pending.append(future)
                        idx += 1

                    if pending:
                        oldest = pending.pop(0)
                        # Đợi task cũ nhất chạy xong
                        results = oldest.result()
                        for img in results:
                            yield img
                        
                        if self.progress:
                            self.progress.progress_set_value(idx - len(pending))

        if self.progress:
            self.progress.progress_set_value(1)

        # Save all images to CBZ (ZIP)
        padding_width = len(str(len(self.image_files) * (2 if self.split_spreads else 1)))
        
        with ZipFile(self.file, mode='w', compression=ZIP_DEFLATED) as zipf:
            for count, img in enumerate(img_gen()):
                filename = f"{count:0{padding_width}}.jpg"
                buf = io.BytesIO()
                if self.quality < 100:
                    img.save(buf, format="JPEG", quality=self.quality, optimize=True)
                else:
                    img.save(buf, format="JPEG")
                zipf.writestr(filename, buf.getvalue())

        if self.progress:
            self.progress.progress_set_value(len(self.image_files))

    def stop(self):
        self.stop_event = True

    def check_is_stopped(self):
        if self.stop_event:
            raise StopException()


class StopException(Exception):
    def __str__(self):
        return "The CBZ creator has been stopped!"
