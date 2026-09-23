import json
import threading
import numpy as np
import faiss
from . import db, vision

_lock = threading.Lock()
_cached_revision = -1
_cached_model = None
_index = None
_metadata = []


def search(profile_id, threshold=0.65, source_id='', mode='all', offset=0, limit=24):
    global _cached_revision, _cached_model, _index, _metadata
    model = vision.model_version()
    refs = db.rows('SELECT embedding FROM refs WHERE profile_id=? AND model=?', (profile_id, model))
    if not refs:
        raise ValueError('ไม่พบใบหน้าอ้างอิงสำหรับโมเดลนี้ กรุณาลงทะเบียนใหม่')
    queries = vision.normalize(np.stack([db.unpack(row['embedding']) for row in refs]))
    feedback = {r['face_id']: r['label'] for r in db.rows('SELECT * FROM feedback WHERE profile_id=?', (profile_id,))}
    with _lock:
        revision = db.revision
        if _index is None or revision != _cached_revision or model != _cached_model:
            metadata = db.rows('''SELECT faces.id AS face_id,faces.embedding,faces.bbox,faces.quality,
                files.id AS file_id,files.name,files.remote_id,files.source_id,sources.name AS source_name,sources.kind
                FROM faces JOIN files ON files.id=faces.file_id JOIN sources ON sources.id=files.source_id
                WHERE faces.model=? AND files.status='ready' ORDER BY faces.id''', (model,))
            _index = faiss.IndexFlatIP(512)
            for start in range(0, len(metadata), 2048):
                batch = metadata[start:start+2048]
                vectors = vision.normalize(np.stack([db.unpack(r.pop('embedding')) for r in batch]))
                _index.add(vectors)
            _metadata = metadata
            _cached_revision, _cached_model = revision, model
        # range_search has no top-k truncation. Exact cosine is intentional
        # for personal albums: returning every matching image matters.
        _, scores, indices = _index.range_search(queries, float(threshold - 1e-6))
        best = {}
        for index, score in zip(indices.tolist(), scores.tolist()):
            if score >= threshold:
                best[index] = max(best.get(index, -1), score)
        # Keep explicitly confirmed faces discoverable even after a threshold change.
        for index, meta in enumerate(_metadata):
            if feedback.get(meta['face_id']) in ('yes', 'no') and index not in best:
                vector = _index.reconstruct(index)
                best[index] = float(np.max(queries @ vector))
        photos = {}
        for index, score in best.items():
            meta = _metadata[index]
            label = feedback.get(meta['face_id'])
            if (label == 'no' and mode != 'rejected') or (source_id and meta['source_id'] != source_id):
                continue
            state = 'rejected' if label == 'no' else ('confirmed' if label == 'yes' else ('match' if score >= max(0.70, threshold) else 'review'))
            if mode != 'all' and state != mode:
                continue
            face = {'id': meta['face_id'], 'bbox': json.loads(meta['bbox']), 'similarity': round(score, 4),
                    'state': state, 'quality': json.loads(meta['quality'])}
            if meta['file_id'] not in photos:
                photos[meta['file_id']] = {k: meta[k] for k in ('file_id', 'name', 'source_id', 'source_name', 'kind')}
                photos[meta['file_id']].update({'faces': [], 'similarity': -1,
                    'drive_url': 'https://drive.google.com/file/d/' + meta['remote_id'] + '/view' if meta['kind'] == 'drive' else None})
            photo = photos[meta['file_id']]
            photo['faces'].append(face)
            photo['similarity'] = max(photo['similarity'], face['similarity'])
        results = sorted(photos.values(), key=lambda r: (-r['similarity'], r['file_id']))
        for photo in results:
            photo['faces'].sort(key=lambda r: -r['similarity'])
        if limit is not None:
            offset = min(offset, max(0, (len(results) - 1) // limit * limit))
        return {'total': len(results), 'items': results[offset:] if limit is None else results[offset:offset+limit], 'offset': offset, 'limit': limit}
