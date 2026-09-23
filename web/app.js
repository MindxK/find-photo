'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const E = escapeHtml;
const paths = {
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  user:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  folder:'<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 9h18"/>',
  activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  settings:'<path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h6l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3Z"/><circle cx="12" cy="12" r="3"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  monitor:'<rect x="3" y="3" width="18" height="13" rx="2"/><path d="M8 21h8m-4-5v5"/>',
  drive:'<path d="m9 3 6 0 8 14-3 5H4l-3-5Z"/><path d="m9 3 8 14H1m3 5L15 3M17 17l3 5"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  images:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m3 17 6-5 4 3 3-4 5 6"/>',
  scan:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><path d="M8 14c2 4 6 4 8 0M8 9h.1M16 9h.1"/>',
  check:'<path d="m5 12 4 4L20 5"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',
  down:'<path d="m6 9 6 6 6-6"/>',
  upload:'<path d="M12 16V3m-5 5 5-5 5 5M3 15v5a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-5"/>',
  download:'<path d="M12 3v13m-5-5 5 5 5-5M3 15v5a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-5"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  lock:'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>',
  arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  refresh:'<path d="M20 8a8 8 0 1 0 0 9M20 3v5h-5"/>',
  link:'<path d="M14 3h7v7m0-7L10 14M10 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
  copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  alert:'<path d="m12 3 10 18H2Z"/><path d="M12 9v5m0 3v.1"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.images}</svg>`;
const decorate = () => $$('[data-icon]').forEach(node => { node.innerHTML = icon(node.dataset.icon); });
const number = value => Number(value || 0).toLocaleString('th-TH');
const date = value => value ? new Date(value * 1000).toLocaleString('th-TH', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : 'ยังไม่เคยสแกน';
const state = {view:'search', status:null, csrf:'', profiles:[], sources:[], selectedProfile:'', selectedSource:'', threshold:0.65, mode:'all', results:null, offset:0, searching:false, uploadFiles:[], uploadUrls:[], folderTrail:[], folderDrive:'', sourceKind:'local', detail:null, detailFace:0};
let searchSequence = 0;
const titles = {search:'ค้นหารูปของฉัน', profiles:'ใบหน้าอ้างอิง', albums:'อัลบั้มรูป', activity:'ประวัติการสแกน', settings:'ตั้งค่าการเชื่อมต่อ'};

async function api(path, {method='GET', body, ...rest} = {}) {
  const headers = method === 'GET' ? {} : {'Content-Type':'application/json', 'X-CSRF-Token':state.csrf};
  const response = await fetch('/api' + path, {method, headers, credentials:'same-origin', ...(body === undefined ? {} : {body:JSON.stringify(body)}), ...rest});
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { location.replace('/login'); throw new Error('กรุณาเข้าสู่ระบบใหม่'); }
  if (!response.ok) {
    const message = typeof data.detail === 'string' ? data.detail : (Array.isArray(data.detail) ? 'ข้อมูลไม่ครบหรือรูปแบบไม่ถูกต้อง กรุณาตรวจสอบแล้วลองอีกครั้ง' : 'ทำรายการไม่สำเร็จ กรุณาลองอีกครั้ง');
    throw new Error(message);
  }
  return data;
}

function toast(message, error=false) {
  const node = document.createElement('div'); node.className = 'toast' + (error ? ' error' : ''); node.textContent = message;
  $('#toasts').append(node); setTimeout(() => node.remove(), 5500);
}
function errorInModal(error) {
  let node = $('.form-error', $('#modal'));
  if (!node) { node = document.createElement('div'); node.className = 'form-error'; node.setAttribute('role','alert'); ($('.modal-actions', $('#modal')) || $('#modal-body')).before(node); }
  node.textContent = error.message;
}
async function busyButton(button, task, label='กำลังดำเนินการ…') {
  if (button?.disabled) return;
  const original = button?.innerHTML;
  if (button) { button.disabled = true; button.innerHTML = `<span class="spinner"></span>${E(label)}`; }
  try { return await task(); }
  catch (error) { $('#modal').open ? errorInModal(error) : toast(error.message, true); }
  finally { if (button) { button.disabled = false; button.innerHTML = original; } }
}
function closeModal() {
  $('#modal').close(); state.uploadUrls.forEach(URL.revokeObjectURL); state.uploadUrls = []; state.uploadFiles = []; state.detail = null;
}
function openModal(html, photo=false) {
  closeModal(); $('#modal').className = photo ? 'photo-dialog' : '';
  $('#modal-body').innerHTML = html; $('#modal').showModal();
}
function modalHeader(title) { return `<div class="modal-head"><h2 id="modal-title">${E(title)}</h2><button class="icon-button" data-action="close-modal" aria-label="ปิด">${icon('close')}</button></div>`; }
function confirmAction(message, label='ยืนยัน') {
  $('#confirm-message').textContent = message; $('#confirm-yes').textContent = label; $('#confirm-modal').showModal();
  return new Promise(resolve => {
    const dialog = $('#confirm-modal');
    const finish = value => { dialog.close(); resolve(value); };
    $('#confirm-yes').onclick = () => finish(true); $('#confirm-no').onclick = () => finish(false);
    dialog.oncancel = event => { event.preventDefault(); finish(false); };
  });
}
function pageHead(title, description, button='') { return `<div class="page-head"><div><div class="eyebrow">YOUR PERSONAL PHOTO FINDER</div><h1>${E(title)}</h1><p>${E(description)}</p></div>${button}</div>`; }
function empty(title, description, symbol='scan', button='') { return `<div class="empty-state"><div class="empty-icon">${icon(symbol)}</div><h3>${E(title)}</h3><p>${E(description)}</p>${button}</div>`; }
function stats() {
  const items = [['photos','รูปในคลัง','images'],['faces','ใบหน้าที่ตรวจพบ','scan'],['profiles','โปรไฟล์ใบหน้า','user'],['sources','อัลบั้มที่เชื่อมต่อ','folder']];
  return `<div class="stats">${items.map(([key,label,symbol]) => `<div class="stat"><div><div class="label">${label}</div><strong data-stat="${key}">${number(state.status?.stats[key])}</strong></div><div class="stat-icon">${icon(symbol)}</div></div>`).join('')}</div>`;
}
function setupStrip() {
  if (state.status?.model_ready && state.profiles.length && state.status.stats.photos) return '';
  const steps = [ ['settings','เตรียมระบบ',state.status?.model_ready], ['profiles','เพิ่มใบหน้าของคุณ',state.profiles.length>0], ['albums','สแกนอัลบั้ม',state.status?.stats.photos>0] ];
  return `<div class="setup-strip"><div class="setup-lead">${icon('scan')}<div><strong>เริ่มต้นค้นหารูปของคุณ</strong><p>เตรียมให้พร้อมใน 3 ขั้นตอน</p></div></div><div class="steps">${steps.map(([view,label,done],i) => `${i ? '<div class="step-line"></div>' : ''}<button class="step ${done?'done':''}" data-action="navigate" data-target="${view}"><span>${done?'✓':i+1}</span>${label}</button>`).join('')}</div></div>`;
}
function activeJob() { return state.status?.jobs.find(job => ['queued','running','cancelling'].includes(job.status)); }
function inlineJob() {
  const job = activeJob(); if (!job) return '';
  const done = job.processed + job.skipped;
  return `<div class="inline-job"><div class="inline-job-top"><div><strong>${E(job.phase)}</strong> <small>· ${E(job.source_name||'อัลบั้ม')}</small></div><button class="button ghost small" data-action="navigate" data-target="activity">ดูความคืบหน้า ${icon('arrow')}</button></div><small>${number(done)} / ${number(job.total)} รูป${job.current_file ? ' · '+E(job.current_file) : ''}</small><div class="progress ${done===0?'indeterminate':''}"><span style="width:${job.total?Math.min(100,done/job.total*100):0}%"></span></div></div>`;
}

function renderSearch() {
  const profile = state.profiles.find(p => p.id === state.selectedProfile);
  return pageHead('ทุกรูปที่มีคุณ อยู่ที่นี่', 'ค้นหารูปจากอัลบั้มของคุณ ด้วยใบหน้าเพียงไม่กี่ภาพ', `<button class="button secondary" data-action="add-source">${icon('plus')}เพิ่มอัลบั้ม</button>`) + stats() + setupStrip() + '<div id="inline-job">'+inlineJob()+'</div>' + `
  <div class="search-layout"><section class="panel search-controls" aria-label="ตั้งค่าการค้นหา"><div class="panel-header"><h2>${icon('search')}ค้นหาด้วยใบหน้า</h2></div>
    <div class="control-section"><div class="field-label">คนที่คุณต้องการค้นหา<button class="icon-button" data-action="add-profile" aria-label="เพิ่มใบหน้า">${icon('plus')}</button></div>
    ${profile ? `<div class="profile-choice"><span class="avatar">${E(profile.name[0])}</span><div><strong>${E(profile.name)}</strong><small>ภาพอ้างอิง ${profile.reference_count} ใบหน้า</small></div>${icon('check')}</div>${state.profiles.length>1?`<label class="sr-only" for="profile-select">เลือกโปรไฟล์</label><select id="profile-select" style="margin-top:10px">${state.profiles.map(p=>`<option value="${p.id}" ${p.id===profile.id?'selected':''}>${E(p.name)}</option>`).join('')}</select>`:''}` : `<button class="upload-profile" data-action="add-profile"><span>${icon('user')}</span><strong>เพิ่มใบหน้าของคุณ</strong><small>ใช้ภาพใบหน้า 3–5 มุมมอง</small></button>`}</div>
    <div class="control-section"><label class="field-label" for="source-select">ค้นหาในอัลบั้ม</label><select id="source-select"><option value="">ทุกอัลบั้ม</option>${state.sources.map(s=>`<option value="${s.id}" ${s.id===state.selectedSource?'selected':''}>${E(s.name)}</option>`).join('')}</select><p class="helper">ค้นหาได้จากอัลบั้มที่สแกนแล้ว</p></div>
    <div class="control-section"><label class="field-label" for="threshold">ความคล้ายขั้นต่ำ <output class="threshold-value" id="threshold-output">${state.threshold.toFixed(2)}</output></label><input type="range" id="threshold" min="0.30" max="0.95" step="0.01" value="${state.threshold}"><div class="range-labels"><span>ค้นหาได้กว้างขึ้น</span><span>คล้ายมากขึ้น</span></div><p class="helper">คะแนนความคล้ายไม่ใช่เปอร์เซ็นต์ความแม่นยำ คุณสามารถยืนยันผลได้อีกครั้ง</p></div>
    <div class="control-section"><button class="button full" id="search-button" data-action="search" ${!profile?'disabled':''}>${icon('search')}ค้นหารูปของฉัน</button><div class="privacy-note">${icon('lock')}<span>ภาพอ้างอิงไม่ถูกเก็บไว้<br>ใช้เฉพาะเวกเตอร์ใบหน้าในการค้นหา</span></div></div>
  </section><section class="panel results-panel" aria-label="ผลการค้นหา"><div class="results-toolbar"><div class="result-title">ผลการค้นหา <span id="result-count">${number(state.results?.total)}</span></div><div class="tabs" role="group" aria-label="กรองผลลัพธ์"><button class="tab ${state.mode==='all'?'active':''}" data-action="filter" data-mode="all">ทั้งหมด</button><button class="tab ${state.mode==='review'?'active':''}" data-action="filter" data-mode="review">รอตรวจสอบ</button><button class="tab ${state.mode==='confirmed'?'active':''}" data-action="filter" data-mode="confirmed">ยืนยันแล้ว</button><button class="tab ${state.mode=== 'rejected'?'active':' '}" data-action="filter" data-mode="rejected">ไม่ใช่</button></div></div><div id="results" style="display:flex;flex-direction:column;flex:1">${resultsContent()}</div><div class="results-foot"><span class="mini-info">${icon('shield')}แสดงเฉพาะภาพในอัลบั้มของคุณ</span><span>Cosine similarity · 512D</span></div></section></div>`;
}
function resultsContent() {
  if (state.searching) return '<div class="loading-box" role="status"><span class="spinner"></span>กำลังค้นหาใบหน้าในคลังรูป…</div>';
  if (!state.results) return empty('พร้อมค้นหาความทรงจำของคุณ', 'เพิ่มใบหน้าอ้างอิงและสแกนอัลบั้ม แล้วกดค้นหา รูปที่มีคุณจะปรากฏตรงนี้', 'scan');
  if (!state.results.total) return empty('ยังไม่พบรูปที่ตรงกัน', 'ลองเลือกอัลบั้มอื่น ลดค่าความคล้าย หรือเพิ่มภาพอ้างอิงที่เห็นใบหน้าชัดเจน', 'search');
  const limit=state.results.limit||24;
  const offset=state.results.offset;
  const lastOffset=Math.max(0,(Math.ceil(state.results.total/limit)-1)*limit);
  const downloadQuery=new URLSearchParams(state.resultQuery||{});
  return `<div class="result-actions"><a class="button secondary small" href="/api/search/download?${E(downloadQuery)}" download="FindFace-photos.zip" target="_blank" rel="noopener noreferrer">${icon('download')}ดาวน์โหลดทั้งหมด (${number(state.results.total)} รูป) · ZIP</a><small>รูปต้นฉบับตามตัวกรองนี้ทุกหน้า · ดูความคืบหน้าในรายการดาวน์โหลดของเบราว์เซอร์</small></div><div class="gallery">${state.results.items.map((photo,i)=>`<button class="photo-card" data-action="open-photo" data-index="${i}" aria-label="ดูรูป ${E(photo.name)}"><div class="photo-frame"><img src="/api/files/${photo.file_id}/preview" alt="${E(photo.name)}" loading="lazy"><span class="photo-score">${photo.similarity.toFixed(3)}</span></div><div class="photo-caption"><strong>${E(photo.name)}</strong><div><small>${E(photo.source_name)}</small><span class="pill ${photo.faces[0].state==='review'?'amber':''}">${photo.faces[0].state==='rejected'?'ไม่ใช่':photo.faces[0].state==='confirmed'?'ยืนยันแล้ว':photo.faces[0].state==='review'?'รอตรวจสอบ':'ใบหน้าคล้าย'}</span></div></div></button>`).join('')}</div><nav class="pagination" aria-label="หน้าผลการค้นหา"><button class="button secondary small" data-action="first-page" ${offset===0?'disabled':''}>หน้าแรก</button><button class="button secondary small" data-action="previous-page" ${offset===0?'disabled':''}>ก่อนหน้า</button><span aria-live="polite">${Math.floor(offset/limit)+1} / ${Math.ceil(state.results.total/limit)}</span><button class="button secondary small" data-action="next-page" ${offset>=lastOffset?'disabled':''}>ถัดไป</button><button class="button secondary small" data-action="last-page" ${offset>=lastOffset?'disabled':''}>หน้าสุดท้าย</button></nav>`;
}
function renderProfiles() {
  return pageHead('ใบหน้าอ้างอิง', 'ใช้ภาพที่เห็นใบหน้าชัดเจนหลายมุม เพื่อให้ค้นหารูปของคุณได้ดีขึ้น', `<button class="button" data-action="add-profile">${icon('plus')}เพิ่มใบหน้า</button>`) +
    (state.profiles.length ? `<div class="cards">${state.profiles.map(p=>`<article class="panel profile-card"><div class="card-top"><div class="avatar large">${E(p.name[0])}</div><button class="icon-button" data-action="delete-profile" data-id="${p.id}" aria-label="ลบโปรไฟล์ ${E(p.name)}">${icon('trash')}</button></div><h3>${E(p.name)}</h3><p>${p.reference_count} เวกเตอร์อ้างอิง · เพิ่มเมื่อ ${date(p.created)}</p><div class="card-actions"><button class="button small" data-action="search-profile" data-id="${p.id}">${icon('search')}ค้นหารูป</button><span class="pill">ไม่เก็บภาพต้นฉบับ</span></div></article>`).join('')}</div>` : `<section class="panel">${empty('เริ่มด้วยใบหน้าของคุณ', 'เตรียมภาพหน้าตรง หันซ้าย หันขวา หรือสีหน้าต่างกัน 3–5 ภาพ แต่ละภาพควรมีคุณเพียงคนเดียว', 'user', '<button class="button" data-action="add-profile">'+icon('plus')+'เพิ่มใบหน้าอ้างอิง</button>')}</section>`);
}
function renderAlbums() {
  return pageHead('อัลบั้มรูปของคุณ', 'เลือกโฟลเดอร์ที่ต้องการค้นหา แล้วสแกนเพื่อสร้างดัชนีใบหน้า', `<button class="button" data-action="add-source">${icon('plus')}เพิ่มอัลบั้ม</button>`) + '<div id="inline-job">'+inlineJob()+'</div>' +
    (state.sources.length ? `<div class="cards">${state.sources.map(s=>`<article class="panel album-card"><div style="display:flex;justify-content:space-between"><div class="album-icon">${icon(s.kind==='drive'?'drive':'folder')}</div><button class="icon-button" data-action="delete-source" data-id="${s.id}" aria-label="ลบอัลบั้ม ${E(s.name)}">${icon('trash')}</button></div><h3>${E(s.name)}</h3><span class="pill ${s.kind==='drive'?'blue':''}">${s.kind==='drive'?'Google Drive':'โฟลเดอร์ในเครื่อง'}</span><div class="album-meta"><span>${number(s.photo_count)} รูป</span><span>${s.error_count?number(s.error_count)+' รูปอ่านไม่ได้':'รวมโฟลเดอร์ย่อย'}</span></div><p class="path">${E(s.locator||'ไฟล์ทั้งหมดในขอบเขต Drive ที่เลือก')}</p><div class="card-actions"><button class="button small" data-action="scan-source" data-id="${s.id}" ${state.status?.busy?'disabled':''}>${icon('scan')}${s.last_scan?'สแกนการเปลี่ยนแปลง':'เริ่มสแกน'}</button><button class="button secondary small" data-action="issues" data-id="${s.id}">รายการที่ข้าม</button></div><p class="helper">ล่าสุด: ${date(s.last_scan)}</p></article>`).join('')}</div>` : `<section class="panel">${empty('ให้เราเริ่มจากอัลบั้มแรก', 'เชื่อมต่อ Google Drive หรือเลือกโฟลเดอร์รูปบนเครื่องนี้ ภาพทั้งหมดจะยังอยู่ที่เดิม', 'folder', '<button class="button" data-action="add-source">'+icon('plus')+'เพิ่มอัลบั้มรูป</button>')}</section>`);
}
function jobCards() {
  const jobs = state.status?.jobs || [];
  if (!jobs.length) return `<section class="panel">${empty('ยังไม่มีงานสแกน', 'เมื่อเริ่มสแกนอัลบั้ม คุณจะติดตามความคืบหน้าและดูผลการประมวลผลได้ที่นี่', 'activity', '<button class="button secondary" data-action="navigate" data-target="albums">เลือกอัลบั้ม</button>')}</section>`;
  const labels = {completed:'เสร็จแล้ว',running:'กำลังสแกน',queued:'รอเริ่ม',cancelling:'กำลังหยุด',cancelled:'หยุดแล้ว',failed:'ไม่สำเร็จ',interrupted:'หยุดเมื่อปิดโปรแกรม'};
  return '<div class="job-list">'+jobs.map(j=>`<article class="panel job-card"><div class="job-title"><strong>${E(j.source_name||'อัลบั้มที่ลบแล้ว')}</strong><span class="pill ${j.status==='failed'?'red':j.status==='running'?'blue':''}">${labels[j.status]||E(j.status)}</span></div><p>${E(j.phase)}${j.current_file?' · '+E(j.current_file):''}</p><div class="job-metrics"><span>พบ ${number(j.total)} รูป</span><span>ประมวลผล ${number(j.processed)}</span><span>ไม่เปลี่ยนแปลง ${number(j.skipped)}</span><span>อ่านไม่ได้ ${number(j.failed)}</span><span>ใบหน้า ${number(j.faces)}</span></div><div class="progress ${j.status==='running'&&!j.processed?'indeterminate':''}"><span style="width:${j.status==='completed'?100:j.total?Math.min(100,(j.processed+j.skipped)/j.total*100):0}%"></span></div>${j.error?`<div class="notice error" style="margin-top:15px">${E(j.error)}</div>`:''}<div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px"><small class="muted">${date(j.created)}</small>${['running','queued'].includes(j.status)?`<button class="button secondary small" data-action="cancel-job" data-id="${j.id}">หยุดสแกน</button>`:''}</div></article>`).join('')+'</div>';
}
function renderActivity() { return pageHead('ประวัติการสแกน', 'ติดตามการประมวลผลภาพ งานที่หยุดสามารถสแกนต่อได้โดยไม่ประมวลผลภาพเดิมซ้ำ') + '<div id="job-list">'+jobCards()+'</div>'; }
function renderLegacySettings() {
  const s = state.status || {};
  return pageHead('ตั้งค่าให้พร้อมค้นหา', 'เชื่อมต่อแหล่งภาพและเตรียมโมเดลบนเครื่องของคุณ') + `<div class="settings-grid"><div class="settings-stack"><section class="panel"><div class="panel-header"><h2>${icon('drive')}Google Drive</h2><span class="pill ${s.google_connected?'':'amber'}">${s.google_connected?'เชื่อมต่อแล้ว':'ยังไม่เชื่อมต่อ'}</span></div><div class="panel-body">${s.google_connected?`<div class="setting-line"><div><strong>${E(s.google_user?.displayName||'บัญชี Google ของคุณ')}</strong><p>${E(s.google_user?.emailAddress||'สิทธิ์อ่านไฟล์เท่านั้น')}</p></div><button class="button secondary small" data-action="disconnect">ยกเลิกการเชื่อมต่อ</button></div>`:`<p class="small-copy">อนุญาตให้ FindFace อ่านรูปใน Google Drive ของคุณ โดยไม่แก้ไขหรือลบไฟล์ต้นฉบับ</p><ol class="instruction-list"><li>เปิด <a href="https://console.cloud.google.com/apis/library/drive.googleapis.com" target="_blank" rel="noopener noreferrer">Google Cloud Console ${icon('link')}</a> สร้างโปรเจกต์และเปิด Google Drive API</li><li>ตั้งค่า OAuth consent screen เพิ่ม scope <code>drive.readonly</code> และเพิ่มอีเมลของคุณเป็น Test user</li><li>สร้าง OAuth client ชนิด <strong>Web application</strong> แล้วเพิ่ม Redirect URI นี้<div class="code-line"><code id="callback-url">${E(s.callback_url||'http://127.0.0.1:8765/api/google/callback')}</code><button class="icon-button" data-action="copy-callback" aria-label="คัดลอก Redirect URI">${icon('copy')}</button></div></li><li>ดาวน์โหลดไฟล์ Client JSON แล้วเลือกไฟล์ด้านล่าง</li></ol><label class="button secondary oauth-upload" for="oauth-file">${icon('upload')}เลือกไฟล์ OAuth JSON<input type="file" accept=".json,application/json" id="oauth-file" class="sr-only"></label><p class="small-copy">${s.google_configured?'บันทึกข้อมูล OAuth แล้ว พร้อมเชื่อมต่อบัญชี':'Client secret จะถูกเข้ารหัสและเก็บไว้บนเครื่องนี้'}</p><button class="button full" style="margin-top:18px" data-action="connect" ${s.google_configured?'':'disabled'}>${icon('drive')}เชื่อมต่อ Google Drive</button>`}</div></section><section class="panel"><div class="panel-header"><h2>${icon('folder')}เริ่มด้วยรูปบนเครื่อง</h2></div><div class="panel-body"><p class="small-copy">คุณสามารถค้นหารูปจากโฟลเดอร์ในเครื่องได้ทันที โดยไม่ต้องตั้งค่าบัญชี Google</p><button class="button secondary" style="margin-top:17px" data-action="add-local">${icon('plus')}เลือกโฟลเดอร์รูป</button></div></section></div><div class="settings-stack"><section class="panel"><div class="panel-header"><h2>${icon('scan')}โมเดลใบหน้า</h2><span class="pill ${s.model_ready?'':'amber'}" id="model-pill">${s.model_ready?'พร้อมใช้งาน':'ยังไม่ได้ติดตั้ง'}</span></div><div class="panel-body"><div class="status-row"><span>โมเดล</span><strong>ArcFace · InsightFace</strong></div><div class="status-row"><span>เวกเตอร์</span><strong>512 มิติ</strong></div><div class="status-row"><span>ประมวลผล</span><strong>CPU บนเครื่องนี้</strong></div><div class="status-row"><span>ดัชนีค้นหา</span><strong>FAISS · Exact cosine</strong></div><div id="model-install-box">${modelInstallContent()}</div><p class="helper">โมเดล ${E(s.model_name||"buffalo_sc")} ที่แจกโดย InsightFace ใช้สำหรับการวิจัยที่ไม่ใช่เชิงพาณิชย์ หากใช้เชิงพาณิชย์ต้องมีสิทธิ์ใช้งาน weights ที่เหมาะสม</p><a class="small-copy" style="text-decoration:underline" href="https://github.com/deepinsight/insightface/tree/master/python-package" target="_blank" rel="noopener noreferrer">อ่านเงื่อนไขของโมเดล ${icon('link')}</a></div></section><section class="panel"><div class="panel-header"><h2>${icon('shield')}พื้นที่ส่วนตัวของคุณ</h2></div><div class="panel-body"><p class="small-copy">ภาพอ้างอิงใช้ชั่วคราวในหน่วยความจำ เวกเตอร์และ Google tokens ถูกเข้ารหัสก่อนบันทึก ภาพในอัลบั้มแสดงจากตำแหน่งต้นฉบับ</p><p class="small-copy" style="margin-top:12px">การสแกนจะเก็บเวกเตอร์ของทุกใบหน้าในอัลบั้ม รวมถึงคนอื่นในภาพ เลือกเฉพาะอัลบั้มที่คุณมีสิทธิ์ประมวลผล และลบอัลบั้มเพื่อถอนข้อมูลออกจากดัชนีได้ทุกเมื่อ</p><div class="privacy-note">${icon('lock')}<span>ใช้เฉพาะบนเครื่องนี้ · ไม่เปิดรับการเชื่อมต่อจากเครือข่ายภายนอก</span></div></div></section></div></div>`;
}
function renderSettings() {
  const s=state.status;
  if(!s?.server)return renderLegacySettings();
  const google=s.google_connected?`<strong>${E(s.google_user?.displayName||'บัญชี Google ของคุณ')}</strong><p>${E(s.google_user?.emailAddress||'')}</p><button class="button secondary" data-action="disconnect">ยกเลิกการเชื่อมต่อ</button>`:`<p>เชื่อมต่อ Google Drive ของคุณเพื่อเลือกอัลบั้มและเริ่มค้นหารูป</p><button class="button" data-action="connect" ${s.google_configured?'':'disabled'}>เชื่อมต่อ Google Drive</button>${!s.google_configured?'<p class="helper">รอเจ้าของเซิร์ฟเวอร์ตั้งค่า Google OAuth</p>':''}`;
  const admin=s.user?.admin?`<section class="panel"><div class="panel-body"><h2>จัดการเซิร์ฟเวอร์</h2><p>เชิญผู้ใช้ด้วยลิงก์ใช้ครั้งเดียว มีอายุ 24 ชั่วโมง</p><button class="button" data-action="invite-user" ${s.public_url?'':'disabled'}>สร้างลิงก์เชิญ</button><p class="helper">ลิงก์เข้าเว็บ: ${s.public_url?`<a href="${E(s.public_url)}" target="_blank" rel="noopener noreferrer">${E(s.public_url)}</a>`:'กำลังเตรียมลิงก์ภายนอก'}</p><h3>การเชื่อมต่อ Google</h3><p class="helper">เพิ่ม Redirect URI ด้านล่างใน OAuth Client เดิม และเพิ่มอีเมลผู้ใช้ใน Test users หากแอปยังอยู่ในโหมด Testing</p><div class="code-line"><code>${E(s.public_url?s.public_url+'/api/google/callback':s.callback_url)}</code></div><label class="button secondary oauth-upload" for="oauth-file">เปลี่ยนไฟล์ OAuth JSON<input type="file" accept=".json" id="oauth-file" class="sr-only"></label><p class="helper">${s.server_google_configured?'ตั้งค่า Web OAuth แล้ว':'เลือกไฟล์ OAuth ชนิด Web application เพื่อให้สมาชิกเชื่อมต่อ Drive'}</p><h3>รูปบนเครื่องเซิร์ฟเวอร์</h3><button class="button secondary" data-action="add-local">เลือกโฟลเดอร์รูป</button></div></section>`:'';
  return pageHead('บัญชีและการเชื่อมต่อ','ข้อมูลและ Google Drive ของแต่ละบัญชีแยกกัน')+`<div class="settings-grid"><div class="settings-stack"><section class="panel"><div class="panel-header"><h2>Google Drive ของคุณ</h2></div><div class="panel-body">${google}</div></section>${admin}</div><div class="settings-stack"><section class="panel"><div class="panel-body"><h2>บัญชี ${E(s.user?.username)}</h2><p>ภาพถูกอ่านจาก Google Drive มาประมวลผลในหน่วยความจำบนเซิร์ฟเวอร์ เก็บเฉพาะข้อมูลดัชนีและเวกเตอร์ใบหน้า</p><p>ลบอัลบั้มเพื่อถอนข้อมูลออกจากดัชนีได้ทุกเมื่อ การลบไม่กระทบไฟล์ต้นฉบับ</p><button class="button secondary" data-action="logout">ออกจากระบบ</button></div></section><section class="panel"><div class="panel-body"><h2>ระบบประมวลผล</h2><p>ArcFace · เวกเตอร์ 512 มิติ · FAISS</p><p>งานสแกนเข้าคิวและประมวลผลทีละงานบนเซิร์ฟเวอร์</p><div id="model-install-box">${modelInstallContent()}</div></div></section></div></div>`;
}
function modelInstallContent() {
  const s = state.status;
  if (s?.model_ready) return '<p class="notice" style="margin-top:17px;margin-bottom:0">โมเดลพร้อมสำหรับลงทะเบียนและสแกนภาพ</p>';
  if(s?.server&&!s.user?.admin)return '<p class="notice">รอผู้ดูแลติดตั้งโมเดล</p>';
  const install = s?.model_install;
  if (install?.status==='downloading') return `<p class="small-copy" style="margin-top:15px">${E(install.message)} ${install.progress}%</p><div class="progress"><span style="width:${install.progress}%"></span></div>`;
  return `${install?.status==='error'?`<p class="notice error" style="margin-top:12px">${E(install.message)}</p>`:''}<button class="button full" data-action="install-model" style="margin-top:20px">${icon('download')}ติดตั้งโมเดล · ${s?.model_name==="buffalo_l"?"281":"15"} MB</button>`;
}
function render() {
  if (!state.status) { $('#page').innerHTML='<div class="loading-box"><span class="spinner"></span>กำลังเปิดพื้นที่ทำงาน…</div>'; return; }
  const view = ({search:renderSearch,profiles:renderProfiles,albums:renderAlbums,activity:renderActivity,settings:renderSettings})[state.view];
  $('#page').innerHTML=view();
  if(state.status.server){
    $('#account-controls').innerHTML=`<span>${E(state.status.user?.username)}</span><button class="button secondary small" data-action="logout">ออกจากระบบ</button>`;
    $('.local-indicator').textContent='เซิร์ฟเวอร์ส่วนตัว';
    $('.sidebar-bottom p').innerHTML='แยกข้อมูลตามบัญชี<br>เก็บเฉพาะเวกเตอร์ใบหน้า';
    $('.local-label').textContent='PRIVATE ACCOUNT';
  } $('#breadcrumb-current').textContent=titles[state.view];
  $$('nav [data-view]').forEach(a=>{a.classList.toggle('active',a.dataset.view===state.view);if(a.dataset.view===state.view)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('#nav-profiles').textContent=state.profiles.length;
  $('#header-drive').innerHTML=icon('drive')+(state.status.google_connected?'Drive เชื่อมต่อแล้ว':'เชื่อมต่อ Google Drive');
  $('#header-drive').dataset.action=state.status.google_connected?'settings':'connect';
}
function navigate(view) {
  if (!(view in titles)) view='search';
  if (location.hash !== '#'+view) location.hash=view;
  state.view=view; render();
}
async function refreshData() {
  const [profiles,sources,status] = await Promise.all([api('/profiles'),api('/sources'),api('/status')]);
  state.profiles=profiles;state.sources=sources;state.status=status;state.csrf=status.csrf;
  if (!profiles.some(p=>p.id===state.selectedProfile)) state.selectedProfile=profiles[0]?.id||'';
  if (!sources.some(s=>s.id===state.selectedSource)) state.selectedSource='';
}
async function runSearch(reset=true) {
  if (!state.selectedProfile) { toast('เพิ่มใบหน้าอ้างอิงก่อนเริ่มค้นหา',true); return; }
  if (reset) state.offset=0;
  const sequence=++searchSequence;
  state.searching=true;
  if ($('#results')) $('#results').innerHTML=resultsContent();
  try {
    const query=new URLSearchParams({profile_id:state.selectedProfile,threshold:state.threshold,source_id:state.selectedSource,mode:state.mode,offset:state.offset});
    const result=await api('/search?'+query);
    if (sequence===searchSequence) {
      state.results=result;state.offset=result.offset;
      query.delete('offset');state.resultQuery=Object.fromEntries(query);
    }
  } finally {
    if (sequence===searchSequence) {
      state.searching=false;
      if ($('#results')) $('#results').innerHTML=resultsContent();
      if ($('#result-count')) $('#result-count').textContent=number(state.results?.total);
    }
  }
}

function addProfile() {
  if (!state.status.model_ready) { toast('ติดตั้งโมเดลก่อนเพิ่มใบหน้าอ้างอิง'); navigate('settings'); return; }
  openModal(`<form id="profile-form" class="modal-content">${modalHeader('เพิ่มใบหน้าอ้างอิง')}<p>ใช้ภาพบุคคลเดียวกัน 3–5 ภาพ มีใบหน้าเดียวในแต่ละภาพ</p><label for="profile-name">ชื่อโปรไฟล์</label><input class="input" id="profile-name" maxlength="80" placeholder="เช่น ฉัน หรือชื่อของคุณ" required autofocus><label for="reference-files" class="dropzone" id="reference-drop">${icon('upload')}<strong>เลือกภาพ หรือลากรูปมาวางที่นี่</strong><small>หน้าตรง · หันซ้าย · หันขวา · สีหน้าต่างกัน</small><small>JPEG, PNG, WebP · ไม่เกิน 8 MB ต่อภาพ</small><input id="reference-files" class="sr-only" type="file" accept="image/jpeg,image/png,image/webp" multiple></label><div class="reference-previews" id="reference-previews"></div><div class="ref-counter" id="ref-counter">เลือกแล้ว 0 / 5 ภาพ</div><div class="privacy-note">${icon('shield')}<span>ภาพจะไม่ถูกบันทึกลงฐานข้อมูล ใช้สร้างเวกเตอร์แล้วปล่อยออกจากหน่วยความจำ</span></div><div class="modal-actions"><button type="button" class="button secondary" data-action="close-modal">ยกเลิก</button><button type="submit" class="button" id="save-profile">${icon('scan')}สร้างโปรไฟล์</button></div></form>`);
  $('#profile-form').addEventListener('submit',event=>{event.preventDefault();busyButton($('#save-profile'),saveProfile,'กำลังวิเคราะห์ใบหน้า…');});
  const drop=$('#reference-drop');
  drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('dragover');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));
  drop.addEventListener('drop',event=>{event.preventDefault();drop.classList.remove('dragover');addReferenceFiles(event.dataTransfer.files);});
}
function addReferenceFiles(files) {
  for(const file of files) {
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)){toast('รองรับ JPEG, PNG และ WebP สำหรับภาพอ้างอิง',true);continue;}
    if(file.size>8*1024*1024){toast(file.name+': ขนาดเกิน 8 MB',true);continue;}
    if(state.uploadFiles.length>=5){toast('เลือกได้สูงสุด 5 ภาพ',true);break;}
    if(state.uploadFiles.some(f=>f.name===file.name&&f.size===file.size&&f.lastModified===file.lastModified))continue;
    state.uploadFiles.push(file);state.uploadUrls.push(URL.createObjectURL(file));
  }
  renderReferencePreviews();
}
function renderReferencePreviews(){
  $('#reference-previews').innerHTML=state.uploadFiles.map((file,i)=>`<div class="ref-preview"><img src="${state.uploadUrls[i]}" alt="${E(file.name)}"><button type="button" data-action="remove-reference" data-index="${i}" aria-label="นำภาพ ${E(file.name)} ออก">×</button></div>`).join('');
  $('#ref-counter').textContent=`เลือกแล้ว ${state.uploadFiles.length} / 5 ภาพ${state.uploadFiles.length<3?' · ต้องมีอย่างน้อย 3 ภาพ':''}`;
}
function fileBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('อ่านไฟล์ไม่ได้'));reader.readAsDataURL(file);});}
async function saveProfile(){
  if(state.uploadFiles.length<3)throw new Error('กรุณาเลือกภาพอ้างอิงอย่างน้อย 3 ภาพ');
  const name=$('#profile-name').value.trim();if(!name)throw new Error('กรุณาระบุชื่อโปรไฟล์');
  const images=[];for(const file of state.uploadFiles)images.push({name:file.name,data:await fileBase64(file)});
  const profile=await api('/profiles',{method:'POST',body:{name,images}});
  state.selectedProfile=profile.id;state.results=null;closeModal();await refreshData();render();toast(`สร้างโปรไฟล์แล้ว ใช้ภาพอ้างอิง ${profile.reference_count} ภาพ${profile.skipped_images?.length?` · ข้าม ${profile.skipped_images.length} ภาพ`:''}`);
}

