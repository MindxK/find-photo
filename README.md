# FindFace

เว็บภาษาไทยสำหรับค้นหาภาพบุคคลจาก Google Drive หรือโฟลเดอร์บนเครื่อง ด้วย InsightFace / ArcFace 512D และ FAISS

ระบบรุ่นนี้เป็น **single-user localhost application** เปิดเฉพาะ `127.0.0.1` ไม่ใช่บริการหลายผู้ใช้บนอินเทอร์เน็ต ไม่มีผลค้นหาจำลอง

## เปิดใช้งานบน Windows

1. ดับเบิลคลิก `Start-FindFace.cmd` และเปิด **http://127.0.0.1:8765**
2. เปิดหน้าตั้งค่า ตรวจว่าโมเดลพร้อมใช้งาน ถ้ายังไม่พร้อม กดติดตั้งโมเดล (รุ่น CPU เริ่มต้นดาวน์โหลดประมาณ 15 MB)
3. เพิ่มใบหน้าอ้างอิงของบุคคลเดียวกัน 3–5 ภาพ แต่ละภาพมีใบหน้าเดียว เห็นหน้าตรง ซ้าย ขวา หรือสีหน้าแตกต่างกัน
4. เพิ่มอัลบั้มจากโฟลเดอร์ในเครื่อง หรือเชื่อม Google Drive ตามขั้นตอนด้านล่าง
5. กดเริ่มสแกน รอประมวลผล แล้วเปิดหน้าค้นหารูป เลือกโปรไฟล์และกดค้นหา
6. เปิดผลลัพธ์เพื่อดูกรอบใบหน้า กดใช่/ไม่ใช่รายใบหน้า สามารถเลือกเพิ่มใบหน้าที่ยืนยันเป็น reference และย้อนกลับการยืนยันได้

ปิดหน้าต่างโปรแกรมหรือ Ctrl+C เพื่อหยุด การปิดแท็บเว็บอย่างเดียวไม่หยุดเซิร์ฟเวอร์ งานที่ถูกหยุดเมื่อปิดโปรแกรมจะเป็น `interrupted` และกดสแกนอีกครั้งได้ ภาพที่ยังไม่เปลี่ยนจะถูกข้าม

