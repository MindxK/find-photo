import base64
import io
import json
import time
from pathlib import Path
from unittest.mock import Mock
import numpy as np
from PIL import Image
from backend import db, drive, jobs, vision


def vector(index=0):
    result = np.zeros(512, dtype=np.float32)
    result[index] = 1
    return result


def seed_profile(profile_id='p'):
    db.execute('INSERT INTO profiles VALUES(?,?,?)', (profile_id, 'เจ้าของภาพ', time.time()))
    for i in range(3):
        db.execute('INSERT INTO refs VALUES(?,?,?,?,?,?)', (f'{profile_id}-r{i}', profile_id, db.pack(vector()), 'test-model', '{}', None))


def seed_photos(count=1, similarity=1.0):
    db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)', ('s', 'Album', 'local', 'C:/Pictures', '', time.time(), None))
    embedding = vector() * similarity + vector(1) * np.sqrt(1-similarity**2)
    with db.connect() as c:
        for i in range(count):
            c.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?)', (f'file{i}', 's', f'remote{i}', f'photo{i}.jpg', 'v', 'test-model', 100, 100, 'ready', None, time.time()))
            c.execute('INSERT INTO faces VALUES(?,?,?,?,?,?)', (f'face{i}', f'file{i}', db.pack(embedding), '[0.1,0.1,0.9,0.9]', '{}', 'test-model'))
    db.changed()


def test_no_session_and_csrf_are_rejected(client):
    assert client.post('/api/model/install', headers={'X-CSRF-Token': ''}).status_code == 403
    assert client.post('/api/model/install', headers={'Origin': 'https://evil.example'}).status_code == 403
    client.cookies.clear()
    assert client.get('/api/status').status_code == 401


def test_host_and_private_response_headers(client):
    assert client.get('/', headers={'Host': 'evil.example'}).status_code == 400
    response = client.get('/api/status')
    assert response.headers['cache-control'] == 'no-store'
    assert 'frame-ancestors' in response.headers['content-security-policy']


def test_registration_is_atomic_and_stores_no_photos(client, monkeypatch):
    def analysis(data, registration=False):
        if data == b'bad':
            raise ValueError('ภาพไม่ชัด')
        return {'faces': [{'vector': vector(), 'quality': {'sharpness': 100}}]}
    monkeypatch.setattr(vision, 'analyze', analysis)
    payload = {'name': 'ฉัน', 'images': [{'name': f'{i}.png', 'data': base64.b64encode(raw).decode()} for i, raw in enumerate((b'one', b'two', b'bad'))]}
    assert client.post('/api/profiles', json=payload).status_code == 400
    assert client.get('/api/profiles').json() == []
    payload['images'][2]['data'] = base64.b64encode(b'three').decode()
    response = client.post('/api/profiles', json=payload)
    assert response.status_code == 200
    refs = db.rows('SELECT * FROM refs')
    assert len(refs) == 3
    assert all(len(db.unpack(row['embedding'])) == 512 for row in refs)
    assert all(row['embedding'] != vector().tobytes() for row in refs)
    assert client.get('/api/profiles').json()[0]['reference_count'] == 3
    profile_id = response.json()['id']
    assert client.delete('/api/profiles/' + profile_id).status_code == 200
    assert db.rows('SELECT * FROM refs') == []


def test_duplicate_references_rejected(client, monkeypatch):
    monkeypatch.setattr(vision, 'analyze', lambda *a, **k: {'faces': [{'vector': vector(), 'quality': {}}]})
    payload = {'name': 'test', 'images': [{'name': 'same.jpg', 'data': 'b25l'}] * 3}
    assert client.post('/api/profiles', json=payload).status_code == 400
    assert db.rows('SELECT * FROM profiles') == []


def test_registration_skips_unusable_images_and_keeps_valid_reference(client, monkeypatch):
    monkeypatch.setattr(vision, 'analyze', lambda data, **kwargs: {
        'faces': [{'vector': vector(), 'quality': {}}] if data == b'valid' else []})
    payload = {'name': 'test', 'images': [
        {'name': f'{i}.png', 'data': base64.b64encode(data).decode()}
        for i, data in enumerate((b'valid', b'no-face', b'invalid-landmarks'))]}
    response = client.post('/api/profiles', json=payload)
    assert response.status_code == 200
    assert response.json()['reference_count'] == 1
    assert response.json()['skipped_images'] == ['1.png', '2.png']
    assert len(db.rows('SELECT * FROM refs')) == 1


