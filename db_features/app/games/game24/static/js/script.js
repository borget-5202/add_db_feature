(() => {
  'use strict';

  // ---- Bases injected by the template (with safe fallbacks) ----
  const API_BASE    = (typeof window !== 'undefined' && window.GAME24_API_BASE)    ? window.GAME24_API_BASE    : '/game24/api';
  const STATIC_BASE = (typeof window !== 'undefined' && window.GAME24_STATIC_BASE) ? window.GAME24_STATIC_BASE : '';
  const CARD_IMG_BASE = (typeof window !== 'undefined' && window.CARD_IMG_BASE) ? window.CARD_IMG_BASE : (STATIC_BASE + '/assets/images/classic/');

  console.log('[GAME24] Using API_BASE:', API_BASE);

  const autoCloseSummary = false;

  // ---- per-tab / per-browser ids ----
  const CLIENT_ID = (() => {
    try {
      const existing = sessionStorage.getItem('client_id');
      if (existing) return existing;
      const id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : 'c_' + Math.random().toString(36).slice(2);
      sessionStorage.setItem('client_id', id);
      return id;
    } catch { return 'c_' + Math.random().toString(36).slice(2); }
  })();

  const GUEST_ID = (() => {
    try {
      const existing = localStorage.getItem('guest_id');
      if (existing) return existing;
      const id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : 'g_' + Math.random().toString(36).slice(2);
      localStorage.setItem('guest_id', id);
      return id;
    } catch { return 'g_' + Math.random().toString(36).slice(2); }
  })();

  // ---- tiny helpers ----
  const $  = (q)=>document.querySelector(q);
  const on = (el, evt, fn) => { if (el) el.addEventListener(evt, fn); };
  const safeValue = (node, def) => (node && node.value !== undefined && node.value !== '') ? node.value : def;
  const preprocess = (s) => s.replace(/\^/g,'**').replace(/×/g,'*').replace(/÷/g,'/');
  const normalizeRankExpr = (s) =>
    s.replace(/\bA\b/gi,'1')
     .replace(/\bT\b/g,'10')
     .replace(/\bJ\b/gi,'11')
     .replace(/\bQ\b/gi,'12')
     .replace(/\bK\b/gi,'13');

  const rankTok = (v) => {
    const n = Number(v);
    if (!Number.isNaN(n)) return ({1:'A',10:'T',11:'J',12:'Q',13:'K'}[n] || String(n));
    return String(v);
  };

  // ---- state ----
  let current = null;
  let handCounter = 0;   // what we display in "Q{handCounter}"
  let nextSeq     = 1;   // what we send to the server for the next deal
  let revealedThisQuestion = false;
  let nextTimer = null;
  let autoDealEnabled = true;

  // ---- timer ----
  let tStart=0, tTick=null;
  const fmt=(ms)=>{ const T=Math.max(0,Math.floor(ms)), t=Math.floor((T%1000)/100), s=Math.floor(T/1000)%60, m=Math.floor(T/60000); return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${t}`; };
  function timerStart(){ timerStop(); tStart=performance.now(); $('#timer').textContent='00:00.0'; tTick=setInterval(()=>{$('#timer').textContent=fmt(performance.now()-tStart)},100); }
  function timerStop(){ if(tTick){ clearInterval(tTick); tTick=null; } }
//  function addToTotalTime(){ if(tStart){ stats.totalTime += Math.floor((performance.now()-tStart)/1000); tStart=0; updateStats(); } }
  function addToTotalTime(){ 
    if(tStart){
        const elapsedSeconds = Math.floor((performance.now()-tStart)/1000);
        stats.totalTime += elapsedSeconds;
        tStart = 0; 
        updateStats(); 
    } 
}

  // ---- stats (local mirrors; backend remains source of truth) ----
  const stats = { played:0, solved:0, revealed:0, incorrect:0, skipped:0, totalTime:0 };
  let countedPlayedThisHand = false;
  let revealedThisHand = false;

  function updateStats(){
  const S = (id, text) => {
    const el = document.getElementById(id);
    if (!el) {
      console.warn(`[GAME24] missing stat element #${id}`);
      return;
    }
    el.textContent = text;
  };
  S('played',    `Played: ${stats.played}`);
  S('solved',    `Solved: ${stats.solved}`);
  S('revealed',  `Revealed: ${stats.revealed}`);
  S('incorrect', `Incorrect: ${stats.incorrect}`);
  S('skipped',   `Skipped: ${stats.skipped}`);
  const m = String(Math.floor(stats.totalTime/60)).padStart(2,'0');
  const s = String(stats.totalTime%60).padStart(2,'0');
  S('totalTime', `Time: ${m}:${s}`);
}

  function applyServerStats(s){
  if (!s) return;
  console.log('[GAME24] applyServerStats: incoming =', JSON.parse(JSON.stringify(s)));
 // stats.played     = (s.played        ?? stats.played);
  //stats.solved     = (s.solved        ?? stats.solved);
//  stats.revealed   = (s.revealed      ?? stats.revealed);
//  stats.skipped    = (s.skipped       ?? stats.skipped);
//  stats.totalTime  = (s.total_time    ?? stats.totalTime);
//  stats.incorrect  = (s.answer_wrong  ?? stats.incorrect);
    // Map backend -> local (do NOT Object.assign; do NOT rename the param to "stats")
  if ('played'       in s) stats.played    = s.played;
  if ('solved'       in s) stats.solved    = s.solved;
  if ('revealed'     in s) stats.revealed  = s.revealed;
  if ('skipped'      in s) stats.skipped   = s.skipped;
  if ('total_time'   in s) stats.totalTime = s.total_time;
  if ('answer_wrong' in s) stats.incorrect = s.answer_wrong;

  try {
  updateStats();
  }catch (e) {
    console.error('[GAME24] updateStats failed', e);
  }
  console.log('[GAME24] applyServerStats: after local =', JSON.parse(JSON.stringify({
    played: stats.played,
    solved: stats.solved,
    revealed: stats.revealed,
    skipped: stats.skipped,
    totalTime: stats.totalTime,
    incorrect: stats.incorrect
  })));
}
  function resetLocalStats(){
    stats.played=stats.solved=stats.revealed=stats.skipped=stats.incorrect=0;
    stats.totalTime=0;
    countedPlayedThisHand = false;
    updateStats();
  }

  // ---- dom refs (match your HTML) ----
  const el = {
    theme: $('#theme'), level: $('#level'),
    question: $('#question'), cards: $('#cards'),
    answer: $('#answer'), feedback: $('#answerFeedback'),
    solutionPanel: $('#solutionPanel'), solutionMsg: $('#solutionMsg'),
    msg: $('#msg'),
    restart: $('#restart'), exit: $('#exit'),
    autoDeal: $('#autoDeal'),

    noBtn: $('#no'),
    ops: $('#ops'),
    backspace: $('#backspace'), clear: $('#clear'), next: $('#next'),
    check: $('#check'), help: $('#help'), helpAll: $('#helpAll'),
    caseIdInput: $('#caseIdInput'), loadCaseBtn: $('#loadCaseBtn'),

    // modals (Count-by-2s style)
    restartModal:    $('#restartModal'),
    restartConfirm:  $('#restartConfirm'),
    restartCancel:   $('#restartCancel'),
    restartClose:    $('#restartClose'),
    exitModal:       $('#exitModal'),
    exitConfirm:     $('#exitConfirm'),
    exitCancel:      $('#exitCancel'),
    exitClose:       $('#exitClose'),
    summaryBackdrop: $('#summaryBackdrop'),
    summaryBody:     $('#summaryBody'),
    summaryOk:       $('#summaryOk'),
    summaryClose:    $('#summaryClose'),
  };

  // ---- modal helpers ----
  function showModal(nodeOrId){ const m = (typeof nodeOrId==='string')?document.getElementById(nodeOrId):nodeOrId; if (m) m.style.display='flex'; }
  function hideModal(nodeOrId){ const m = (typeof nodeOrId==='string')?document.getElementById(nodeOrId):nodeOrId; if (m) m.style.display='none'; }

  // ---- UI helpers ----
  function clearPanels(){
    if (el.feedback){ el.feedback.textContent=''; el.feedback.className='answer-feedback'; }
    if (el.msg){ el.msg.textContent=''; el.msg.className='status'; }
    if (el.solutionPanel) el.solutionPanel.style.display='none';
    if (el.solutionMsg) el.solutionMsg.textContent='';
  }
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

  // ---- cards rendering ----
  function paintCardsFromPayload(data){
    if (!el.cards) return;
    el.cards.innerHTML = '';

    // server-provided images (if any)
    if (Array.isArray(data.images) && data.images.length) {
      data.images.forEach(c => {
        const img = document.createElement('img');
        img.src = c.url; img.alt = c.code; img.className = 'card';
        const rtok = c.code.startsWith('10') ? 'T' : c.code[0];
        img.title = `Click to insert ${rtok}`;
        img.addEventListener('click', () => insertAtCursor(rtok));
        el.cards.appendChild(img);
      });
      return;
    }

    // derive from values
    const suits = ['C','D','H','S'];
    const values = Array.isArray(data.question) ? data.question.slice(0,4) : [];
    values.forEach((v,i)=>{
      const code = `${rankTok(v)}${suits[i%4]}`;
      const img = document.createElement('img');
      const src = (CARD_IMG_BASE.endsWith('/')) ? (CARD_IMG_BASE + code + '.png') : (CARD_IMG_BASE + '/' + code + '.png');
      img.src = src;
      img.alt = code; img.className = 'card'; img.title = `Click to insert ${rankTok(v)}`;
      img.addEventListener('click', () => insertAtCursor(rankTok(v)));
      el.cards.appendChild(img);
    });
  }

  function cancelNextDeal(){ if (nextTimer){ clearTimeout(nextTimer); nextTimer=null; } }
  function scheduleNextDeal(){ cancelNextDeal(); if (autoDealEnabled){ nextTimer = setTimeout(()=>{ nextTimer=null; deal({advanceCounter:true}); }, 900); } }

  // ---- deal (with robust seq handling) ----
  async function deal({advanceCounter = true} = {}){
    clearPanels();
    if (el.cards) el.cards.innerHTML = '';
    if (el.question) el.question.textContent = 'Dealing…';
    revealedThisQuestion = false;
    revealedThisHand = false;

    const themeVal = safeValue(el.theme, 'classic');
    const levelVal = safeValue(el.level, 'easy');
    const seqToSend = nextSeq;
    countedPlayedThisHand = false;

    try{
      const url = `${API_BASE}/next?theme=${encodeURIComponent(themeVal)}&level=${encodeURIComponent(levelVal)}&seq=${seqToSend}&client_id=${encodeURIComponent(CLIENT_ID)}&guest_id=${encodeURIComponent(GUEST_ID)}`;
      console.log('[GAME24] GET', url);
      const r = await fetch(url);
      if (!r.ok) {
        let msg = `HTTP ${r.status}`;
        try { const j = await r.json(); if (j && j.error) msg = j.error; } catch {}
        throw new Error(msg);
      }
      const data = await r.json();

      let displaySeq;
      if (Number.isFinite(data.seq)) {
        displaySeq = (data.seq >= 1) ? data.seq : (data.seq + 1); // tolerate 0-based server
      } else {
        displaySeq = seqToSend;
      }

      if (advanceCounter) {
        handCounter = displaySeq;
        nextSeq     = handCounter + 1;
      }

      if (el.question) {
        const qText = Array.isArray(data.question) ? data.question.join(', ') : (data.question ?? '');
        el.question.textContent = `Q${displaySeq} [#${data.case_id ?? ''}] — Cards: ${qText}`;
      }
      current = data || {};
      if (el.answer) { el.answer.value=''; el.answer.focus(); }
      paintCardsFromPayload(data);
      timerStart();

      const lv = (levelVal||'').toLowerCase();
      if (data.pool_done && (lv === 'custom' || lv === 'competition')) {
        if (el.msg) { el.msg.textContent = 'All cases used. Pool reset.'; el.msg.className='status status-info'; }
      }
    }catch(e){
      if (el.question) el.question.textContent = '';
      showError(`Failed to get a new question from ${API_BASE}. ${e.message || e}`);
      console.error('[GAME24] /next error:', e);
    }
  }

  // ---- check / help ----
