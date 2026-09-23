import concurrent.futures
from contextvars import copy_context
from collections import deque
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
import httpx
from . import db, vision
from .config import EXTENSIONS, MAX_BYTES
from .drive import Drive, DriveError

_guard = threading.Lock()
_cancel = threading.Event()
_active = None
_pending = {}
_waiting = deque()


def busy():
    return db.scope_key() in _pending.values()


def _launch_next():
    global _active
    while _waiting:
        job_id, source, context = _waiting.popleft()
        if job_id not in _pending:
            continue
        _active = job_id
        _cancel.clear()
        threading.Thread(target=context.run, args=(run, job_id, source), daemon=True, name='face-scan').start()
        return
    _active = None


def update(job_id, **values):
    allowed = {'status', 'phase', 'total', 'processed', 'skipped', 'failed', 'faces', 'current_file', 'error', 'finished'}
    assert set(values) <= allowed
    db.execute('UPDATE jobs SET ' + ','.join(f'{key}=?' for key in values) + ' WHERE id=?', (*values.values(), job_id))


def start(source_id):
    global _active
    with _guard:
        if busy():
            raise ValueError('บัญชีนี้มีงานสแกนอยู่ในคิวแล้ว กรุณารอหรือหยุดงานเดิม')
        if len(_pending) >= 30:
            raise ValueError('คิวสแกนเต็ม กรุณาลองใหม่ภายหลัง')
        source = db.one('SELECT * FROM sources WHERE id=?', (source_id,))
        if not source:
            raise ValueError('ไม่พบอัลบั้ม')
        if not vision.model_available():
            raise ValueError('กรุณาติดตั้งโมเดลในหน้าตั้งค่าก่อนเริ่มสแกน')
        job_id = uuid.uuid4().hex
        db.execute('INSERT INTO jobs(id,source_id,status,phase,created) VALUES(?,?,?,?,?)',
                   (job_id, source_id, 'queued', 'กำลังเตรียมสแกน', time.time()))
        _pending[job_id] = db.scope_key()
        _waiting.append((job_id, source, copy_context()))
        if _active is None:
            _launch_next()
        else:
            update(job_id, phase='รอคิวประมวลผลบนเซิร์ฟเวอร์')
        return job_id


def cancel(job_id):
    with _guard:
        if _pending.get(job_id) != db.scope_key():
            raise ValueError('งานนี้ไม่ได้กำลังทำงาน')
        if _active == job_id:
            _cancel.set()
            update(job_id, status='cancelling', phase='กำลังหยุดหลังประมวลผลภาพปัจจุบัน')
        else:
            _pending.pop(job_id, None)
            update(job_id, status='cancelled', phase='ยกเลิกคิวแล้ว', finished=time.time())


def local_items(root):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('ไม่พบโฟลเดอร์รูปภาพ')
    for path in root.rglob('*'):
        if _cancel.is_set():
            return
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            continue
        stat = resolved.stat()
        yield {'id': str(resolved), 'name': path.name, 'size': stat.st_size,
               'version': f'{stat.st_mtime_ns}-{stat.st_size}'}


def get_bytes(source, item):
    if int(item.get('size', 0)) > MAX_BYTES:
        raise ValueError('ไฟล์ใหญ่เกิน 25 MB')
    if source['kind'] == 'local':
        if db.SERVER_MODE and db.scope_key() != 'legacy':
            raise ValueError('บัญชีนี้เข้าถึงโฟลเดอร์บนเซิร์ฟเวอร์ไม่ได้')
        root = Path(source['locator']).resolve(strict=True)
        path = Path(item['id']).resolve(strict=True)
        if not path.is_relative_to(root) or path.suffix.lower() not in EXTENSIONS:
            raise ValueError('ไฟล์อยู่นอกขอบเขตอัลบั้ม')
        with path.open('rb') as handle:
            data = handle.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('ไฟล์ใหญ่เกิน 25 MB')
        return data
    drive = Drive()
    try:
        return drive.download(item['id'])
    finally:
        drive.close()


