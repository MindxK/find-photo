import asyncio
import base64
import binascii
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
import uuid
import httpx
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from typing import Literal
from pydantic import BaseModel, Field
from . import auth, db, downloads, drive, jobs, models, previews, search, vision
from .config import ROOT, ORIGIN, CALLBACK, MAX_BYTES, MODEL_NAME, SERVER_MODE, public_origin
from urllib.parse import urlsplit

_sessions = {}
_preview_slots = threading.BoundedSemaphore(3)


@asynccontextmanager
async def lifespan(app):
    app.state.preview_slots = asyncio.Semaphore(6)
    if SERVER_MODE:
        auth.init()
        jobs.resume_after_restart()
    else:
        db.init()
    yield


app = FastAPI(title='FindFace', docs_url=None, redoc_url=None, lifespan=lifespan)
app.include_router(auth.router)


@app.middleware('http')
async def local_security(request: Request, call_next):
    public = public_origin() if SERVER_MODE else ''
    origins = {ORIGIN, ORIGIN.replace('127.0.0.1', 'localhost')}
    if public:
        origins.add(public)
    if request.headers.get('host', '') not in {urlsplit(o).netloc for o in origins}:
        return JSONResponse({'detail': 'Invalid host'}, status_code=400)
    session_id = request.cookies.get('findface_session', '')
    session = _sessions.get(session_id)
    now = time.time()
    if session and session['expires'] < now:
        _sessions.pop(session_id, None)
        session = None
    new_session = False
    if request.url.path in ('/', '/login') and request.method == 'GET' and not session:
        for key in list(_sessions):
            if _sessions[key]['expires'] < now:
                del _sessions[key]
        if len(_sessions) >= 2000:
            return JSONResponse({'detail': 'เซิร์ฟเวอร์มีผู้ใช้มาก กรุณาลองใหม่ภายหลัง'}, status_code=503)
        session_id = secrets.token_urlsafe(32)
        session = {'csrf': secrets.token_urlsafe(32), 'expires': now + 86400}
        _sessions[session_id] = session
        new_session = True
    user = auth.get_user(session.get('user_id')) if SERVER_MODE and session else None
    if request.url.path.startswith('/api/'):
        if not session:
            return JSONResponse({'detail': 'เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่'}, status_code=401)
        if SERVER_MODE and not user and not request.url.path.startswith('/api/auth/'):
            return JSONResponse({'detail': 'กรุณาเข้าสู่ระบบ'}, status_code=401)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            # Bind mutations to the origin of this request, not another allowed origin.
            expected_origin = public if public and request.url.hostname == urlsplit(public).hostname else str(request.base_url).rstrip('/')
            if request.headers.get('origin') != expected_origin or not secrets.compare_digest(
                    request.headers.get('x-csrf-token', ''), session['csrf']):
                return JSONResponse({'detail': 'คำขอไม่ผ่านการตรวจสอบความปลอดภัย'}, status_code=403)
            content = bytearray()
            body_limit = 32768 if request.url.path.startswith('/api/auth/') else 64 * 1024 * 1024
            async for chunk in request.stream():
                content.extend(chunk)
                if len(content) > body_limit:
                    return JSONResponse({'detail': 'ข้อมูลอัปโหลดเกินขนาดที่อนุญาต'}, status_code=413)
            request._body = bytes(content)
    request.state.session_id = session_id
    request.state.csrf = session['csrf'] if session else ''
    request.state.user = user
    callback_origin = public if public and request.url.hostname == urlsplit(public).hostname else ORIGIN
    callback_token = drive.callback_url.set(callback_origin + '/api/google/callback')
    scope_token = db.tenant.set(user['scope'] if user else (None if SERVER_MODE else 'legacy'))
    try:
        response = await call_next(request)
    finally:
        db.tenant.reset(scope_token)
        drive.callback_url.reset(callback_token)
    if getattr(request.state, 'login_user', None):
        _sessions.pop(session_id, None)
        session_id = secrets.token_urlsafe(32)
        _sessions[session_id] = {'csrf': secrets.token_urlsafe(32), 'expires': now+86400, 'user_id': request.state.login_user}
        new_session = True
    if getattr(request.state, 'logout', False):
        _sessions.pop(session_id, None)
        response.delete_cookie('findface_session')
        new_session = False
    if new_session:
        response.set_cookie('findface_session', session_id, httponly=True, samesite='lax', max_age=86400,
                            secure=request.url.hostname not in ('127.0.0.1', 'localhost'))
    response.headers.update({
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'",
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    })
    return response


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