async function check(){
  if (!current) return;

  const exprRaw = el.answer ? el.answer.value.trim() : '';
  if (!exprRaw) return;

  // Normalize ranks then normalize operators
  const expr = preprocess(normalizeRankExpr(exprRaw));

  try {
    const r = await fetch(`${API_BASE}/check`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        values: current.values,
        answer: expr,
        client_id: CLIENT_ID,
        guest_id: GUEST_ID
      })
    });

    const res = await r.json();
    console.log('[GAME24] CHECK raw response =', JSON.parse(JSON.stringify(res)));

    // Prefer backend truth when provided
    const serverStats =
      (res && (res.stats || res.stats_payload)) ||
      ((res && (('answer_wrong' in res) || ('played' in res))) ? res : null);

     console.log('[GAME24] CHECK stats source =',
        res?.stats            ? 'res.stats' :
        res?.stats_payload    ? 'res.stats_payload' :
        serverStats === res   ? 'res (top-level)' :
                                'none');

    if (serverStats) {
      applyServerStats(serverStats);
    }

    if (res.ok) {
      // success UI
      if (el.feedback) { el.feedback.textContent = '✓'; el.feedback.className = 'answer-feedback success-icon'; }
      if (el.msg) {
        el.msg.textContent = (res.kind === 'no-solution') ? 'Correct: no solution' : '24! Correct!';
        el.msg.className = 'status status-success';
      }
      timerStop();
      addToTotalTime();

      // If server didn't send stats, do minimal local accounting
      if (!res.stats && !countedPlayedThisHand) {
        stats.played++;
        countedPlayedThisHand = true;
        updateStats();
      }

      scheduleNextDeal();
    } else {
      // wrong UI
      if (el.feedback) { el.feedback.textContent = '✗'; el.feedback.className = 'answer-feedback error-icon'; }
      let msg = res.reason || 'Try again!';
      if (typeof res.value === 'number') msg += ` (got ${res.value})`;
      if (el.msg) { el.msg.textContent = msg; el.msg.className = 'status status-error'; }

      // If server didn't send stats, do local fallbacks
      if (!res.stats && !countedPlayedThisHand) {
        stats.played++;
        countedPlayedThisHand = true;
      }
      if (!res.stats) {
        stats.incorrect++;
      }
      updateStats();
    }
  } catch (e) {
    showError('Error checking answer');
    console.error('[GAME24] /check error:', e);
  }
}
async function help(showAll = false){
  if (!current) return;

  try {
    const r = await fetch(`${API_BASE}/help`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        values: current.values,
        all: showAll,
        client_id: CLIENT_ID,
        guest_id: GUEST_ID
      })
    });

    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();

    // Prefer server truth if provided
    if (data && data.stats) applyServerStats(data.stats);

    // Clear any status line and reveal the solution panel
    if (el.msg) { el.msg.textContent = ''; el.msg.className = 'status'; }
    if (el.solutionPanel) el.solutionPanel.style.display = 'block';

    // Render solution(s)
    if (!data.has_solution) {
      if (el.solutionMsg) el.solutionMsg.textContent = 'No solution.';
    } else if (showAll) {
      if (el.solutionMsg) {
        el.solutionMsg.innerHTML = `Solutions (${data.solutions.length}):`;
        const grid = document.createElement('div');
        grid.className = 'solution-grid';
        data.solutions.forEach(s => {
          const d = document.createElement('div');
          d.textContent = s;
          grid.appendChild(d);
        });
        el.solutionMsg.appendChild(grid);
      }
    } else {
      if (el.solutionMsg) el.solutionMsg.innerHTML = `<strong>Solution:</strong> ${data.solutions[0]}`;
    }

    // Local fallback accounting if server didn't send stats
    if (!data?.stats) {
      if (!countedPlayedThisHand) { stats.played++; countedPlayedThisHand = true; }
      if (!revealedThisHand)      { stats.revealed++; revealedThisHand = true; }
      updateStats();
    }
  } catch (e) {
    if (el.solutionPanel) el.solutionPanel.style.display = 'block';
    if (el.solutionMsg)   el.solutionMsg.textContent = 'Error loading help';
    console.error('[GAME24] /help error:', e);
  }
}
  // ---- load by Case ID (does NOT advance Q counter) ----
  async function loadCaseById(){
    const val = (el.caseIdInput && el.caseIdInput.value) || '';
    const id = parseInt(val, 10);
    if (!val || Number.isNaN(id) || id < 1) { showError('Please enter a valid Case ID'); return; }

    clearPanels();
    if (el.cards) el.cards.innerHTML = '';
    if (el.question) el.question.textContent = `Loading Case #${id}…`;

    const themeVal = safeValue(el.theme, 'classic');
    const levelVal = safeValue(el.level, 'easy');

    try{
      const r = await fetch(`${API_BASE}/next?theme=${encodeURIComponent(themeVal)}&level=${encodeURIComponent(levelVal)}&case_id=${id}&seq=${handCounter || 1}&client_id=${encodeURIComponent(CLIENT_ID)}&guest_id=${encodeURIComponent(GUEST_ID)}`);
      if (!r.ok) {
        const e = await r.json().catch(()=>({}));
        throw new Error(e.error || `HTTP ${r.status}`);
      }
      const data = await r.json();

      const displaySeq = handCounter > 0 ? handCounter : 1;
      if (el.question) {
        const qText = Array.isArray(data.question) ? data.question.join(', ') : (data.question ?? '');
        el.question.textContent = `Q${displaySeq} [#${data.case_id ?? id}] — Cards: ${qText}`;
      }
      current = data;
      paintCardsFromPayload(data);
      if (el.answer) { el.answer.value=''; el.answer.focus(); }
      timerStart();
    }catch(e){
      if (el.question) el.question.textContent = '';
      showError(`Failed to load case #${id}. ${e.message || e}`);
    }
  }

  // static/js/script.js - Fix the summary rendering