def save_file(source, item, result, model, version, status, reason=None):
    file_id = hashlib.sha256((source['id'] + ':' + item['id']).encode()).hexdigest()
    with db.connect() as c:
        # Replace faces atomically; stale feedback is removed by foreign keys.
        c.execute('DELETE FROM faces WHERE file_id=?', (file_id,))
        c.execute('''INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET name=excluded.name,version=excluded.version,model=excluded.model,
          width=excluded.width,height=excluded.height,status=excluded.status,reason=excluded.reason,scanned=excluded.scanned''',
          (file_id, source['id'], item['id'], item['name'], version, model,
           result.get('width', 0), result.get('height', 0), status, reason, time.time()))
        for face in result.get('faces', []):
            c.execute('INSERT INTO faces VALUES(?,?,?,?,?,?)',
                      (uuid.uuid4().hex, file_id, db.pack(face['vector']), json.dumps(face['bbox']),
                       json.dumps(face['quality']), model))
    db.changed()


def run(job_id, source):
    global _active
    drive = None
    seen, pending = set(), []
    processed = skipped = failed = face_count = total = 0
    try:
        update(job_id, status='running', phase='กำลังอ่านรายชื่อรูปภาพ')
        model = vision.model_version()
        if source['kind'] == 'drive':
            drive = Drive()
            iterator = drive.images(source['locator'], source['drive_id'])
        else:
            iterator = local_items(source['locator'])
        # Download concurrency is bounded to three images. Inference uses a
        # single locked model instance, so concurrent web requests stay safe.
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            def consume():
                nonlocal processed, failed, face_count
                item, version, future = pending.pop(0)
                if _cancel.is_set():
                    future.cancel()
                    return
                update(job_id, phase='กำลังตรวจจับใบหน้า', current_file=item['name'])
                try:
                    data = future.result()
                    result = vision.analyze(data)
                    del data
                    status = 'ready' if result['faces'] else 'no_faces'
                    reason = None if result['faces'] else ('ไม่พบใบหน้า' if not result['detected'] else 'ใบหน้าไม่ผ่านเกณฑ์คุณภาพ')
                    save_file(source, item, result, model, version, status, reason)
                    face_count += len(result['faces'])
                except DriveError as exc:
                    save_file(source, item, {}, model, version, 'error', str(exc))
                    failed += 1
                    if exc.status == 401:
                        raise
                except (ValueError, OSError, httpx.RequestError) as exc:
                    save_file(source, item, {}, model, version, 'error', str(exc)[:240])
                    failed += 1
                processed += 1
                update(job_id, processed=processed, failed=failed, faces=face_count)

            for item in iterator:
                if _cancel.is_set():
                    break
                if item['id'] in seen:
                    continue
                seen.add(item['id'])
                total += 1
                version = str(item.get('md5Checksum') or item.get('version') or item.get('modifiedTime', ''))
                existing = db.one('SELECT version,model,status FROM files WHERE source_id=? AND remote_id=?',
                                  (source['id'], item['id']))
                if existing and existing['version'] == version and existing['model'] == model and existing['status'] != 'error':
                    skipped += 1
                    # File names may change without changing image content.
                    db.execute('UPDATE files SET name=? WHERE source_id=? AND remote_id=?', (item['name'], source['id'], item['id']))
                else:
                    pending.append((item, version, pool.submit(copy_context().run, get_bytes, source, item)))
                update(job_id, total=total, skipped=skipped)
                if len(pending) >= 3:
                    consume()
            while pending and not _cancel.is_set():
                consume()
        if _cancel.is_set():
            update(job_id, status='cancelled', phase='หยุดแล้ว ข้อมูลที่สแกนสำเร็จยังใช้งานได้', finished=time.time())
        else:
            # Only reconcile removals after a complete successful listing.
            with db.connect() as c:
                old = c.execute('SELECT id,remote_id FROM files WHERE source_id=?', (source['id'],)).fetchall()
                c.executemany('DELETE FROM files WHERE id=?', [(row['id'],) for row in old if row['remote_id'] not in seen])
                c.execute('UPDATE sources SET last_scan=? WHERE id=?', (time.time(), source['id']))
            db.changed()
            update(job_id, status='completed', phase='สแกนเสร็จแล้ว', current_file=None, finished=time.time())
    except Exception as exc:
        message = str(exc) if isinstance(exc, (ValueError, OSError)) else 'ประมวลผลไม่สำเร็จ กรุณาลองใหม่หรือตรวจการติดตั้งโมเดล'
        update(job_id, status='failed', phase='งานสแกนไม่สำเร็จ', error=message[:300], finished=time.time())
    finally:
        if drive:
            drive.close()
        with _guard:
            _pending.pop(job_id, None)
            _launch_next()
