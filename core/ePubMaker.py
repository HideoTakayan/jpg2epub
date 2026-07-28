# coding=utf-8
""" Convert a folder with images to an ePub file. Great for comics and manga!
    Copyright (C) 2021  Antoine Veenstra

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see [http://www.gnu.org/licenses/]
"""
import math
import os
import re
import sys
import threading
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import concurrent.futures
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED

import PIL.Image
from PIL import ImageChops, ImageEnhance
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from core import cv2_filters

# Danh sách định dạng ảnh chuẩn được ePub 3 hỗ trợ mặc định
MEDIA_TYPES = {
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
    '.tiff': 'image/tiff',
    '.tif': 'image/tiff'
}
# Các định dạng khác ngoài chuẩn thì ép phải convert sang PNG
EPUB_CONVERT_TO_PNG = {'.bmp', '.tiff', '.tif'}
TEMPLATE_DIR = Path(__file__).parent.joinpath("templates")


def natural_keys(text):
    """
    http://nedbatchelder.com/blog/200712/human_sorting.html
    """
    return [(int(c) if c.isdigit() else c) for c in re.split(r'(\d+)', text)]


def filter_images(files):
    files.sort(key=natural_keys)
    for x in files:
        _, extension = os.path.splitext(x)
        file_type = MEDIA_TYPES.get(extension.lower())
        if file_type:
            yield x, file_type, extension


class Chapter:
    def __init__(self, dir_path, title, start: str | None = None):
        self.dir_path = dir_path
        self.title = title
        self.children: list[Chapter] = []
        self._start = start

    @property
    def start(self) -> str | None:
        if self._start:
            return self._start
        if self.children:
            return self.children[0].start

    @start.setter
    def start(self, value):
        self._start = value

    @property
    def depth(self) -> int:
        if self.children:
            return 1 + max(child.depth for child in self.children)
        return 1


