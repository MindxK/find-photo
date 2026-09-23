"""Windows desktop server supervisor. Loopback app + authenticated HTTPS tunnel."""
import ctypes
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from backend.config import DATA, PORT
from server_tunnel import load_config, ensure_tailscale, stop_tailscale
DATA.mkdir(parents=True, exist_ok=True)
STOP = DATA / 'server-stop'
FLAGS = subprocess.CREATE_NO_WINDOW
TOOL = DATA / 'tools' / 'cloudflared.exe'
TOOL_HASH = '2837888cc0f5d58f15b6dc478376de90b4d3ba5241c7947455d1e0a0df429712'
TOOL_URL = 'https://github.com/cloudflare/cloudflared/releases/download/2026.9.1/cloudflared-windows-amd64.exe'


def status(message, **values):
    destination = DATA / 'server-status.json'
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps({'message':message, 'updated':time.time(), **values}), encoding='utf-8')
    temporary.replace(destination)


def set_origin(value):
    destination = DATA / 'server.json'
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps({'public_origin':value}), encoding='utf-8')
    temporary.replace(destination)


def install_tunnel():
    if TOOL.exists() and hashlib.sha256(TOOL.read_bytes()).hexdigest() == TOOL_HASH:
        return
    TOOL.parent.mkdir(parents=True, exist_ok=True)
    target = TOOL.with_suffix('.' + uuid.uuid4().hex + '.download')
    digest = hashlib.sha256()
    with urllib.request.urlopen(TOOL_URL, timeout=60) as response, target.open('wb') as output:
        while chunk := response.read(1024*1024):
            output.write(chunk); digest.update(chunk)
    if digest.hexdigest() != TOOL_HASH:
        target.unlink(missing_ok=True)
        raise RuntimeError('Cloudflare download checksum mismatch')
    target.replace(TOOL)


def owner_ready():
    path = DATA / 'accounts.sqlite3'
    if not path.exists(): return False
    try:
        with sqlite3.connect(path) as c:
            return bool(c.execute('SELECT 1 FROM users WHERE admin=1').fetchone())
    except sqlite3.Error:
        return False


def log_tunnel(process):
    log = DATA / 'tunnel.log'
    with log.open('w', encoding='utf-8') as output:
        for line in process.stdout:
            if output.tell() > 4*1024*1024:
                output.seek(0); output.truncate()
            output.write(line); output.flush()
            match = re.search(r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com', line)
            if match:
                set_origin(match.group(0))
                status('public', public_url=match.group(0), callback_url=match.group(0)+'/api/google/callback')


def stop_child(process):
    if process and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)


def main():
    lock = (DATA / 'server.lock').open('a+b')
    lock.seek(0)
    if not lock.read(1): lock.write(b'1'); lock.flush()
    lock.seek(0)
    try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError: return
    STOP.unlink(missing_ok=True)
    (DATA / 'server-enabled').touch()
    set_origin('')
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', PORT)) == 0:
            status('port_in_use', port=PORT)
            return
    try:
        tunnel = load_config(DATA)
    except (OSError, ValueError) as error:
        status('configuration_error', error=str(error))
        lock.close()
        return
    fixed = tunnel['provider'] == 'tailscale'
    fixed_origin = tunnel.get('public_origin','')
    next_tunnel_check = 0
    children = [None, None]
    # Prevent idle sleep while serving; restore normal policy on exit.
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    status('starting')
    try:
        env = dict(os.environ, FIND_FACE_SERVER='1', PYTHONUNBUFFERED='1')
        python = ROOT / '.venv' / 'Scripts' / 'python.exe'
        with (DATA / 'server.log').open('a',encoding='utf-8') as log:
            children[0] = subprocess.Popen([str(python),str(ROOT/'run.py')],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=FLAGS)
            failures = 0
            while not STOP.exists():
                if children[0].poll() is not None:
                    failures += 1
                    if failures > 5: raise RuntimeError('Application stopped repeatedly; see server.log')
                    time.sleep(3)
                    children[0] = subprocess.Popen([str(python),str(ROOT/'run.py')],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=FLAGS)
                if not owner_ready():
                    status('waiting_for_owner', local_url=f'http://127.0.0.1:{PORT}/login')
                elif fixed:
                    if time.monotonic() >= next_tunnel_check:
                        try:
                            ensure_tailscale(fixed_origin, PORT)
                            set_origin(fixed_origin)
                            status('public', provider='tailscale', public_url=fixed_origin, callback_url=fixed_origin+'/api/google/callback')
                        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                            status('tunnel_error', provider='tailscale', public_url=fixed_origin, error=str(error))
                        next_tunnel_check = time.monotonic() + 30
                elif children[1] is None or children[1].poll() is not None:
                    if children[1] is not None:
                        set_origin(''); time.sleep(5)
                    status('connecting_tunnel')
                    try:
                        install_tunnel()
                        children[1] = subprocess.Popen([str(TOOL),'tunnel','--no-autoupdate','--url',f'http://127.0.0.1:{PORT}','--protocol','http2'],cwd=DATA,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=FLAGS)
                        threading.Thread(target=log_tunnel,args=(children[1],),daemon=True).start()
                    except (OSError,RuntimeError) as error:
                        status('tunnel_error',error=str(error))
                        for _ in range(30):
                            if STOP.exists(): break
                            time.sleep(1)
                time.sleep(1)
    except Exception as error:
        status('error',error=str(error))
    finally:
        cleanup_error = None
        if fixed:
            try:
                stop_tailscale(fixed_origin, PORT)
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                cleanup_error = str(error)
        stop_child(children[1]); stop_child(children[0])
        set_origin('')
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        if cleanup_error:
            status('cleanup_error', error=cleanup_error)
        elif STOP.exists():
            status('stopped')
        STOP.unlink(missing_ok=True)
        lock.close()


if __name__ == '__main__':
    main()