function addSource(kind){
  state.sourceKind=state.status.server&&!state.status.user?.admin?'drive':kind || (state.status.google_connected?'drive':'local');state.folderTrail=[{id:'root',name:'My Drive'}];state.folderDrive='';
  openModal(`<div class="modal-content">${modalHeader('เพิ่มอัลบั้มรูป')}<p>เลือกแหล่งภาพที่ต้องการสแกน รวมถึงโฟลเดอร์ย่อย</p><div class="source-tabs"><button class="source-tab ${state.sourceKind==='local'?'active':''}" data-action="source-tab" data-kind="local">${icon('folder')} ในเครื่องนี้</button><button class="source-tab ${state.sourceKind==='drive'?'active':''}" data-action="source-tab" data-kind="drive">${icon('drive')} Google Drive</button></div><form id="source-form"><label for="source-name">ชื่ออัลบั้ม</label><input class="input" id="source-name" maxlength="100" placeholder="เช่น ทริปเชียงใหม่" required><div id="source-fields"></div><div class="modal-actions"><button type="button" class="button secondary" data-action="close-modal">ยกเลิก</button><button class="button" type="submit" id="save-source">เพิ่มอัลบั้ม</button></div></form></div>`);
  if(state.status.server&&!state.status.user?.admin)$('[data-kind="local"]').remove();
  renderSourceFields();$('#source-form').addEventListener('submit',event=>{event.preventDefault();busyButton($('#save-source'),saveSource);});
}
async function renderSourceFields(){
  $$('.source-tab').forEach(b=>b.classList.toggle('active',b.dataset.kind===state.sourceKind));
  if(state.sourceKind==='local'){
    $('#source-fields').innerHTML='<label for="local-path">พาธโฟลเดอร์รูปบนเครื่อง</label><input class="input" id="local-path" placeholder="C:\\Users\\ชื่อผู้ใช้\\Pictures\\ทริปเชียงใหม่" required><p class="helper">เปิดโฟลเดอร์ใน File Explorer คลิกแถบที่อยู่ด้านบน แล้วคัดลอกพาธมาวาง ภาพต้นฉบับจะยังอยู่ในโฟลเดอร์นี้</p>';$('#save-source').disabled=false;return;
  }
  if(!state.status.google_connected){$('#source-fields').innerHTML='<div class="notice warning" style="margin-top:17px">เชื่อมต่อ Google Drive ในหน้าตั้งค่าก่อนเพิ่มอัลบั้ม</div><button type="button" class="button secondary" data-action="setup-google">ตั้งค่าการเชื่อมต่อ</button>';$('#save-source').disabled=true;return;}
  $('#save-source').disabled=false;
  $('#source-fields').innerHTML='<label for="drive-select">Drive</label><select id="drive-select"><option value="">My Drive และไฟล์ที่แชร์กับฉัน</option></select><label class="check-label"><input type="checkbox" id="whole-drive">สแกนไฟล์ภาพทั้งหมดใน Drive ที่เลือก</label><div id="folder-browser"><div id="folder-trail" class="folder-trail"></div><div id="folder-list" class="folder-list"></div><button type="button" class="button ghost small hidden" id="folders-more" data-action="more-folders">โหลดโฟลเดอร์เพิ่มเติม</button></div><label for="folder-id">หรือวางลิงก์ / Folder ID โดยตรง</label><input class="input" id="folder-id" placeholder="https://drive.google.com/drive/folders/…"><p class="helper">โฟลเดอร์ที่เลือกด้านบนจะถูกสแกนพร้อมโฟลเดอร์ย่อย ไม่ติดตาม shortcuts</p>';
  try{const drives=await api('/google/drives');if($('#drive-select'))$('#drive-select').innerHTML+=drives.map(d=>`<option value="${E(d.id)}">${E(d.name)}</option>`).join('');await loadFolders();}catch(error){errorInModal(error);}
}