หากย้ายไปเครื่องใหม่: ติดตั้ง Python 3.12 และ [uv](https://docs.astral.sh/uv/getting-started/installation/) แล้วรัน `Install-FindFace.ps1` หรือใช้:

```powershell
uv venv --python 3.12 --cache-dir .uv-cache .venv
uv pip install --python .venv/Scripts/python.exe --cache-dir .uv-cache -r requirements.lock
.venv/Scripts/python.exe run.py
```

`.env.example` แสดงตัวเลือกพอร์ตและตำแหน่งโมเดล ถ้าเปลี่ยนพอร์ตให้ใช้ URL ใหม่และแก้ Google redirect URI ให้ตรงกัน

## เชื่อม Google Drive ของคุณ

ไม่สามารถตั้งค่าบัญชี Google แทนเจ้าของบัญชีได้ โดยต้องสร้าง OAuth credentials และอนุญาตด้วยตัวเอง:

1. สร้างโปรเจกต์ใน [Google Cloud Console](https://console.cloud.google.com/)
2. เปิด Google Drive API
3. ตั้งค่า OAuth consent screen, เพิ่ม scope `https://www.googleapis.com/auth/drive.readonly` และเพิ่มอีเมลของคุณเป็น Test user ถ้าแอปยังอยู่ในโหมด Testing
4. สร้าง OAuth Client ID ชนิด **Web application**
5. เพิ่ม Authorized redirect URI: `http://127.0.0.1:8765/api/google/callback`
6. ดาวน์โหลด JSON แล้วเลือกไฟล์ในหน้าตั้งค่าของ FindFace (อย่า commit หรือส่งไฟล์ secret ให้ผู้อื่น)
7. กดเชื่อมต่อ Google Drive และอนุญาตให้แอปอ่านไฟล์

เปิดเว็บผ่าน `127.0.0.1` ตาม URL ข้างบนตลอดขั้นตอน OAuth เพื่อให้ session cookie กลับมาที่ host เดิม Scope นี้เป็น restricted scope; การเผยแพร่แอปให้บุคคลอื่นอาจต้องผ่านกระบวนการ verification/security assessment ของ Google โหมด Testing อาจต้องเชื่อมต่อใหม่เมื่อ token หมดอายุ

เลือกโฟลเดอร์จากตัวเลือกบนหน้าเว็บ หรือวางลิงก์โฟลเดอร์ที่มีสิทธิ์อ่าน รองรับโฟลเดอร์ย่อยและ Shared Drives โดยเลือก Drive ให้ตรงกับโฟลเดอร์ การสแกน "ทั้งหมด" ครอบคลุม corpus ที่เลือก; หากมีหลาย Shared Drives ให้เพิ่มแต่ละ Drive แยกกัน ไม่ติดตาม Google Drive shortcuts และไม่รวม Google Photos ที่ไม่ได้เป็นไฟล์ใน Drive

## สิ่งที่ทำงานจริง

- ตรวจจับหลายใบหน้า, landmark alignment และ ArcFace 512D พร้อมบันทึกค่าความคมและแสงเป็นข้อมูลประกอบ โดยไม่ปฏิเสธใบหน้าเพราะขนาด ความมืด หรือความเบลอ หากตรวจจับและสร้างเวกเตอร์ได้
- การลงทะเบียนจะข้ามภาพที่ไม่พบใบหน้า มีหลายคน หรือสร้างเวกเตอร์ไม่ได้ แล้วใช้ภาพที่เหลือสร้างโปรไฟล์ได้เมื่อมีอย่างน้อย 1 ภาพ พร้อมแสดงจำนวนภาพที่ใช้และข้าม (แนะนำ 3–5 มุมมอง)
- ภาพอ้างอิง 3–5 ภาพ ตรวจภาพซ้ำ ตรวจความสอดคล้องเบื้องต้น และบันทึกแบบ atomic
- สแกน background thread พร้อมดาวน์โหลดไม่เกิน 3 ภาพพร้อมกัน ไม่ขวางหน้าเว็บ
- Pagination จนหมด, recursive folders, retry/backoff, แสดงปัญหารายไฟล์, หยุดงานสแกนได้
- สแกนซ้ำจะอ่าน metadata ใหม่และประมวลผลเฉพาะไฟล์ที่เปลี่ยน ล้างไฟล์ที่ถูกลบเมื่อ enumeration สำเร็จครบเท่านั้น
- FAISS `IndexFlatIP.range_search` บน L2-normalized vectors คืนทุกภาพผ่าน threshold ไม่มี top-k ตัดผลหาย
- รวมผลตามภาพ แต่เก็บ bounding box และ feedback รายใบหน้า
- ผลค้นหามีปุ่มหน้าแรก/ก่อนหน้า/ถัดไป/หน้าสุดท้าย และดาวน์โหลดรูปต้นฉบับทีละรูปจากหน้ารายละเอียด
- ดาวน์โหลดผลค้นหาทุกหน้าตามตัวกรองเป็น ZIP แบบ streaming โดยไม่สร้างสำเนาบนเซิร์ฟเวอร์ มี `download-report.txt` บอกจำนวนที่สำเร็จและรูปที่อ่านไม่ได้ใน ZIP
- Similarity และสถานะ review/confirmed แยกกัน ไม่แสดงคะแนนเป็นเปอร์เซ็นต์ความแม่นยำ
- เลือกยืนยันและเพิ่ม reference ได้ไม่เกิน 12 เวกเตอร์ต่อโปรไฟล์ ไม่ fine-tune encoder อัตโนมัติ
- Google OAuth state + PKCE, session cookie, CSRF check, Host validation, ไม่บันทึก query string OAuth ใน access log

## ข้อมูลและความเป็นส่วนตัว

ข้อมูล runtime ทั้งหมดอยู่ใน `data/` ซึ่งถูก ignore จาก source control:

- `findface.sqlite3`: metadata, jobs, embeddings และ feedback
- `encryption.key`: กุญแจ Fernet ของเครื่องนี้
- `models/buffalo_sc/`: weights ของ detector และ recognition สำหรับ CPU

Embedding และ Google tokens ถูกเข้ารหัสก่อนเก็บใน SQLite; metadata เช่นชื่อไฟล์ พาธ และ bounding box ไม่ได้เข้ารหัสทั้งฐานข้อมูล FAISS อยู่ใน RAM และสร้างใหม่จาก SQLite กุญแจอยู่ในเครื่องเดียวกับฐานข้อมูล จึงควรใช้สิทธิ์บัญชีระบบและการเข้ารหัสดิสก์ช่วยปกป้อง ไม่ใช่ hardware-backed vault

ภาพอ้างอิงและ preview ใช้หน่วยความจำชั่วคราว ไม่เขียนภาพไปฐานข้อมูลหรือโฟลเดอร์อัปโหลด ภาพอัลบั้มยังอยู่ใน Drive/โฟลเดอร์เดิม การปล่อย Python objects ไม่ได้รับรอง secure erasure ของ RAM, swap หรือ crash dump เบราว์เซอร์ใช้ `Cache-Control: no-store`

การสแกนเก็บ embeddings ทุกใบหน้าในภาพ รวมคนอื่นด้วย ใช้เฉพาะอัลบั้มที่มีสิทธิ์ประมวลผล ลบอัลบั้มเพื่อลบดัชนีของมัน ลบโปรไฟล์เพื่อลบ reference/feedback ภาพต้นฉบับจะไม่ถูกลบ หากสำรอง `data/` ต้องสำรอง key คู่กันและรักษาความปลอดภัยของ backup ด้วย

## โมเดลและข้อจำกัดที่ต้องรู้

**Pretrained InsightFace weights มีเงื่อนไข non-commercial research** ตรวจ [สิทธิ์โมเดล](https://github.com/deepinsight/insightface/tree/master/python-package) ก่อนใช้งานเชิงพาณิชย์ ระบบเริ่มต้นใช้ `buffalo_sc` (SCRFD-500M + MobileFaceNet ArcFace 512D) เหมาะกับ CPU และไฟล์เล็ก รุ่นใหญ่ `buffalo_l` อาจให้ผลดีกว่าในภาพยาก แต่ต้องวัดกับภาพจริง

Inference ใช้ **ONNX Runtime โดยตรง** กับ weights ของ InsightFace พร้อม NumPy/Pillow สำหรับ SCRFD decoding, five-point alignment และ normalization จึงไม่ต้องติดตั้ง OpenCV, SciPy หรือ InsightFace toolbox ทั้งชุด ผล embedding อาจต่างเล็กน้อยจาก OpenCV preprocessing และต้อง calibrate บน pipeline นี้โดยเฉพาะ

หากต้องการรุ่นใหญ่ กำหนด `FIND_FACE_MODEL=buffalo_l` ใน `.env` แล้วติดตั้งโมเดลใหม่ (ประมาณ 281 MB) และลงทะเบียน/สแกนใหม่ ห้ามนำเวกเตอร์คนละรุ่นมาเทียบกัน หากมี weights ที่ได้รับอนุญาตและเข้ากันได้ กำหนด `FIND_FACE_MODEL_DIR`; รุ่น sc ต้องมี `det_500m.onnx` กับ `w600k_mbf.onnx` ส่วนรุ่น l ต้องมี `det_10g.onnx` กับ `w600k_r50.onnx` รุ่น pipeline และ SHA256 ของ weights ใช้แยกดัชนี

ติดตั้งโมเดลด้วยคำสั่งได้:

```powershell
.venv/Scripts/python.exe scripts/install_model.py
```

- ค่า similarity เริ่มต้น 0.65 และเส้นแบ่ง review/match 0.70 เป็นค่าทดลอง ต้อง calibrate กับคลังภาพจริง ไม่รับรองความแม่นยำ
- ไม่ได้ยืนยันว่าคนอัปโหลดคือบุคคลในภาพ ไม่มี liveness สำหรับการพิสูจน์ตัวตน
- ภาพแมส วัยเด็ก ฝาแฝด ภาพเบลอ และใบหน้าเล็กอาจหาไม่ครบหรือจับคู่ผิดได้
- Detector ใช้ขนาด 1024; ยังไม่มี tiled detection สำหรับภาพหมู่ขนาดใหญ่มาก
- รองรับ JPEG, PNG, WebP, BMP, TIFF; ไม่รองรับ HEIC/RAW โดยอัตโนมัติ ขนาดสูงสุด 25 MB / 40 MP ต่อภาพ ภาพอ้างอิงจำกัด 8 MB ในหน้าเว็บ
- ใช้ SQLite + worker ใน process เดียวสำหรับเครื่องส่วนตัว ยังไม่มี Redis/Celery หรือ PostgreSQL สำหรับ production หลายเครื่อง
- Incremental scan ใช้ file version/checksum/mtime จาก enumeration ใหม่ ยังไม่ใช้ Drive Changes API
- Exact FAISS index ใช้ RAM ประมาณ 2 KB ต่อใบหน้า บวก metadata; 500,000 ใบหน้าใช้ RAM สำหรับ vectors ราว 1 GB และยังต้องวัดเวลาบนเครื่องจริง
- การยกเลิกงานรอภาพปัจจุบันและ download ที่กำลังทำงานจบก่อน
- ผลยืนยันเชื่อมกับ face ID; เมื่อไฟล์ภาพเปลี่ยนและถูกประมวลผลใหม่ ผลยืนยันเดิมของไฟล์นั้นจะถูกล้าง

## โครงสร้างและการทดสอบ

```text
backend/app.py       FastAPI, local session, API routes
backend/vision.py    detection → FQA → aligned ArcFace embeddings
backend/inference.py SCRFD / ArcFace ONNX Runtime + NumPy/Pillow preprocessing
backend/drive.py     Google OAuth + paginated Drive API
backend/jobs.py      background scan / bounded downloads / reconciliation
backend/search.py    exact FAISS index + feedback + pagination
backend/db.py        SQLite and encrypted fields
web/                 HTML/CSS/JavaScript responsive Thai interface
tests/               API, security, matching and scan regression tests
```

```powershell
uv pip install --python .venv/Scripts/python.exe --cache-dir .uv-cache -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
node --check web/app.js
```

Tests ใช้ฐานข้อมูลชั่วคราวและ embeddings สังเคราะห์เพื่อทดสอบตรรกะ ไม่ใช่ benchmark ความแม่นยำของใบหน้า การทดสอบ Google Drive จริงต้องมี OAuth ของเจ้าของบัญชี

`requirements.lock` เก็บเวอร์ชันที่ทดสอบบนเครื่องนี้ หากต้องการตรวจโมเดลจริงแบบครบขั้นตอนบนฐานข้อมูลชั่วคราว ใช้ `scripts/verify_inference.py --image <ภาพทดสอบที่มีสิทธิ์ใช้และมีใบหน้าเดียว>` สคริปต์จะตรวจลงทะเบียน, สแกน, ภาพหมู่, ค้นหา, preview, feedback และการลบดัชนี โดยไม่แตะบัญชี Google หรือข้อมูลใช้งานจริง การใช้ภาพเดียวที่ปรับแสง/ขนาดเป็นเพียง smoke test ไม่ใช่การประเมินความแม่นยำข้ามบุคคล

สำหรับการเปิดให้หลายคนใช้ ต้องเพิ่ม authentication/authorization รายผู้ใช้, tenant isolation, durable queue, HTTPS, deployment secrets, retention และการประเมิน threshold ก่อนเปิดใช้งาน ห้ามเปลี่ยน bind เป็น `0.0.0.0` แล้วถือว่าเป็นระบบ production

ทดสอบปุ่มแบ่งหน้าและลิงก์ดาวน์โหลดบนเว็บด้วย `node --test tests/test_web.cjs` (ใช้ Node.js)

## ทดลอง Oracle Cloud

มี [คู่มือติดตั้ง Oracle Always Free](deploy/ORACLE.md) พร้อม Dockerfile และ Compose แบบเข้าผ่าน SSH tunnel โดยเก็บข้อมูลใน volume ถาวร ชุดนี้ยังต้องทดสอบ build บน ARM64 VM จริงและยังไม่ใช่เว็บสาธารณะหลายผู้ใช้


## ใช้เครื่อง Windows เป็นเซิร์ฟเวอร์หลายบัญชี

เปิดด้วย `Start-Server.cmd` และหยุดด้วย `Stop-Server.cmd` มีบัญชีเจ้าของ คำเชิญใช้ครั้งเดียว ฐานข้อมูลและ Google Drive แยกตามผู้ใช้ พร้อมคิวสแกนและ HTTPS ผ่าน Tailscale Funnel สำหรับ URL คงที่ หรือ Cloudflare Quick Tunnel สำหรับทดลอง ดูขั้นตอน Google OAuth การเปิดอัตโนมัติ และข้อจำกัดลิงก์ฟรีใน [คู่มือ Windows Server](deploy/WINDOWS-SERVER.md)
