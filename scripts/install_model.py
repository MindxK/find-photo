import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.models import install
from backend.config import MODEL_NAME

if __name__ == '__main__':
    print(f'Installing InsightFace {MODEL_NAME} for personal/non-commercial research use.', flush=True)
    install()
    print('Model ready.', flush=True)