async function loadFolders(pageToken=''){
  if(!$('#folder-list'))return;
  const parent=state.folderTrail.at(-1);
  $('#folder-trail').innerHTML=state.folderTrail.map((f,i)=>`<button type="button" data-action="folder-back" data-index="${i}">${E(f.name)}</button>`).join('<span>/</span>');
  if(!pageToken)$('#folder-list').innerHTML='<div class="loading-box" style="padding:25px"><span class="spinner"></span>กำลังอ่านโฟลเดอร์…</div>';
  const params=new URLSearchParams({parent:parent.id,drive_id:state.folderDrive,page_token:pageToken});
  const data=await api('/google/folders?'+params);
  if(!$('#folder-list'))return;
  const html=data.files.map(f=>`<button type="button" class="folder-row" data-action="folder-open" data-id="${E(f.id)}" data-name="${E(f.name)}"><span>${icon('folder')}${E(f.name)}</span>${icon('chevron')}</button>`).join('');
  if(pageToken)$('#folder-list').insertAdjacentHTML('beforeend',html);else $('#folder-list').innerHTML=html||'<p class="small-copy" style="padding:17px">ไม่มีโฟลเดอร์ย่อย เลือกโฟลเดอร์ปัจจุบันได้เลย</p>';
  $('#folders-more').classList.toggle('hidden',!data.nextPageToken);$('#folders-more').dataset.token=data.nextPageToken||'';
}
async function saveSource(){
  const name=$('#source-name').value.trim();if(!name)throw new Error('กรุณาตั้งชื่ออัลบั้ม');
  let locator='',drive_id='';
  if(state.sourceKind==='local')locator=$('#local-path').value.trim();
  else{
    drive_id=state.folderDrive;
    if(!$('#whole-drive').checked){
      locator=$('#folder-id').value.trim();
      if(locator.startsWith('http')){try{const url=new URL(locator);if(url.hostname!=='drive.google.com')throw new Error();locator=url.pathname.match(/\/folders\/([\w-]+)/)?.[1]||url.searchParams.get('id')||'';if(!locator)throw new Error();}catch{throw new Error('ลิงก์โฟลเดอร์ Google Drive ไม่ถูกต้อง');}}
      if(!locator)locator=state.folderTrail.at(-1).id;
    }
  }
  const source=await api('/sources',{method:'POST',body:{name,kind:state.sourceKind,locator,drive_id}});
  closeModal();await refreshData();navigate('albums');toast('เพิ่มอัลบั้มแล้ว กดเริ่มสแกนเพื่อค้นหาใบหน้า');return source;
}

