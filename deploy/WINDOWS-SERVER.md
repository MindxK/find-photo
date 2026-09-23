# ใช้คอม Windows เป็น FindFace server

ระบบหลายบัญชีเปิดด้วย `Start-Server.cmd` (ต้องติดตั้ง dependencies ใน `.venv` ก่อน) เว็บไซต์ยังฟังเฉพาะ `127.0.0.1:8765`; Tailscale Funnel หรือ Cloudflare Tunnel เปิด HTTPS ให้เข้าจากภายนอก โดยไม่ต้องเปิดพอร์ตเราเตอร์

## ครั้งแรก

1. เปิด `Start-Server.cmd` แล้วไป `http://127.0.0.1:8765/login`
2. ตั้งชื่อบัญชีเจ้าของและรหัสผ่านอย่างน้อย 12 ตัวอักษร ช่องรหัสเชิญใช้ค่าจาก `data/owner-setup.txt` บนเครื่องนี้ ไฟล์นี้ถูกลบทันทีเมื่อสร้างบัญชีเจ้าของสำเร็จ อย่าส่งรหัสตั้งค่าให้ผู้อื่น
3. บัญชีแรกได้รับข้อมูลเดิมใน `data/findface.sqlite3` ทั้งโปรไฟล์ อัลบั้ม และ Google connection ไม่ย้ายหรือทำลายไฟล์เดิม
4. หลังสร้างเจ้าของ ตัวเปิดเซิร์ฟเวอร์จะดาวน์โหลด cloudflared release ทางการที่ตรึงเวอร์ชันและตรวจ SHA-256 แล้วสร้างลิงก์ HTTPS ดูลิงก์ที่ **ตั้งค่า → จัดการเซิร์ฟเวอร์** หรือ `data/server-status.json`
5. Google Cloud → OAuth Client ชนิด Web application (ถ้าเดิมเป็น Desktop ให้สร้าง Web client ใหม่) → Authorized redirect URIs: **เพิ่ม** `https://ชื่อที่ได้รับ.trycloudflare.com/api/google/callback` โดยคง localhost URI เดิมไว้
   เลือกไฟล์ JSON ของ Web client ใน FindFace → ตั้งค่า → จัดการเซิร์ฟเวอร์ การตั้งค่านี้แยกจาก Desktop connection เดิม จึงไม่ลบดัชนีหรือ token เดิม
6. ถ้า OAuth app ยังเป็น Testing ให้เพิ่มอีเมล Google ของผู้ที่จะเชื่อมต่อใน Audience → Test users
7. กด **สร้างลิงก์เชิญ** ในหน้าตั้งค่า ส่งให้คนที่ต้องการสมัคร ลิงก์ใช้ได้ครั้งเดียวภายใน 24 ชั่วโมง แต่ละคนตั้งรหัสผ่านและเชื่อมต่อ Drive ของตัวเอง

Cloudflare Quick Tunnel เหมาะกับการทดลอง: URL อาจเปลี่ยนทุกครั้งที่ตัว tunnel เริ่มใหม่ ไม่มี SLA และจำกัด 200 คำขอพร้อมกัน ถ้าลิงก์เปลี่ยน ต้องเพิ่ม redirect URI ใหม่ใน Google OAuth ด้วย สำหรับ URL คงที่ควรใช้ named tunnel กับโดเมนของเจ้าของ

แอป Google ที่อยู่ใน Testing อาจได้รับ refresh token อายุ 7 วันสำหรับ scope Drive ผู้ใช้ต้องเชื่อมต่อใหม่เมื่อหมดอายุ การเปิดให้บุคคลทั่วไปใช้ scope ที่จำกัดอาจต้องผ่าน OAuth verification ของ Google

