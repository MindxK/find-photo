import io
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from backend import vision
from backend.inference import TEMPLATE


def image_bytes(size, brightness):
    buffer = io.BytesIO()
    Image.new('RGB', (size, size), (brightness,) * 3).save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.mark.parametrize('registration', [False, True])
@pytest.mark.parametrize('size,brightness', [(200, 10), (24, 120), (24, 10)])
def test_dark_small_and_low_sharpness_faces_are_accepted(monkeypatch, registration, size, brightness):
    engine = Mock()
    engine.detect.return_value = (
        np.array([[0, 0, size, size, 0.55]]),
        np.array([TEMPLATE * size / 112]),
    )
    engine.embed.return_value = np.ones(512, dtype=np.float32)
    monkeypatch.setattr(vision, 'engine', lambda: engine)

    result = vision.analyze(image_bytes(size, brightness), registration=registration)

    assert len(result['faces']) == 1
    face = result['faces'][0]
    assert face['vector'].shape == (512,)
    assert np.linalg.norm(face['vector']) == pytest.approx(1)
    assert face['quality']['brightness'] == brightness
    assert face['quality']['sharpness'] == 0
    engine.embed.assert_called_once()


def test_invalid_landmarks_still_rejected_without_dark_or_small_message(monkeypatch):
    engine = Mock()
    engine.detect.return_value = (np.array([[0, 0, 24, 24, 0.95]]), np.ones((1, 5, 2)))
    monkeypatch.setattr(vision, 'engine', lambda: engine)

    assert vision.analyze(image_bytes(24, 10), registration=True)['faces'] == []
    engine.embed.assert_not_called()


@pytest.mark.parametrize('count', [0, 2])
def test_registration_skips_missing_or_ambiguous_face(monkeypatch, count):
    engine = Mock()
    engine.detect.return_value = (np.zeros((count, 5)), np.zeros((count, 5, 2)))
    monkeypatch.setattr(vision, 'engine', lambda: engine)
    assert vision.analyze(image_bytes(24, 10), registration=True)['faces'] == []
    engine.embed.assert_not_called()


def test_invalid_embedding_is_skipped(monkeypatch):
    engine = Mock()
    engine.detect.return_value = (np.array([[0, 0, 24, 24, 0.55]]), np.array([TEMPLATE * 24 / 112]))
    engine.embed.return_value = np.zeros(512)
    monkeypatch.setattr(vision, 'engine', lambda: engine)
    assert vision.analyze(image_bytes(24, 10), registration=True)['faces'] == []