function openPhoto(index){
  const photo=state.results?.items[index];if(!photo)return;
  openModal(`<div class="photo-detail"><div class="photo-view"><div class="photo-image-wrap"><img id="detail-image" src="/api/files/${photo.file_id}/preview" alt="${E(photo.name)}"><div id="face-boxes"></div></div></div><aside class="photo-detail-side"><div style="display:flex;justify-content:space-between;align-items:center"><span class="pill">ผลการค้นหา</span><button class="icon-button" data-action="close-modal" aria-label="ปิด">${icon('close')}</button></div><h3 id="modal-title">${E(photo.name)}</h3><p>${E(photo.source_name)}</p><div id="detail-face"></div><button class="button secondary small" style="margin:12px 0" data-action="download-photo">${icon('download')}ดาวน์โหลดรูปต้นฉบับ</button>${photo.drive_url?`<a class="button secondary small" style="margin-top:auto" href="${E(photo.drive_url)}" target="_blank" rel="noopener noreferrer">${icon('link')}เปิดใน Google Drive</a>`:''}</aside></div>`,true);
  state.detail=photo;state.detailFace=0;renderDetailFace();
}
async function downloadPhoto(){
  const photo=state.detail;if(!photo)return;
  const response=await fetch('/api/files/'+encodeURIComponent(photo.file_id)+'/download');
  if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(error.detail||'ดาวน์โหลดรูปไม่ได้ กรุณาลองใหม่');}
  const url=URL.createObjectURL(await response.blob());
  const link=document.createElement('a');link.href=url;link.download=photo.name;document.body.appendChild(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),60000);
  toast('ส่งรูปต้นฉบับไปยังรายการดาวน์โหลดแล้ว');
}
function renderDetailFace(){
  const photo=state.detail;if(!photo)return;const face=photo.faces[state.detailFace];
  $('#face-boxes').innerHTML=photo.faces.map((f,i)=>`<button class="face-box ${i===state.detailFace?'selected':''}" data-action="select-face" data-index="${i}" aria-label="เลือกใบหน้า ${i+1}" style="left:${f.bbox[0]*100}%;top:${f.bbox[1]*100}%;width:${(f.bbox[2]-f.bbox[0])*100}%;height:${(f.bbox[3]-f.bbox[1])*100}%"><span>${i+1} · ${f.similarity.toFixed(3)}</span></button>`).join('');
  $('#detail-face').innerHTML=`<div class="face-options">${photo.faces.map((f,i)=>`<button data-action="select-face" data-index="${i}" class="${i===state.detailFace?'active':''}">ใบหน้า ${i+1}</button>`).join('')}</div><div class="detail-score"><small>คะแนนความคล้าย</small><strong>${face.similarity.toFixed(3)}</strong><small>${face.state==='rejected'?'คุณระบุว่าไม่ใช่บุคคลนี้':face.state==='confirmed'?'คุณยืนยันใบหน้านี้แล้ว':face.state==='review'?'ควรตรวจสอบก่อนยืนยัน':'ระบบพบใบหน้าที่คล้ายกัน'}</small></div><h3>ใช่คุณในกรอบนี้ไหม?</h3><p>คำตอบช่วยปรับผลค้นหาของโปรไฟล์นี้</p><label class="check-label"><input type="checkbox" id="learn-face">เพิ่มใบหน้านี้เป็นภาพอ้างอิงด้วย</label><div class="detail-buttons"><button class="button" data-action="feedback" data-label="yes">${icon('check')}ใช่ คนนี้</button><button class="button secondary" data-action="feedback" data-label="no">${icon('close')}ไม่ใช่คนนี้</button>${['confirmed','rejected'].includes(face.state)?'<button class="button ghost small" data-action="feedback" data-label="clear">ยกเลิกการยืนยัน</button>':''}</div><p class="helper">คะแนนเป็น cosine similarity ไม่ใช่เปอร์เซ็นต์ความมั่นใจ ไม่ควรใช้ผลค้นหาเป็นหลักฐานยืนยันตัวบุคคลเพียงอย่างเดียว</p>`;
}
async function submitFeedback(label){
  const photo=state.detail,face=photo.faces[state.detailFace];
  const learn=label==='yes'&&$('#learn-face').checked;
  await api('/feedback',{method:'POST',body:{profile_id:state.selectedProfile,face_id:face.id,label,learn}});
  if(label==='no'){photo.faces.splice(state.detailFace,1);state.detailFace=0;if(!photo.faces.length)closeModal();else renderDetailFace();}
  else{face.state=label==='yes'?'confirmed':face.similarity>=0.7?'match':'review';renderDetailFace();}
  await refreshData();await runSearch(false);toast(label==='yes'?(learn?'ยืนยันและเพิ่มเวกเตอร์อ้างอิงแล้ว':'ยืนยันใบหน้าแล้ว'):label==='no'?'นำใบหน้านี้ออกจากผลค้นหาแล้ว':'ยกเลิกการยืนยันแล้ว');
}
async function connectGoogle(){
  if(!state.status.google_configured){closeModal();navigate('settings');toast('ตั้งค่า Google OAuth ก่อนเชื่อมต่อบัญชี');return;}
  const {url}=await api('/google/connect',{method:'POST'});location.assign(url);
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  const action=button.dataset.action;
  if(button.closest('form')&&button.type==='submit'&&!['close-modal'].includes(action))return;
  event.preventDefault();
  if(action==='close-modal'){closeModal();return;}
  if(action==='navigate'){navigate(button.dataset.target);return;}
  if(action==='settings'){navigate('settings');return;}
  if(action==='add-profile'){addProfile();return;}
  if(action==='add-source'||action==='add-local'){addSource(action==='add-local'?'local':undefined);return;}
  if(action==='open-photo'){openPhoto(Number(button.dataset.index));return;}
  if(action==='select-face'){state.detailFace=Number(button.dataset.index);renderDetailFace();return;}
  if(action==='remove-reference'){const i=Number(button.dataset.index);URL.revokeObjectURL(state.uploadUrls[i]);state.uploadUrls.splice(i,1);state.uploadFiles.splice(i,1);renderReferencePreviews();return;}
  if(action==='setup-google'){closeModal();navigate('settings');return;}
  await busyButton(button,async()=>{
    switch(action){
      case 'connect':await connectGoogle();break;
      case 'search':await runSearch();break;
      case 'filter':state.mode=button.dataset.mode;$$('.tab').forEach(b=>b.classList.toggle('active',b.dataset.mode===state.mode));if(state.results)await runSearch();break;
      case 'first-page':state.offset=0;await runSearch(false);break;
      case 'last-page':state.offset=Math.max(0,(Math.ceil(state.results.total/(state.results.limit||24))-1)*(state.results.limit||24));await runSearch(false);break;
      case 'next-page':state.offset+=(state.results.limit||24);await runSearch(false);break;
      case 'previous-page':state.offset=Math.max(0,state.offset-(state.results.limit||24));await runSearch(false);break;
      case 'download-photo':await downloadPhoto();break;
      case 'search-profile':state.selectedProfile=button.dataset.id;state.results=null;navigate('search');await runSearch();break;
      case 'delete-profile':if(await confirmAction('ลบโปรไฟล์นี้พร้อมเวกเตอร์อ้างอิงและผลยืนยันทั้งหมด? ภาพต้นฉบับไม่ถูกลบ','ลบโปรไฟล์')){await api('/profiles/'+button.dataset.id,{method:'DELETE'});state.results=null;await refreshData();render();toast('ลบโปรไฟล์แล้ว');}break;
      case 'delete-source':if(await confirmAction('นำอัลบั้มนี้และเวกเตอร์ใบหน้าทั้งหมดออกจากระบบ? ภาพต้นฉบับยังอยู่ที่เดิม','นำอัลบั้มออก')){await api('/sources/'+button.dataset.id,{method:'DELETE'});state.results=null;await refreshData();render();toast('นำอัลบั้มออกแล้ว');}break;
      case 'scan-source':await api('/sources/'+button.dataset.id+'/scan',{method:'POST'});await refreshData();render();toast('เริ่มสแกนแล้ว คุณยังใช้งานหน้าอื่นได้');break;
      case 'cancel-job':await api('/jobs/'+button.dataset.id+'/cancel',{method:'POST'});await refreshData();render();break;
      case 'install-model':await api('/model/install',{method:'POST'});await refreshData();render();toast('เริ่มติดตั้งโมเดลแล้ว');break;
      case 'copy-callback':await navigator.clipboard.writeText(state.status.callback_url);toast('คัดลอก Redirect URI แล้ว');break;
      case 'logout':await api('/auth/logout',{method:'POST'});location.replace('/login');break;
      case 'invite-user':{const invite=await api('/auth/invites',{method:'POST'});openModal(`<div class="modal-content">${modalHeader('เชิญเข้า FindFace')}<p>ส่งลิงก์นี้ให้ผู้ที่ต้องการเชิญ ใช้สร้างบัญชีได้ครั้งเดียวภายใน 24 ชั่วโมง</p><div class="invite-link">${E(invite.url)}</div><button class="button" id="copy-invite">คัดลอกลิงก์</button></div>`);$('#copy-invite').onclick=async()=>{await navigator.clipboard.writeText(invite.url);toast('คัดลอกลิงก์เชิญแล้ว');};break;}
      case 'disconnect':if(await confirmAction('ยกเลิกการเชื่อมต่อและลบดัชนีอัลบั้ม Google Drive ทั้งหมด? ไฟล์ใน Drive ไม่ถูกลบ','ยกเลิกการเชื่อมต่อ')){await api('/google/disconnect',{method:'POST'});state.results=null;await refreshData();render();toast('ยกเลิกการเชื่อมต่อแล้ว');}break;
      case 'source-tab':state.sourceKind=button.dataset.kind;await renderSourceFields();break;
      case 'folder-open':state.folderTrail.push({id:button.dataset.id,name:button.dataset.name});await loadFolders();break;
      case 'folder-back':state.folderTrail=state.folderTrail.slice(0,Number(button.dataset.index)+1);await loadFolders();break;
      case 'more-folders':await loadFolders(button.dataset.token);break;
      case 'feedback':await submitFeedback(button.dataset.label);break;
      case 'issues':{const items=await api('/files/issues?source_id='+button.dataset.id);openModal(`<div class="modal-content">${modalHeader('ภาพที่อ่านไม่ได้หรือไม่พบใบหน้า')}<p>แสดง 100 รายการล่าสุด ไม่ได้นับเป็นผลที่ไม่ตรงกับบุคคล</p>${items.length?items.map(i=>`<div class="issue-row">${E(i.name)}<small>${E(i.reason||'ไม่พบใบหน้าที่ผ่านเกณฑ์คุณภาพ')}</small></div>`).join(''):'<p class="notice">ยังไม่มีรายการที่ต้องตรวจสอบ</p>'}</div>`);break;}
    }
  });
});

