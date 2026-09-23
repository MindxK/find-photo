import base64
import hashlib
import os
import random
import re
import secrets
import threading
import time
from urllib.parse import urlencode, urlsplit
import httpx
from . import db
from .config import CALLBACK, MAX_BYTES, SERVER_MODE
from contextvars import ContextVar

callback_url = ContextVar("callback_url", default=CALLBACK)

SCOPE = 'https://www.googleapis.com/auth/drive.readonly'
BASE = 'https://www.googleapis.com/drive/v3'
_refresh_lock = threading.Lock()


class DriveError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def config():
    own = db.setting('google_config')
    if own:
        return own
    if SERVER_MODE and db.scope_key() != 'legacy':
        # Share only the OAuth client definition; tokens remain per workspace.
        with db.workspace('legacy'):
            shared = db.setting('google_server_config')
        if shared:
            return shared
    return {'client_id': os.getenv('GOOGLE_CLIENT_ID', ''),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET', '')}


def authorization_config():
    if SERVER_MODE:
        with db.workspace('legacy'):
            shared = db.setting('google_server_config')
        if shared:
            return shared
    return config()


def configured():
    settings = authorization_config()
    return bool(settings.get('client_id') and settings.get('client_secret'))


def authorization_url(session):
    if not configured():
        raise ValueError('กรุณาตั้งค่า Google OAuth ก่อนเชื่อมต่อ')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    db.set_setting('oauth_pending', {'state': state, 'verifier': verifier,
                                    'session': session, 'expires': time.time() + 600,
                                    'callback': callback_url.get(), 'config': authorization_config()})
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': authorization_config()['client_id'], 'redirect_uri': callback_url.get(),
        'response_type': 'code', 'scope': SCOPE, 'state': state,
        'access_type': 'offline', 'prompt': 'consent',
        'code_challenge': challenge, 'code_challenge_method': 'S256',
    })


def complete_oauth(code, state, session):
    pending = db.setting('oauth_pending', {})
    if (not state or not secrets.compare_digest(state, pending.get('state', ''))
            or pending.get('session') != session or pending.get('expires', 0) < time.time()):
        raise ValueError('คำขอเชื่อมต่อหมดอายุหรือไม่ถูกต้อง กรุณาเริ่มเชื่อมต่อใหม่')
    db.execute("DELETE FROM settings WHERE key='oauth_pending'")
    result = httpx.post('https://oauth2.googleapis.com/token', data={
        **pending.get('config', config()), 'code': code, 'code_verifier': pending['verifier'],
        'redirect_uri': pending.get('callback', CALLBACK), 'grant_type': 'authorization_code',
    }, timeout=30)
    if result.status_code != 200:
        raise ValueError('เชื่อมต่อ Google ไม่สำเร็จ ตรวจ Client ID, Secret และ Redirect URI')
    token = result.json()
    if SCOPE not in token.get('scope', '').split():
        raise ValueError('ไม่ได้รับสิทธิ์อ่าน Google Drive กรุณาอนุญาตแล้วเชื่อมต่อใหม่')
    if not token.get('refresh_token'):
        raise ValueError('ไม่ได้รับ refresh token กรุณาเชื่อมต่อและอนุญาตอีกครั้ง')
    token['expires_at'] = time.time() + token.get('expires_in', 3600)
    # Existing Drive data is tied to the previous connection. Never reuse it
    # across an account change, even if the next Google account looks similar.
    with db.connect() as c:
        c.execute("DELETE FROM sources WHERE kind='drive'")
    db.set_setting('google_config', pending.get('config', config()))
    db.set_setting('google_token', token)
    db.changed()


def access_token():
    with _refresh_lock:
        token = db.setting('google_token')
        if not token:
            raise DriveError('ยังไม่ได้เชื่อมต่อ Google Drive', 401)
        if token.get('expires_at', 0) > time.time() + 90:
            return token['access_token']
        result = httpx.post('https://oauth2.googleapis.com/token', data={
            **config(), 'refresh_token': token['refresh_token'], 'grant_type': 'refresh_token',
        }, timeout=30)
        if result.status_code != 200:
            raise DriveError('สิทธิ์ Google หมดอายุ กรุณาเชื่อมต่อบัญชีอีกครั้ง', 401)
        token.update(result.json())
        token['expires_at'] = time.time() + token.get('expires_in', 3600)
        db.set_setting('google_token', token)
        return token['access_token']


def safe_id(value):
    if value and not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('รหัสโฟลเดอร์หรือ Drive ไม่ถูกต้อง')
    return value


