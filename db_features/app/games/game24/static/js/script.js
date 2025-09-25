(()=>{'use strict';

/* =========================
   Config & stable IDs
========================= */
const API_BASE =
  (typeof window !== 'undefined' && window.GAME24_API_BASE) ? window.GAME24_API_BASE :
  (window.location.pathname.includes('/games/game24/') ? '/games/game24/api' : '/game24/api');

const STATIC_BASE  = (typeof window !== 'undefined' && window.GAME24_STATIC_BASE) ? window.GAME24_STATIC_BASE : '';
const CARD_IMG_BASE= (STATIC_BASE ? (STATIC_BASE + '/cards/') : '/games/assets/cards/');

console.log('[GAME24] Using API_BASE:', API_BASE);
console.log('[GAME24] Using STATIC_BASE:', STATIC_BASE);
console.log('[GAME24] Using CARD_IMG_BASE:', CARD_IMG_BASE);

// === Target init (default 24) + read ?target= ===
let TARGET = 24;
if (typeof window.INIT_TARGET !== 'undefined' && window.INIT_TARGET !== null) {
  TARGET = window.INIT_TARGET;
  localStorage.setItem('target_g24', String(TARGET));
}

(function initTargetFromURL(){
  try {
    const qp = new URLSearchParams(location.search);
    const qsTarget = qp.get('target');
    const saved = localStorage.getItem('target_g24');

    if (qsTarget) {
      if (qsTarget !== 'custom') {
        const t = parseInt(qsTarget, 10);
        if (!Number.isNaN(t)) TARGET = t;
      }
      localStorage.setItem('target_g24', String(TARGET));
    } else if (saved) {
      const t = parseInt(saved, 10);
      if (!Number.isNaN(t)) TARGET = t;
    }
  } catch {}
})();

const CLIENT_ID = (()=>{ try{
  const ex = sessionStorage.getItem('client_id'); if (ex) return ex;
  const id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : 'c_' + Math.random().toString(36).slice(2);
  sessionStorage.setItem('client_id', id); return id;
}catch{ return 'c_' + Math.random().toString(36).slice(2); }})();

const GUEST_ID = (()=>{ try{
  const ex = localStorage.getItem('guest_id'); if (ex) return ex;
  const id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : 'g_' + Math.random().toString(36).slice(2);
  localStorage.setItem('guest_id', id); return id;
}catch{ return 'g_' + Math.random().toString(36).slice(2); }})();

console.log('[GAME24] API_BASE:', API_BASE);

/* =========================
   DOM refs & helpers
========================= */
const $  = (q)=>document.querySelector(q);
const on = (el, evt, fn) => { if (el) el.addEventListener(evt, fn); };

const el = {
  theme: $('#theme'), level: $('#level'),
  targetSelect: $('#targetSelect'),

  question: $('#question'), cards: $('#cards'),
  answer: $('#answer'), feedback: $('#answerFeedback'),
  solutionPanel: $('#solutionPanel'), solutionMsg: $('#solutionMsg'),
  msg: $('#msg'),

  // toolbar
  restart: $('#restart'),
  exit: $('#exit'),
  summaryBtn: $('#summaryBtn'),
  autoDeal: $('#autoDeal'),
  noBtn: $('#no'), ops: $('#ops'), backspace: $('#backspace'), clear: $('#clear'),
  next: $('#next'), check: $('#check'), help: $('#help'), helpAll: $('#helpAll'),

  // case pool / jump to id
  casePoolRow: $('#casePoolRow'),
  casePoolInput: $('#casePoolInput'),
  compDurationInput: $('#compDurationInput'),
  saveCasePoolBtn: $('#saveCasePool'),
  caseIdInput: $('#caseIdInput'), loadCaseBtn: $('#loadCaseBtn'),

  // summary modal
  summaryBackdrop: $('#summaryBackdrop'),
  summaryClose: $('#summaryClose'),
  summaryReport: $('#summary-report'),
  summaryCsv: $('#summaryCsv'),
  summaryExit: $('#summaryExit'),
  summaryResume: $('#summaryResume'),

  // misc
  timer: $('#timer'),
};

/* =========================
   Target (24 / 10 / 36)
========================= */
const targetSel = document.getElementById('targetSelect');
const targetCustom = document.getElementById('targetCustom');
const applyTarget  = document.getElementById('applyTarget');

function setTarget(t){
  const n = parseInt(t, 10);
  const clamped = Number.isFinite(n) ? Math.max(-100, Math.min(100, n)) : 24;
  window.TARGET = clamped;               // just set it
  localStorage.setItem('target_g24', String(clamped));
}

(function initTarget(){
  // 1) pull from URL if present
  const qp = new URLSearchParams(location.search);
  const qsTarget = qp.get('target');

  if (qsTarget === 'custom') {
    // show custom UI; don't set TARGET yet
    if (targetSel) targetSel.value = 'custom';
    if (targetCustom) { targetCustom.style.display=''; targetCustom.focus(); }
    if (applyTarget)  applyTarget.style.display='';
  } else if (qsTarget && !Number.isNaN(parseInt(qsTarget,10))) {
    // numeric in URL → apply immediately
    setTarget(parseInt(qsTarget,10));
    if (targetSel) targetSel.value = String(TARGET);
    if (targetCustom) targetCustom.style.display='none';
    if (applyTarget)  applyTarget.style.display='none';
  } else {
    // 2) fallback to saved value or 24
    const saved = localStorage.getItem('target_g24');
    if (saved && !Number.isNaN(parseInt(saved,10))) {
      setTarget(parseInt(saved,10));
      if (targetSel) targetSel.value = (saved==='10'||saved==='36'||saved==='24') ? saved : 'custom';
      if (targetSel && targetSel.value==='custom') {
        if (targetCustom) { targetCustom.style.display=''; targetCustom.value = saved; }
        if (applyTarget)  applyTarget.style.display='';
      }
    } else {
      setTarget(24); // default
      if (targetSel) targetSel.value = '24';
    }
  }

  // 3) UI interactions
  if (targetSel) {
    targetSel.addEventListener('change', ()=>{
      if (targetSel.value === 'custom') {
        if (targetCustom) { targetCustom.style.display=''; targetCustom.focus(); }
        if (applyTarget)  applyTarget.style.display='';
      } else {
        if (targetCustom) targetCustom.style.display='none';
        if (applyTarget)  applyTarget.style.display='none';
        setTarget(parseInt(targetSel.value,10));
      }
    });
  }

  if (applyTarget) {
    applyTarget.addEventListener('click', ()=>{
      const v = parseInt(targetCustom?.value ?? '', 10);
      if (!Number.isNaN(v)) setTarget(v);
    });
  }
  if (targetCustom) {
    targetCustom.addEventListener('keydown', (e)=>{
      if (e.key === 'Enter') {
        e.preventDefault();
        applyTarget?.click();
      }
    });
  }
})();

/* =========================
   State & stats
========================= */
let current = null;
let handCounter = 0;  // what we display (Q1, Q2,…)
let nextSeq     = 1;  // what we send to the server
let autoDealEnabled = true;
let nextTimer = null;

let helpDisabled = false;
let revealedThisHand = false;
let countedPlayedThisHand = false;
let sessionEnded = false;

const stats = {
  played:0, solved:0, revealed:0, skipped:0,
  incorrect:0, totalTime:0, attempts:0, correct:0, dealSwaps:0
};

/* =========================
   Timer
========================= */
let tStart=0, tTick=null;
const fmt=(ms)=>{ const T=Math.max(0,Math.floor(ms)), t=Math.floor((T%1000)/100), s=Math.floor(T/1000)%60, m=Math.floor(T/60000); return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${t}`; };
function timerStart(){ timerStop(); tStart=performance.now(); if (el.timer) el.timer.textContent='00:00.0'; tTick=setInterval(()=>{ if(el.timer) el.timer.textContent=fmt(performance.now()-tStart); },100); }
function timerStop(){ if(tTick){ clearInterval(tTick); tTick=null; } }
function addToTotalTime(){ if(tStart){ stats.totalTime += Math.floor((performance.now()-tStart)/1000); tStart=0; updateStats(); } }

/* =========================
   UI helpers
========================= */
function setCaret(pos){ if(!el.answer) return; el.answer.selectionStart=el.answer.selectionEnd=pos; }
function insertAtCursor(text){
  const inp=el.answer; if(!inp) return;
  const start=inp.selectionStart ?? inp.value.length, end=inp.selectionEnd ?? inp.value.length;
  const before=inp.value.slice(0,start), after=inp.value.slice(end);
  inp.value = before + text + after;
  let p = start + text.length; if(text==='()'){ p = start+1; }
  inp.focus(); setCaret(p);
}
function backspaceAtCursor(){
  const inp=el.answer; if(!inp) return;
  const start=inp.selectionStart ?? 0, end=inp.selectionEnd ?? 0;
  if (start===end && start>0){
    inp.value = inp.value.slice(0, start-1) + inp.value.slice(end);
    setCaret(start-1);
  } else {
    inp.value = inp.value.slice(0, start) + inp.value.slice(end);
    setCaret(start);
  }
  inp.focus();
}
function clearAnswer(){ if(el.answer){ el.answer.value=''; el.answer.focus(); } }
function showError(message){ if(el.msg){ el.msg.textContent=message; el.msg.className='status status-error'; } }
function clearPanels(){
  if (el.feedback){ el.feedback.textContent=''; el.feedback.className='answer-feedback'; }
  if (el.msg){ el.msg.textContent=''; el.msg.className='status'; }
  if (el.solutionPanel) el.solutionPanel.style.display='none';
  if (el.solutionMsg) el.solutionMsg.textContent='';
}

function setGameplayEnabled(enabled){
  const ids = ['no','backspace','clear','next','check','help','helpAll'];
  ids.forEach(id=>{
    const b = document.getElementById(id);
    if (b){ b.disabled = !enabled; b.classList.toggle('is-disabled', !enabled); }
  });
  if (el.ops){
    [...el.ops.querySelectorAll('button')].forEach(btn=>{
      btn.disabled = !enabled;
      btn.classList.toggle('is-disabled', !enabled);
    });
  }
}

/* =========================
   Stats UI
========================= */
function updateStats(){
  const w=(id,txt)=>{ const n=document.getElementById(id); if(n) n.textContent=txt; };
  w('played',   `Played: ${stats.played}`);
  w('solved',   `Solved: ${stats.solved}`);
  w('revealed', `Revealed: ${stats.revealed}`);
  w('skipped',  `Skipped: ${stats.skipped}`);
  w('incorrect', `Incorrect: ${stats.incorrect}`);

  const m=String(Math.floor(stats.totalTime/60)).padStart(2,'0'),
        s=String(stats.totalTime%60).padStart(2,'0');
  w('totalTime',`Time: ${m}:${s}`);
}
function applyServerStats(s){
  if(!s) return;
  console.log('Applying server stats:', s); // DEBUG

  if('played'          in s) stats.played      = s.played;
  if('solved'          in s) stats.solved      = s.solved;
  if('revealed'        in s) stats.revealed    = s.revealed;
  if('skipped'         in s) stats.skipped     = s.skipped;
  if('total_time'      in s) stats.totalTime   = s.total_time;
  if('answer_attempts' in s) stats.attempts    = s.answer_attempts;
  if('answer_correct'  in s) stats.correct     = s.answer_correct;
  if('answer_wrong'    in s) stats.incorrect   = s.answer_wrong;
  if('deal_swaps'      in s) stats.dealSwaps   = s.deal_swaps;

  updateStats();
}
function resetLocalStats(){
  stats.played = stats.solved = stats.revealed = stats.skipped =
  stats.incorrect = stats.attempts = stats.correct = stats.dealSwaps = 0;
  stats.totalTime = 0;
  updateStats();
}

/* =========================
   Cards render
========================= */
const rankTok = (v)=>{ const n=Number(v); if(!Number.isNaN(n)) return ({1:'A',10:'T',11:'J',12:'Q',13:'K'}[n]||String(n)); return String(v); };
function paintCardsFromPayload(data){
  if (!el.cards) return;
  el.cards.innerHTML = '';
  const suits = ['C','D','H','S'];
  const values = Array.isArray(data.question) ? data.question.slice(0,4) : [];
  values.forEach((v,i)=>{
    const code = `${rankTok(v)}${suits[i%4]}`;
    const img = document.createElement('img');
    const src = (CARD_IMG_BASE.endsWith('/')) ? (CARD_IMG_BASE + code + '.png') : (CARD_IMG_BASE + '/' + code + '.png');
    img.src = src; img.alt = code; img.className='card'; img.title = `Click to insert ${rankTok(v)}`;
    img.addEventListener('click', ()=>insertAtCursor(rankTok(v)));
    el.cards.appendChild(img);
  });
}

/* =========================
   Deal / sequencing
========================= */
function cancelNextDeal(){ if (nextTimer){ clearTimeout(nextTimer); nextTimer=null; } }
function scheduleNextDeal(){ 
  cancelNextDeal(); 
  if (sessionEnded || !autoDealEnabled) return;
  if (autoDealEnabled){ nextTimer = setTimeout(()=>{ nextTimer=null; deal({advanceCounter:true}); }, 900); } }

async function deal({advanceCounter=true, caseId=null} = {}){
  if (sessionEnded) return;
  clearPanels();
  if (el.cards) el.cards.innerHTML='';
  if (el.question) el.question.textContent='Dealing…';
  revealedThisHand = false;
  countedPlayedThisHand = false;

  const themeVal = (el.theme && el.theme.value) ? el.theme.value : 'classic';
  const levelVal = (el.level && el.level.value) ? el.level.value : 'easy';
  const seqToSend = nextSeq;

  try{
    const params = new URLSearchParams({
      theme: themeVal, level: levelVal, seq: String(seqToSend),
      client_id: CLIENT_ID, guest_id: GUEST_ID, target: String(TARGET)
    });
    if (caseId) params.set('case_id', String(caseId));
    const r = await fetch(`${API_BASE}/next?${params.toString()}`);
    if (!r.ok){
      let msg=`HTTP ${r.status}`; try{ const j=await r.json(); if(j?.error) msg=j.error; }catch{}
      throw new Error(msg);
    }
    const data = await r.json();
    if (data && (data.stats || data.stats_payload)) { applyServerStats(data.stats || data.stats_payload); }

    const displaySeq = Number.isFinite(data.seq) ? (data.seq>=1?data.seq:data.seq+1) : seqToSend;
    if (advanceCounter && !caseId){ handCounter = displaySeq; nextSeq = handCounter + 1; }
    if (caseId && handCounter===0) { handCounter = 1; }

    if (el.question){
      const qText = Array.isArray(data.question) ? data.question.join(', ') : (data.question ?? '');
      const shownSeq = caseId ? handCounter : displaySeq;
      el.question.textContent = `Q${shownSeq} [#${data.case_id ?? (caseId||'')}] — Cards: ${qText} — Target: ${TARGET}`;
    }

    current = data || {};
    if (el.answer){ el.answer.value=''; el.answer.focus(); }
    paintCardsFromPayload(data);
    timerStart();

    if (typeof data.help_disabled === 'boolean') helpDisabled = data.help_disabled;

  }catch(e){
    if (el.question) el.question.textContent='';
    showError(`Failed to get a new question from ${API_BASE}. ${e.message || e}`);
  }
}

/* =========================
   Answer / Help / Skip
========================= */
const preprocess = (s)=>
  s.replace(/\^/g,'**').replace(/×/g,'*').replace(/∗/g,'*').replace(/·/g,'*')
   .replace(/÷/g,'/').replace(/／/g,'/')
   .replace(/−|—|–/g,'-')
   .replace(/\bA\b/gi,'1').replace(/\bT\b/g,'10').replace(/\bJ\b/gi,'11').replace(/\bQ\b/gi,'12').replace(/\bK\b/gi,'13');

async function check(){
  if(!current) return;
  console.log('Current object:', current);
  console.log('Current.case_id:', current.case_id);
  console.log('Current.values:', current.values);

  const exprRaw = el.answer ? el.answer.value.trim() : '';
  if(!exprRaw) return;

  try{
    const r = await fetch(`${API_BASE}/check`, {
      method: 'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        values: current.values,
        answer: preprocess(exprRaw),
        case_id: current.case_id,
        client_id: CLIENT_ID, guest_id: GUEST_ID,
        target: TARGET
      })
    });
    const res = await r.json();

    if (res && (res.stats || res.stats_payload)) applyServerStats(res.stats || res.stats_payload);

    if (res.ok){
      if (el.feedback){ el.feedback.textContent='✓'; el.feedback.className='answer-feedback success-icon'; }
      if (el.msg){ el.msg.textContent = (res.kind==='no-solution') ? `Correct: no solution` : `${TARGET}! Correct!`; el.msg.className='status status-success'; }
      timerStop(); addToTotalTime(); scheduleNextDeal();
    } else {
      if (el.feedback){ el.feedback.textContent='✗'; el.feedback.className='answer-feedback error-icon'; }
      if (el.msg){ el.msg.textContent = res.reason || `Try again!`; el.msg.className='status status-error'; }
    }
  }catch(e){
    showError('Error checking answer'); console.error(e);
  }
}