document.addEventListener('change',async event=>{
  const element=event.target;
  try{
    if(element.id==='reference-files')addReferenceFiles(element.files);
    if(element.id==='source-select'){state.selectedSource=element.value;state.results=null;if($('#results'))$('#results').innerHTML=resultsContent();$('#result-count').textContent='0';}
    if(element.id==='profile-select'){state.selectedProfile=element.value;state.results=null;render();}
    if(element.id==='oauth-file'){
      const file=element.files[0];if(!file)return;if(file.size>20000)throw new Error('ไฟล์ OAuth JSON มีขนาดใหญ่ผิดปกติ');
      await api(state.status.server?'/admin/google/config':'/google/config',{method:'POST',body:{credentials:await file.text()}});await refreshData();render();toast('บันทึก OAuth แล้ว กดเชื่อมต่อ Google Drive ได้เลย');
    }
    if(element.id==='drive-select'){state.folderDrive=element.value;state.folderTrail=[{id:element.value||'root',name:element.selectedOptions[0].text}];await loadFolders();}
    if(element.id==='whole-drive'){$('#folder-browser').classList.toggle('hidden',element.checked);$('#folder-id').disabled=element.checked;}
  }catch(error){$('#modal').open?errorInModal(error):toast(error.message,true);}
});
document.addEventListener('input',event=>{if(event.target.id==='threshold'){state.threshold=Number(event.target.value);$('#threshold-output').textContent=state.threshold.toFixed(2);}});
document.addEventListener('error',event=>{
  const img=event.target;
  if(img instanceof HTMLImageElement&&img.src.includes('/api/files/')){
    img.style.display='none';const message=document.createElement('div');message.className='image-error';message.textContent='เปิดภาพต้นฉบับไม่ได้ กรุณาตรวจตำแหน่งไฟล์หรือสิทธิ์ Drive';img.parentElement.append(message);
  }
},true);
$('#modal').addEventListener('cancel',()=>{state.uploadUrls.forEach(URL.revokeObjectURL);state.uploadUrls=[];state.uploadFiles=[];state.detail=null;});
window.addEventListener('hashchange',()=>{state.view=location.hash.slice(1) in titles?location.hash.slice(1):'search';render();});

