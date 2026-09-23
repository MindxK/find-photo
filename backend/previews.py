"""Bounded, short-lived thumbnail cache in RAM; never persists photo copies."""
from collections import OrderedDict
import threading
import time
import httpx
from . import db, drive, jobs, vision

MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_CACHE_ITEMS = 256
TTL = 120
_cache = OrderedDict()
_cache_bytes = 0
_lock = threading.Lock()
_load_locks = [threading.Lock() for _ in range(32)]


def _cached(key):
    global _cache_bytes
    with _lock:
        now = time.monotonic()
        for old in list(_cache):
            if _cache[old][0] <= now:
                _cache_bytes -= len(_cache.pop(old)[1])
        value = _cache.get(key)
        if value:
            _cache.move_to_end(key)
            return value[1]


def _store(key, data):
    global _cache_bytes
    if len(data) > MAX_CACHE_BYTES:
        return
    with _lock:
        old = _cache.pop(key, None)
        if old:
            _cache_bytes -= len(old[1])
        while _cache and (_cache_bytes + len(data) > MAX_CACHE_BYTES or len(_cache) >= MAX_CACHE_ITEMS):
            _cache_bytes -= len(_cache.popitem(last=False)[1][1])
        _cache[key] = (time.monotonic() + TTL, data)
        _cache_bytes += len(data)


def get(file_id, size='detail'):
    # Recheck membership on every request, including cache hits after deletion.
    file = db.one('SELECT * FROM files WHERE id=?', (file_id,))
    if not file:
        raise ValueError('Photo not found')
    source = db.one('SELECT * FROM sources WHERE id=?', (file['source_id'],))
    if not source:
        raise ValueError('Album not found')
    key = (str(db.workspace_path()), file_id, file['source_id'], file['remote_id'],
           file['version'], file['scanned'], size)
    with _load_locks[hash(key) % len(_load_locks)]:
        cached = _cached(key)
        if cached is not None:
            return cached
        if size == 'grid' and source['kind'] == 'drive':
            reader = drive.Drive()
            try:
                small = reader.thumbnail(file['remote_id'])
                if small:
                    result = vision.thumbnail(small, size=480, quality=75)
                    _store(key, result)
                    return result
            except drive.DriveError:
                raise
            except (ValueError, OSError, httpx.RequestError):
                # Missing, expired or unsupported thumbnails use the original.
                pass
            finally:
                reader.close()
        data = jobs.get_bytes(source, {'id': file['remote_id']})
        result = vision.thumbnail(data, size=480 if size == 'grid' else 1600,
                                  quality=75 if size == 'grid' else 86)
        _store(key, result)
        return result
