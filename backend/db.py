import contextlib
import json
import sqlite3
import threading
import time
from cryptography.fernet import Fernet
import numpy as np
from .config import DATA

DB_PATH = DATA / 'findface.sqlite3'
_key_path = DATA / 'encryption.key'
if not _key_path.exists():
    try:
        with _key_path.open('xb') as handle:
            handle.write(Fernet.generate_key())
    except FileExistsError:
        pass
CIPHER = Fernet(_key_path.read_bytes())
REVISION_LOCK = threading.Lock()
revision = 0


@contextlib.contextmanager
def connect():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init():
    with connect() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles(
          id TEXT PRIMARY KEY,name TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS refs(
          id TEXT PRIMARY KEY,profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
          embedding BLOB NOT NULL,model TEXT NOT NULL,quality TEXT NOT NULL,origin_face TEXT);
        CREATE INDEX IF NOT EXISTS refs_profile ON refs(profile_id);
        CREATE TABLE IF NOT EXISTS sources(
          id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,locator TEXT NOT NULL,
          drive_id TEXT,created REAL NOT NULL,last_scan REAL,UNIQUE(kind,locator,drive_id));
        CREATE TABLE IF NOT EXISTS files(
          id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          remote_id TEXT NOT NULL,name TEXT NOT NULL,version TEXT NOT NULL,model TEXT NOT NULL,
          width INTEGER,height INTEGER,status TEXT NOT NULL,reason TEXT,scanned REAL NOT NULL,
          UNIQUE(source_id,remote_id));
        CREATE INDEX IF NOT EXISTS files_source ON files(source_id);
        CREATE TABLE IF NOT EXISTS faces(
          id TEXT PRIMARY KEY,file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          embedding BLOB NOT NULL,bbox TEXT NOT NULL,quality TEXT NOT NULL,model TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS faces_file ON faces(file_id);
        CREATE TRIGGER IF NOT EXISTS remove_learned_references BEFORE DELETE ON faces
        BEGIN DELETE FROM refs WHERE origin_face=OLD.id; END;
        CREATE TABLE IF NOT EXISTS feedback(
          profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
          face_id TEXT NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
          label TEXT NOT NULL CHECK(label IN ('yes','no')),created REAL NOT NULL,
          PRIMARY KEY(profile_id,face_id));
        CREATE TABLE IF NOT EXISTS jobs(
          id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
          status TEXT NOT NULL,phase TEXT NOT NULL,total INTEGER NOT NULL DEFAULT 0,
          processed INTEGER NOT NULL DEFAULT 0,skipped INTEGER NOT NULL DEFAULT 0,
          failed INTEGER NOT NULL DEFAULT 0,faces INTEGER NOT NULL DEFAULT 0,
          current_file TEXT,error TEXT,created REAL NOT NULL,finished REAL);
        ''')
        c.execute("UPDATE jobs SET status='interrupted',phase='งานหยุดเมื่อปิดโปรแกรม กดสแกนอีกครั้งเพื่อทำต่อ',finished=? WHERE status IN ('queued','running','cancelling')", (time.time(),))


def rows(sql, args=()):
    with connect() as c:
        return [dict(row) for row in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    found = rows(sql, args)
    return found[0] if found else None


def execute(sql, args=()):
    with connect() as c:
        c.execute(sql, args)


def setting(key, default=None):
    row = one('SELECT value FROM settings WHERE key=?', (key,))
    return json.loads(CIPHER.decrypt(row['value'])) if row else default


def set_setting(key, value):
    execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (key, CIPHER.encrypt(json.dumps(value).encode())))


def pack(vector):
    return CIPHER.encrypt(np.asarray(vector, dtype=np.float32).tobytes())


def unpack(blob):
    return np.frombuffer(CIPHER.decrypt(blob), dtype=np.float32).copy()


def changed():
    global revision
    with REVISION_LOCK:
        revision += 1