class EPubMaker(threading.Thread):
    def __init__(
            self,
            master,
            input_dir,
            file,
            name,
            wrap_pages,
            grayscale,
            max_width,
            max_height,
            author="",
            rtl=False,
            quality=100,
            auto_crop=False,
            split_spreads=False,
            cleanup_dir=None,
            progress=None,
            binarize=False,
            use_webp=False,
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

        self.template_env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            undefined=StrictUndefined)

        self.zip: ZipFile | None = None
        self.cover = None
        self.chapter_tree: Chapter | None = None
        self.images = []
        self.uuid = f"urn:uuid:{uuid.uuid1()}"
        self.grayscale = grayscale
        self.max_width = max_width
        self.max_height = max_height
        self.wrap_pages = wrap_pages
        self.author = author
        self.rtl = rtl
        self.quality = quality
        self.auto_crop = auto_crop
        self.split_spreads = split_spreads
        self.cleanup_dir = cleanup_dir
        self.binarize = binarize
        self.use_webp = use_webp
        self.ai_upscale = ai_upscale
        self.deskew_crop = deskew_crop
        self.guided_view = guided_view

    def run(self):
        try:
            assert os.path.isdir(
                self.dir), "The given directory does not exist!"
            assert self.name, "No name given!"

            self.make_epub()

            if self.master is None:
                print()
                print("ePub created")
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
            except IOError:
                pass
        finally:
            if self.cleanup_dir and os.path.exists(self.cleanup_dir):
                import shutil
                shutil.rmtree(self.cleanup_dir, ignore_errors=True)

    def make_epub(self):
        with ZipFile(self.file, mode='w', compression=ZIP_DEFLATED) as self.zip:
            self.zip.writestr(
                'mimetype',
                'application/epub+zip',
                compress_type=ZIP_STORED)
            self.add_file('META-INF', "container.xml")
            self.add_file('stylesheet.css')
            self.make_tree()
            self.assign_image_ids()
            self.write_images()
            self.write_template('package.opf')
            self.write_template('toc.xhtml')
            self.write_template('toc.ncx')

    def add_file(self, *path: str):
        self.zip.write(TEMPLATE_DIR.joinpath(*path), Path(*path).as_posix())

    def make_tree(self):
        root = Path(self.dir)
        self.chapter_tree = Chapter(root.parent, None)
        chapter_shortcuts = {root.parent: self.chapter_tree}

        for dir_path, dir_names, filenames in os.walk(self.dir):
            dir_names.sort(key=natural_keys)
            images = self.get_images(filenames, dir_path)
            dir_path = Path(dir_path)
            chapter = Chapter(
                dir_path,
                dir_path.name,
                images[0] if images else None)
            chapter_shortcuts[dir_path.parent].children.append(chapter)
            chapter_shortcuts[dir_path] = chapter

        while len(self.chapter_tree.children) == 1:
            self.chapter_tree = self.chapter_tree.children[0]

    def get_images(self, files, root):
        result = []
        for x, file_type, extension in filter_images(files):
            data = self.add_image(str(Path(root) / x), file_type, extension)
            result.append(data)
            if not self.cover and 'cover' in x.lower():
                self.cover = data
                data["is_cover"] = True
        return result

    def add_image(self, source, file_type, extension):
        data = {
            "extension": extension,
            "type": file_type,
            "source": source,
            "is_cover": False}
        self.images.append(data)
        return data

    def assign_image_ids(self):
        if not self.cover and self.images:
            cover = self.images[0]
            cover["is_cover"] = True
            self.cover = cover
        padding_width = len(str(len(self.images)))
        for count, image in enumerate(self.images):
            image["id"] = f"image_{count:0{padding_width}}"
            # Dùng đuôi file mới nếu ảnh vừa bị convert (ví dụ qua WebP/PNG)
            image["filename"] = image["id"] + image["extension"]

    def write_images(self):
        if self.progress:
            self.progress.progress_set_maximum(len(self.images))
            self.progress.progress_set_value(0)

        template = self.template_env.get_template("page.xhtml.jinja2")
        new_images = []

        def process_single_image(image):
            image_data: PIL.Image.Image = PIL.Image.open(image["source"])
            image["width"], image["height"] = image_data.size

            ext_lower = image["extension"].lower()
            must_convert_to_png = ext_lower in EPUB_CONVERT_TO_PNG
            
            if self.use_webp:
                image["extension"] = ".webp"
                image["type"] = "image/webp"
                image["filename"] = image["id"] + ".webp"
                if image_data.mode not in ("RGB", "RGBA"):
                    image_data = image_data.convert("RGB")
            elif must_convert_to_png:
                image["extension"] = ".png"
                image["type"] = "image/png"
                image["filename"] = image["id"] + ".png"
                if image_data.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                    image_data = image_data.convert("RGB")
            else:
                if image_data.mode in ("RGBA", "P"):
                    image_data = image_data.convert("RGB")

            # Xén viền trắng (Auto Crop)
            if self.auto_crop:
                bg = PIL.Image.new(image_data.mode, image_data.size, image_data.getpixel((0, 0)))
                diff = ImageChops.difference(image_data, bg)
                bbox = diff.getbbox()
                if bbox:
                    image_data = image_data.crop(bbox)
                    image["width"], image["height"] = image_data.size

            if self.deskew_crop:
                image_data = cv2_filters.deskew_and_crop(image_data)
                image["width"], image["height"] = image_data.size
                
            if self.ai_upscale:
                image_data = cv2_filters.ai_upscale(image_data)
                image["width"], image["height"] = image_data.size

            # Cắt trang đôi
            img_list = []
            if self.split_spreads and image["width"] > image["height"]:
                mid = image["width"] // 2
                left = image_data.crop((0, 0, mid, image["height"]))
                right = image_data.crop((mid, 0, image["width"], image["height"]))

                img_dict_1 = image.copy()
                img_dict_1["id"] = image["id"] + "_1"
                img_dict_1["filename"] = img_dict_1["id"] + img_dict_1["extension"]

                img_dict_2 = image.copy()
                img_dict_2["id"] = image["id"] + "_2"
                img_dict_2["filename"] = img_dict_2["id"] + img_dict_2["extension"]

                if self.rtl:
                    img_list = [(img_dict_1, right), (img_dict_2, left)]
                else:
                    img_list = [(img_dict_1, left), (img_dict_2, right)]
            else:
                img_list = [(image, image_data)]

            # Chế độ Guided View (Ghi đè luôn cắt trang đôi)
            if self.guided_view:
                panels = cv2_filters.guided_view_panels(image_data, self.rtl)
                img_list = []
                for i, p in enumerate(panels):
                    p_dict = image.copy()
                    if len(panels) > 1:
                        p_dict["id"] = image["id"] + f"_{i+1}"
                        p_dict["filename"] = p_dict["id"] + p_dict["extension"]
                    img_list.append((p_dict, p))

            # Quét mảng ảnh và bắt đầu render ra template html
            results = []
            for img_dict, img_data in img_list:
                should_resize = (self.max_width and self.max_width < img_dict["width"]) or (
                        self.max_height and self.max_height < img_dict["height"])

                if should_resize:
                    width_scale = img_dict["width"] / \
                                  self.max_width if self.max_width else 1.0
                    height_scale = img_dict["height"] / \
                                   self.max_height if self.max_height else 1.0

                    scale = max(width_scale, height_scale)

                    img_data = img_data.resize(
                        (int(img_dict["width"] / scale),
                         int(img_dict["height"] / scale)),
                        resample=PIL.Image.Resampling.LANCZOS)
                    img_dict["width"], img_dict["height"] = img_data.size

                if self.grayscale and img_data.mode != "L":
                    img_data = img_data.convert("L")
                
                if self.binarize:
                    if img_data.mode != "L":
                        img_data = img_data.convert("L")
                    enhancer = ImageEnhance.Contrast(img_data)
                    img_data = enhancer.enhance(2.0)
                    img_data = img_data.point(lambda p: 255 if p > 128 else 0, mode='1')

                results.append((img_dict, img_data))
                
            return results

        # Quăng hết ảnh vào ThreadPool cho chạy song song
        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            pending = []
            idx = 0
            total = len(self.images)
            
            while idx < total or pending:
                while idx < total and len(pending) < (os.cpu_count() or 1) * 2:
                    future = executor.submit(process_single_image, self.images[idx])
                    pending.append(future)
                    idx += 1
                
                if pending:
                    oldest = pending.pop(0)
                    results = oldest.result()
                    for img_dict, img_data in results:
                        # Nén zip tuần tự vì zip write không an toàn khi chạy đa luồng
                        import io
                        buf = io.BytesIO()
                        format_str = "WEBP" if img_dict["extension"].lower() == ".webp" else img_data.format or img_dict["extension"][1:].upper()
                        if format_str == "JPG": format_str = "JPEG"
                        img_data.save(buf, format=format_str, quality=self.quality, optimize=True)
                        
                        self.zip.writestr(
                            f"{OEBPS}/{img_dict['filename']}",
                            buf.getvalue()
                        )
                        new_images.append(img_dict)

                        page_html = template.render(
                            image=img_dict,
                            title=self.name)

                        self.zip.writestr(
                            f"{OEBPS}/{img_dict['id']}.xhtml",
                            page_html.encode('utf-8'))
                    
                    if self.progress:
                        self.progress.progress_set_value(idx - len(pending))

        self.images = new_images
        self.images = new_images

        if self.progress:
            self.progress.progress_set_value(len(self.images))

    def write_template(self, name, *, out=None, data=None):
        out = out or name
        data = data or {
            "name": self.name,
            "author": self.author,
            "uuid": self.uuid,
            "now": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cover": self.cover,
            "chapter_tree": self.chapter_tree,
            "images": self.images,
            "wrap_pages": self.wrap_pages,
            "rtl": self.rtl,
        }
        self.zip.writestr(
            out, self.template_env.get_template(
                name + '.jinja2').render(data))

    def stop(self):
        self.stop_event = True

    def check_is_stopped(self):
        if self.stop_event:
            raise StopException()


class StopException(Exception):
    def __str__(self):
        return "The ePub creator has been stopped!"


class CmdProgress:
    def __init__(self, nice):
        self.last_update = datetime.now()
        self.update_interval = timedelta(seconds=0.25)
        self.nice = nice
        self.edges = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
        self.width = 60
        self.maximum = 150
        self.value = 0

    def progress_set_value(self, value):
        self.value = value
        if 0 <= self.value <= self.maximum:
            if self.maximum == self.value or datetime.now() > self.last_update + \
                    self.update_interval:
                self.last_update = datetime.now()
                if self.nice:
                    if self.value < self.maximum:
                        progress = self.value / self.maximum * self.width * 8.0
                        done = math.floor(progress / 8)
                        edge = self.edges[int(progress - done * 8)]

                        print('\r│' + '█' * done + edge + ' ' *
                              (self.width - done - 1) + '│ ', end="")
                    else:
                        print(f'\r│{"█" * self.width}│')
                else:
                    print(f'At {self.value}/{self.maximum}')

    def progress_set_maximum(self, value):
        self.maximum = value
        if 0 <= value:
            if self.nice:
                print('\r│' + ' ' * self.width + '│ ', end="")