async function help(all=false){
  if(!current) return;
  if (helpDisabled){
    if (el.solutionPanel) el.solutionPanel.style.display='block';
    if (el.solutionMsg) el.solutionMsg.textContent='Help is disabled in competition mode.';
    return;
  }
  try{
    const r = await fetch(`${API_BASE}/help`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        values: current.values,
        case_id: current.case_id,
        all,
        client_id: CLIENT_ID, guest_id: GUEST_ID,
        target: TARGET
      })
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    if (data && data.stats) applyServerStats(data.stats);

    if (el.msg){ el.msg.textContent=''; el.msg.className='status'; }
    if (el.solutionPanel) el.solutionPanel.style.display='block';

    if (!data.has_solution){
      if (el.solutionMsg) el.solutionMsg.textContent=`No solution for target ${TARGET}.`;
    } else if (all){
      if (el.solutionMsg){
        el.solutionMsg.innerHTML = `Solutions (${data.solutions.length}) for target ${TARGET}:`;
        const grid=document.createElement('div'); grid.className='solution-grid';
        data.solutions.forEach(s=>{ const d=document.createElement('div'); d.textContent=s; grid.appendChild(d); });
        el.solutionMsg.appendChild(grid);
      }
    } else {
      if (el.solutionMsg) el.solutionMsg.innerHTML = `<strong>Solution (target ${TARGET}):</strong> ${data.solutions?.[0] || data.solution || ''}`;
    }
  }catch(e){
    if (el.solutionPanel) el.solutionPanel.style.display='block';
    if (el.solutionMsg)   el.solutionMsg.textContent='Error loading help';
  }
}

