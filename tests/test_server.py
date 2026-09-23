import concurrent.futures
import importlib
import io
import threading
import time
import zipfile
import pytest
from fastapi.testclient import TestClient
from backend import auth, db, drive, jobs, search, vision
from test_app import seed_profile, seed_photos

application = importlib.import_module('backend.app')
ORIGIN = 'http://127.0.0.1:8765'


def refresh(client):
    info = client.get('/api/auth/session').json()
    client.headers.update({'Origin': ORIGIN, 'X-CSRF-Token': info['csrf']})
    return info


def signup(client, name, code=None):
    client.get('/login')
    refresh(client)
    payload = {'username': name, 'password': 'Long-test-password-123!'}
    if code is not None:
        payload['code'] = code
    response = client.post('/api/auth/register', json=payload)
    assert response.status_code == 200, response.text
    return refresh(client)['user']


@pytest.fixture
def accounts(client, monkeypatch, tmp_path):
    for module in (application, auth, db, drive):
        monkeypatch.setattr(module, 'SERVER_MODE', True)
    monkeypatch.setattr(auth, 'ACCOUNTS', tmp_path / 'accounts.sqlite3')
    monkeypatch.setattr(auth, 'BOOTSTRAP', tmp_path / 'setup.txt')
    auth._attempts.clear()
    auth.init()
    owner = signup(client, 'owner', auth.BOOTSTRAP.read_text())
    other = TestClient(application.app, base_url=ORIGIN)
    member = signup(other, 'member')
    yield client, other, owner, member
    other.close()
    auth._attempts.clear()


def test_login_sessions_csrf_and_open_registration(accounts):
    owner, member, _, _ = accounts
    assert member.post('/api/model/install').status_code == 403
    assert member.post('/api/sources', json={'name':'private', 'kind':'local', 'locator':'.'}).status_code == 403
    stale = member.cookies.get('findface_session')
    assert member.post('/api/auth/logout').status_code == 200
    assert member.get('/api/profiles').status_code == 401
    member.cookies.set('findface_session', stale)
    assert member.get('/api/status').status_code == 401
    member.cookies.clear()
    member.get('/login')
    refresh(member)
    assert member.post('/api/auth/login', json={'username':'member','password':'wrong-password-123'}).status_code == 401
    old = member.cookies.get('findface_session')
    assert member.post('/api/auth/login', json={'username':'member','password':'Long-test-password-123!'}).status_code == 200
    assert member.cookies.get('findface_session') != old
    refresh(member)
    assert member.get('/api/status').json()['user']['username'] == 'member'
    assert member.post('/api/auth/logout', headers={'Origin':'https://evil.example'}).status_code == 403
    assert member.post('/api/auth/logout', headers={'X-CSRF-Token':'bad'}).status_code == 403
    third = TestClient(application.app, base_url=ORIGIN)
    third_user = signup(third, 'third')
    assert third_user['admin'] == 0
    assert third_user['scope'] != 'legacy'
    fourth = TestClient(application.app, base_url=ORIGIN)
    fourth.get('/login'); refresh(fourth)
    payload = {'username':'third','password':'Long-test-password-123!'}
    assert fourth.post('/api/auth/register', json=payload).status_code == 400
    payload['username'] = 'fourth'
    assert fourth.post('/api/auth/register', json=payload, headers={'X-CSRF-Token':'bad'}).status_code == 403
    fourth_user = signup(fourth, 'fourth')
    assert fourth_user['scope'] != third_user['scope']
    with auth.connect() as c:
        hashes = [r[0] for r in c.execute('SELECT password FROM users')]
    assert len(set(hashes)) == len(hashes)
    assert all('Long-test' not in value for value in hashes)
    third.close(); fourth.close()


def test_workspace_api_and_vector_cache_isolation(accounts, monkeypatch):
    owner, member, a, b = accounts
    for user, name in ((a, 'owner-photo.jpg'), (b, 'member-photo.jpg')):
        with db.workspace(user['scope']):
            seed_profile(); seed_photos()
            db.execute('UPDATE files SET name=?', (name,))
            db.set_setting('google_token', {'access_token':user['username'], 'expires_at':time.time()+3600})
    for client, name in ((owner,'owner-photo.jpg'), (member,'member-photo.jpg'), (owner,'owner-photo.jpg')):
        assert client.get('/api/search?profile_id=p').json()['items'][0]['name'] == name
    with db.workspace(a['scope']):
        seed_profile('owner-only')
    assert member.get('/api/search?profile_id=owner-only').status_code == 400
    member.delete('/api/profiles/owner-only')
    with db.workspace(a['scope']):
        assert db.one('SELECT id FROM profiles WHERE id=?', ('owner-only',))
    # Even colliding record IDs resolve to the caller's source and token.
    monkeypatch.setattr(jobs, 'get_bytes', lambda *args: drive.access_token().encode())
    assert owner.get('/api/files/file0/download').content == b'owner'
    assert member.get('/api/files/file0/download').content == b'member'
    def download(client, expected):
        response = client.get('/api/search/download?profile_id=p')
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.read('000001_'+expected+'-photo.jpg') == expected.encode()
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(download, owner, 'owner'), pool.submit(download, member, 'member')]
        for future in futures: future.result()
    with db.workspace(a['scope']):
        db.execute('INSERT INTO files SELECT ?,source_id,?,name,version,model,width,height,status,reason,scanned FROM files WHERE id=?', ('owner-only-file','owner-remote','file0'))
    assert member.get('/api/files/owner-only-file/download').status_code == 404
    assert member.get('/api/files/owner-only-file/preview').status_code == 404
    member.post('/api/google/disconnect')
    with db.workspace(a['scope']):
        assert db.setting('google_token')['access_token'] == 'owner'


