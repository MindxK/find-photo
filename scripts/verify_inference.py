"""Real-model integration smoke test; uses an isolated temporary database.

Pass an authorized reference image with exactly one clear face. This script
uses controlled transforms of that image to test the plumbing, not accuracy.
No production profiles, Drive tokens, albums, or jobs are touched.
"""
import argparse
import base64
import io
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--image',required=True)
args = parser.parse_args()
source_path = Path(args.image).resolve()
model_dir = ROOT / 'data' / 'models' / os.getenv('FIND_FACE_MODEL','buffalo_sc')

with tempfile.TemporaryDirectory(prefix='findface-real-model-') as temporary:
    os.environ['FIND_FACE_DATA'] = temporary
    os.environ['FIND_FACE_MODEL_DIR'] = str(model_dir)
    from PIL import Image, ImageEnhance, ImageOps
    import numpy as np
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend import vision, db, jobs

    source = Image.open(source_path).convert('RGB')
    source = source.resize((source.width*2,source.height*2))
    def jpeg(image):
        buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=95)
        return buffer.getvalue()
    started=time.monotonic()
    analyzed=vision.analyze(jpeg(source),registration=True)
    embedding=analyzed['faces'][0]['vector']
    assert embedding.shape == (512,)
    assert abs(float(np.linalg.norm(embedding))-1)<1e-5
    variants=[source,ImageEnhance.Brightness(source).enhance(0.9),ImageOps.expand(source,border=15,fill='#ddd')]
    album=Path(temporary)/'test-album';album.mkdir()
    (album/'match.jpg').write_bytes(jpeg(ImageEnhance.Contrast(source).enhance(0.85)))
    group=Image.new('RGB',(source.width*2,source.height));group.paste(source,(0,0));group.paste(source,(source.width,0))
    (album/'group.jpg').write_bytes(jpeg(group))
    Image.new('RGB',(600,400),'#6087a9').save(album/'no-face.png')
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.get('/')
        client.headers.update({'Origin':'http://127.0.0.1:8765','X-CSRF-Token':client.get('/api/status').json()['csrf']})
        result=client.post('/api/profiles',json={'name':'Isolated verification','images':[
            {'name':f'ref{i}.jpg','data':base64.b64encode(jpeg(image)).decode()} for i,image in enumerate(variants)]})
        assert result.status_code==200,result.text
        profile=result.json()['id']
        source_id=client.post('/api/sources',json={'name':'Isolated test album','kind':'local','locator':str(album)}).json()['id']
        job_id=client.post(f'/api/sources/{source_id}/scan').json()['id']
        deadline=time.monotonic()+120
        while jobs.busy() and time.monotonic()<deadline:
            time.sleep(0.1)
        job=db.one('SELECT * FROM jobs WHERE id=?',(job_id,))
        assert job['status']=='completed',job
        assert job['faces']==3,job
        result=client.get('/api/search',params={'profile_id':profile,'threshold':0.65}).json()
        assert result['total']==2,result
        group_result=next(p for p in result['items'] if p['name']=='group.jpg')
        assert len(group_result['faces'])==2
        preview=client.get('/api/files/'+group_result['file_id']+'/preview')
        assert preview.status_code==200 and preview.headers['content-type']=='image/jpeg'
        assert client.post('/api/feedback',json={'profile_id':profile,'face_id':group_result['faces'][0]['id'],'label':'yes','learn':True}).status_code==200
        assert len(db.rows('SELECT * FROM refs'))==4
        assert client.delete('/api/sources/'+source_id).status_code==200
        assert len(db.rows('SELECT * FROM refs'))==3
        print({'passed':True,'embedding_dimensions':512,'photos_scanned':3,'faces_detected':job['faces'],
               'matching_photos':result['total'],'group_faces':2,'preview':'JPEG',
               'similarities':[round(p['similarity'],4) for p in result['items']],
               'seconds':round(time.monotonic()-started,2)},flush=True)