async function skipThenDeal(all=false){
  try {
    const r = await fetch(`${API_BASE}/skip`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        values: current.values,
        case_id: current.case_id,
        all,
        client_id: CLIENT_ID, guest_id: GUEST_ID,
        target: TARGET
      })
    });
    if (r.ok) {
      const j = await r.json().catch(()=>null);
      console.log('Skip response:', j);
      if (j && (j.stats || j.stats_payload)) { applyServerStats(j.stats || j.stats_payload); }
    }
  } catch(e){ console.warn('skip failed', e); }
  await deal({ advanceCounter: true });
}

/* =========================
   Load by Case ID (works in any mode)
========================= */
async function loadCaseById(){
  const val = (el.caseIdInput && el.caseIdInput.value) || '';
  const id  = parseInt(val, 10);
  if (!val || Number.isNaN(id) || id < 1 || id > 1820){ showError('Please enter a valid Case ID (1–1820).'); return; }

  clearPanels();
  if (el.cards) el.cards.innerHTML='';
  if (el.question) el.question.textContent = `Loading Case #${id}…`;

  try{
    await deal({ advanceCounter:false, caseId:id });
  }catch(e){
    showError(`Failed to load case #${id}. ${e.message || e}`);
  }
}

/* =========================
   Restart
========================= */
async function doRestart(){
  try{
    cancelNextDeal(); timerStop(); addToTotalTime(); clearPanels();
    sessionEnded = false;
    setGameplayEnabled(true);
    if (el.question) el.question.textContent='Restarting…';

    clearPanels();
    if (el.answer) el.answer.value = '';
    if (el.cards) el.cards.innerHTML = '';
    if (el.solutionPanel) el.solutionPanel.style.display = 'none';

    handCounter=0; nextSeq=1; resetLocalStats();
    try{
      const r = await fetch(`${API_BASE}/restart`, {
        method:'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ client_id: CLIENT_ID, guest_id: GUEST_ID, target: TARGET })
      });
      if (r.ok){
        const j=await r.json().catch(()=>null);
        if (j?.stats) applyServerStats(j.stats);
        current = null;
      }
    }catch(e){ console.warn('[GAME24] /restart not available', e); }

    await deal({ advanceCounter:true });
  }catch(e){
    console.error('[doRestart] failed', e);
    try{ await deal({advanceCounter:true}); }catch{}
  }
}
window.doRestart = doRestart;

