import sys
from pathlib import Path
# Import parent project modules before any local imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.PdfMaker import PdfMaker
from core.ePubMaker import EPubMaker
from core.CbzMaker import CbzMaker
from flask import Flask, request, send_file, send_from_directory, render_template, jsonify
import os
import io
import shutil
import tempfile
import zipfile
import datetime
import hashlib
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB limit

DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

IMAGE_EXTS = {'.jpg', '.jpeg', '.png',
              '.webp', '.bmp', '.tiff', '.tif', '.gif'}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/convert', methods=['POST'])
def convert():
    files = request.files.getlist('files[]')
    paths = request.form.getlist('paths[]')
    title = (request.form.get('title',  'My Book') or 'My Book').strip()
    author = (request.form.get('author', '') or '').strip()
    fmt = request.form.get('format',  'epub').lower()
    quality = int(request.form.get('quality',    '100') or 100)
    rtl = request.form.get('rtl',       'false') == 'true'
    grayscale = request.form.get('grayscale', 'false') == 'true'
    auto_crop = request.form.get('auto_crop', 'false') == 'true'
    split_spreads = request.form.get('split_spreads', 'false') == 'true'
    max_width = request.form.get('max_width',  '').strip()
    max_height = request.form.get('max_height', '').strip()
    max_width = int(max_width) if max_width.isdigit() else None
    max_height = int(max_height) if max_height.isdigit() else None
    binarize = request.form.get('binarize', 'false') == 'true'
    use_webp = request.form.get('use_webp', 'false') == 'true'
    use_ocr = request.form.get('use_ocr', 'false') == 'true'
    ai_upscale = request.form.get('ai_upscale', 'false') == 'true'
    deskew_crop = request.form.get('deskew_crop', 'false') == 'true'
    guided_view = request.form.get('guided_view', 'false') == 'true'

    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'Không có file nào được upload!'}), 400

    input_dir = tempfile.mkdtemp(prefix='img2epub_in_')
    output_dir = tempfile.mkdtemp(prefix='img2epub_out_')

    try:
        counter = 0
        for i, f in enumerate(files):
            rel_path = paths[i] if i < len(paths) else f.filename
            if not rel_path:
                rel_path = f'image_{counter}.jpg'
            
            # Chống tấn công Path Traversal (bảo mật)
            safe_rel_path = rel_path.lstrip('/').lstrip('\\')
            safe_rel_path = os.path.normpath(safe_rel_path)
            if safe_rel_path.startswith('..'):
                safe_rel_path = os.path.basename(rel_path)
                
            fname = Path(safe_rel_path)
            ext = fname.suffix.lower()

            if ext in ('.zip', '.cbz'):
                # Xả file nén (Zip/CBZ) nhưng vẫn giữ nguyên cấu trúc thư mục con bên trong
                data = f.read()
                zip_base = fname.stem
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    entries = sorted(
                        n for n in zf.namelist()
                        if Path(n).suffix.lower() in IMAGE_EXTS
                        and not zf.getinfo(n).is_dir()
                    )
                    for entry in entries:
                        safe_entry = Path(os.path.normpath(entry.lstrip('/').lstrip('\\')))
                        if str(safe_entry).startswith('..'):
                            safe_entry = Path(safe_entry.name)
                            
                        # Giữ lại thư mục con trong zip, thêm số thứ tự vào tên file để dễ sort
                        out_path = os.path.join(input_dir, zip_base, safe_entry.parent, f'{counter:06d}_{safe_entry.name}')
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, 'wb') as out:
                            out.write(zf.read(entry))
                        counter += 1
            elif ext in IMAGE_EXTS:
                # Giữ nguyên cấu trúc thư mục, đánh số thứ tự đầu file
                out_path = os.path.join(input_dir, fname.parent, f'{counter:06d}_{fname.name}')
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                f.save(out_path)
                counter += 1

        if counter == 0:
            return jsonify({'error': 'Không tìm thấy ảnh hợp lệ nào!'}), 400

        # Tạo tên file an toàn (bỏ các ký tự đặc biệt)
        safe_title = ''.join(c for c in title if c.isalnum()
                             or c in ' -_').strip() or 'output'
        output_file = os.path.join(output_dir, f'{safe_title}.{fmt}')

        # Tiến hành convert (Không cần chạy Thread/Subprocess vì request của Flask có thể handle)
        if fmt == 'pdf':
            page_size = request.form.get('page_size', 'fit')
            margin_str = request.form.get('margin', '0')
            margin = int(margin_str) if margin_str.isdigit() else 0
            
            maker = PdfMaker(
                master=None, input_dir=input_dir, file=output_file, name=title,
                grayscale=grayscale, max_width=max_width, max_height=max_height,
                quality=quality, rtl=rtl, auto_crop=auto_crop, split_spreads=split_spreads,
                page_size=page_size, margin=margin, binarize=binarize, use_ocr=use_ocr,
                ai_upscale=ai_upscale, deskew_crop=deskew_crop, guided_view=guided_view
            )
        elif fmt == 'cbz':
            maker = CbzMaker(
                master=None, input_dir=input_dir, file=output_file, name=title,
                grayscale=grayscale, max_width=max_width, max_height=max_height,
                quality=quality, rtl=rtl, auto_crop=auto_crop, split_spreads=split_spreads,
                binarize=binarize, ai_upscale=ai_upscale, deskew_crop=deskew_crop, guided_view=guided_view
            )
        else:
            maker = EPubMaker(
                master=None, input_dir=input_dir, file=output_file, name=title,
                author=author, grayscale=grayscale, max_width=max_width,
                max_height=max_height, quality=quality, rtl=rtl,
                auto_crop=auto_crop, split_spreads=split_spreads, wrap_pages=True,
                binarize=binarize, use_webp=use_webp,
                ai_upscale=ai_upscale, deskew_crop=deskew_crop, guided_view=guided_view
            )

        if fmt == 'pdf':
            maker.make_pdf()
        elif fmt == 'cbz':
            maker.make_cbz()
        else:
            maker.make_epub()

        # Lưu một bản vào thư mục downloads để chia sẻ qua OPDS
        import shutil
        shutil.copy2(output_file, os.path.join(DOWNLOADS_DIR, os.path.basename(output_file)))

        # Đọc ngược file từ ổ cứng lên RAM để chuẩn bị xoá thư mục rác ngay lập tức
        with open(output_file, 'rb') as fh:
            file_data = io.BytesIO(fh.read())

        mime = 'application/epub+zip' if fmt == 'epub' else 'application/pdf'
        if fmt == 'cbz':
            mime = 'application/vnd.comicbook+zip'

        return send_file(
            file_data, mimetype=mime,
            as_attachment=True,
            download_name=f'{safe_title}.{fmt}'
        )

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(exc)}), 500
    finally:
        shutil.rmtree(input_dir,  ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)