let polling=false;
async function poll(){
  if(polling||document.hidden)return;polling=true;
  try{
    const previous=state.status;
    const status=await api('/status');state.status=status;state.csrf=status.csrf;
    $('#connection-error').classList.add('hidden');
    $$('[data-stat]').forEach(node=>node.textContent=number(status.stats[node.dataset.stat]));
    if($('#inline-job'))$('#inline-job').innerHTML=inlineJob();
    if($('#job-list'))$('#job-list').innerHTML=jobCards();
    if($('#model-install-box'))$('#model-install-box').innerHTML=modelInstallContent();
    if($('#model-pill')){$('#model-pill').textContent=status.model_ready?'พร้อมใช้งาน':'ยังไม่ได้ติดตั้ง';$('#model-pill').classList.toggle('amber',!status.model_ready);}
    const changed=previous&&(previous.busy!==status.busy||previous.stats.photos!==status.stats.photos||previous.model_ready!==status.model_ready||previous.public_url!==status.public_url);
    if(changed){await refreshData();if(['albums','profiles','settings'].includes(state.view))render();if(previous.busy&&!status.busy)toast(status.jobs[0]?.status==='completed'?'สแกนเสร็จแล้ว พร้อมค้นหารูป':'งานสแกนหยุดแล้ว ดูรายละเอียดในประวัติ');}
  }catch(error){$('#connection-error').textContent=error.message+' หากปิดโปรแกรมไปแล้ว ให้เปิด FindFace ใหม่';$('#connection-error').classList.remove('hidden');}
  finally{polling=false;}
}