// ===== Confirm modal helper =====
const qs = (q)=>document.querySelector(q);
const confirmEls = {
  backdrop: qs('#confirmBackdrop'),
  title:    qs('#confirmTitle'),
  msg:      qs('#confirmMsg'),
  ok:       qs('#confirmOK'),
  cancel:   qs('#confirmCancel'),
};
function openConfirm({title, msg, onOK}){
  if (confirmEls.title)  confirmEls.title.textContent = title || 'Are you sure?';
  if (confirmEls.msg)    confirmEls.msg.textContent   = msg || '';
  const doClose = ()=>{ if(confirmEls.backdrop) confirmEls.backdrop.style.display='none'; };
  const handleOK = ()=>{ try{ onOK && onOK(); } finally { cleanup(); } };
  const cleanup = ()=>{
    if (confirmEls.ok)     confirmEls.ok.removeEventListener('click', handleOK);
    if (confirmEls.cancel) confirmEls.cancel.removeEventListener('click', doClose);
    doClose();
  };
  if (confirmEls.ok)     confirmEls.ok.addEventListener('click', handleOK);
  if (confirmEls.cancel) confirmEls.cancel.addEventListener('click', doClose);
  if (confirmEls.backdrop) confirmEls.backdrop.style.display='flex';
}
/* =========================
   Summary / Exit flow
========================= */
function showSummaryModalReport(html){
  if (el.summaryReport) el.summaryReport.innerHTML = html || '<p>No summary.</p>';
  if (el.summaryBackdrop) el.summaryBackdrop.style.display='flex';
}
async function openSummaryFlow(){
  try{
    const r = await fetch(`${API_BASE}/summary`, {
      method: 'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ client_id: CLIENT_ID, guest_id: GUEST_ID, auto_deal: autoDealEnabled, target: TARGET })
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    window._lastSummary = j;
    const html = j?.play_summary?.report_html || '<p>No summary.</p>';
    if (el.summaryCsv){
      el.summaryCsv.style.display = j?.export_url ? 'inline-block' : 'none';
      if (j?.export_url) {
         const qs = new URLSearchParams({
           client_id: CLIENT_ID,
           guest_id: GUEST_ID
         }).toString();
         el.summaryCsv.href = `${j.export_url}${j.export_url.includes('?') ? '&' : '?'}${qs}`;
      }
    }
    showSummaryModalReport(html);
  }catch(e){ console.error('[openSummaryFlow]', e); alert('Could not load summary'); }
}
window.openSummaryFlow = openSummaryFlow;

async function finalizeFromSummary(){
  try {
    const r = await fetch(`${API_BASE}/exit`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        client_id: CLIENT_ID,
        guest_id: GUEST_ID,
      })
    });

    if (!r.ok) throw new Error(`HTTP ${r.status}`);

    let url = document.body?.dataset?.homeUrl || "/";
    try {
      const txt = await r.text();
      const j = txt ? JSON.parse(txt) : null;
      if (j && j.redirect_url) url = j.redirect_url;
    } catch { /* ignore parse errors; use fallback url */ }

    hideSummaryModal?.();
    cancelNextDeal?.();
    window.location.assign(url);

  } catch (err) {
    console.error('[exit] failed:', err);
    const fallback = document.body?.dataset?.homeUrl || "/";
    window.location.assign(fallback);
  }
}
window.finalizeFromSummary = finalizeFromSummary;