@app.route('/opds')
def opds_catalog():
    feed = Element('feed', xmlns="http://www.w3.org/2005/Atom")
    
    title = SubElement(feed, 'title')
    title.text = "JPG2EPUB OPDS Catalog"
    
    id_elem = SubElement(feed, 'id')
    id_elem.text = "urn:uuid:12345678-1234-5678-1234-567812345678"
    
    updated = SubElement(feed, 'updated')
    updated.text = datetime.datetime.utcnow().isoformat() + "Z"
    
    author = SubElement(feed, 'author')
    name = SubElement(author, 'name')
    name.text = "JPG2EPUB Server"
    
    link = SubElement(feed, 'link', rel="self", href=request.url, type="application/atom+xml;profile=opds-catalog;kind=acquisition")
    link = SubElement(feed, 'link', rel="start", href=request.url, type="application/atom+xml;profile=opds-catalog;kind=acquisition")
    
    for filename in sorted(os.listdir(DOWNLOADS_DIR), reverse=True):
        if filename.endswith(('.epub', '.pdf', '.cbz')):
            filepath = os.path.join(DOWNLOADS_DIR, filename)
            stat = os.stat(filepath)
            
            entry = SubElement(feed, 'entry')
            entry_title = SubElement(entry, 'title')
            entry_title.text = filename
            
            entry_id = SubElement(entry, 'id')
            entry_id.text = f"urn:uuid:{hashlib.md5(filename.encode()).hexdigest()}"
            
            entry_updated = SubElement(entry, 'updated')
            entry_updated.text = datetime.datetime.fromtimestamp(stat.st_mtime).isoformat() + "Z"
            
            content = SubElement(entry, 'content', type="text")
            content.text = f"Size: {stat.st_size // (1024*1024)} MB"
            
            mime = 'application/epub+zip'
            if filename.endswith('.pdf'): mime = 'application/pdf'
            elif filename.endswith('.cbz'): mime = 'application/vnd.comicbook+zip'
            
            SubElement(entry, 'link', rel="http://opds-spec.org/acquisition", 
                       href=f"{request.host_url}downloads/{filename}", type=mime)
                       
    xml_str = minidom.parseString(tostring(feed)).toprettyxml(indent="  ")
    from flask import Response
    return Response(xml_str, mimetype='application/atom+xml;profile=opds-catalog;kind=acquisition')


@app.route('/downloads/<path:filename>')
def download_file(filename):
    return send_from_directory(DOWNLOADS_DIR, filename)

if __name__ == '__main__':
    import threading
    import webbrowser
    import time

    def _open():
        time.sleep(1.2)
        webbrowser.open('http://127.0.0.1:5000')

    threading.Thread(target=_open, daemon=True).start()
    print('Images -> ePub / PDF  --  http://127.0.0.1:5000')
    app.run(host='127.0.0.1', port=5000, debug=False)
