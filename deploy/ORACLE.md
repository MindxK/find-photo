# ทดลอง FindFace บน Oracle Always Free

สถานะ: เตรียมชุดติดตั้งแล้ว ยังไม่ได้สร้าง VM หรือทดสอบ Docker บน Oracle จริง

ชุดนี้เป็นการทดลองสำหรับเจ้าของระบบ ผ่าน SSH tunnel เท่านั้น แอปยังใช้ Google Drive และฐานข้อมูลร่วมกัน ไม่มีบัญชีผู้ใช้แยก จึงยังไม่เปิดพอร์ตเว็บสาธารณะ ผู้มีสิทธิ์ SSH และเข้าเว็บได้จะมีสิทธิ์จัดการพื้นที่ทำงานทั้งหมด

## 1. สมัคร Oracle ด้วยตนเอง

- สมัครที่ https://signup.cloud.oracle.com/ และยืนยันอีเมล/โทรศัพท์/ข้อมูลบัตรตามที่ Oracle ขอ ไม่ส่งรหัสผ่าน OTP หรือเลขบัตรในแชต
- เลือก Home Region ให้รอบคอบ เพราะเปลี่ยนภายหลังไม่ได้ และ Always Free ต้องอยู่ใน Home Region
- ใช้ Always Free ไม่อัปเกรดเป็น Pay As You Go เพื่อข้ามปัญหาเครื่องไม่ว่างโดยไม่ได้ตัดสินใจเรื่องค่าใช้จ่ายก่อน
- เอกสารที่ตรวจวันที่ 23 กันยายน 2026 ระบุ A1 รวม 2 OCPU / RAM 12 GB และ boot/block volume รวม 200 GB ฟรี แต่ต้องตรวจโควตาและทรัพยากรที่ใช้อยู่ในบัญชีจริงอีกครั้ง
- เครื่อง Always Free ที่ใช้น้อยอาจถูกเรียกคืน ต้องมีสำรองฐานข้อมูลและ encryption.key คู่กัน

แหล่งข้อมูล: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

## 2. สร้าง VM เมื่อบัญชีพร้อม

เลือก Compute > Instances > Create instance:

- Image: Ubuntu 24.04 ARM64 สำหรับ A1
- Shape: VM.Standard.A1.Flex โดยจัดสรรไม่เกินโควตาฟรีที่เหลือ (เป้าหมาย 2 OCPU / RAM 12 GB)
- Boot volume: 50 GB ภายในโควตาที่เหลือ ไม่เปิดตัวเลือกคิดเงินเพิ่ม
- Public subnet พร้อม public IPv4 และ Internet Gateway เพื่อเชื่อม SSH
- เปิด inbound TCP 22 เฉพาะ public IP ของผู้ดูแล /32 ทั้งใน OCI Security List/NSG และ firewall ของเครื่อง ไม่เปิด 8765 สู่สาธารณะ
- ใช้ SSH public key ของตัวเอง เก็บ private key ไว้ในเครื่อง ไม่ commit ลง Git
- ตรวจสรุปค่าใช้จ่ายและป้าย Always Free ก่อนกดสร้าง ถ้าพบ Out of capacity ให้รอหรือเลือก availability domain อื่นใน Home Region ไม่เปลี่ยนไปใช้ shape เสียเงินอัตโนมัติ

คู่มือสร้าง VM: https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm

## 3. ติดตั้งบน VM

เชื่อม SSH จากเครื่องเจ้าของ (แทน SERVER_IP และพาธ key ด้วยค่าจริง):

```powershell
ssh -i "C:\path\oracle.key" ubuntu@SERVER_IP
```

ติดตั้ง Docker Engine และ Compose plugin ตามคู่มือ Ubuntu อย่างเป็นทางการ:
https://docs.docker.com/engine/install/ubuntu/

จากนั้นบน VM:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/MindxK/find-photo.git
cd find-photo
sudo docker compose config --quiet
sudo docker compose build
sudo docker compose up -d
sudo docker compose exec findface python scripts/install_model.py
sudo docker compose ps
```

หาก pip แจ้งไม่มี ARM64 wheel สำหรับแพ็กเกจใน requirements.lock ให้หยุดและส่งเฉพาะข้อความ error มาเพื่อตรวจเวอร์ชัน ห้ามข้ามแพ็กเกจหรือเปลี่ยน shape เสียเงินเพื่อให้ผ่านโดยไม่ตรวจสอบ

Container รันด้วยผู้ใช้ที่ไม่ใช่ root ใช้ worker เดียวเพื่อให้คิวสแกน/session/FAISS สอดคล้องกัน และเก็บฐานข้อมูล token คีย์ และโมเดลใน named volume ไม่คัดลอกข้อมูลส่วนตัวจากคอมขึ้นเซิร์ฟเวอร์ให้อัตโนมัติ

## 4. เปิดเว็บผ่าน SSH tunnel

หยุด FindFace ที่รันในคอมก่อนเพื่อให้พอร์ต 8765 ว่าง แล้วเปิด PowerShell:

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -i "C:\path\oracle.key" -L 127.0.0.1:8765:127.0.0.1:8765 ubuntu@SERVER_IP
```

เปิด http://127.0.0.1:8765 ในเบราว์เซอร์ของเครื่องนี้ ข้อมูลและการสแกนทำงานบน Oracle ปิด tunnel แล้วงานบนเซิร์ฟเวอร์ยังทำต่อได้ แต่ต้องต่อ tunnel ใหม่เพื่อเปิดเว็บ การรีบูต VM จะเริ่ม container ใหม่ งานสแกนที่ขาดช่วงต้องกดสแกนต่อเอง

ตั้งค่า Google OAuth บนหน้าเว็บใหม่ โดยใช้ redirect URI `http://127.0.0.1:8765/api/google/callback` สำหรับ tunnel นี้ บัญชีทดสอบ Google ต้องอยู่ในรายชื่อ Test users ของ OAuth project

โฟลเดอร์บนเครื่องในหน้าเว็บหมายถึงโฟลเดอร์ภายในเซิร์ฟเวอร์/container ไม่ใช่ไดรฟ์ C: ของผู้เปิดเบราว์เซอร์ ในขั้นนี้ให้เชื่อม Google Drive เป็นแหล่งรูป

## 5. ดูสถานะและอัปเดต

```bash
sudo docker compose logs --tail=80 findface
git pull --ff-only
sudo docker compose up -d --build
```

หลีกเลี่ยงการอัปเดตขณะมีงานสแกน `docker compose down -v` ลบข้อมูลถาวร ห้ามใช้เมื่อต้องการเก็บโปรไฟล์และการเชื่อมต่อเดิม สำรอง named volume โดยหยุดงานและ container ก่อน เพื่อให้ SQLite และคีย์อยู่ในสถานะเดียวกัน

## ก่อนเปิดเป็นลิงก์ให้คนทั่วไป

ต้องเพิ่มระบบเข้าสู่ระบบ แยกสิทธิ์/ข้อมูลผู้ใช้ จำกัดการเข้าถึงไฟล์บนเซิร์ฟเวอร์ รองรับ HTTPS/โดเมน และเปลี่ยน Google OAuth redirect URI กับ allowed origins ให้ตรงกันก่อน การเปิด 8765 สาธารณะเพียงอย่างเดียวไม่ใช่การติดตั้งระบบหลายผู้ใช้
