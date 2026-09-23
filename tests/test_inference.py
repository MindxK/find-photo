import numpy as np
import pytest
from backend.inference import TEMPLATE, similarity_transform, suppress_overlaps


def test_alignment_recovers_rotation_scale_and_translation():
    angle = 0.37
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    source = (TEMPLATE @ rotation.T) * 1.6 + [81, 45]
    transform = similarity_transform(source)
    mapped = np.column_stack((source, np.ones(5))) @ transform.T
    np.testing.assert_allclose(mapped[:, :2], TEMPLATE, atol=1e-7)


def test_alignment_rejects_degenerate_landmarks():
    with pytest.raises(ValueError):
        similarity_transform(np.ones((5,2)))


def test_nms_retains_separate_people_and_removes_duplicate_boxes():
    boxes = np.array([[0,0,100,100],[1,1,99,99],[200,200,300,300]], dtype=np.float32)
    assert suppress_overlaps(boxes, np.array([0.9,0.8,0.7])).tolist() == [0,2]