def test_fail_closed_and_private_files(accounts):
    _, member, _, b = accounts
    with db.workspace(None):
        with pytest.raises(RuntimeError): db.rows('SELECT * FROM profiles')
    with db.workspace(b['scope']):
        with pytest.raises(ValueError): jobs.get_bytes({'kind':'local','locator':'.'}, {'id':'README.md'})
    stranger = TestClient(application.app, base_url=ORIGIN)
    assert stranger.get('/').url.path == '/login'
    for path in ('/api/status','/api/profiles','/api/sources','/api/files/a/download','/api/files/a/preview','/api/search?profile_id=p'):
        assert stranger.get(path).status_code == 401
    assert stranger.get('/data/encryption.key').status_code == 404
    assert stranger.get('/static/../data/encryption.key').status_code == 404
    stranger.close()


def test_google_shared_client_without_shared_tokens(accounts):
    owner, member, a, b = accounts
    with db.workspace(a['scope']):
        db.set_setting('google_server_config', {'client_id':'example.apps.googleusercontent.com','client_secret':'test-secret'})
        db.set_setting('google_token', {'access_token':'owner-token'})
    info = member.get('/api/status').json()
    assert info['google_configured'] and not info['google_connected']
    assert 'test-secret' not in str(info)
    assert member.post('/api/google/connect').status_code == 200
    with db.workspace(b['scope']):
        pending = db.setting('oauth_pending')
        assert pending['config']['client_secret'] == 'test-secret'
        assert db.setting('google_token') is None
    with db.workspace(a['scope']):
        assert db.setting('oauth_pending') is None
        with pytest.raises(ValueError): drive.complete_oauth('code',pending['state'],pending['session'])


def test_public_host_and_secure_cookie(accounts, monkeypatch):
    monkeypatch.setattr(application, 'public_origin', lambda: 'https://findface.example')
    client = TestClient(application.app, base_url='https://findface.example')
    response = client.get('/login')
    assert 'Secure' in response.headers['set-cookie']
    assert 'HttpOnly' in response.headers['set-cookie']
    csrf = client.get('/api/auth/session').json()['csrf']
    response = client.post('/api/auth/login', headers={'Origin':'https://findface.example','X-CSRF-Token':csrf}, json={'username':'member','password':'Long-test-password-123!'})
    assert response.status_code == 200
    status = client.get('/api/status').json()
    assert status['callback_url'] == 'https://findface.example/api/google/callback'
    assert client.post('/api/auth/logout', headers={'Origin':ORIGIN,'X-CSRF-Token':status['csrf']}).status_code == 403
    assert client.get('/',headers={'Host':'evil.example'}).status_code == 400
    client.close()


def test_queue_and_worker_token_isolation(accounts, monkeypatch):
    owner, member, a, b = accounts
    entered = threading.Event(); release = threading.Event()
    seen = []
    class FakeDrive:
        def images(self, *args):
            yield {'id':'same-photo-id','name':'photo.jpg','version':'1'}
        def download(self, item):
            token = drive.access_token()
            seen.append((db.scope_key(), token))
            if token == 'owner':
                entered.set(); assert release.wait(10)
            return b'image'
        def close(self): pass
    monkeypatch.setattr(jobs, 'Drive', FakeDrive)
    monkeypatch.setattr(vision, 'analyze', lambda data: {'faces':[], 'detected':0, 'width':10, 'height':10})
    for user in (a,b):
        with db.workspace(user['scope']):
            db.set_setting('google_token',{'access_token':user['username'],'expires_at':time.time()+3600})
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',('s','album','drive','root','',time.time(),None))
    try:
        first = owner.post('/api/sources/s/scan').json()['id']
        assert entered.wait(5)
        second = member.post('/api/sources/s/scan').json()['id']
        assert member.get('/api/status').json()['jobs'][0]['status'] == 'queued'
        assert member.post('/api/jobs/'+first+'/cancel').status_code == 400
        assert member.post('/api/sources/s/scan').status_code == 400
    finally:
        release.set()
        deadline = time.monotonic()+10
        while jobs._pending and time.monotonic()<deadline: time.sleep(.02)
    assert not jobs._pending
    assert seen == [(a['scope'],'owner'),(b['scope'],'member')]
    for client, job_id in ((owner,first),(member,second)):
        info = client.get('/api/status').json()
        assert len(info['jobs']) == 1 and info['jobs'][0]['id'] == job_id
        assert info['jobs'][0]['status'] == 'completed'
        assert info['stats']['photos'] == 1


