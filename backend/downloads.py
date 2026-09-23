"""Original photo downloads and ZIP streaming without storing copies on disk."""
from collections import deque
import re
from urllib.parse import quote
import zipfile
import httpx
from . import db, jobs


def safe_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', name).strip(' .')[:180]
    return name or 'photo'


def attachment(name):
    return "attachment; filename*=UTF-8''" + quote(safe_filename(name), safe='')


def original(file_id):
    file = db.one('SELECT * FROM files WHERE id=?', (file_id,))
    if not file:
        raise ValueError('ไม่พบรูปนี้ในอัลบั้ม')
    source = db.one('SELECT * FROM sources WHERE id=?', (file['source_id'],))
    if not source:
        raise ValueError('ไม่พบอัลบั้มต้นทาง')
    return jobs.get_bytes(source, {'id': file['remote_id']}), safe_filename(file['name'])


class ZipBuffer:
    def __init__(self):
        self.chunks = deque()

    def write(self, data):
        self.chunks.append(data)
        return len(data)

    def flush(self):
        pass

    def drain(self):
        while self.chunks:
            data = self.chunks.popleft()
            for start in range(0, len(data), 256 * 1024):
                yield data[start:start + 256 * 1024]


def archive(photos):
    buffer = ZipBuffer()
    errors = []
    saved = 0
    # Non-seekable ZIP supports Zip64 and holds only one photo at a time.
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as output:
        for index, photo in enumerate(photos, 1):
            try:
                data, name = original(photo['file_id'])
            except (ValueError, OSError, httpx.RequestError):
                errors.append(f'{index:06d}_{safe_filename(photo["name"])}: ดาวน์โหลดไม่ได้ โปรดตรวจไฟล์ต้นทางหรือการเชื่อมต่อ')
                continue
            output.writestr(f'{index:06d}_{name}', data)
            del data
            saved += 1
            yield from buffer.drain()
        report = f'รูปในผลค้นหา: {len(photos)}\nดาวน์โหลดสำเร็จ: {saved}\nดาวน์โหลดไม่ได้: {len(errors)}\n'
        if errors:
            report += '\n' + '\n'.join(errors) + '\n'
        output.writestr('download-report.txt', report.encode('utf-8-sig'))
        yield from buffer.drain()
    yield from buffer.drain()