class Drive:
    def __init__(self):
        self.client = httpx.Client(timeout=httpx.Timeout(60, connect=15), follow_redirects=False)

    def close(self):
        self.client.close()

    def request(self, endpoint, params=None, media=False):
        for attempt in range(5):
            headers = {'Authorization': 'Bearer ' + access_token()}
            with self.client.stream('GET', BASE + endpoint, params=params, headers=headers) as response:
                if response.status_code == 200:
                    if not media:
                        return response.read() and response.json()
                    if int(response.headers.get('content-length', '0')) > MAX_BYTES:
                        raise ValueError('ไฟล์มีขนาดเกิน 25 MB')
                    content = bytearray()
                    for chunk in response.iter_bytes(256 * 1024):
                        content.extend(chunk)
                        if len(content) > MAX_BYTES:
                            raise ValueError('ไฟล์มีขนาดเกิน 25 MB')
                    return bytes(content)
                response.read()
                reason = ''
                try:
                    reason = response.json().get('error', {}).get('errors', [{}])[0].get('reason', '')
                except (ValueError, IndexError, AttributeError):
                    pass
                retry = response.status_code == 429 or response.status_code >= 500 or reason in {
                    'rateLimitExceeded', 'userRateLimitExceeded'}
                if not retry or attempt == 4:
                    raise DriveError('อ่าน Google Drive ไม่สำเร็จ: ' + {
                        401: 'กรุณาเชื่อมต่อบัญชีใหม่', 403: 'ไม่มีสิทธิ์เข้าถึงหรือดาวน์โหลดไฟล์',
                        404: 'ไม่พบไฟล์หรือถูกถอนสิทธิ์', 429: 'ใช้งานเกินโควตาชั่วคราว ลองอีกครั้งภายหลัง',
                    }.get(response.status_code, 'บริการไม่พร้อมใช้งานชั่วคราว'), response.status_code)
            time.sleep(min(16, 2 ** attempt) + random.random())

    def pages(self, query, drive_id=''):
        params = {'q': query, 'spaces': 'drive', 'pageSize': 1000,
                  'fields': 'nextPageToken,incompleteSearch,files(id,name,mimeType,size,version,md5Checksum,modifiedTime)',
                  'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true',
                  'corpora': 'drive' if drive_id else 'user'}
        if drive_id:
            params['driveId'] = safe_id(drive_id)
        while True:
            result = self.request('/files', params)
            if result.get('incompleteSearch'):
                raise ValueError('Google ส่งรายการไม่ครบ กรุณาเลือก Drive หรือโฟลเดอร์ให้แคบลง')
            yield from result.get('files', [])
            if not result.get('nextPageToken'):
                break
            params['pageToken'] = result['nextPageToken']

    def images(self, folder='', drive_id=''):
        folder = safe_id(folder)
        if not folder:
            for item in self.pages("trashed=false and mimeType contains 'image/'", drive_id):
                yield item
            return
        pending, visited = [folder], set()
        while pending:
            parent = pending.pop()
            if parent in visited:
                continue
            visited.add(parent)
            query = f"trashed=false and '{parent}' in parents and (mimeType contains 'image/' or mimeType='application/vnd.google-apps.folder')"
            for item in self.pages(query, drive_id):
                if item['mimeType'] == 'application/vnd.google-apps.folder':
                    pending.append(item['id'])
                else:
                    yield item

    def download(self, file_id):
        return self.request('/files/' + safe_id(file_id), {'alt': 'media', 'supportsAllDrives': 'true'}, media=True)

    def thumbnail(self, file_id):
        """Fetch private Drive thumbnails through our authenticated proxy only."""
        metadata = self.request('/files/' + safe_id(file_id),
                                {'fields': 'thumbnailLink', 'supportsAllDrives': 'true'})
        link = metadata.get('thumbnailLink')
        if not link:
            return None
        url = urlsplit(link)
        # Never forward a Google token to arbitrary metadata URLs or redirects.
        if (url.scheme != 'https' or not url.hostname
                or not url.hostname.endswith('.googleusercontent.com')
                or url.username or url.password or url.port not in (None, 443)):
            return None
        link = re.sub(r'=s[0-9]+$', '=s480', link)
        with self.client.stream('GET', link, headers={'Authorization': 'Bearer ' + access_token()},
                                timeout=20, follow_redirects=False) as response:
            if response.status_code != 200:
                return None
            if int(response.headers.get('content-length', '0')) > 4 * 1024 * 1024:
                return None
            content = bytearray()
            for chunk in response.iter_bytes(64 * 1024):
                content.extend(chunk)
                if len(content) > 4 * 1024 * 1024:
                    return None
            return bytes(content) or None

    def drives(self):
        found, token = [], None
        while True:
            params = {'pageSize': 100, 'fields': 'nextPageToken,drives(id,name)'}
            if token:
                params['pageToken'] = token
            data = self.request('/drives', params)
            found.extend(data.get('drives', []))
            token = data.get('nextPageToken')
            if not token:
                return found
