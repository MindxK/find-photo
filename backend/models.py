import hashlib
import threading
import urllib.request
import zipfile
import shutil
import time
import os
from .config import DATA, MODEL_DIR, MODEL_NAME, MODEL_FILES
from . import vision

_lock = threading.Lock()
state = {'status': 'idle', 'progress': 0, 'message': ''}
MODEL_URL = f'https://github.com/deepinsight/insightface/releases/download/v0.7/{MODEL_NAME}.zip'


def install():
    if vision.model_available():
        vision.engine()
        state.update(status='ready', progress=100, message='โมเดลพร้อมใช้งาน')
        return
    with _lock:
        if state['status'] == 'downloading':
            return
        state.update(status='downloading', progress=0, message='กำลังดาวน์โหลดโมเดล ' + MODEL_NAME)
    supplied_archive = DATA / (MODEL_NAME + '.zip')
    archive = DATA / (MODEL_NAME + '.download')
    owns_archive = True
    lock_handle = (DATA / 'model-install.lock').open('a+b')
    lock_handle.seek(0)
    if not lock_handle.read(1):
        lock_handle.write(b'1')
        lock_handle.flush()
    lock_handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_handle.close()
        state.update(status='error', message='กำลังติดตั้งโมเดลจากอีกหน้าต่าง กรุณารอให้เสร็จ')
        return
    try:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        if supplied_archive.is_file() and zipfile.is_zipfile(supplied_archive):
            archive = supplied_archive
            owns_archive = False
        else:
            if supplied_archive.is_file() and not archive.exists():
                shutil.copyfile(supplied_archive, archive)
            for attempt in range(5):
                if archive.exists() and zipfile.is_zipfile(archive):
                    break
                received = archive.stat().st_size if archive.exists() else 0
                headers = {'User-Agent':'FindFace/1.0', 'Accept-Encoding':'identity'}
                if received:
                    headers['Range'] = f'bytes={received}-'
                request = urllib.request.Request(MODEL_URL, headers=headers)
                try:
                    with urllib.request.urlopen(request, timeout=90) as response:
                        append = response.status == 206 and received > 0
                        if not append:
                            received = 0
                        total = received + int(response.headers.get('Content-Length', 0))
                        with archive.open('ab' if append else 'wb') as handle:
                            while chunk := response.read(256 * 1024):
                                received += len(chunk)
                                if received > 600 * 1024 * 1024:
                                    raise ValueError('Model archive unexpectedly large')
                                handle.write(chunk)
                                state['progress'] = round(90 * received / total) if total else 0
                except OSError:
                    if attempt == 4:
                        raise
                    time.sleep(2 ** attempt)
            if not zipfile.is_zipfile(archive):
                raise ValueError('Incomplete download, retry to resume')
        state.update(progress=92, message='กำลังตรวจสอบและเตรียมโมเดล')
        with zipfile.ZipFile(archive) as bundle:
            required = MODEL_FILES
            for filename in required:
                matches = [name for name in bundle.namelist() if name.split('/')[-1] == filename]
                if len(matches) != 1 or bundle.getinfo(matches[0]).file_size > 400 * 1024 * 1024:
                    raise ValueError('Invalid model archive')
                partial = MODEL_DIR / (filename + '.partial')
                with bundle.open(matches[0]) as source, partial.open('wb') as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
                partial.replace(MODEL_DIR / filename)
        digest = hashlib.sha256()
        with archive.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        (MODEL_DIR / 'download-sha256.txt').write_text(digest.hexdigest(), encoding='utf-8')
        vision.engine()
        state.update(status='ready', progress=100, message='โมเดลพร้อมใช้งาน')
    except Exception:
        state.update(status='error', message='ติดตั้งไม่สำเร็จ ตรวจอินเทอร์เน็ตแล้วลองอีกครั้ง หรือใช้คำสั่งติดตั้งในคู่มือ')
        raise
    finally:
        lock_handle.close()
        if state['status'] == 'ready' and owns_archive and archive.exists():
            archive.unlink()


def start():
    if state['status'] == 'downloading':
        return
    def worker():
        try:
            install()
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True, name='model-install').start()
