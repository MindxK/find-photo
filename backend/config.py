import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DATA = Path(os.getenv('FIND_FACE_DATA', str(ROOT / 'data'))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
PORT = int(os.getenv('FIND_FACE_PORT', '8765'))
ORIGIN = f'http://127.0.0.1:{PORT}'
CALLBACK = f'{ORIGIN}/api/google/callback'
MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 40_000_000
MODEL_NAME = os.getenv('FIND_FACE_MODEL', 'buffalo_sc')
if MODEL_NAME not in ('buffalo_sc', 'buffalo_l'):
    raise ValueError('FIND_FACE_MODEL must be buffalo_sc or buffalo_l')
MODEL_DIR = Path(os.getenv('FIND_FACE_MODEL_DIR') or DATA / 'models' / MODEL_NAME).resolve()
MODEL_FILES = ('det_500m.onnx', 'w600k_mbf.onnx') if MODEL_NAME == 'buffalo_sc' else ('det_10g.onnx', 'w600k_r50.onnx')
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}

# Server mode is explicit; the marker is written by Start-Server.cmd.
SERVER_MODE = os.getenv('FIND_FACE_SERVER', '') == '1' or (DATA / 'server-enabled').exists()


def public_origin():
    import json
    from urllib.parse import urlsplit
    try:
        value = json.loads((DATA / 'server.json').read_text())['public_origin'].rstrip('/')
        url = urlsplit(value)
        if url.scheme == 'https' and url.hostname and url.netloc == url.hostname and not url.path and not url.query and not url.fragment:
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return ''