@app.exception_handler(httpx.RequestError)
async def network_error(request, exc):
    return JSONResponse({'detail': 'ติดต่อ Google ไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่'}, status_code=502)


@app.get('/')
def home(request: Request):
    if SERVER_MODE and not request.state.user:
        return RedirectResponse('/login')
    return FileResponse(ROOT / 'web' / 'index.html')


@app.get('/login')
def login_page():
    return FileResponse(ROOT / 'web' / 'login.html')


@app.get('/api/status')
def status(request: Request):
    stats = {
        'photos': db.one("SELECT COUNT(*) AS n FROM files WHERE status IN ('ready','no_faces')")['n'],
        'faces': db.one('SELECT COUNT(*) AS n FROM faces')['n'],
        'profiles': db.one('SELECT COUNT(*) AS n FROM profiles')['n'],
        'sources': db.one('SELECT COUNT(*) AS n FROM sources')['n'],
        'errors': db.one("SELECT COUNT(*) AS n FROM files WHERE status='error'")['n'],
    }
    return {'server': SERVER_MODE, 'user': request.state.user, 'public_url': public_origin() if SERVER_MODE else '',
            'csrf': request.state.csrf, 'stats': stats, 'model_ready': vision.model_available(), 'model_name': MODEL_NAME,
            'model_install': models.state, 'google_configured': drive.configured(),
            'google_connected': bool(db.setting('google_token')), 'google_user': db.setting('google_user', {}),
            'callback_url': drive.callback_url.get(), 'server_google_configured': bool(db.setting('google_server_config')) if request.state.user and request.state.user['admin'] else False, 'busy': jobs.busy(),
            'jobs': db.rows('SELECT jobs.*,sources.name AS source_name FROM jobs LEFT JOIN sources ON sources.id=jobs.source_id ORDER BY jobs.created DESC LIMIT 15')}


@app.post('/api/model/install')
def install_model(request: Request):
    auth.require_admin(request)
    if not vision.model_available():
        models.start()
    return {'ok': True}


class OAuthConfig(BaseModel):
    credentials: str = Field(min_length=10, max_length=20000)


@app.post('/api/google/config')
def configure_google(payload: OAuthConfig):
    if jobs.busy():
        raise ValueError('กรุณาหยุดงานสแกนก่อนเปลี่ยนการตั้งค่า')
    try:
        data = json.loads(payload.credentials)
        data = data.get('web') or data.get('installed') or data
        client_id, secret = data['client_id'], data['client_secret']
        if not isinstance(client_id, str) or not client_id.endswith('.apps.googleusercontent.com') or not isinstance(secret, str) or not secret:
            raise ValueError()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('กรุณาใช้ไฟล์ OAuth Client JSON ที่ดาวน์โหลดจาก Google Cloud')
    old = drive.config()
    if old.get('client_id') != client_id:
        db.execute("DELETE FROM settings WHERE key IN ('google_token','google_user','oauth_pending')")
        db.execute("DELETE FROM sources WHERE kind='drive'")
        db.changed()
    db.set_setting('google_config', {'client_id': client_id, 'client_secret': secret})
    return {'ok': True, 'callback_url': drive.callback_url.get()}


@app.post('/api/admin/google/config')
def configure_server_google(payload: OAuthConfig, request: Request):
    auth.require_admin(request)
    if not SERVER_MODE:
        raise ValueError('เปิดโหมดเซิร์ฟเวอร์ก่อน')
    try:
        client = json.loads(payload.credentials)['web']
        client_id, secret = client['client_id'], client['client_secret']
        if not isinstance(client_id, str) or not client_id.endswith('.apps.googleusercontent.com') or not isinstance(secret, str) or not secret:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ValueError('ใช้ไฟล์ OAuth JSON ชนิด Web application สำหรับเซิร์ฟเวอร์')
    # Deliberately separate from the owner's existing Desktop client/token.
    db.set_setting('google_server_config', {'client_id': client_id, 'client_secret': secret})
    return {'ok': True}