def test_login_rate_limit(accounts):
    _, member, _, _ = accounts
    member.post('/api/auth/logout'); member.get('/login'); refresh(member)
    auth._attempts.clear()
    for _ in range(8):
        assert member.post('/api/auth/login',json={'username':'member','password':'wrong-password-123'}).status_code == 401
    assert member.post('/api/auth/login',json={'username':'member','password':'wrong-password-123'}).status_code == 429


def test_web_client_update_preserves_owner_data(accounts):
    import json
    owner, member, a, b = accounts
    with db.workspace(a['scope']):
        seed_profile(); seed_photos()
        db.set_setting('google_config', {'client_id':'desktop.apps.googleusercontent.com','client_secret':'desktop-secret'})
        db.set_setting('google_token', {'access_token':'existing-owner-token'})
    payload = {'credentials':json.dumps({'web':{'client_id':'web.apps.googleusercontent.com','client_secret':'web-secret'}})}
    assert member.post('/api/admin/google/config',json=payload).status_code == 403
    assert owner.post('/api/admin/google/config',json=payload).status_code == 200
    with db.workspace(a['scope']):
        assert drive.config()['client_id'] == 'desktop.apps.googleusercontent.com'
        assert drive.authorization_config()['client_id'] == 'web.apps.googleusercontent.com'
        assert db.setting('google_token')['access_token'] == 'existing-owner-token'
        assert db.one('SELECT COUNT(*) n FROM files')['n'] == 1
    with db.workspace(b['scope']):
        assert drive.authorization_config()['client_id'] == 'web.apps.googleusercontent.com'
        assert db.setting('google_token') is None


def test_planned_restart_resumes_only_selected_interrupted_jobs(accounts, monkeypatch):
    import json
    from backend.config import DATA
    _, _, a, b = accounts
    plan=[]; calls=[]
    for index,user in enumerate((a,b)):
        with db.workspace(user['scope']):
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',('s','album','drive','root','',time.time(),None))
            db.execute('INSERT INTO jobs(id,source_id,status,phase,created) VALUES(?,?,?,?,?)',('old','s','interrupted','test',time.time()))
            db.execute('INSERT INTO jobs(id,source_id,status,phase,created) VALUES(?,?,?,?,?)',('done','s','completed','test',time.time()))
        plan.append({'scope':user['scope'],'job_id':'old','source_id':'s'})
    plan.extend([{'scope':a['scope'],'job_id':'done','source_id':'s'}, {'scope':'../outside','job_id':'old','source_id':'s'}])
    (DATA/'resume-scans.json').write_text(json.dumps(plan))
    def start(source):
        calls.append((db.scope_key(),source))
        return 'resumed-'+db.scope_key()
    monkeypatch.setattr(jobs,'start',start)
    jobs.resume_after_restart()
    assert calls == [(a['scope'],'s'),(b['scope'],'s')]
    assert not (DATA/'resume-scans.json').exists()
    jobs.resume_after_restart()
    assert len(calls)==2
    report=json.loads((DATA/'resumed-scans.json').read_text())
    assert [row['status'] for row in report]==['resumed','resumed','skipped','rejected']


def test_owner_setup_still_requires_local_secret(client, monkeypatch, tmp_path):
    for module in (application, auth, db, drive):
        monkeypatch.setattr(module, 'SERVER_MODE', True)
    monkeypatch.setattr(auth, 'ACCOUNTS', tmp_path / 'accounts.sqlite3')
    monkeypatch.setattr(auth, 'BOOTSTRAP', tmp_path / 'setup.txt')
    auth._attempts.clear()
    auth.init()
    refresh(client)
    payload = {'username':'owner','password':'Long-test-password-123!'}
    assert client.post('/api/auth/register', json=payload).status_code == 403
    assert not auth.owner_exists()
    owner = signup(client, 'owner', auth.BOOTSTRAP.read_text())
    assert owner['admin'] == 1 and owner['scope'] == 'legacy'
    assert not auth.BOOTSTRAP.exists()
    auth._attempts.clear()
