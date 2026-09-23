"""Self-service accounts with protected owner setup. Passwords and account metadata never enter workspace APIs."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from . import db
from .config import DATA, SERVER_MODE

router = APIRouter(prefix='/api/auth')
ACCOUNTS = DATA / 'accounts.sqlite3'
BOOTSTRAP = DATA / 'owner-setup.txt'
_lock = threading.RLock()
_attempts = {}
_password_slots = threading.BoundedSemaphore(2)


@contextmanager
def connect():
    c = sqlite3.connect(ACCOUNTS, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL,scope TEXT UNIQUE NOT NULL,admin INTEGER NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS invites(digest TEXT PRIMARY KEY,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0);
        """)
        users = c.execute('SELECT scope FROM users').fetchall()
    if not users and not BOOTSTRAP.exists():
        BOOTSTRAP.write_text(secrets.token_urlsafe(32), encoding='utf-8')
    for row in users:
        with db.workspace(row['scope']):
            db.init()


def owner_exists():
    with connect() as c:
        return bool(c.execute('SELECT 1 FROM users WHERE admin=1').fetchone())


def public_user(row):
    return {k: row[k] for k in ('id', 'username', 'scope', 'admin')}


def get_user(user_id):
    if not user_id:
        return None
    with connect() as c:
        row = c.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    return public_user(row) if row else None


def require_admin(request):
    if SERVER_MODE and not (request.state.user and request.state.user['admin']):
        raise HTTPException(403, 'เฉพาะเจ้าของเซิร์ฟเวอร์เท่านั้น')


def throttle(request, username):
    # Do not trust X-Forwarded-For: all public traffic comes through the tunnel.
    now = time.monotonic()
    with _lock:
        for key in list(_attempts):
            _attempts[key] = [t for t in _attempts[key] if now-t < 600]
            if not _attempts[key]:
                del _attempts[key]
        keys = ['global', 'name:' + username.lower()]
        if any(len(_attempts.get(key, [])) >= (100 if key == 'global' else 8) for key in keys):
            raise HTTPException(429, 'ลองเข้าสู่ระบบหลายครั้งเกินไป กรุณารอ 10 นาที')
        for key in keys:
            _attempts.setdefault(key, []).append(now)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    with _password_slots:
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=1, maxmem=64*1024*1024)
    return salt + ':' + digest.hex()


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=12, max_length=128)
    code: str = Field(default='', max_length=200)


def username(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}', value):
        raise ValueError('ชื่อบัญชีใช้ a-z, 0-9, จุด ขีดกลาง หรือขีดล่าง 3–40 ตัว')
    return value


@router.get('/session')
def session(request: Request):
    return {'csrf': request.state.csrf, 'server': SERVER_MODE,
            'setup_needed': not owner_exists() if SERVER_MODE else False,
            'user': request.state.user}


@router.post('/register')
def register(payload: Credentials, request: Request):
    if not SERVER_MODE:
        raise HTTPException(404)
    name = username(payload.username)
    throttle(request, name)
    with _lock:
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            first = not c.execute('SELECT 1 FROM users').fetchone()
            if first:
                if (request.url.hostname not in ('localhost', '127.0.0.1') or not BOOTSTRAP.exists()
                        or not hmac.compare_digest(payload.code, BOOTSTRAP.read_text().strip())):
                    raise HTTPException(403, 'เปิดลิงก์ตั้งค่าบัญชีเจ้าของจากเครื่องเซิร์ฟเวอร์')
            user_id = secrets.token_hex(16)
            scope = 'legacy' if first else user_id
            try:
                c.execute('INSERT INTO users VALUES(?,?,?,?,?,?)', (user_id, name, password_hash(payload.password), scope, int(first), time.time()))
            except sqlite3.IntegrityError:
                raise ValueError('ชื่อบัญชีนี้ถูกใช้แล้ว')
            with db.workspace(scope):
                db.init()
        if first:
            BOOTSTRAP.unlink(missing_ok=True)
    request.state.login_user = user_id
    return {'ok': True}


@router.post('/login')
def login(payload: Credentials, request: Request):
    name = username(payload.username)
    throttle(request, name)
    with connect() as c:
        row = c.execute('SELECT * FROM users WHERE username=?', (name,)).fetchone()
    expected = row['password'] if row else ('00'*16 + ':' + '00'*64)
    actual = password_hash(payload.password, expected.split(':')[0])
    if not row or not hmac.compare_digest(expected, actual):
        raise HTTPException(401, 'ชื่อบัญชีหรือรหัสผ่านไม่ถูกต้อง')
    request.state.login_user = row['id']
    return {'ok': True}


@router.post('/logout')
def logout(request: Request):
    request.state.logout = True
    return {'ok': True}