อ้างอิง: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/), [Google OAuth web server](https://developers.google.com/identity/protocols/oauth2/web-server), [Google token expiration](https://developers.google.com/identity/protocols/oauth2#expiration)

## การเปิดและปิด

- เปิด: `Start-Server.cmd` ทำงานเบื้องหลัง ปิดหน้าต่าง command ได้
- หยุด: `Stop-Server.cmd` ปิดทั้งเว็บและ tunnel โดยไม่ลบข้อมูล
- เปิดอัตโนมัติหลังเข้า Windows: รัน `scripts/Enable-ServerStartup.ps1` สร้าง shortcut ชื่อ `FindFace Server` ใน Startup ของบัญชี Windows ปัจจุบัน ไม่ใช่บริการที่เปิดก่อนล็อกอิน
- ยกเลิกเปิดอัตโนมัติ: กด Win+R → `shell:startup` แล้วลบเฉพาะ shortcut `FindFace Server`
- ขณะเปิด supervisor จะกันการ sleep จากการไม่ได้ใช้งาน และคืนค่านโยบายเดิมเมื่อหยุด ไม่เปลี่ยน power plan ถาวร การกด Sleep เอง ปิดฝา laptop ปิดเครื่อง ไฟดับ หรือเน็ตหลุดยังทำให้เว็บหยุดได้
- Session หมดอายุใน 24 ชั่วโมงหรือเมื่อเว็บรีสตาร์ต ให้เข้าสู่ระบบใหม่
- ดูสถานะ: `data/server-status.json`; บันทึกการทำงาน: `data/server.log` และ `data/tunnel.log` อย่าแชร์โฟลเดอร์ data ทั้งหมด

## การแยกข้อมูล

บัญชีถูกเก็บที่ `data/accounts.sqlite3` รหัสผ่านใช้ scrypt พร้อม salt รายบัญชี จำกัดความถี่การลองเข้าสู่ระบบ สมัครผ่านคำเชิญเท่านั้น

บัญชีเจ้าของใช้ฐานข้อมูลเดิม บัญชีอื่นใช้ `data/users/<id>/workspace.sqlite3` แยกโปรไฟล์ อัลบั้ม ไฟล์ ใบหน้า ผลยืนยัน งานสแกน และ Google token แต่ละบัญชี API ยึดบัญชีจาก cookie ฝั่งเซิร์ฟเวอร์ และไม่รับชื่อฐานข้อมูลจาก browser

คิวสแกนทำทีละงาน สูงสุดหนึ่งงานต่อบัญชี และ 30 งานรวม ผู้ใช้แต่ละคนเห็นและยกเลิกได้เฉพาะงานของตัวเอง เฉพาะเจ้าของเพิ่มอัลบั้มจากโฟลเดอร์ Windows และติดตั้งโมเดลได้

Web OAuth client ของเซิร์ฟเวอร์ถูกใช้สำหรับการเชื่อมต่อใหม่ทุกบัญชี แต่ Google access/refresh tokens แยกตามบัญชี ข้อมูล client ถูกตรึงไว้ใน workspace เมื่อเชื่อมต่อสำเร็จ เพื่อไม่ให้การเปลี่ยน client ของเจ้าของกระทบ token เดิมของบัญชีอื่น ภาพถ่ายใช้ในหน่วยความจำและไม่ถูกบันทึกถาวร

เจ้าของเครื่องยังเป็นผู้ดูแลข้อมูลที่จัดเก็บบนเครื่องนี้ การแยกบัญชีเป็นการควบคุมสิทธิ์ของแอป ไม่ใช่การเข้ารหัสที่ปิดกั้นผู้ดูแลเครื่อง Cloudflare ทำหน้าที่ proxy สำหรับ HTTPS

## สำรองและกู้คืน

หยุด server ก่อนสำรอง จากนั้นสำรองโฟลเดอร์ `data` ไปยังที่เก็บส่วนตัวที่ปลอดภัย โดยต้องมี **encryption.key, accounts.sqlite3, findface.sqlite3 และ users/** ครบ จึงถอดรหัสเวกเตอร์และ Google tokens เดิมได้ อย่าส่งไฟล์เหล่านี้ขึ้น Git

สำรองก่อนเปิดหลายบัญชีอยู่ใน `data/backups/before-multiuser-*.sqlite3` ซึ่งเป็นสำเนาฐานข้อมูลเดิม ต้องใช้ encryption.key เดิมในการอ่าน

## ขอบเขตการใช้งาน

เหมาะกับกลุ่มผู้ใช้ที่เจ้าของเชิญและทรัพยากรของพีซีเครื่องเดียว ไม่ใช่บริการสาธารณะขนาดใหญ่ การเปิด 24 ชั่วโมงต้องเปิดเครื่อง เข้า Windows และมีอินเทอร์เน็ตตลอด ไม่สามารถรับประกัน uptime ของไฟบ้านหรือ Quick Tunnel ได้

InsightFace weights ที่แจกมากับโปรเจกต์มีข้อกำหนดการใช้สำหรับการวิจัยที่ไม่ใช่เชิงพาณิชย์ ตรวจสิทธิ์โมเดลก่อนนำไปให้บริการเชิงพาณิชย์


## URL ฟรีคงที่ด้วย Tailscale Funnel

ถ้ามี Tailscale บนเครื่อง ให้เข้าสู่บัญชีเดิม เปิด MagicDNS และอนุญาต Funnel ผ่านลิงก์ที่คำสั่ง `tailscale funnel --bg --https=443 http://127.0.0.1:8765` แสดง จากนั้นบันทึก `data/tunnel-config.json`:

```json
{"provider":"tailscale","public_origin":"https://ชื่อเครื่อง.ชื่อเครือข่าย.ts.net"}
```

ใช้ URL จริงจาก `tailscale status --json` → `Self.DNSName` โดยตัดจุดสุดท้ายออก และเพิ่ม `/api/google/callback` ใน Web OAuth Client เดิม จากนั้นหยุดและเปิด `Start-Server.cmd` ใหม่

- เซิร์ฟเวอร์จะใช้ hostname นี้ทุกครั้ง ไม่มีการถอยกลับไปสุ่มลิงก์ Quick Tunnel เมื่อมีปัญหา
- เปิดเครื่อง เข้า Windows และต่ออินเทอร์เน็ตแล้วใช้ลิงก์เดิมได้ การเข้าสู่ระบบ Tailscale ต้องยังใช้ได้
- อย่าเปลี่ยนชื่อเครื่องใน Tailscale, เปลี่ยน tailnet DNS name หรือลบอุปกรณ์นี้แล้วลงทะเบียนใหม่ หากชื่อเปลี่ยน ตัวเปิดเซิร์ฟเวอร์จะแจ้งข้อผิดพลาดเพื่อให้ผู้ดูแลตรวจ ไม่สลับ URL เอง
- `Stop-Server.cmd` ปิดเฉพาะ Funnel 443 ที่ชี้มายัง FindFace และหยุดเว็บ การเปิดใหม่สร้างเส้นทางเดิมกลับมา โดยไม่แตะบริการที่ชี้ไปพอร์ตอื่น
- Tailscale ต้องทำงานอยู่ คีย์อุปกรณ์อาจหมดอายุและต้องลงชื่อเข้าใช้อีกครั้ง ตรวจวันหมดอายุในหน้า Machines ของ Tailscale ไม่ได้ปิด key expiry อัตโนมัติ
- ผู้เข้าชมไม่ต้องติดตั้ง Tailscale; ทุกคนยังต้องเข้าสู่บัญชี FindFace ของตนเอง
- Funnel ยังเป็น beta มีข้อจำกัด bandwidth และไม่มีคำรับรอง uptime สำหรับเว็บนี้ ดู [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel)
- การเปลี่ยน provider เป็นงานตั้งค่าในเครื่อง ไม่เปิด API ให้ผู้ใช้ทั่วไปแก้การเผยแพร่เซิร์ฟเวอร์

หากยังไม่มี `tunnel-config.json` ระบบยังใช้ Cloudflare Quick Tunnel ตามเดิม ส่วนค่าที่ไม่ถูกต้องจะหยุดการเริ่ม tunnel และแสดง `configuration_error` ใน `server-status.json`