def test_registration_cannot_create_empty_profile(client, monkeypatch):
    monkeypatch.setattr(vision, 'analyze', lambda *a, **kw: {'faces': []})
    payload = {'name': 'test', 'images': [
        {'name': f'{i}.png', 'data': base64.b64encode(str(i).encode()).decode()} for i in range(3)]}
    assert client.post('/api/profiles', json=payload).status_code == 400
    assert db.rows('SELECT * FROM profiles') == []


def test_exact_search_returns_all_matches_beyond_top_k(client):
    seed_profile();seed_photos(250)
    response = client.get('/api/search', params={'profile_id': 'p', 'threshold': 0.7}).json()
    assert response['total'] == 250
    assert len(response['items']) == 24
    assert response['items'][0]['similarity'] == 1.0
    assert client.get('/api/search', params={'profile_id': 'p', 'offset': 240}).json()['items'].__len__() == 10
    assert client.get('/api/search', params={'profile_id': 'p', 'threshold': 1.2}).status_code == 400


def test_feedback_filters_only_selected_face_and_is_reversible(client):
    seed_profile();seed_photos(2, similarity=0.68)
    assert client.get('/api/search?profile_id=p&mode=review').json()['total'] == 2
    payload = {'profile_id': 'p', 'face_id': 'face0', 'label': 'no'}
    assert client.post('/api/feedback', json=payload).status_code == 200
    assert client.get('/api/search?profile_id=p').json()['total'] == 1
    assert client.get('/api/search?profile_id=p&mode=rejected').json()['total'] == 1
    payload.update(label='yes', learn=True)
    assert client.post('/api/feedback', json=payload).status_code == 200
    assert len(db.rows('SELECT * FROM refs')) == 4
    assert client.get('/api/search?profile_id=p&threshold=0.95&mode=confirmed').json()['total'] == 1
    payload.update(label='clear', learn=False)
    assert client.post('/api/feedback', json=payload).status_code == 200
    assert len(db.rows('SELECT * FROM refs')) == 3
    assert client.get('/api/search?profile_id=p&mode=confirmed').json()['total'] == 0


def test_delete_album_invalidates_search_index(client):
    seed_profile();seed_photos()
    assert client.get('/api/search?profile_id=p').json()['total'] == 1
    assert client.delete('/api/sources/s').status_code == 200
    assert client.get('/api/search?profile_id=p').json()['total'] == 0


def test_drive_pagination_continues_across_empty_page():
    client = drive.Drive()
    client.request = Mock(side_effect=[{'files': [], 'nextPageToken': 'next'}, {'files': [{'id': 'photo', 'name': 'a.jpg'}]}])
    try:
        assert list(client.pages("trashed=false")) == [{'id': 'photo', 'name': 'a.jpg'}]
        assert client.request.call_count == 2
        assert client.request.call_args.args[1]['pageToken'] == 'next'
    finally:
        client.close()


def test_drive_recursive_listing_skips_folder_records():
    client = drive.Drive()
    client.pages = Mock(side_effect=[[
        {'id': 'child', 'name': 'Subfolder', 'mimeType': 'application/vnd.google-apps.folder'},
        {'id': 'one', 'mimeType': 'image/jpeg'},
    ], [{'id': 'two', 'mimeType': 'image/jpeg'}]])
    try:
        assert [r['id'] for r in client.images('root')] == ['one', 'two']
    finally:
        client.close()


def test_oauth_state_cannot_be_reused_or_cross_session(client):
    db.set_setting('oauth_pending', {'state': 'expected', 'session': 'original', 'expires': time.time()+600})
    for token, session in [('wrong', 'original'), ('expected', 'different')]:
        try:
            drive.complete_oauth('code', token, session)
            assert False, 'Must reject state before contacting Google'
        except ValueError:
            pass


def test_scan_is_idempotent_and_reconciles_deleted_files(client, monkeypatch, tmp_path):
    path = tmp_path / 'album';path.mkdir()
    for name in ['one.jpg', 'two.jpg']:
        (path / name).write_bytes(b'test-image')
    calls = []
    def analyze(data, **kwargs):
        calls.append(1)
        return {'faces':[{'vector':vector(), 'bbox':[0,0,1,1], 'quality':{}}], 'width':100, 'height':100, 'detected':1}
    monkeypatch.setattr(vision, 'analyze', analyze)
    source_id = client.post('/api/sources', json={'name':'Album','kind':'local','locator':str(path)}).json()['id']
    def scan():
        result = client.post(f'/api/sources/{source_id}/scan')
        assert result.status_code == 200, result.text
        deadline = time.monotonic() + 10
        while jobs.busy() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not jobs.busy()
        return db.one('SELECT * FROM jobs WHERE id=?', (result.json()['id'],))
    assert scan()['processed'] == 2
    assert scan()['skipped'] == 2
    assert len(calls) == 2
    (path / 'two.jpg').unlink()
    assert scan()['status'] == 'completed'
    assert len(db.rows('SELECT * FROM files')) == 1
    assert len(db.rows('SELECT * FROM faces')) == 1