const hideSummary = ()=>{ if (el.summaryBackdrop) el.summaryBackdrop.style.display='none'; };

/* =========================
   Events
========================= */
on(el.ops,'click',(e)=>{ const t=e.target.closest('button[data-op]'); if(!t) return;
  const op=t.dataset.op; if(op==='(') return insertAtCursor('()'); return insertAtCursor(op); });

on(el.backspace,'click', backspaceAtCursor);
on(el.clear,'click', clearAnswer);

on(el.check,'click', check);
on(el.noBtn,'click', ()=>{ if(el.answer){ el.answer.value='no solution'; check(); } });

on(el.help,'click', ()=>help(false));
on(el.helpAll,'click', ()=>help(true));
on(el.next,'click', skipThenDeal);

on(el.loadCaseBtn,'click', loadCaseById);
if (el.caseIdInput) el.caseIdInput.addEventListener('keydown', (e)=>{ if(e.key==='Enter'){ e.preventDefault(); loadCaseById(); } });

on(el.restart,'click', (e)=>{
  e.preventDefault();
  cancelNextDeal();
  openConfirm({
    title: 'Restart?',
    msg: 'This will reset counters and start a new session.',
    onOK: ()=>{ doRestart(); }
  });
});

// Summary button (peek)
on(el.summaryBtn,'click', (e)=>{ e.preventDefault(); cancelNextDeal(); openSummaryFlow(); });

