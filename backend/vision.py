import hashlib
import io
import threading
import warnings
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from .config import MAX_BYTES, MAX_PIXELS, MODEL_DIR, MODEL_FILES

Image.MAX_IMAGE_PIXELS = MAX_PIXELS
_lock = threading.RLock()
_engine = None
_fingerprint = None


def model_available():
    return all((MODEL_DIR / name).is_file() for name in MODEL_FILES)


def model_version():
    global _fingerprint
    if _fingerprint is None:
        if not model_available():
            raise ValueError('ยังไม่ได้ติดตั้งโมเดลใบหน้า เปิดหน้าตั้งค่าเพื่อติดตั้ง')
        digest = hashlib.sha256()
        for name in MODEL_FILES:
            with (MODEL_DIR / name).open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
        _fingerprint = 'arcface512-pillow-v2-' + digest.hexdigest()[:20]
    return _fingerprint


def engine():
    global _engine
    with _lock:
        if _engine is None:
            model_version()
            from .inference import FaceEngine
            _engine = FaceEngine()
        return _engine


def decode(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('ไฟล์ต้องมีขนาดไม่เกิน 25 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as im:
                if im.width * im.height > MAX_PIXELS:
                    raise ValueError('รูปภาพต้องมีขนาดไม่เกิน 40 ล้านพิกเซล')
                im = ImageOps.exif_transpose(im).convert('RGB')
                return np.asarray(im)[:, :, ::-1].copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('อ่านรูปภาพไม่ได้ รองรับ JPEG, PNG, WebP, BMP และ TIFF') from exc


def normalize(x):
    x = np.asarray(x, dtype=np.float32)
    if x.ndim != 2 or x.shape[1] != 512 or not np.isfinite(x).all():
        raise ValueError('Invalid 512D embeddings')
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    if np.any(norms < 1e-8):
        raise ValueError('Empty embedding')
    return np.ascontiguousarray(x / norms)


def analyze(data, registration=False):
    image = decode(data)
    height, width = image.shape[:2]
    with _lock:
        app = engine()
        boxes, kps = app.detect(image, max_num=0)
        if registration and len(boxes) != 1:
            return {'faces': [], 'detected': len(boxes), 'width': width, 'height': height}
        accepted = []
        for i, box in enumerate(boxes):
            if not np.isfinite(box).all():
                continue
            x1, y1 = np.maximum(np.floor(box[:2]).astype(int), 0)
            x2, y2 = np.minimum(np.ceil(box[2:4]).astype(int), [width, height])
            if min(x2-x1, y2-y1) <= 0 or kps is None:
                continue
            points = kps[i]
            if points.shape != (5, 2) or not np.isfinite(points).all() or np.linalg.norm(points[0]-points[1]) < 1e-6:
                continue
            crop = Image.fromarray(image[y1:y2, x1:x2, ::-1]).convert('L').resize((112,112), Image.Resampling.BILINEAR)
            gray = np.asarray(crop, dtype=np.float32)
            laplacian = gray[1:-1,:-2] + gray[1:-1,2:] + gray[:-2,1:-1] + gray[2:,1:-1] - 4*gray[1:-1,1:-1]
            sharpness = float(laplacian.var())
            exposure = float(gray.mean())
            # Keep quality measurements as metadata. Dark and small faces also
            # tend to have low sharpness, so none of these metrics reject a face.
            try:
                vector = normalize(app.embed(image, points).reshape(1,-1))[0]
            except (ValueError, np.linalg.LinAlgError):
                continue
            accepted.append({'vector': vector, 'bbox': [x1/width, y1/height, x2/width, y2/height],
                             'quality': {'sharpness': round(sharpness, 2), 'brightness': round(exposure, 2),
                                         'detection': round(float(box[4]), 4)}})
    return {'faces': accepted, 'detected': len(boxes), 'width': width, 'height': height}


def thumbnail(data, size=1600, quality=86):
    bgr = decode(data)
    image = Image.fromarray(bgr[:, :, ::-1])
    image.thumbnail((size, size))
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=quality)
    return buffer.getvalue()