function renderSummary(stats, totalSecs) {
    const n = (x) => (x == null ? 0 : Number(x));
    const pad2 = (x) => (x < 10 ? `0${x}` : `${x}`);
    const fmtTime = (secs) => {
        secs = Math.max(0, Math.floor(+secs || 0));
        const m = Math.floor(secs / 60), 
              s = secs % 60;
        return `${pad2(m)}:${pad2(s)}`;
    };

    // Map backend stats to frontend display
    const totals = {
        played: n(stats.played),
        solved: n(stats.solved),
        revealed: n(stats.revealed),
        skipped: n(stats.skipped),
        incorrect: n(stats.answer_wrong || stats.incorrect),
        timeStr: fmtTime(totalSecs || stats.total_time || 0)
    };

    // Extract action stats from backend with fallbacks
    const actions = {
        attempts: n(stats.answer_attempts) || n(stats.attempts) || 0,
        correct: n(stats.answer_correct) || n(stats.correct) || 0,
        wrong: n(stats.answer_wrong) || n(stats.wrong) || n(stats.incorrect) || 0,
        helpSingle: n(stats.help_single) || n(stats.help_used) || 0,
        helpAll: n(stats.help_all) || n(stats.help_all_used) || 0,
        dealSwaps: n(stats.deal_swaps) || n(stats.swaps) || 0
    };

    // By Difficulty
    const by = stats.difficulty || {};
    const order = ['easy', 'medium', 'hard', 'challenge'];
    const rows = order.map(level => {
        const r = by[level] || {};
        const p = n(r.played), s = n(r.solved);
        const acc = p > 0 ? Math.round((s / p) * 100) + '%' : '—';
        return `<tr>
            <td style="text-transform:capitalize">${level}</td>
            <td style="text-align:center">${p}</td>
            <td style="text-align:center">${s}</td>
            <td style="text-align:center">${acc}</td>
        </tr>`;
    }).join('');

    const diffTable = `
        <table style="width:100%; border-collapse:collapse; margin-top:6px">
            <thead>
                <tr>
                    <th style="text-align:left">Level</th>
                    <th style="text-align:center">Played</th>
                    <th style="text-align:center">Solved</th>
                    <th style="text-align:center">Accuracy</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>`;

    // Actions summary
    const actionsBlock = `
        <hr />
        <div style="margin:6px 0"><strong>Actions</strong></div>
        <table style="width:100%; border-collapse:collapse">
            <tbody>
                <tr><td>Answer attempts</td><td style="text-align:right">${actions.attempts}</td></tr>
                <tr><td>&nbsp;&nbsp;• Correct</td><td style="text-align:right">${actions.correct}</td></tr>
                <tr><td>&nbsp;&nbsp;• Wrong / Invalid</td><td style="text-align:right">${actions.wrong}</td></tr>
                <tr><td>Help used</td><td style="text-align:right">${actions.helpSingle}</td></tr>
                <tr><td>Help-All used</td><td style="text-align:right">${actions.helpAll}</td></tr>
                <tr><td>Deal swaps (no action before next deal)</td><td style="text-align:right">${actions.dealSwaps}</td></tr>
            </tbody>
        </table>
    `;

    // Pool Progress
    let poolBlock = '';
    if (stats.pool_mode && (stats.pool_len || 0) > 0) {
        const len = n(stats.pool_len);
        const scoreMap = stats.pool_score || {};
        const solvedInPool = Object.values(scoreMap).reduce((a, b) => a + (parseInt(b, 10) || 0), 0);
        const unfinished = (stats.unfinished || []).slice().sort((a, b) => a - b);
        const unfinishedStr = unfinished.length ? unfinished.map(id => `#${id}`).join(', ') : '';

        poolBlock = `
            <hr />
            <div style="margin:6px 0">
                <strong>Pool Progress</strong>
                <span style="opacity:.7">(${stats.pool_mode}, ${len} case${len === 1 ? '' : 's'})</span>
            </div>
            <div><em>Solved in pool:</em> ${solvedInPool} / ${len}</div>
            ${unfinishedStr ? `<div><em>Unfinished:</em> ${unfinishedStr}</div>` : ''}
        `;
    }

    // Assemble
    return `
        <div style="display:grid; grid-template-columns: repeat(6, auto); gap:10px; margin-bottom:8px">
            <div><strong>Played:</strong> ${totals.played}</div>
            <div><strong>Solved:</strong> ${totals.solved}</div>
            <div><strong>Revealed:</strong> ${totals.revealed}</div>
            <div><strong>Skipped:</strong> ${totals.skipped}</div>
            <div><strong>Incorrect:</strong> ${totals.incorrect}</div>
            <div><strong>Time:</strong> ${totals.timeStr}</div>
        </div>
        <div><strong>By Difficulty</strong></div>
        ${diffTable}
        ${actionsBlock}
        ${poolBlock}
    `;
}
  async function exitAndShowSummary() {
    try {
      const r = await fetch(`${API_BASE}/exit`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ client_id: window.CLIENT_ID, guest_id: window.GUEST_ID })
      });
      if (!r.ok) throw new Error('exit http ' + r.status);
      const j = await r.json();
      if (!j || j.ok !== true) throw new Error('exit payload');
      const html = renderSummary(j.stats || {}, getTotalSeconds());
      showSummaryModal(html);
    } catch (e) {
      console.error('[exitAndShowSummary]', e);
      alert('Could not load session summary.');
    }
  }
  window.exitAndShowSummary = exitAndShowSummary;

  function showSummaryAndGo(statsObj, url){
    if (el.summaryBackdrop && el.summaryBody && el.summaryOk && el.summaryClose){
      //el.summaryBody.innerHTML = renderSummary(statsObj);
      el.summaryBody.innerHTML = renderSummary(statsObj, totalTime);
      showModal(el.summaryBackdrop);
      const go = () => { hideModal(el.summaryBackdrop); window.location.href = url; };
      el.summaryOk.onclick = go; el.summaryClose.onclick = go;
      if (autoCloseSummary) {
        setTimeout(go, 1500);
      }
    }else{
      alert('Session Finished');
      window.location.href = url;
    }
  }

  async function doRestart(){
    hideModal(el.restartModal); cancelNextDeal(); timerStop();
    try { await fetch(`${API_BASE}/restart`, { method:'POST' }); } catch {}
    current = null; revealedThisQuestion = false;
    handCounter = 0; nextSeq = 1;
    resetLocalStats();
    if (el.cards) el.cards.innerHTML='';
    if (el.question) el.question.textContent='';
    clearPanels();
    deal({advanceCounter:true}); // fresh Q1
  }

  async function doExit(){
    hideModal(el.exitModal); cancelNextDeal(); timerStop();
    addToTotalTime();
    let resp = null;
    try {
      resp = await fetch(`${API_BASE}/exit`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ client_id: CLIENT_ID, guest_id: GUEST_ID })
      }).then(r => r.json()).catch(()=>null);
    } catch {}
    console.log('[EXIT] Backend response:', resp);
    const nextUrl = (resp && resp.next_url) ? resp.next_url : '/';
      // Use server stats if available, otherwise fall back to local
    const serverStats = resp && resp.stats ? resp.stats : stats;
    const totalTime = serverStats.total_time || stats.totalTime;

    // Use local mirrors for a quick summary
    console.log('[GAME24] doExit: before showSummaryAndGo =', JSON.parse(JSON.stringify({
    played: stats.played,
    solved: stats.solved,
    revealed: stats.revealed,
    skipped: stats.skipped,
    totalTime: stats.totalTime,
    incorrect: stats.incorrect
  })));
    showSummaryAndGo(stats, nextUrl);
  }

  // ---- operator panel / buttons / shortcuts ----
  on(el.ops, 'click', (e)=>{
    const tgt = e.target;
    if(!(tgt instanceof HTMLButtonElement)) return;
    const op = tgt.dataset.op;
    if(op==='(') return insertAtCursor('()');
    if(op==='*') return insertAtCursor('*');
    if(op==='/') return insertAtCursor('/');
    insertAtCursor(op);
  });
  on(el.backspace, 'click', backspaceAtCursor);
  on(el.clear, 'click', clearAnswer);
  on(el.next, 'click', ()=>{ stats.skipped++; updateStats(); deal({advanceCounter:true}); });
  on(el.check, 'click', check);
  on(el.noBtn, 'click', ()=>{ if(el.answer){ el.answer.value='no solution'; check(); } });
  on(el.help, 'click', ()=>help(false));
  on(el.helpAll, 'click', ()=>help(true));
  on(el.loadCaseBtn, 'click', loadCaseById);

  // Show modals
  on(el.restart, 'click', ()=>{ cancelNextDeal(); showModal(el.restartModal || 'restartModal'); });
  on(el.exit,    'click', ()=>{ cancelNextDeal(); showModal(el.exitModal || 'exitModal'); });
  // Modal buttons
  on(el.restartConfirm,'click', doRestart);
  on(el.restartCancel, 'click', ()=> hideModal(el.restartModal));
  on(el.restartClose,  'click', ()=> hideModal(el.restartModal));
  on(el.exitConfirm,   'click', doExit);
  on(el.exitCancel,    'click', ()=> hideModal(el.exitModal));
  on(el.exitClose,     'click', ()=> hideModal(el.exitModal));

  document.addEventListener('keydown',(e)=>{
    if (e.target === el.answer && e.key === 'Enter') { e.preventDefault(); check(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k==='d') { e.preventDefault(); deal({advanceCounter:true}); }
    else if (k==='n'){ e.preventDefault(); if(el.answer){ el.answer.value='no solution'; check(); } }
    else if (k==='h' && e.shiftKey){ e.preventDefault(); help(true); }
    else if (k==='h'){ e.preventDefault(); help(false); }
    else if (k==='r'){ e.preventDefault(); cancelNextDeal(); showModal(el.restartModal || 'restartModal'); }
    else if (k==='x'){ e.preventDefault(); cancelNextDeal(); showModal(el.exitModal || 'exitModal'); }
    else if (k==='backspace' && document.activeElement !== el.answer){ e.preventDefault(); backspaceAtCursor(); }
  });

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

  // ---- go ----
  updateStats();
  // initial deal; if API path is wrong you'll now see a clear error
  setTimeout(()=>deal({advanceCounter:true}), 0);
})();

