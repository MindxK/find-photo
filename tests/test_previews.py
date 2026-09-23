import io
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import httpx
import pytest
from PIL import Image
from backend import db, drive, jobs, previews
from test_app import seed_photos


def photo(color='red'):
    output = io.BytesIO()
    Image.new('RGB', (1800, 1200), color).save(output, format='JPEG')
    return output.getvalue()


@pytest.fixture(autouse=True)
def empty_cache():
    previews._cache.clear()
    previews._cache_bytes = 0
    yield
    previews._cache.clear()
    previews._cache_bytes = 0


def test_grid_uses_drive_thumbnail_and_detail_keeps_original(client, monkeypatch):
    seed_photos()
    db.execute("UPDATE sources SET kind='drive'")
    reader = Mock()
    reader.thumbnail.return_value = photo()
    monkeypatch.setattr(drive, 'Drive', lambda: reader)
    original = Mock(return_value=photo('blue'))
    monkeypatch.setattr(jobs, 'get_bytes', original)
    grid = client.get('/api/files/file0/preview?size=grid')
    assert grid.status_code == 200
    assert Image.open(io.BytesIO(grid.content)).size == (480, 320)
    assert client.get('/api/files/file0/preview?size=grid').content == grid.content
    assert reader.thumbnail.call_count == 1
    original.assert_not_called()
    detail = client.get('/api/files/file0/preview')
    assert Image.open(io.BytesIO(detail.content)).size == (1600, 1067)
    original.assert_called_once()
    assert client.get('/api/files/file0/preview?size=huge').status_code == 422
    db.execute("UPDATE files SET version='new'")
    client.get('/api/files/file0/preview?size=grid')
    assert reader.thumbnail.call_count == 2
    db.execute("DELETE FROM sources")
    assert client.get('/api/files/file0/preview?size=grid').status_code == 404


def test_thumbnail_missing_falls_back_and_concurrent_requests_load_once(client, monkeypatch):
    seed_photos()
    db.execute("UPDATE sources SET kind='drive'")
    reader = Mock()
    reader.thumbnail.return_value = None
    monkeypatch.setattr(drive, 'Drive', lambda: reader)
    original = Mock(return_value=photo())
    monkeypatch.setattr(jobs, 'get_bytes', original)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: previews.get('file0', 'grid'), range(4)))
    assert len(set(results)) == 1
    original.assert_called_once()
    reader.thumbnail.assert_called_once()


def test_cache_isolated_between_accounts(client, monkeypatch):
    seen = []
    def original(*args):
        seen.append(db.scope_key())
        return photo('red' if db.scope_key() == 'a'*32 else 'blue')
    monkeypatch.setattr(jobs, 'get_bytes', original)
    results = []
    for scope in ('a'*32, 'b'*32):
        with db.workspace(scope):
            db.init(); seed_photos()
            results.append(previews.get('file0', 'grid'))
    with db.workspace('a'*32):
        assert previews.get('file0', 'grid') == results[0]
    assert results[0] != results[1]
    assert seen == ['a'*32, 'b'*32]


def test_cache_expiry_and_memory_bound(monkeypatch):
    monkeypatch.setattr(previews, 'MAX_CACHE_BYTES', 6)
    monkeypatch.setattr(previews, 'MAX_CACHE_ITEMS', 2)
    clock = [10]
    monkeypatch.setattr(previews.time, 'monotonic', lambda: clock[0])
    previews._store('a', b'1234'); previews._store('b', b'5678')
    assert previews._cached('a') is None
    assert previews._cache_bytes == 4
    clock[0] += previews.TTL + 1
    assert previews._cached('b') is None
    assert previews._cache_bytes == 0


def test_drive_thumbnail_credentials_and_redirect_guard(monkeypatch):
    monkeypatch.setattr(drive, 'access_token', lambda: 'test-token')
    calls = []
    def transport(request):
        calls.append(request)
        assert request.headers['authorization'] == 'Bearer test-token'
        if request.url.host == 'www.googleapis.com':
            return httpx.Response(200, json={'thumbnailLink':'https://lh3.googleusercontent.com/photo=s220'})
        assert str(request.url).endswith('=s480')
        return httpx.Response(302, headers={'Location':'https://evil.example/steal'})
    reader = drive.Drive(); reader.client.close()
    reader.client = httpx.Client(transport=httpx.MockTransport(transport))
    try:
        assert reader.thumbnail('file') is None
        assert len(calls) == 2
        calls.clear()
        reader.request = lambda *args: {'thumbnailLink':'https://googleusercontent.com.evil.example/x'}
        assert reader.thumbnail('file') is None
        assert calls == []
    finally:
        reader.close()


def test_drive_thumbnail_reads_small_media(monkeypatch):
    monkeypatch.setattr(drive, 'access_token', lambda: 'test-token')
    reader = drive.Drive(); reader.client.close()
    reader.request = lambda *args: {'thumbnailLink':'https://lh3.googleusercontent.com/photo=s220'}
    reader.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'thumbnail')))
    try:
        assert reader.thumbnail('file') == b'thumbnail'
    finally:
        reader.close()