@app.post('/api/google/connect')
def google_connect(request: Request):
    if jobs.busy():
        raise ValueError('กรุณาหยุดงานสแกนก่อนเชื่อมต่อบัญชี')
    return {'url': drive.authorization_url(request.state.session_id)}


@app.get('/api/google/callback')
def google_callback(request: Request, state: str = '', code: str = '', error: str = ''):
    if error:
        return RedirectResponse('/?oauth=cancelled')
    if jobs.busy():
        return RedirectResponse('/?oauth=busy')
    try:
        drive.complete_oauth(code, state, request.state.session_id)
        client = drive.Drive()
        try:
            user = client.request('/about', {'fields': 'user(displayName,emailAddress)'})
            db.set_setting('google_user', user.get('user', {}))
        finally:
            client.close()
    except (ValueError, httpx.RequestError):
        return RedirectResponse('/?oauth=error')
    return RedirectResponse('/?oauth=connected')


@app.post('/api/google/disconnect')
def google_disconnect():
    if jobs.busy():
        raise ValueError('กรุณาหยุดงานสแกนก่อนยกเลิกการเชื่อมต่อ')
    token = db.setting('google_token', {})
    db.execute("DELETE FROM settings WHERE key IN ('google_token','google_user','oauth_pending')")
    db.execute("DELETE FROM sources WHERE kind='drive'")
    db.changed()
    if token.get('refresh_token'):
        try:
            httpx.post('https://oauth2.googleapis.com/revoke', data={'token': token['refresh_token']}, timeout=10)
        except httpx.RequestError:
            pass
    return {'ok': True}


@app.get('/api/google/folders')
def google_folders(parent: str = 'root', drive_id: str = '', page_token: str = ''):
    drive.safe_id(parent)
    drive.safe_id(drive_id)
    client = drive.Drive()
    try:
        params = {'q': f"trashed=false and mimeType='application/vnd.google-apps.folder' and '{parent}' in parents",
                  'pageSize': 100, 'orderBy': 'name', 'fields': 'nextPageToken,files(id,name)',
                  'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true',
                  'corpora': 'drive' if drive_id else 'user'}
        if drive_id:
            params['driveId'] = drive_id
        if page_token:
            params['pageToken'] = page_token
        return client.request('/files', params)
    finally:
        client.close()


@app.get('/api/google/drives')
def google_drives():
    client = drive.Drive()
    try:
        return client.drives()
    finally:
        client.close()


@app.get('/api/profiles')
def profiles():
    return db.rows('SELECT profiles.*,COUNT(refs.id) AS reference_count FROM profiles LEFT JOIN refs ON refs.profile_id=profiles.id GROUP BY profiles.id ORDER BY created')


class ReferenceImage(BaseModel):
    name: str = Field(max_length=250)
    data: str = Field(max_length=12_000_000)