function registerAgentTools(){
  if(!document.modelContext?.registerTool)return;
  const controller=new AbortController();
  window.addEventListener('pagehide',()=>controller.abort(),{once:true});
  const tools=[{
    name:'get_findface_workspace',title:'ดูสถานะ FindFace',description:'Read local scan status and registered profiles. Does not start scans or reveal biometric vectors.',
    inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},
    async execute(input){if(!input||Object.keys(input).length)throw new Error('Expected empty object');await refreshData();return{stats:state.status.stats,modelReady:state.status.model_ready,profiles:state.profiles.map(({id,name})=>({id,name})),busy:state.status.busy};}
  },{
    name:'navigate_findface',title:'เปิดหน้าของ FindFace',description:'Navigate to an existing FindFace view. Does not upload photos, connect accounts, or start a scan.',
    inputSchema:{type:'object',properties:{view:{type:'string',enum:Object.keys(titles)}},required:['view'],additionalProperties:false},annotations:{readOnlyHint:false},
    execute(input){if(!input||Object.keys(input).some(k=>k!=='view')||!(input.view in titles))throw new Error('Invalid view');navigate(input.view);return{view:state.view};}
  }];
  for(const tool of tools){try{Promise.resolve(document.modelContext.registerTool(tool,{signal:controller.signal})).catch(()=>{});}catch{}}
}

async function init(){
  decorate();render();state.view=location.hash.slice(1) in titles?location.hash.slice(1):'search';
  try{
    await refreshData();render();registerAgentTools();
    const oauth=new URLSearchParams(location.search).get('oauth');
    if(oauth){history.replaceState(null,'',location.pathname+'#settings');navigate('settings');toast(oauth==='connected'?'เชื่อมต่อ Google Drive สำเร็จ':oauth==='cancelled'?'ยกเลิกการเชื่อมต่อแล้ว':oauth==='busy'?'หยุดงานสแกนก่อนเชื่อมต่อบัญชีใหม่':'เชื่อมต่อไม่สำเร็จ ตรวจ OAuth Client และ Redirect URI แล้วลองใหม่',!['connected','cancelled'].includes(oauth));}
  }catch(error){$('#page').innerHTML=`<section class="panel">${empty('เปิดพื้นที่ทำงานไม่สำเร็จ',error.message,'alert')}</section>`;}
  setInterval(poll,5000);
}
init();
