"use strict";
const $ = s => document.querySelector(s);
let csrf = '', mode = 'login', setup = false;
const fragment = new URLSearchParams(location.hash.slice(1));
const code = fragment.get('setup') || fragment.get('invite') || '';
history.replaceState(null, '', '/login');
$('#code').value = code;
function render() {
  $('#title').textContent = setup ? 'สร้างบัญชีเจ้าของเซิร์ฟเวอร์' : mode === 'register' ? 'พื้นที่รูปภาพของคุณ' : 'ค้นหาทุกรูปที่มีคุณ';
  $('#description').textContent = setup ? 'ตั้งชื่อบัญชีและรหัสผ่านสำหรับคุณ ข้อมูลเดิมในเครื่องจะอยู่ในบัญชีนี้' : mode === 'register' ? 'ตั้งชื่อบัญชีและรหัสผ่าน เพื่อสร้างพื้นที่รูปภาพส่วนตัวของคุณ' : 'เข้าสู่ระบบเพื่อค้นหารูปและเชื่อมต่อ Google Drive ของคุณ';
  $('#code-field').hidden = !setup;
  $('#code').required = setup;
  $('#password').autocomplete = mode === 'register' ? 'new-password' : 'current-password';
  $('#submit').textContent = mode === 'register' ? 'สร้างบัญชีและเริ่มใช้งาน' : 'เข้าสู่ระบบ';
  $('#switch').hidden = setup;
  $('#switch').textContent = mode === 'register' ? 'มีบัญชีแล้ว? เข้าสู่ระบบ' : 'ยังไม่มีบัญชี? สร้างบัญชีใหม่';
}
$('#switch').addEventListener('click', () => { mode = mode === 'register' ? 'login' : 'register'; $('#error').hidden = true; render(); });
$('#auth-form').addEventListener('submit', async event => {
  event.preventDefault(); $('#submit').disabled = true; $('#error').hidden = true;
  try {
    const response = await fetch('/api/auth/' + mode, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify({username:$('#username').value.trim(),password:$('#password').value,code:$('#code').value.trim()})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'ตรวจสอบชื่อบัญชีและรหัสผ่านอย่างน้อย 12 ตัวอักษร');
    location.replace('/');
  } catch(error) { $('#error').textContent = error.message; $('#error').hidden = false; }
  finally { $('#submit').disabled = false; }
});
(async () => {
  try {
    const response = await fetch('/api/auth/session');
    if (!response.ok) throw new Error('เปิดเซสชันไม่ได้ กรุณารีเฟรชหน้าเว็บ');
    const data = await response.json(); csrf = data.csrf;
    if (data.user || !data.server) { location.replace('/'); return; }
    setup = data.setup_needed; mode = setup || code ? 'register' : 'login'; render();
  } catch(error) { $('#error').textContent = error.message; $('#error').hidden = false; }
})();
