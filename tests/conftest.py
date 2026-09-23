import os
import tempfile

_workspace = tempfile.TemporaryDirectory(prefix='findface-tests-')
os.environ['FIND_FACE_DATA'] = _workspace.name

import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend import db, vision, jobs


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(vision, 'model_available', lambda: True)
    monkeypatch.setattr(vision, 'model_version', lambda: 'test-model')
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        with db.connect() as c:
            for table in ('feedback', 'faces', 'files', 'refs', 'profiles', 'sources', 'jobs', 'settings'):
                c.execute('DELETE FROM ' + table)
        db.changed()
        client.get('/')
        csrf = client.get('/api/status').json()['csrf']
        client.headers.update({'Origin': 'http://127.0.0.1:8765', 'X-CSRF-Token': csrf})
        yield client