class Registration(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    images: list[ReferenceImage] = Field(min_length=3, max_length=5)


@app.post('/api/profiles')
def register_profile(payload: Registration):
    if not payload.name.strip():
        raise ValueError('กรุณาระบุชื่อโปรไฟล์')
    model = vision.model_version()
    faces, hashes, skipped = [], set(), []
    for upload in payload.images:
        try:
            data = base64.b64decode(upload.data, validate=True)
        except binascii.Error:
            raise ValueError('ข้อมูลภาพอัปโหลดไม่ถูกต้อง')
        digest = hashlib.sha256(data).hexdigest()
        if digest in hashes:
            raise ValueError('กรุณาใช้ภาพอ้างอิงที่แตกต่างกัน 3–5 ภาพ')
        hashes.add(digest)
        try:
            result = vision.analyze(data, registration=True)
            if result['faces']:
                faces.append(result['faces'][0])
            else:
                skipped.append(upload.name)
        except ValueError as exc:
            raise ValueError(f'{upload.name}: {exc}')
    if not faces:
        raise ValueError('ยังไม่มีใบหน้าอ้างอิงสำหรับค้นหา เพิ่มภาพที่เห็นใบหน้าคนเดียวอย่างน้อย 1 ภาพ')
    vectors = np.stack([face['vector'] for face in faces])
    agreement = vectors @ vectors.T
    np.fill_diagonal(agreement, -1)
    if len(faces) > 1 and np.any(agreement.max(axis=1) < 0.25):
        raise ValueError('ภาพอ้างอิงบางภาพไม่สอดคล้องกัน กรุณาใช้ภาพบุคคลเดียวกันที่เห็นใบหน้าชัด')
    profile_id = uuid.uuid4().hex
    with db.connect() as c:
        c.execute('INSERT INTO profiles VALUES(?,?,?)', (profile_id, payload.name.strip(), time.time()))
        for face in faces:
            c.execute('INSERT INTO refs VALUES(?,?,?,?,?,?)', (uuid.uuid4().hex, profile_id, db.pack(face['vector']), model, json.dumps(face['quality']), None))
    return {'id': profile_id, 'reference_count': len(faces), 'skipped_images': skipped}


@app.delete('/api/profiles/{profile_id}')
def delete_profile(profile_id: str):
    db.execute('DELETE FROM profiles WHERE id=?', (profile_id,))
    return {'ok': True}


@app.get('/api/sources')
def sources():
    return db.rows('''SELECT sources.*,COUNT(files.id) AS photo_count,
      SUM(CASE WHEN files.status='error' THEN 1 ELSE 0 END) AS error_count
      FROM sources LEFT JOIN files ON files.source_id=sources.id GROUP BY sources.id ORDER BY sources.created DESC''')


class Source(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str
    locator: str = Field(default='', max_length=2000)
    drive_id: str = Field(default='', max_length=200)


@app.post('/api/sources')
def add_source(payload: Source, request: Request):
    if payload.kind == "local":
        auth.require_admin(request)
    locator = payload.locator.strip().strip('"')
    if payload.kind == 'local':
        path = Path(locator).expanduser().resolve()
        if not locator or not path.is_dir():
            raise ValueError('ไม่พบโฟลเดอร์ กรุณาวางพาธเต็มของโฟลเดอร์รูปในเครื่อง')
        locator = str(path)
    elif payload.kind == 'drive':
        if not db.setting('google_token'):
            raise ValueError('กรุณาเชื่อมต่อ Google Drive ก่อน')
        drive.safe_id(locator)
        drive.safe_id(payload.drive_id)
    else:
        raise ValueError('ประเภทอัลบั้มไม่ถูกต้อง')
    existing = db.one('SELECT id FROM sources WHERE kind=? AND locator=? AND drive_id=?', (payload.kind, locator, payload.drive_id))
    if existing:
        return {'id': existing['id']}
    source_id = uuid.uuid4().hex
    db.execute('INSERT INTO sources(id,name,kind,locator,drive_id,created) VALUES(?,?,?,?,?,?)',
               (source_id, payload.name.strip() or 'อัลบั้มของฉัน', payload.kind, locator, payload.drive_id, time.time()))
    return {'id': source_id}


@app.delete('/api/sources/{source_id}')
def delete_source(source_id: str):
    if jobs.busy():
        raise ValueError('กรุณาหยุดงานสแกนก่อนลบอัลบั้ม')
    db.execute('DELETE FROM sources WHERE id=?', (source_id,))
    db.changed()
    return {'ok': True}


@app.post('/api/sources/{source_id}/scan')
def scan_source(source_id: str):
    return {'id': jobs.start(source_id)}


@app.post('/api/jobs/{job_id}/cancel')
def cancel_job(job_id: str):
    jobs.cancel(job_id)
    return {'ok': True}


@app.get('/api/files/issues')
def issues(source_id: str = ''):
    sql = "SELECT id,name,status,reason FROM files WHERE status IN ('error','no_faces')"
    args = ()
    if source_id:
        sql += ' AND source_id=?'
        args = (source_id,)
    return db.rows(sql + ' ORDER BY scanned DESC LIMIT 100', args)


@app.get('/api/search')
def search_faces(profile_id: str, threshold: float = 0.65, source_id: str = '', mode: str = 'all', offset: int = 0):
    validate_search(threshold, mode, offset)
    return search.search(profile_id, threshold, source_id, mode, offset)


def validate_search(threshold, mode, offset=0):
    if not 0.3 <= threshold <= 0.95 or mode not in ('all', 'review', 'confirmed', 'match', 'rejected') or offset < 0:
        raise ValueError('ตัวเลือกการค้นหาไม่ถูกต้อง')


@app.get('/api/search/download')
def download_results(profile_id: str, threshold: float = 0.65, source_id: str = '', mode: str = 'all'):
    validate_search(threshold, mode)
    result = search.search(profile_id, threshold, source_id, mode, limit=None)
    if not result['total']:
        raise ValueError('ไม่มีรูปในผลค้นหานี้สำหรับดาวน์โหลด')
    return StreamingResponse(downloads.archive(result['items']), media_type='application/zip',
                             headers={'Content-Disposition': downloads.attachment('FindFace-photos.zip')})


@app.get('/api/files/{file_id}/download')
def download_photo(file_id: str):
    with _preview_slots:
        try:
            data, name = downloads.original(file_id)
        except (ValueError, OSError, httpx.RequestError):
            return JSONResponse({'detail': 'ดาวน์โหลดรูปไม่ได้ กรุณาตรวจไฟล์ต้นทางหรือการเชื่อมต่อ Google Drive'}, status_code=404)
    return Response(data, media_type='application/octet-stream',
                    headers={'Content-Disposition': downloads.attachment(name)})


@app.get('/api/files/{file_id}/preview')
async def preview(file_id: str, request: Request, size: Literal['grid', 'detail'] = 'detail'):
    # Waiting previews must not occupy the shared API worker pool.
    async with request.app.state.preview_slots:
        try:
            data = await run_in_threadpool(previews.get, file_id, size)
            return Response(data, media_type='image/jpeg')
        except (ValueError, OSError, httpx.RequestError):
            return Response(status_code=404)


class Feedback(BaseModel):
    profile_id: str
    face_id: str
    label: str
    learn: bool = False


@app.post('/api/feedback')
def feedback(payload: Feedback):
    if payload.label not in ('yes', 'no', 'clear'):
        raise ValueError('ผลยืนยันไม่ถูกต้อง')
    profile = db.one('SELECT id FROM profiles WHERE id=?', (payload.profile_id,))
    face = db.one('SELECT * FROM faces WHERE id=?', (payload.face_id,))
    if not profile or not face:
        raise ValueError('ไม่พบโปรไฟล์หรือใบหน้า กรุณาค้นหาอีกครั้ง')
    with db.connect() as c:
        # Undoing/changing feedback also withdraws that learned reference.
        if payload.label != 'yes':
            c.execute('DELETE FROM refs WHERE profile_id=? AND origin_face=?', (payload.profile_id, payload.face_id))
        if payload.label == 'clear':
            c.execute('DELETE FROM feedback WHERE profile_id=? AND face_id=?', (payload.profile_id, payload.face_id))
        else:
            c.execute('INSERT INTO feedback VALUES(?,?,?,?) ON CONFLICT(profile_id,face_id) DO UPDATE SET label=excluded.label,created=excluded.created',
                      (payload.profile_id, payload.face_id, payload.label, time.time()))
        if payload.learn and payload.label == 'yes':
            refs = c.execute('SELECT * FROM refs WHERE profile_id=? AND model=?', (payload.profile_id, face['model'])).fetchall()
            if not refs:
                raise ValueError('โมเดลของภาพนี้ไม่ตรงกับโปรไฟล์')
            if len(refs) >= 12:
                raise ValueError('โปรไฟล์มีภาพอ้างอิงครบ 12 ใบหน้าแล้ว')
            similarity = max(float(db.unpack(r['embedding']) @ db.unpack(face['embedding'])) for r in refs)
            if similarity < 0.3:
                raise ValueError('ใบหน้านี้ต่างจากชุดอ้างอิงมากเกินไป กรุณาลงทะเบียนโปรไฟล์ใหม่แทน')
            if not any(r['origin_face'] == payload.face_id for r in refs):
                c.execute('INSERT INTO refs VALUES(?,?,?,?,?,?)', (uuid.uuid4().hex, payload.profile_id, face['embedding'], face['model'], face['quality'], payload.face_id))
    return {'ok': True}


app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')
