"""CPU inference for InsightFace's SCRFD + ArcFace ONNX model packs.

Uses NumPy and Pillow for preprocessing so installing the desktop app does not
require OpenCV, SciPy, a compiler, or the full training/toolbox dependencies.
Model contracts: RGB normalization, SCRFD stride-8/16/32 anchor outputs, and
the ArcFace five-point 112px template. Weights retain their upstream license.
"""
import os
import numpy as np
import onnxruntime as ort
from PIL import Image
from .config import MODEL_DIR, MODEL_FILES

TEMPLATE = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                     [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float64)


def similarity_transform(source, target=TEMPLATE):
    """Least-squares scaled rotation + translation from source to target."""
    source = np.asarray(source, dtype=np.float64)
    if source.shape != (5, 2) or not np.isfinite(source).all():
        raise ValueError('Invalid facial landmarks')
    centered_source = source - source.mean(axis=0)
    centered_target = target - target.mean(axis=0)
    variance = np.sum(centered_source ** 2) / len(source)
    if variance < 1e-6:
        raise ValueError('Degenerate facial landmarks')
    covariance = centered_target.T @ centered_source / len(source)
    u, singular, vt = np.linalg.svd(covariance)
    signs = np.ones(2)
    if np.linalg.det(u @ vt) < 0:
        signs[-1] = -1
    rotation = u @ np.diag(signs) @ vt
    scale = np.sum(singular * signs) / variance
    transform = np.eye(3)
    transform[:2, :2] = scale * rotation
    transform[:2, 2] = target.mean(axis=0) - scale * rotation @ source.mean(axis=0)
    return transform


def suppress_overlaps(boxes, scores, threshold=0.4):
    order = np.argsort(-scores)
    area = np.maximum(0, boxes[:, 2]-boxes[:, 0]+1) * np.maximum(0, boxes[:, 3]-boxes[:, 1]+1)
    retained = []
    while len(order):
        best = order[0]
        retained.append(best)
        remaining = order[1:]
        if not len(remaining):
            break
        lower = np.maximum(boxes[best, :2], boxes[remaining, :2])
        upper = np.minimum(boxes[best, 2:], boxes[remaining, 2:])
        intersection = np.prod(np.maximum(0, upper-lower+1), axis=1)
        iou = intersection / np.maximum(1e-6, area[best]+area[remaining]-intersection)
        order = remaining[iou <= threshold]
    return np.asarray(retained, dtype=np.int64)


class FaceEngine:
    def __init__(self):
        options = ort.SessionOptions()
        # Legacy SCRFD exports annotate outputs for 640px, but support the
        # dynamic 1024px input. Shapes are checked by our decoder below.
        options.log_severity_level = 3
        options.intra_op_num_threads = min(4, os.cpu_count() or 2)
        options.inter_op_num_threads = 1
        self.detector = ort.InferenceSession(str(MODEL_DIR / MODEL_FILES[0]), sess_options=options, providers=['CPUExecutionProvider'])
        self.recognizer = ort.InferenceSession(str(MODEL_DIR / MODEL_FILES[1]), sess_options=options, providers=['CPUExecutionProvider'])
        self.detector_input = self.detector.get_inputs()[0].name
        self.recognizer_input = self.recognizer.get_inputs()[0].name
        if len(self.detector.get_outputs()) != 9:
            raise ValueError('Expected SCRFD detector with five-point landmarks')
        if self.recognizer.get_inputs()[0].shape[-2:] != [112, 112]:
            raise ValueError('Expected ArcFace 112x112 model')

    def detect(self, bgr, max_num=0):
        height, width = bgr.shape[:2]
        input_shape = self.detector.get_inputs()[0].shape
        size = int(input_shape[-1]) if isinstance(input_shape[-1], int) else 1024
        if isinstance(input_shape[-2], int) and input_shape[-2] != size:
            raise ValueError('Expected square SCRFD input')
        scale = size / max(height, width)
        scaled_w, scaled_h = max(1, int(width*scale)), max(1, int(height*scale))
        resized = Image.fromarray(bgr[:, :, ::-1]).resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
        pixels = np.zeros((size, size, 3), dtype=np.float32)
        pixels[:scaled_h, :scaled_w] = np.asarray(resized)
        blob = np.ascontiguousarray(((pixels-127.5)/128.0).transpose(2,0,1)[None])
        outputs = self.detector.run(None, {self.detector_input: blob})
        boxes, points, confidence = [], [], []
        for level, stride in enumerate((8,16,32)):
            scores = outputs[level].reshape(-1)
            offsets = outputs[level+3].reshape(-1,4) * stride
            keypoints = outputs[level+6].reshape(-1,5,2) * stride
            cells = size // stride
            y, x = np.mgrid[:cells, :cells]
            anchors = np.stack((x,y),axis=-1).reshape(-1,2).astype(np.float32) * stride
            repeats = len(scores) // len(anchors)
            if repeats not in (1,2) or len(scores) != len(anchors)*repeats:
                raise ValueError('Unsupported detector anchor layout')
            anchors = np.repeat(anchors,repeats,axis=0)
            keep = np.flatnonzero(scores >= 0.5)
            if not len(keep):
                continue
            box = np.column_stack((anchors[keep]-offsets[keep,:2], anchors[keep]+offsets[keep,2:]))
            boxes.append(box)
            points.append(anchors[keep,None,:] + keypoints[keep])
            confidence.append(scores[keep])
        if not boxes:
            return np.empty((0,5),dtype=np.float32), np.empty((0,5,2),dtype=np.float32)
        boxes, points, confidence = np.concatenate(boxes), np.concatenate(points), np.concatenate(confidence)
        boxes[:, [0,2]] /= scaled_w / width
        boxes[:, [1,3]] /= scaled_h / height
        points[:,:,0] /= scaled_w / width
        points[:,:,1] /= scaled_h / height
        selected = suppress_overlaps(boxes, confidence)
        if max_num:
            selected = selected[:max_num]
        return np.column_stack((boxes[selected],confidence[selected])), points[selected]

    def embed(self, bgr, landmarks):
        transform = similarity_transform(landmarks)
        inverse = np.linalg.inv(transform)
        source = Image.fromarray(bgr[:, :, ::-1])
        aligned = source.transform((112,112), Image.Transform.AFFINE, tuple(inverse[:2].reshape(-1)),
                                   resample=Image.Resampling.BILINEAR)
        rgb = np.asarray(aligned, dtype=np.float32)
        tensor = np.ascontiguousarray(((rgb-127.5)/127.5).transpose(2,0,1)[None])
        return self.recognizer.run(None, {self.recognizer_input:tensor})[0].reshape(-1)
