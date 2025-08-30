document.addEventListener('DOMContentLoaded', () => {
(() => {

  // ---------- tiny helpers ----------
  const $ = (q)=>document.querySelector(q);
  const on = (el, evt, fn) => { if (el) el.addEventListener(evt, fn); };

  // Unique per TAB so each tab has its own session on the server (safe if backend ignores it)
  const CLIENT_ID = (sessionStorage.getItem('client_id') || (() => {
    let id;
    if (window.crypto && window.crypto.randomUUID) id = crypto.randomUUID();
    else id = 'c_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    sessionStorage.setItem('client_id', id);
    return id;
  })());
  console.log('CLIENT_ID99999999999999', CLIENT_ID);

  // Stable per BROWSER (persists across tabs/windows on the same machine)
  const GUEST_ID = (localStorage.getItem('guest_id') || (() => {
    let id;
    if (window.crypto && window.crypto.randomUUID) id = crypto.randomUUID();
    else id = 'g_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem('guest_id', id);
    return id;
  })());
  console.log('GUEST_ID', GUEST_ID); // optional debug


  // Surface any uncaught JS error so we don't silently stall on "Dealing…"
  window.addEventListener('error', (ev)=>{
    const m = document.getElementById('msg');
    if (m) {
      m.textContent = `Script error: ${ev.message || 'unknown'} (see console)`;
      m.className = 'status status-error';
    }
  });

  function safeValue(node, def) {
    try { return (node && typeof node.value !== 'undefined' && node.value !== '') ? node.value : def; }
    catch { return def; }
  }
  function getCompDurationWrap() {
    const el = document.getElementById('compDurationInput');
    return el ? el.parentElement : null;
  }
  function getCasePoolInlineRow() {
    return document.querySelector('#casePoolRow .row-inline');
  }

  // ---------- state ----------
  let current = null;
  let currentSeq = 0;
  const stats = { played:0, solved:0, revealed:0, skipped:0, totalTime:0 };
  let currentStatus='idle';
  let revealedThisQuestion=false;
  let autoDealEnabled = true;
  let helpDisabled = false;

  // ---------- timer ----------
  let tStart=0, tTick=null;
  const fmt=(ms)=>{ const T=Math.max(0,Math.floor(ms)), t=Math.floor((T%1000)/100), s=Math.floor(T/1000)%60, m=Math.floor(T/60000); return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${t}`; };
  function timerStart(){ timerStop(); tStart=performance.now(); $('#timer').textContent='00:00.0'; tTick=setInterval(()=>{$('#timer').textContent=fmt(performance.now()-tStart)},100); }
  function timerStop(){ if(tTick){ clearInterval(tTick); tTick=null; } }
  function addToTotalTime(){ if(tStart){ stats.totalTime += Math.floor((performance.now()-tStart)/1000); tStart=0; updateStats(); } }

  // ---------- dom refs ----------
  const el = {
    theme: $('#theme'), level: $('#level'),
    question: $('#question'), cards: $('#cards'),
    answer: $('#answer'), feedback: $('#answerFeedback'),
    solutionPanel: $('#solutionPanel'), solutionMsg: $('#solutionMsg'),
    msg: $('#msg'),
    restart: $('#restart'),
    exit: $('#exit'),
    played: $('#played'), solved: $('#solved'), revealed: $('#revealed'), skipped: $('#skipped'), total: $('#totalTime')
  };
  const casePoolRow = $('#casePoolRow') || null;
  const casePoolInput = $('#casePoolInput') || null;
  const compDurationInput = $('#compDurationInput') || null;
  const saveCasePoolBtn = $('#saveCasePool') || null;

  // ---------- competition countdown ----------
  let competitionOver = false;
  let compDeadline = null;   // ms epoch end
  let compInterval = null;

  function ensureCompBanner() {
    let node = document.getElementById('compBanner');
    if (!node) {
      node = document.createElement('div');
      node.id = 'compBanner';
      node.style.position = 'fixed';
      node.style.top = '8px';
      node.style.right = '8px';
      node.style.background = 'rgba(0,0,0,0.80)';
      node.style.color = '#fff';
      node.style.padding = '6px 10px';
      node.style.borderRadius = '8px';
      node.style.font = '600 13px/1.2 system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
      node.style.zIndex = 1000;
      document.body.appendChild(node);
    }
    return node;
  }
  function hideCompBanner() { const n = document.getElementById('compBanner'); if (n) n.remove(); }
  function formatMMSS(sec) { const m = Math.floor(sec / 60), s = sec % 60; return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`; }
  function updateCompBanner() {
    if (!compDeadline) return;
    const left = Math.max(0, Math.ceil((compDeadline - Date.now()) / 1000));
    ensureCompBanner().textContent = left > 0 ? `🏁 Competition: ${formatMMSS(left)} left` : `🏁 Competition over`;
    if (left <= 0) endCompetitionUI();
  }
  function startCompetitionCountdown(seconds) {
    if (typeof seconds !== 'number') return;
    competitionOver = false;
    compDeadline = Date.now() + seconds * 1000;
    if (compInterval) clearInterval(compInterval);
    updateCompBanner();
    compInterval = setInterval(updateCompBanner, 1000);
  }
  function stopCompetitionCountdown() {
    compDeadline = null;
    if (compInterval) { clearInterval(compInterval); compInterval = null; }
    hideCompBanner();
  }
  // Only toggles the Next button now
  function setControlsEnabled(enabled) {
    const b = document.getElementById('next');
    if (b) {
      b.disabled = !enabled;
      b.style.opacity = enabled ? 1 : 0.6;
      b.style.pointerEvents = enabled ? 'auto' : 'none';
    }
  }

  function endCompetitionUI() {
    competitionOver = true;
    stopCompetitionCountdown();
    setControlsEnabled(false);
    if (el.question) el.question.textContent = 'Competition over.';
    if (el.msg) { el.msg.textContent = 'Time is up!'; el.msg.className = 'status status-success'; }
  }

  // ---------- ui helpers ----------
  function resetStats() {
    stats.played = 0; stats.solved = 0; stats.revealed = 0; stats.skipped = 0; stats.totalTime = 0;
    updateStats();
    if (el.msg) el.msg.textContent = 'Game restarted!';
  }

  function updateStats(){
    if (el.played) el.played.textContent=`Played: ${stats.played}`;
    if (el.solved) el.solved.textContent=`Solved: ${stats.solved}`;
    if (el.revealed) el.revealed.textContent=`Revealed: ${stats.revealed}`;
    if (el.skipped) el.skipped.textContent=`Skipped: ${stats.skipped}`;
    const m=String(Math.floor(stats.totalTime/60)).padStart(2,'0'), s=String(stats.totalTime%60).padStart(2,'0');
    if (el.total) el.total.textContent=`Time: ${m}:${s}`;
  }
  function clearPanels(){
    if (el.feedback){ el.feedback.textContent=''; el.feedback.className='answer-feedback'; }
    if (el.msg){ el.msg.textContent=''; el.msg.className='status'; }
    if (el.solutionPanel) el.solutionPanel.style.display='none';
    if (el.solutionMsg) el.solutionMsg.textContent='';
  }
  function preprocess(expr){ return expr.replace(/\^/g,'**').replace(/×/g,'*').replace(/÷/g,'/'); }

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

  function parseCasePool(text) {
    if (!text) return [];
    const parts = text.split(/[\s,\|]+/g).filter(Boolean);
    const nums = []; const seen = new Set();
    for (const p of parts) {
      const n = parseInt(p, 10);
      if (!Number.isFinite(n)) continue;
      if (n < 1 || n > 1820) continue;
      if (seen.has(n)) continue;
      nums.push(n); seen.add(n);
      if (nums.length >= 25) break;
    }
    return nums;
  }

  function updateCasePoolUI() {
    const lvl = el.level ? el.level.value : 'easy';
    const isPool = (lvl === 'custom' || lvl === 'competition');
    if (casePoolRow) casePoolRow.style.display = isPool ? '' : 'none';

    const wrap = getCompDurationWrap();
    if (wrap) wrap.style.display = (lvl === 'competition') ? '' : 'none';
    if (compDurationInput) compDurationInput.disabled = (lvl !== 'competition');

    const row = getCasePoolInlineRow();
    if (row) {
      row.style.gridTemplateColumns = (lvl === 'competition')
        ? 'minmax(260px,1fr) auto auto'
        : 'minmax(260px,1fr) auto';
    }

    helpDisabled = (lvl === 'competition');
    const setDis = (btn, on) => {
      if (!btn) return;
      btn.disabled = !!on;
      btn.style.opacity = on ? 0.5 : 1;
      btn.style.pointerEvents = on ? 'none' : 'auto';
      btn.title = on ? 'Disabled in competition mode' : '';
    };
    setDis(document.getElementById('help'), helpDisabled);
    setDis(document.getElementById('helpAll'), helpDisabled);
  }

  // ---------- summary helpers ----------
  function formatHMS(totalSeconds){
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  }

  // static/js/script.js - Add stats synchronization
function updateStatsFromServer(statsData) {
    if (!statsData) return;
    
    // Update local stats
    stats.played = parseInt(statsData.played || 0);
    stats.solved = parseInt(statsData.solved || 0);
    stats.revealed = parseInt(statsData.revealed || 0);
    stats.skipped = parseInt(statsData.skipped || 0);
    
    // Update UI
    updateStats();
}

  // Modify the fetch wrapper to sync stats
  const originalFetch = window.fetch;
  window.fetch = async function(input, init = {}) {
      try {
          const response = await originalFetch(input, init);
          
          // Check if this is an API call that returns stats
          if (response.url && (response.url.includes('/api/game24') || response.url.includes('/api/')) && 
              response.headers.get('content-type')?.includes('application/json')) {
              const data = await response.clone().json();
              if (data && data.stats) {
                  updateStatsFromServer(data.stats);
              }
          }
          
          return response;
      } catch (error) {
          console.error('Fetch error:', error);
          throw error;
      }
  };

  // ---------- server → ui ----------
  function handleNewPuzzleData(data) {
    currentSeq = data.seq;
    current = data;

    if (typeof data.help_disabled === 'boolean') {
      helpDisabled = data.help_disabled;
      updateCasePoolUI();
    }
    if (typeof data.time_left === 'number') startCompetitionCountdown(data.time_left);
    else stopCompetitionCountdown();
    competitionOver = false;

    // reset first-interaction counter
    updateStats();

    if (el.question) el.question.textContent = `Q${data.seq} [#${data.case_id}] — Cards: ${data.question}`;
    if (el.cards) {
      el.cards.innerHTML = '';
      data.images.forEach(c => {
        const img = document.createElement('img');
        img.src = c.url; img.alt = c.code; img.className = 'card';
        const rankToken = c.code.startsWith('10') ? 'T' : c.code[0];
        img.title = `Click to insert ${rankToken}`;
        img.addEventListener('click', () => insertAtCursor(rankToken));
        el.cards.appendChild(img);
      });
    }
    if (el.answer){ el.answer.value = ''; el.answer.focus(); }
    timerStart();

    if (data.pool_done && el.msg) {
      el.msg.textContent = `All questions in your Custom pool are done.`;
      el.msg.className = 'status status-success';
    }
  }

  function showError(message) {
    if (!el.msg) return;
    el.msg.textContent = message;
    el.msg.className = 'status status-error';
  }

  // ---------- Deal ----------
// static/js/script.js - Fix competition handling
  async function deal() {
      if (competitionOver) return;
  
      clearPanels();
      if (el.cards) el.cards.innerHTML = '';
      if (el.question) el.question.textContent = 'Dealing…';
      revealedThisQuestion = false;
      currentStatus = 'pending';
  
      const themeVal = safeValue(el.theme, 'classic');
      const levelVal = safeValue(el.level, 'easy');
  
      try {
          const r = await fetch(`/api/game24/next?theme=${encodeURIComponent(themeVal)}&level=${encodeURIComponent(levelVal)}&seq=${currentSeq}&client_id=${encodeURIComponent(CLIENT_ID)}&guest_id=${encodeURIComponent(GUEST_ID)}`);
  
          if (r.ok) {
              const data = await r.json();
              handleNewPuzzleData(data);
              setControlsEnabled(true);
              return;
          }
  
          let data = null;
          try { data = await r.json(); } catch { }
  
          if (r.status === 403 && data && data.competition_over) {
              endCompetitionUI();
              currentStatus = 'idle';
              return;
          }
  
          if (r.status === 400 && data && data.pool_done) {
              if (el.question) el.question.textContent = '';
              const list = (data.unfinished || []).map(id => `#${id}`).join(', ');
              el.msg.textContent = list && list.length
                  ? `✅ All questions in this pool have been shown once. Unfinished: ${list}`
                  : `✅ All questions in this pool have been shown once.`;
              el.msg.className = 'status status-success';
              setControlsEnabled(false);
              currentStatus = 'idle';
              return;
          }
  
          const lvl = levelVal;
          const missingPool = (r.status === 400 && data && typeof data.error === 'string' && /No (custom|competition) pool set/i.test(data.error));
          if (missingPool && (lvl === 'custom' || lvl === 'competition')) {
              const modeLabel = (lvl === 'competition') ? 'Competition' : 'Custom';
              if (el.question) el.question.textContent = '';
              showError(`${modeLabel} pool is empty. Open "Settings", enter up to 25 Case IDs, then click "Save Pool".`);
              const settings = document.querySelector('details.settings');
              if (settings) settings.open = true;
              const row = document.getElementById('casePoolRow');
              if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
              const inp = document.getElementById('casePoolInput');
              if (inp) inp.focus();
              currentStatus = 'idle';
              return;
          }
  
          if (el.question) el.question.textContent = '';
          showError((data && data.error) ? `Failed to get a new question. ${data.error}` : 'Failed to get a new question.');
          currentStatus = 'idle';
      } catch (e) {
          console.error("Deal error:", e);
          if (el.question) el.question.textContent = '';
          showError('Failed to get a new question. See console for details.');
          currentStatus = 'idle';
      }
  }

   async function showPoolReportNow(){
     try{
       const r = await fetch('/api/game24/pool_report');
       const j = await r.json();
       if(!j.ok){ throw new Error('pool_report failed'); }
       const s = j.stats || {};
       renderSummary(s, totalSeconds); // re-use your existing summary modal
     }catch(e){
       console.error(e);
       alert('Could not load pool report.');
     }
   }

  // ---------- Load by Case ID ----------
  async function loadCaseById() {
    const inputEl = document.getElementById('caseIdInput');
    const caseIdInput = inputEl ? inputEl.value : '';
    const caseId = parseInt(caseIdInput, 10);

    if (!caseIdInput || Number.isNaN(caseId)) { showError('Please enter a valid number for the Case ID.'); return; }
    if (caseId < 1 || caseId > 1820) { showError('Please enter a Case ID between 1 and 1820.'); return; }

    if (el.msg) el.msg.textContent = '';
    clearPanels();
    if (el.cards) el.cards.innerHTML = '';
    if (el.question) el.question.textContent = `Loading Case #${caseId}…`;
    currentStatus = 'pending';

    try {
      const themeVal = safeValue(el.theme, 'classic');
      const levelVal = safeValue(el.level, 'easy');
      const r = await fetch(`/api/game24/next?theme=${encodeURIComponent(themeVal)}&level=${encodeURIComponent(levelVal)}&case_id=${caseId}&seq=${currentSeq}&client_id=${encodeURIComponent(CLIENT_ID)}&guest_id=${encodeURIComponent(GUEST_ID)}`);
      if (!r.ok) {
        const errorData = await r.json().catch(()=>({}));
        throw new Error(errorData.error || 'Case not found.');
      }
      const data = await r.json();
      handleNewPuzzleData(data);
    } catch (e) {
      console.error("Load case error:", e);
      showError(`Error: ${e.message}`);
      currentStatus = 'idle';
    }
  }

  // ---------- Check ----------
  async function check(){
    if(!current) return;
    const expr = el.answer ? el.answer.value.trim() : ''; if(!expr) return;
    try{
      const r = await fetch('/api/game24/check', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ values: current.values, answer: preprocess(expr), client_id: CLIENT_ID,  guest_id: GUEST_ID })
      });
      const res = await r.json();
      if(res.ok){
        if (el.feedback){ el.feedback.textContent='✓'; el.feedback.className='answer-feedback success-icon'; }
        if (el.msg){ el.msg.textContent = (res.kind==='no-solution') ? 'Correct: no solution' : '24! Correct!'; el.msg.className = 'status status-success'; }
        // Count on first interaction only
        if (!revealedThisQuestion && currentStatus==='pending') { stats.played++; }
        stats.solved++; currentStatus='solved'; timerStop(); addToTotalTime(); updateStats();
        if (autoDealEnabled) { setTimeout(deal, 1500); }
      } else {
        if (el.feedback){ el.feedback.textContent='✗'; el.feedback.className='answer-feedback error-icon'; }
        if (el.msg){ let m = res.reason || 'Try again!'; if(typeof res.value==='number') m += ` (got ${res.value})`; el.msg.textContent = m; el.msg.className = 'status status-error'; }
        if (!revealedThisQuestion && currentStatus==='pending') { stats.played++; updateStats(); }
      }
    }catch(e){ showError('Error checking answer'); }
  }

  // ---------- Help ----------
  async function help(all=false){
    if(!current) return;
    if (helpDisabled) {
      if (el.solutionPanel) el.solutionPanel.style.display='block';
      if (el.solutionMsg) el.solutionMsg.textContent='Help is disabled in competition mode.';
      return;
    }
    try{
      const r = await fetch('/api/game24/help', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ values: current.values, all, client_id: CLIENT_ID,  guest_id: GUEST_ID })
      });
      if(!r.ok) throw new Error('help fetch');
      const data = await r.json();
      if (el.msg) el.msg.textContent='';
      if (el.solutionPanel) el.solutionPanel.style.display='block';
      if(!data.has_solution){
        if (el.solutionMsg) el.solutionMsg.textContent='No solution.';
      } else if (all){
        if (el.solutionMsg){
          el.solutionMsg.innerHTML = `Solutions (${data.solutions.length}):`;
          const grid=document.createElement('div'); grid.className='solution-grid';
          data.solutions.forEach(s=>{ const d=document.createElement('div'); d.textContent=s; grid.appendChild(d); });
          el.solutionMsg.appendChild(grid);
        }
      } else {
        if (el.solutionMsg) el.solutionMsg.innerHTML = `<strong>Solution:</strong> ${data.solutions[0]}`;
      }
      if (currentStatus==='pending') { stats.played++; updateStats(); }
      if(!revealedThisQuestion){ stats.revealed++; revealedThisQuestion=true; updateStats(); }
      currentStatus='revealed';
    }catch(e){
      if (el.solutionPanel) el.solutionPanel.style.display='block';
      if (el.solutionMsg) el.solutionMsg.textContent='Error loading help';
    }
  }


  // ---------- Operator panel ----------
  on($('#ops'), 'click', (e)=>{
    const tgt = e.target;
    if(!(tgt instanceof HTMLButtonElement)) return;
    const op = tgt.dataset.op;
    if(op==='(')    return insertAtCursor('()');
    if(op==='*')    return insertAtCursor('*');
    if(op==='/')    return insertAtCursor('/');
    return insertAtCursor(op);
  });

  // ---------- Buttons ----------
  on($('#backspace'), 'click', backspaceAtCursor);
  on($('#clear'), 'click', clearAnswer);
  on($('#next'), 'click', deal);
  on($('#check'), 'click', check);
  on($('#no'), 'click', ()=>{ if(el.answer){ el.answer.value='no solution'; check(); } });
  on($('#help'), 'click', ()=>help(false));
  on($('#helpAll'), 'click', ()=>help(true));

   // optional binding (won’t error if button doesn’t exist)
   const btn = document.getElementById('poolStatusBtn');
   if (btn) btn.addEventListener('click', showPoolReportNow);


  // Restart
  on(el.restart, 'click', ()=>{
    if(confirm('Are you sure you want to restart? This will reset all game statistics.')) {
      fetch('/api/game24/restart', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ client_id: CLIENT_ID,  guest_id: GUEST_ID })
      })
        .then(() => {
          currentSeq = 0; current = null; currentStatus = 'idle'; revealedThisQuestion = false;
          timerStop(); tStart = 0;
          if (el.cards) el.cards.innerHTML = '';
          if (el.question) el.question.textContent = '';
          clearPanels();

          stopCompetitionCountdown();
          competitionOver = false;
          setControlsEnabled(true);

          resetStats();
          deal();
        })
        .catch(e => console.error('Restart error:', e));
    }
  });

  // Exit → summary
  on(el.exit, 'click', ()=>{
      if(!confirm('Exit the session and see your summary?')) return;
      addToTotalTime();
      stopCompetitionCountdown();
      competitionOver = false;
      window.exitAndShowSummary();  // Use the global function that already works
  });

  // ---------- Shortcuts ----------
  document.addEventListener('keydown',(e)=>{
    if (!e || !e.key) return;
    if (e.target === el.answer && e.key === 'Enter') { e.preventDefault(); check(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k=e.key.toLowerCase();
    if(k==='d'){ e.preventDefault(); deal(); }
    else if(k==='n'){ e.preventDefault(); if(el.answer){ el.answer.value='no solution'; check(); } }
    else if(k==='h' && e.shiftKey){ e.preventDefault(); help(true); }
    else if(k==='h'){ e.preventDefault(); help(false); }
    else if(k==='r'){ e.preventDefault(); if(el.restart) el.restart.click(); }
    else if(k==='x'){ e.preventDefault(); if(el.exit) el.exit.click(); }
  });

  // ---------- Persist settings ----------
  const tSaved=localStorage.getItem('theme'); if(tSaved && el.theme) el.theme.value=tSaved;
  const lSaved=localStorage.getItem('level'); if(lSaved && el.level) el.level.value=lSaved;
  const poolSaved = localStorage.getItem('casePoolText'); if (poolSaved && casePoolInput) casePoolInput.value = poolSaved;
  const durSaved=localStorage.getItem('compDurationMin'); if (durSaved && compDurationInput) compDurationInput.value = durSaved;

  on($('#theme'), 'change', ()=>{ localStorage.setItem('theme',$('#theme').value); });
  on($('#level'), 'change', ()=>{
    localStorage.setItem('level',$('#level').value);
    updateCasePoolUI();
    if ($('#level').value !== 'competition') { stopCompetitionCountdown(); competitionOver = false; setControlsEnabled(true); }
  });

  // Save pool
  on(saveCasePoolBtn, 'click', async ()=>{
    const level = el.level ? el.level.value : 'easy';
    if (level !== 'custom' && level !== 'competition') { showError('Select "custom" or "competition" first.'); return; }
    const ids = parseCasePool(casePoolInput ? casePoolInput.value : '');
    if (ids.length === 0) { showError('Enter 1–25 valid Case IDs (1–1820).'); return; }
    if (casePoolInput) localStorage.setItem('casePoolText', casePoolInput.value);

    const payload = { mode: level, case_ids: ids, client_id: CLIENT_ID,  guest_id: GUEST_ID };
    let durMsg = '';
    if (level === 'competition') {
      let mins = 5;
      if (compDurationInput) { const v = parseInt(compDurationInput.value, 10); if (Number.isFinite(v)) mins = v; }
      mins = Math.max(1, Math.min(60, mins));
      payload.duration_sec = mins * 60;
      durMsg = ` (duration ${mins} min)`;
      if (compDurationInput) localStorage.setItem('compDurationMin', String(mins));
    }

    try {
      const r = await fetch('/api/game24/pool', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      if (!r.ok) {
        const er = await r.json().catch(()=>({error:'pool set failed'}));
        throw new Error(er.error || 'Failed to set pool');
      }
      if (el.msg) el.msg.textContent = `Pool saved (${ids.length} case IDs) for ${level}${durMsg}. Please click Deal to start`;
      if (currentStatus === 'idle') deal();
    } catch (e) {
      showError(e.message);
    }
  });

  // Auto-deal
  const autoDealSaved = localStorage.getItem('autoDeal');
  if (autoDealSaved !== null) {
    const v = (autoDealSaved === 'true');
    const cb = document.getElementById('autoDeal');
    if (cb) { cb.checked = v; autoDealEnabled = v; }
  } else {
    const cb = document.getElementById('autoDeal');
    if (cb) { cb.checked = true; }
    autoDealEnabled = true;
    localStorage.setItem('autoDeal', 'true');
  }
  on(document.getElementById('autoDeal'), 'change', () => {
      const v = document.getElementById('autoDeal').checked;
      localStorage.setItem('autoDeal', v);
      autoDealEnabled = v;
      if (autoDealEnabled && currentStatus === 'idle') { deal(); }
  });

  // How-to modal tabs
  on(document.getElementById('howtoLink'), 'click', ()=>{ const b=$('#modalBackdrop'); if (b) b.style.display='flex'; });
  on(document.getElementById('modalClose'), 'click', ()=>{ const b=$('#modalBackdrop'); if (b) b.style.display='none'; });
  on(document.getElementById('modalBackdrop'), 'click', (e)=>{ if(e.target===document.getElementById('modalBackdrop')) { e.currentTarget.style.display='none'; } });
  document.querySelectorAll('.tab-link').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.tab-link').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(content => content.style.display = 'none');
      const tabId = button.getAttribute('data-tab');
      const tab = document.getElementById(tabId);
      if (tab) tab.style.display = 'block';
      button.classList.add('active');
    });
  });

  // Summary modal controls
  on(document.getElementById('summaryClose'), 'click', ()=>{ const b = document.getElementById('summaryBackdrop'); if (b) b.style.display='none'; });
  on(document.getElementById('summaryOk'), 'click', ()=>{ const b = document.getElementById('summaryBackdrop'); if (b) b.style.display='none'; });

  // Case ID Enter + button
  const caseIdEl = document.getElementById('caseIdInput');
  if (caseIdEl) {
    caseIdEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); loadCaseById(); }
    });
  }
  on(document.getElementById('loadCaseBtn'), 'click', loadCaseById);

  // ---------- go ----------
  updateCasePoolUI();
  setTimeout(()=>{ try { deal(); } catch(e){ console.error(e); } }, 0);
  updateStats();

})(); // end IIFE
}); // End of DOMContentLoaded
/* ===== SUMMARY + EXIT (anywhere-safe) ===== */
(function initSummaryUI(){
  // --- IDs (per-tab/person), no redeclare: use window.*
  try {
    window.CLIENT_ID = window.CLIENT_ID
      || sessionStorage.getItem('client_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    sessionStorage.setItem('client_id', window.CLIENT_ID);
  } catch (e) {
    window.CLIENT_ID = window.CLIENT_ID || String(Math.random());
  }
  try {
    window.GUEST_ID = window.GUEST_ID
      || localStorage.getItem('guest_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    localStorage.setItem('guest_id', window.GUEST_ID);
  } catch (e) {
    window.GUEST_ID = window.GUEST_ID || String(Math.random());
  }

  // --- modal
  function ensureSummaryModal() {
    let modal = document.getElementById('summaryModal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'summaryModal';
    Object.assign(modal.style, {position:'fixed', inset:'0', background:'rgba(0,0,0,.45)', display:'none', zIndex:'9999'});
    modal.innerHTML = `
      <div style="background:#fff; width:min(740px, 92%); max-height:80vh; overflow:auto; margin:6vh auto; padding:16px; border-radius:12px; box-shadow:0 12px 40px rgba(0,0,0,.25)">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px">
          <strong>Session Summary</strong>
          <button id="summaryCloseBtn" type="button" style="padding:6px 10px; border:1px solid #ccc; background:#fafafa; border-radius:8px; cursor:pointer">Close</button>
        </div>
        <div id="summaryBody"></div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e)=>{ if (e.target === modal) hideSummaryModal(); });
    const close = modal.querySelector('#summaryCloseBtn');
    if (close) close.addEventListener('click', hideSummaryModal);
    return modal;
  }
  function showSummaryModal(html) {
    const m = ensureSummaryModal();
    const body = m.querySelector('#summaryBody');
    if (body) body.innerHTML = html || '';
    m.style.display = 'block';
  }
  function hideSummaryModal() {
    const m = document.getElementById('summaryModal');
    if (m) m.style.display = 'none';
  }

  function getTotalSeconds() {
    if (typeof window.totalSeconds !== 'undefined') return window.totalSeconds|0;
    if (typeof window.__totalSeconds !== 'undefined') return window.__totalSeconds|0;
    return 0;
  }

  // static/js/script.js - Fix the summary rendering
  function renderSummary(stats, totalSecs) {
      const n = (x) => (x == null ? 0 : Number(x));
      const pad2 = (x) => (x < 10 ? `0${x}` : `${x}`);
      const fmtTime = (secs) => {
          secs = Math.max(0, Math.floor(+secs || 0));
          const h = Math.floor(secs / 3600), 
                m = Math.floor((secs % 3600) / 60), 
                s = secs % 60;
          return h > 0 ? `${pad2(h)}:${pad2(m)}:${pad2(s)}` : `${pad2(m)}:${pad2(s)}`;
      };
  
      const totals = {
          played: n(stats.played),
          solved: n(stats.solved),
          revealed: n(stats.revealed),
          skipped: n(stats.skipped),
          timeStr: fmtTime(totalSecs || 0)
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
      const helpSingle = n(stats.help_single);
      const helpAll = n(stats.help_all);
      const attempts = n(stats.answer_attempts);
      const correct = n(stats.answer_correct);
      const wrong = n(stats.answer_wrong);
      const dealSwaps = n(stats.deal_swaps);
  
      const actionsBlock = `
          <hr />
          <div style="margin:6px 0"><strong>Actions</strong></div>
          <table style="width:100%; border-collapse:collapse">
              <tbody>
                  <tr><td>Answer attempts</td><td style="text-align:right">${attempts}</td></tr>
                  <tr><td>&nbsp;&nbsp;• Correct</td><td style="text-align:right">${correct}</td></tr>
                  <tr><td>&nbsp;&nbsp;• Wrong / Invalid</td><td style="text-align:right">${wrong}</td></tr>
                  <tr><td>Help used</td><td style="text-align:right">${helpSingle}</td></tr>
                  <tr><td>Help-All used</td><td style="text-align:right">${helpAll}</td></tr>
                  <tr><td>Deal swaps (no action before next deal)</td><td style="text-align:right">${dealSwaps}</td></tr>
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
          <div style="display:grid; grid-template-columns: repeat(5, auto); gap:10px; margin-bottom:8px">
              <div><strong>Played:</strong> ${totals.played}</div>
              <div><strong>Solved:</strong> ${totals.solved}</div>
              <div><strong>Revealed:</strong> ${totals.revealed}</div>
              <div><strong>Skipped:</strong> ${totals.skipped}</div>
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
      const r = await fetch('/api/game24/exit', {
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

  function showPoolDoneMessage(unfinishedArr) {
    const msgEl = document.getElementById('statusMsg') || document.querySelector('.status') || document.getElementById('message');
    const list = (unfinishedArr||[]).map(id=>`#${id}`).join(', ');
    if (msgEl) {
      msgEl.textContent = list ? `✅ All questions in your pool are done. Unfinished: ${list}` : `✅ All questions in your pool are done.`;
      msgEl.className = 'status status-success';
    } else {
      alert(list ? `All questions are done.\nUnfinished: ${list}` : `All questions are done.`);
    }
    // Always open the full report
    exitAndShowSummary();
  }
  window.showPoolDoneMessage = showPoolDoneMessage;

  function bindExitButtons(){
    const ids = ['exitBtn','exit','btnExit','buttonExit'];
    let found = false;
    ids.forEach(id=>{
      const b = document.getElementById(id);
      if (b && !b.__boundExit) {
        b.addEventListener('click', function(ev){ ev.preventDefault(); exitAndShowSummary(); });
        b.__boundExit = true;
        found = true;
      }
    });
    if (!found) {
      // keyboard fallback
      window.addEventListener('keydown', (e)=>{
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key==='X' || e.key==='x')) {
          e.preventDefault();
          exitAndShowSummary();
        }
      });
      console.warn('Exit button not found. Use Ctrl+Shift+X to open summary, or call window.exitAndShowSummary().');
    }
  }

  // Bind once DOM is ready (safe no matter where we pasted)
  if (document.readyState !== 'loading') bindExitButtons();
  else document.addEventListener('DOMContentLoaded', bindExitButtons);
})();

/* ---- Force client_id / guest_id onto ALL /api/* requests ---- */
(function patchFetchForClientIds(){
  // make sure these exist
  try {
    window.CLIENT_ID = window.CLIENT_ID
      || sessionStorage.getItem('client_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    sessionStorage.setItem('client_id', window.CLIENT_ID);
  } catch(e) { window.CLIENT_ID = window.CLIENT_ID || String(Math.random()); }

  try {
    window.GUEST_ID = window.GUEST_ID
      || localStorage.getItem('guest_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    localStorage.setItem('guest_id', window.GUEST_ID);
  } catch(e) { window.GUEST_ID = window.GUEST_ID || String(Math.random()); }

  const origFetch = window.fetch;
  window.fetch = function(input, init = {}) {
    try {
      let url = (typeof input === 'string') ? input : input.url;
      // Only touch our API
      if (url && (url.indexOf('/api/game24') === 0 || url.indexOf('/api/') === 0)) {
        const isGet = !init.method || String(init.method).toUpperCase() === 'GET';
        const cid = window.CLIENT_ID, gid = window.GUEST_ID;

        if (isGet) {
          const u = new URL(url, location.origin);
          if (!u.searchParams.has('client_id')) u.searchParams.set('client_id', cid);
          if (!u.searchParams.has('guest_id'))  u.searchParams.set('guest_id',  gid);
          url = u.pathname + u.search;
          input = url; // replace input with updated URL
        } else {
          init.headers = Object.assign({'Content-Type':'application/json'}, init.headers || {});
          let body = {};
          if (init.body) {
            try { body = JSON.parse(init.body); } catch {}
          }
          if (!('client_id' in body)) body.client_id = cid;
          if (!('guest_id'  in body)) body.guest_id  = gid;
          init.body = JSON.stringify(body);
        }
      }
    } catch (e) {
      console.warn('fetch patch failed (safe to ignore):', e);
    }
    return origFetch(input, init);
  };
})();

/* --- Force IDs & sync footer with server stats on every /api/* call --- */
(function patchFetchAndSyncCounters(){
  // stable ids
  try {
    window.CLIENT_ID = window.CLIENT_ID
      || sessionStorage.getItem('client_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    sessionStorage.setItem('client_id', window.CLIENT_ID);
  } catch(e){ window.CLIENT_ID = window.CLIENT_ID || String(Math.random()); }
  try {
    window.GUEST_ID = window.GUEST_ID
      || localStorage.getItem('guest_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    localStorage.setItem('guest_id', window.GUEST_ID);
  } catch(e){ window.GUEST_ID = window.GUEST_ID || String(Math.random()); }

  // small helper to set footer counters (adjust IDs to your DOM if different)
  function updateFooterFromStats(st) {
    const setText = (id,val)=>{ const el=document.getElementById(id); if (el) el.textContent = String(val); };
    if (!st) return;
    setText('playedCount',  st.played ?? 0);
    setText('solvedCount',  st.solved ?? 0);
    setText('revealedCount',st.revealed ?? 0);
    setText('skippedCount', st.skipped ?? 0);
    // if you show time separately, keep your timer logic as-is
  }

  const origFetch = window.fetch;
  window.fetch = function(input, init = {}) {
    let url = (typeof input === 'string') ? input : input.url;

    // attach ids
    try {
      if (url && (url.indexOf('/api/game24') === 0 || url.indexOf('/api/') === 0)) {
        const isGet = !init.method || String(init.method).toUpperCase()==='GET';
        if (isGet) {
          const u = new URL(url, location.origin);
          if (!u.searchParams.has('client_id')) u.searchParams.set('client_id', window.CLIENT_ID);
          if (!u.searchParams.has('guest_id'))  u.searchParams.set('guest_id',  window.GUEST_ID);
          url = u.pathname + u.search;
          input = url;
        } else {
          init.headers = Object.assign({'Content-Type':'application/json'}, init.headers || {});
          let body = {};
          if (init.body) { try { body = JSON.parse(init.body); } catch {} }
          if (!('client_id' in body)) body.client_id = window.CLIENT_ID;
          if (!('guest_id'  in body)) body.guest_id  = window.GUEST_ID;
          init.body = JSON.stringify(body);
        }
      }
    } catch(e){ /* ignore */ }

    // call through
    return origFetch(input, init).then((resp)=>{
      try {
        const isApi = url && (url.indexOf('/api/game24/') === 0 || url.indexOf('/api/') === 0);
        if (!isApi) return resp;

        // when a new hand is dealt successfully, clear local "hand interacted" if you track it
        if (url.startsWith('/api/game24/next') && resp.ok) {
          window.__handInteracted = false;
        }

        // sync footer from any JSON with .stats
        const ctype = resp.headers.get('content-type') || '';
        if (ctype.includes('application/json')) {
          resp.clone().json().then((j)=>{
            if (j && j.stats) updateFooterFromStats(j.stats);
          }).catch(()=>{});
        }
      } catch(e){ /* ignore */ }
      return resp;
    });
  };
})();
/* ---------- FORCE SERVER COUNTERS INTO FOOTER ---------- */
(function fixCountersToServerTruth(){
  // Stable IDs
  try {
    window.CLIENT_ID = window.CLIENT_ID
      || sessionStorage.getItem('client_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    sessionStorage.setItem('client_id', window.CLIENT_ID);
  } catch(e){ window.CLIENT_ID = window.CLIENT_ID || String(Math.random()); }
  try {
    window.GUEST_ID = window.GUEST_ID
      || localStorage.getItem('guest_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    localStorage.setItem('guest_id', window.GUEST_ID);
  } catch(e){ window.GUEST_ID = window.GUEST_ID || String(Math.random()); }

  // Update footer DOM from server stats (adjust IDs here if your HTML uses different ones)
  function setCountersFromStats(st) {
    if (!st) return;
    const setText = (id,val)=>{ const el=document.getElementById(id); if (el) el.textContent = String(val ?? 0); };
    setText('playedCount',  st.played);
    setText('solvedCount',  st.solved);
    setText('revealedCount',st.revealed);
    setText('skippedCount', st.skipped);
    // keep a copy for debugging
    window.__lastServerStats = st;
  }

  async function refetchStats() {
    try {
      const r = await fetch(`/api/game24/pool_report?client_id=${encodeURIComponent(window.CLIENT_ID)}&guest_id=${encodeURIComponent(window.GUEST_ID)}`);
      if (!r.ok) return;
      const j = await r.json();
      if (j && j.ok && j.stats) setCountersFromStats(j.stats);
    } catch {}
  }

  // Patch fetch: attach IDs + apply counters from any response that has .stats
  const origFetch = window.fetch;
  window.fetch = function(input, init = {}) {
    let url = (typeof input === 'string') ? input : input.url;

    // Attach IDs
    try {
      if (url && (url.indexOf('/api/game24') === 0 || url.indexOf('/api/') === 0) ) {
        const isGet = !init.method || String(init.method).toUpperCase() === 'GET';
        if (isGet) {
          const u = new URL(url, location.origin);
          if (!u.searchParams.has('client_id')) u.searchParams.set('client_id', window.CLIENT_ID);
          if (!u.searchParams.has('guest_id'))  u.searchParams.set('guest_id',  window.GUEST_ID);
          url = u.pathname + u.search;  // local var for below
          input = url;                   // replace input with updated URL
        } else {
          init.headers = Object.assign({'Content-Type':'application/json'}, init.headers || {});
          let body = {};
          if (init.body) { try { body = JSON.parse(init.body); } catch {} }
          if (!('client_id' in body)) body.client_id = window.CLIENT_ID;
          if (!('guest_id'  in body)) body.guest_id  = window.GUEST_ID;
          init.body = JSON.stringify(body);
        }
      }
    } catch {}

    // Continue with fetch and then sync counters
    const p = origFetch(input, init);
    try {
      if (url && (url.indexOf('/api/game24') === 0 || url.indexOf('/api/') === 0)) {
        p.then((resp)=>{
          const ctype = resp.headers.get('content-type') || '';
          if (ctype.includes('application/json')) {
            resp.clone().json().then((j)=>{
              if (j && j.stats) {
                // Most endpoints now include stats — use them
                setCountersFromStats(j.stats);
              } else if (/\/api\/\game24\/(check|help)/.test(url)) {
                // Fallback: re-pull stats if this endpoint didn't include them
                setTimeout(refetchStats, 0);
                setTimeout(refetchStats, 150);
              }
            }).catch(()=>{});
          } else if (/\/api\/game24\/(check|help)/.test(url)) {
            // Non-JSON fallback
            setTimeout(refetchStats, 0);
            setTimeout(refetchStats, 150);
          }
        }).catch(()=>{});
      }
    } catch {}
    return p;
  };

  // Also hook the main action buttons to force a re-sync shortly after click,
  // in case older code updates the footer after our fetch hook runs.
  ['checkBtn','helpBtn','helpAllBtn'].forEach((id)=>{
    const el = document.getElementById(id);
    if (el && !el.__syncHooked) {
      el.addEventListener('click', ()=>{ setTimeout(refetchStats, 80); setTimeout(refetchStats, 220); });
      el.__syncHooked = true;
    }
  });

  // When a new hand is dealt, the footer should not change; but we can refetch once to be safe.
  (function hookDeal(){
    const ids = ['dealBtn','deal','btnDeal','buttonDeal'];
    ids.forEach((id)=>{
      const b = document.getElementById(id);
      if (b && !b.__dealSync) {
        b.addEventListener('click', ()=>{ setTimeout(refetchStats, 150); });
        b.__dealSync = true;
      }
    });
  })();

  // First sync on load (in case the page printed cached numbers)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', refetchStats);
  } else {
    refetchStats();
  }
})();

/* ===== Session UX: make refresh behavior clear & controllable ===== */
(function sessionUX(){
  // --- Ensure IDs exist (re-use if already defined) ---
  try {
    window.CLIENT_ID = window.CLIENT_ID
      || sessionStorage.getItem('client_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    sessionStorage.setItem('client_id', window.CLIENT_ID);
  } catch(e){ window.CLIENT_ID = window.CLIENT_ID || String(Math.random()); }

  try {
    window.GUEST_ID = window.GUEST_ID
      || localStorage.getItem('guest_id')
      || (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()));
    localStorage.setItem('guest_id', window.GUEST_ID);
  } catch(e){ window.GUEST_ID = window.GUEST_ID || String(Math.random()); }

  // --- Footer updater (adjust IDs if yours differ) ---
  function updateFooterFromStats(st) {
    if (!st) return;
    const setText = (id,val)=>{ const el=document.getElementById(id); if (el) el.textContent = String(val ?? 0); };
    setText('playedCount',  st.played);
    setText('solvedCount',  st.solved);
    setText('revealedCount',st.revealed);
    setText('skippedCount', st.skipped);
    window.__lastServerStats = st; // handy for debugging
  }
})();

  // --- Top banner UI ---
  function ensureBanner() {
    let b = document.getElementById('sessionBanner');
    if (b) return b;
    b = document.createElement('div');
    b.id = 'sessionBanner';
    Object.assign(b.style, {
      position:'fixed', top:'8px', left:'50%', transform:'translateX(-50%)',
      background:'#fffbe6', color:'#6b5900', border:'1px solid #f0e1a0',
      borderRadius:'8px', padding:'6px 10px', boxShadow:'0 6px 20px rgba(0,0,0,.12)',
      zIndex:'9999', display:'none', alignItems:'center', gap:'8px'
    });
    b.innerHTML = `
      <span id="sessionBannerMsg">Continuing previous session</span>
      <button id="startNewSessionBtn" type="button" style="padding:4px 8px; border:1px solid #d6c26a; background:#fff2b3; border-radius:6px; cursor:pointer">
        Start New Session
      </button>`;
    document.body.appendChild(b);
    const btn = b.querySelector('#startNewSessionBtn');
    if (btn) btn.addEventListener('click', newSession);
    return b;
  }
  function showBanner(msg) {
    const b = ensureBanner();
    const t = b.querySelector('#sessionBannerMsg');
    if (t) t.textContent = msg || 'Continuing previous session';
    b.style.display = 'flex';
  }
  function hideBanner() {
    const b = document.getElementById('sessionBanner');
    if (b) b.style.display = 'none';
  }

  // --- Fetch current stats & decide whether to show banner ---
  async function fetchStatsAndMaybeBanner() {
    try {
      const r = await fetch(`/api/game24/pool_report?client_id=${encodeURIComponent(window.CLIENT_ID)}&guest_id=${encodeURIComponent(window.GUEST_ID)}`);
      if (!r.ok) return;
      const j = await r.json();
      if (!j || !j.ok) return;
      const st = j.stats || {};
      updateFooterFromStats(st);
      const hasProgress = (st.played||0) + (st.solved||0) + (st.revealed||0) + (st.skipped||0) > 0;
      if (hasProgress) showBanner('Continuing previous session');
      else hideBanner();
    } catch(e){ /* ignore */ }
  }

  // --- Start a brand-new session: new client_id + backend /api/restart ---
  async function newSession() {
    if (window.__startingNewSession) return;
    window.__startingNewSession = true;
    try {
      const btn = document.getElementById('startNewSessionBtn');
      if (btn) { btn.disabled = true; btn.textContent = 'Resetting…'; }
  
      // New per-tab client id
      const newId = (crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random());
      sessionStorage.setItem('client_id', newId);
      window.CLIENT_ID = newId;
  
      // Reset that exact session on the server
      const r = await fetch('/api/game24/restart', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          client_id: window.CLIENT_ID,
          guest_id:  window.GUEST_ID || (localStorage.getItem('guest_id') || '')
        })
      });
      if (!r.ok) throw new Error('restart http ' + r.status);
  
      // Make sure we don't auto-reset on reload
      try { localStorage.removeItem('autoResetOnReload'); } catch {}
  
      // Reload WITHOUT any query flags to avoid re-triggering a reset
      location.replace(location.pathname);
    } catch (e) {
      console.error('newSession failed:', e);
      alert('Could not start a new session.');
      window.__startingNewSession = false;
      const btn = document.getElementById('startNewSessionBtn');
      if (btn) { btn.disabled = false; btn.textContent = 'Start New Session'; }
    }
  }
  window.newSession = newSession;


  // --- Optional: auto reset on reload if user opted in or via query param ---
  function hasQueryFlag(name) {
    return new URL(location.href).searchParams.has(name);
  }
  // --- One-shot flags and optional persistent setting ---
  const autoReset = (localStorage.getItem('autoResetOnReload') === '1');
  const oneShot   = (new URL(location.href).searchParams.has('new')
                  || new URL(location.href).searchParams.has('reset'));
  
  // If ?new or ?reset is in the URL, strip it and just sync stats (assume we already reset)
  if (oneShot) {
    // remove the query flags so refreshes are clean
    try { history.replaceState(null, '', location.pathname); } catch {}
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fetchStatsAndMaybeBanner);
    } else {
      fetchStatsAndMaybeBanner();
    }
  } else if (autoReset) {
    // Do a single auto-reset, then consume the flag to avoid loops
    localStorage.setItem('autoResetOnReload', '0');
    newSession();
  } else {
    // Normal behavior: just sync stats/banners
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fetchStatsAndMaybeBanner);
    } else {
      fetchStatsAndMaybeBanner();
    }
  }

/* ---- Also attach IDs to plain XMLHttpRequest calls ---- */
(function patchXHRforClientIds(){
  try {
    window.CLIENT_ID = window.CLIENT_ID || sessionStorage.getItem('client_id') || (crypto?.randomUUID?.() || String(Math.random()));
    sessionStorage.setItem('client_id', window.CLIENT_ID);
  } catch(e){ window.CLIENT_ID = window.CLIENT_ID || String(Math.random()); }
  try {
    window.GUEST_ID  = window.GUEST_ID  || localStorage.getItem('guest_id')  || (crypto?.randomUUID?.() || String(Math.random()));
    localStorage.setItem('guest_id', window.GUEST_ID);
  } catch(e){ window.GUEST_ID = window.GUEST_ID || String(Math.random()); }

  const XHROpen = XMLHttpRequest.prototype.open;
  const XHRSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function(method, url, async, user, password){
    this.__isApi = url && (String(url).indexOf('/api/game24') === 0 || String(url).indexOf('/api/') === 0);
    this.__apiUrl = url;
    return XHROpen.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function(body){
    if (this.__isApi) {
      try {
        // 1) Ensure IDs in URL for GETs (or any request with query)
        try {
          const u = new URL(this.__apiUrl, location.origin);
          if (!u.searchParams.has('client_id')) u.searchParams.set('client_id', window.CLIENT_ID);
          if (!u.searchParams.has('guest_id'))  u.searchParams.set('guest_id',  window.GUEST_ID);
          this.__apiUrl = u.pathname + u.search;
          // Re-open with updated URL if needed
          // NOTE: We can't re-open here easily; most XHR users pass full URL into open already.
          // So best effort: if the original had no query, tack on now.
          if (this.__apiUrl !== arguments[1] && this.readyState === 1) {
            // no-op: many libs call open() again on retry; we leave URL as-is.
          }
        } catch(e){}

        // 2) Inject IDs into body for POST/PUT JSON or FormData
        const ct = (this.getRequestHeader && this.getRequestHeader('Content-Type')) || '';
        if (body instanceof FormData) {
          if (!body.has('client_id')) body.append('client_id', window.CLIENT_ID);
          if (!body.has('guest_id'))  body.append('guest_id',  window.GUEST_ID);
        } else if (typeof body === 'string') {
          // try JSON
          try {
            const obj = JSON.parse(body);
            if (!('client_id' in obj)) obj.client_id = window.CLIENT_ID;
            if (!('guest_id'  in obj)) obj.guest_id  = window.GUEST_ID;
            body = JSON.stringify(obj);
          } catch {
            // x-www-form-urlencoded?
            const params = new URLSearchParams(body);
            if (!params.has('client_id')) params.set('client_id', window.CLIENT_ID);
            if (!params.has('guest_id'))  params.set('guest_id',  window.GUEST_ID);
            body = params.toString();
          }
        }
      } catch(e){}
    }
    return XHRSend.call(this, body);
  };
})();