// Exit now opens Summary first
on(el.exit,'click', (e)=>{ e.preventDefault(); cancelNextDeal(); openSummaryFlow(); });

// Summary modal controls
on(el.summaryResume,'click', (e)=>{ e.preventDefault(); hideSummary(); });
on(el.summaryClose, 'click', (e)=>{ e.preventDefault(); hideSummary(); });
on(el.summaryExit,  'click', (e)=>{ e.preventDefault(); finalizeFromSummary(); });

// Keyboard shortcuts
document.addEventListener('keydown',(e)=>{
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target === el.answer && e.key === 'Enter'){ e.preventDefault(); check(); return; }
  const k=e.key.toLowerCase();
  if (k==='d'){ e.preventDefault(); skipThenDeal(); }
  else if (k==='n'){ e.preventDefault(); if(el.answer){ el.answer.value='no solution'; check(); } }
  else if (k==='h' && e.shiftKey){ e.preventDefault(); help(true); }
  else if (k==='h'){ e.preventDefault(); help(false); }
  else if (k==='r'){ e.preventDefault(); doRestart(); }
  else if (k==='x'){ e.preventDefault(); openSummaryFlow(); }
  else if (k==='s' && e.shiftKey){ e.preventDefault(); openSummaryFlow(); }
});

/* =========================
   Custom/Competition UI toggles
========================= */
function parseCasePool(text){
  if (!text) return [];
  const parts = text.split(/[\s,\|]+/g).filter(Boolean);
  const nums=[]; const seen=new Set();
  for (const p of parts){
    const n=parseInt(p,10);
    if (!Number.isFinite(n)) continue;
    if (n<1 || n>1820) continue;
    if (seen.has(n)) continue;
    seen.add(n); nums.push(n);
    if (nums.length>=25) break;
  }
  return nums;
}
function updateCasePoolUI(){
  const lvl = el.level ? el.level.value : 'easy';
  const isPool = (lvl==='custom' || lvl==='competition');
  if (el.casePoolRow) el.casePoolRow.style.display = isPool ? '' : 'none';
  const wrap = el.compDurationInput && el.compDurationInput.parentElement;
  if (wrap) wrap.style.display = (lvl==='competition') ? '' : 'none';
  if (el.compDurationInput) el.compDurationInput.disabled = (lvl!=='competition');
  helpDisabled = (lvl==='competition');
}
on(el.level,'change', ()=>{
  localStorage.setItem('level', el.level.value);
  updateCasePoolUI();
});

