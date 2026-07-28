import cv2
import numpy as np
from PIL import Image
import urllib.request
import os

# Tạo sẵn thư mục lưu model AI nếu chưa có
MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')
os.makedirs(MODELS_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODELS_DIR, 'FSRCNN_x2.pb')
MODEL_URL = "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x2.pb"

_sr = None

def get_sr_model():
    global _sr
    if _sr is not None:
        return _sr

    if not os.path.exists(MODEL_PATH):
        print(f"Downloading AI Super Resolution model to {MODEL_PATH}...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

    _sr = cv2.dnn_superres.DnnSuperResImpl_create()
    _sr.readModel(MODEL_PATH)
    _sr.setModel("fsrcnn", 2)
    return _sr

def ai_upscale(img_pil: Image.Image) -> Image.Image:
    if img_pil.mode != 'RGB':
        img_pil = img_pil.convert('RGB')
        
    img_cv = np.array(img_pil)
    # OpenCV dùng hệ màu BGR, cần đổi từ RGB sang BGR trước khi ném vào model
    img_cv = img_cv[:, :, ::-1].copy()
    
    sr = get_sr_model()
    result = sr.upsample(img_cv)
    
    # Nhớ đổi ngược lại RGB để trả về cho Pillow
    result = result[:, :, ::-1]
    return Image.fromarray(result)

def deskew_and_crop(img_pil: Image.Image) -> Image.Image:
    if img_pil.mode != 'RGB':
        img_pil = img_pil.convert('RGB')
        
    img = np.array(img_pil)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    
    # Đảo ngược màu và chuyển về nhị phân (đen trắng) để dễ bắt khối
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    
    # Tìm tất cả các viền (contours) có trong ảnh
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img_pil
        
    # Chọn khối to nhất, mặc định nó là trang giấy (bỏ qua mấy cái viền rác ở ngoài)
    largest_contour = max(contours, key=cv2.contourArea)
    
    # Tính toán hình chữ nhật bao quanh nhỏ nhất (có xoay)
    rect = cv2.minAreaRect(largest_contour)
    angle = rect[-1]
    
    # Tính góc lệch chuẩn xác
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
        
    # Chỉ xoay lại ảnh nếu lệch lớn hơn 0.5 độ (đỡ mất công tính toán)
    if abs(angle) > 0.5:
        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        # Sau khi xoay xong, phải tính lại ngưỡng (threshold) để crop sát viền
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gray = cv2.bitwise_not(gray)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return img_pil
        largest_contour = max(contours, key=cv2.contourArea)
        
    x, y, w, h = cv2.boundingRect(largest_contour)
    
    # Chừa ra 1 xíu viền (margin) cho đẹp
    margin = 10
    x = max(0, x - margin)
    y = max(0, y - margin)
    w = min(img.shape[1] - x, w + 2*margin)
    h = min(img.shape[0] - y, h + 2*margin)
    
    cropped = img[y:y+h, x:x+w]
    return Image.fromarray(cropped)

def guided_view_panels(img_pil: Image.Image, rtl: bool) -> list[Image.Image]:
    if img_pil.mode != 'RGB':
        img_pil = img_pil.convert('RGB')
        
    img = np.array(img_pil)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    
    # Ngưỡng bắt khung truyện (thường viền màu đen trên nền trắng)
    _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    
    # Dùng thuật toán hình thái học (Morphology) để nối các nét viền đứt gãy
    kernel = np.ones((5,5), np.uint8)
    dilated = cv2.dilate(thresh, kernel, iterations=3)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    panels = []
    min_area = (img.shape[0] * img.shape[1]) * 0.05 # At least 5% of page
    
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h > min_area:
            panels.append((x, y, w, h))
            
    if not panels:
        return [img_pil]
        
    # Sắp xếp các ô thoại: Ưu tiên trên xuống dưới, rồi xét từ phải sang trái (Manga) hoặc trái sang phải (Comic)
    # Cho phép sai số trục Y một chút để nhóm các ô trên cùng 1 hàng
    def panel_sort_key(p):
        x, y, w, h = p
        row = y // 100  # group by roughly 100px rows
        col = -x if rtl else x
        return (row, col)
        
    panels.sort(key=panel_sort_key)
    
    result = []
    for (x, y, w, h) in panels:
        # Thêm padding 5px để không bị sát mép quá
        px = max(0, x - 5)
        py = max(0, y - 5)
        pw = min(img.shape[1] - px, w + 10)
        ph = min(img.shape[0] - y, h + 10)
        panel_img = img[py:py+ph, px:px+pw]
        result.append(Image.fromarray(panel_img))
        
    return result