def test_local_preview_cannot_escape_source_root(client, tmp_path):
    album = tmp_path / 'album';album.mkdir()
    outside = tmp_path / 'private.jpg';outside.write_bytes(b'private')
    try:
        jobs.get_bytes({'kind':'local','locator':str(album)}, {'id':str(outside)})
        assert False
    except ValueError:
        pass


def test_bad_image_and_zero_vector_rejected():
    for data in [b'', b'not an image']:
        try:
            vision.decode(data)
            assert False
        except ValueError:
            pass
    try:
        vision.normalize(np.zeros((1,512)))
        assert False
    except ValueError:
        pass



def test_last_page_clamps_after_result_count_changes(client):
    seed_profile();seed_photos(49)
    page = client.get('/api/search?profile_id=p&offset=480').json()
    assert page['offset'] == 48
    assert len(page['items']) == 1


def test_download_original_and_requires_session(client, monkeypatch):
    seed_photos()
    original = b'original-image-bytes-not-a-thumbnail'
    monkeypatch.setattr(jobs, 'get_bytes', lambda source, item: original)
    db.execute('UPDATE files SET name=? WHERE id=?', ('รูปทดสอบ.png', 'file0'))
    response = client.get('/api/files/file0/download')
    assert response.status_code == 200
    assert response.content == original
    from urllib.parse import unquote
    assert 'รูปทดสอบ.png' in unquote(response.headers['content-disposition'])
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/files/missing/download').status_code == 404
    client.cookies.clear()
    assert client.get('/api/files/file0/download').status_code == 401
    assert client.get('/api/search/download?profile_id=p').status_code == 401


def test_zip_download_includes_every_page_and_reports_missing_files(client, monkeypatch):
    import zipfile
    seed_profile();seed_photos(30)
    db.execute('UPDATE files SET name=?', ('../รูปซ้ำ.jpg',))
    def read(source, item):
        if item['id'] == 'remote5':
            raise OSError('private path should not be exported')
        return item['id'].encode()
    monkeypatch.setattr(jobs, 'get_bytes', read)
    response = client.get('/api/search/download?profile_id=p')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == len(set(names)) == 30
        photos = [name for name in names if name != 'download-report.txt']
        assert all('/' not in name and chr(92) not in name for name in photos)
        assert {archive.read(name) for name in photos} == {f'remote{i}'.encode() for i in range(30) if i != 5}
        report = archive.read('download-report.txt').decode('utf-8-sig')
        assert 'ดาวน์โหลดสำเร็จ: 29' in report
        assert 'ดาวน์โหลดไม่ได้: 1' in report
        assert 'private path' not in report


def test_zip_download_obeys_filters_and_rejects_invalid_options(client, monkeypatch):
    import zipfile
    seed_profile();seed_photos(3)
    monkeypatch.setattr(jobs, 'get_bytes', lambda source, item: item['id'].encode())
    client.post('/api/feedback', json={'profile_id':'p','face_id':'face1','label':'yes'})
    client.post('/api/feedback', json={'profile_id':'p','face_id':'face2','label':'no'})
    for mode, expected in [('all', {b'remote0', b'remote1'}), ('confirmed', {b'remote1'}), ('rejected', {b'remote2'})]:
        response = client.get('/api/search/download', params={'profile_id':'p','mode':mode,'source_id':'s'})
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert {archive.read(n) for n in archive.namelist() if n != 'download-report.txt'} == expected
    for suffix in ['&source_id=missing', '&threshold=2', '&mode=invalid']:
        assert client.get('/api/search/download?profile_id=p'+suffix).status_code == 400


def test_download_respects_local_source_boundary(client, tmp_path):
    seed_photos()
    root = tmp_path / 'album';root.mkdir()
    outside = tmp_path / 'private.jpg';outside.write_bytes(b'private')
    db.execute('UPDATE sources SET locator=?', (str(root),))
    db.execute('UPDATE files SET remote_id=?', (str(outside),))
    assert client.get('/api/files/file0/download').status_code == 404


def test_drive_original_download_uses_drive_reader(client, monkeypatch):
    seed_photos()
    db.execute("UPDATE sources SET kind='drive'")
    mock = Mock()
    mock.download.return_value = b'drive-original'
    monkeypatch.setattr(jobs, 'Drive', lambda: mock)
    response = client.get('/api/files/file0/download')
    assert response.content == b'drive-original'
    mock.download.assert_called_once_with('remote0')
    mock.close.assert_called_once()