// Save pool → backend
on(el.saveCasePoolBtn, 'click', async ()=>{
  const lvl = el.level ? el.level.value : 'easy';
  if (lvl!=='custom' && lvl!=='competition'){ showError('Select custom or competition first.'); return; }
  const ids = parseCasePool(el.casePoolInput ? el.casePoolInput.value : '');
  if (!ids.length){ showError('Enter 1–25 valid Case IDs (1–1820).'); return; }
  if (el.casePoolInput) localStorage.setItem('casePoolText', el.casePoolInput.value);

  const payload = { mode: lvl, case_ids: ids, client_id: CLIENT_ID, guest_id: GUEST_ID };
  if (lvl==='competition'){
    let mins=5;
    if (el.compDurationInput){ const v=parseInt(el.compDurationInput.value,10); if (Number.isFinite(v)) mins=v; }
    mins=Math.max(1,Math.min(60,mins));
    payload.duration_sec = mins*60;
    localStorage.setItem('compDurationMin', String(mins));
  }

  try{
    const r = await fetch(`${API_BASE}/pool`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    if (!r.ok){ const er=await r.json().catch(()=>({})); throw new Error(er.error||'Failed to set pool'); }
    if (el.msg) el.msg.textContent = `Pool saved (${ids.length} case IDs) for ${lvl}. Press Deal to start.`;
  }catch(e){ showError(e.message); }
});

// Persist some settings on load
const tSaved=localStorage.getItem('theme'); if(tSaved && el.theme) el.theme.value=tSaved;
const lSaved=localStorage.getItem('level'); if(lSaved && el.level) el.level.value=lSaved;
const poolSaved=localStorage.getItem('casePoolText'); if(poolSaved && el.casePoolInput) el.casePoolInput.value=poolSaved;
const durSaved=localStorage.getItem('compDurationMin'); if(durSaved && el.compDurationInput) el.compDurationInput.value=durSaved;
on(el.theme,'change', ()=>{ localStorage.setItem('theme', el.theme.value); });

// How-to modal
on($('#howtoLink'),'click', ()=>{ const b=$('#modalBackdrop'); if (b) b.style.display='flex'; });
on($('#modalClose'), 'click', ()=>{ const b=$('#modalBackdrop'); if (b) b.style.display='none'; });
on($('#modalBackdrop'),'click',(e)=>{ if(e.target===$('#modalBackdrop')) e.currentTarget.style.display='none'; });

// ---- settings / auto-deal ----
  const autoDealSaved = localStorage.getItem('autoDeal_g24');
  if (autoDealSaved !== null) {
    const v = (autoDealSaved === 'true');
    if (el.autoDeal) el.autoDeal.checked = v;
    autoDealEnabled = v;
  } else {
    if (el.autoDeal) el.autoDeal.checked = true;
    autoDealEnabled = true;
    localStorage.setItem('autoDeal_g24','true');
  }
  on(el.autoDeal,'change',()=> {
    const v = !!el.autoDeal?.checked;
    localStorage.setItem('autoDeal_g24', String(v));
    autoDealEnabled = v;
  });

// === Initial target from URL or saved value (runs before boot) ===
(function initTargetOnce(){
  try {
    const qp = new URLSearchParams(location.search);
    const qs = qp.get('target');
    const saved = localStorage.getItem('target_g24');

    if (qs && qs !== 'custom' && !Number.isNaN(parseInt(qs,10))) {
      window.TARGET = parseInt(qs,10);
      localStorage.setItem('target_g24', String(window.TARGET));
    } else if (saved && !Number.isNaN(parseInt(saved,10))) {
      window.TARGET = parseInt(saved,10);
    } else {
      window.TARGET = 24;
    }
  } catch {
    window.TARGET = 24;
  }
})();

// Boot once
let booted=false;
async function boot(){ if(booted) return; booted=true; updateStats(); await deal({advanceCounter:true}); }
boot();

})(); // IIFE end

