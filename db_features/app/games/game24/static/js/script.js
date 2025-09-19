(() => {
  'use strict';

  // ---- bases injected by the template (with fallbacks) ----
  const API_BASE    = (typeof window !== 'undefined' && window.GAME24_API_BASE)    ? window.GAME24_API_BASE    : '/game24/api';
  const STATIC_BASE = (typeof window !== 'undefined' && window.GAME24_STATIC_BASE) ? window.GAME24_STATIC_BASE : '/game24/static/game24';

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
  const $ = (q)=>document.querySelector(q);
  const on = (el, evt, fn) => { if (el) el.addEventListener(evt, fn); };
  const safeValue = (node, def) => (node && node.value !== undefined && node.value !== '') ? node.value : def;
  const preprocess = (s) => s.replace(/\^/g,'**').replace(/×/g,'*').replace(/÷/g,'/');

  // rank→token for images (10→T, 1→A, etc.)
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
  let autoDealEnabled = true;
  let competitionOver = false;

  // ---- timer ----
  let tStart=0, tTick=null;
  const fmt=(ms)=>{ const T=Math.max(0,Math.floor(ms)), t=Math.floor((T%1000)/100), s=Math.floor(T/1000)%60, m=Math.floor(T/60000); return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${t}`; };
  function timerStart(){ timerStop(); tStart=performance.now(); $('#timer').textContent='00:00.0'; tTick=setInterval(()=>{$('#timer').textContent=fmt(performance.now()-tStart)},100); }
  function timerStop(){ if(tTick){ clearInterval(tTick); tTick=null; } }

  // ---- stats (local mirrors; your backend still keeps truth) ----
  const stats = { played:0, solved:0, revealed:0, skipped:0, totalTime:0 };
  function addToTotalTime(){ if(tStart){ stats.totalTime += Math.floor((performance.now()-tStart)/1000); tStart=0; updateStats(); } }
  function updateStats(){
    const S = (id, text) => { const el=document.getElementById(id); if (el) el.textContent=text; };
    S('played',  `Played: ${stats.played}`);
    S('solved',  `Solved: ${stats.solved}`);
    S('revealed',`Revealed: ${stats.revealed}`);
    const m=String(Math.floor(stats.totalTime/60)).padStart(2,'0'), s=String(stats.totalTime%60).padStart(2,'0');
    S('totalTime',`Time: ${m}:${s}`);
  }

  // ---- dom refs ----
  const el = {
    theme: $('#theme'), level: $('#level'),
    question: $('#question'), cards: $('#cards'),
    answer: $('#answer'), feedback: $('#answerFeedback'),
    solutionPanel: $('#solutionPanel'), solutionMsg: $('#solutionMsg'),
    msg: $('#msg'),
    restart: $('#restart'), exit: $('#exit'),
  };

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

    // Try server-provided images
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

    // Derive from question values
    const suits = ['C','D','H','S'];
    const values = Array.isArray(data.question) ? data.question.slice(0,4) : [];
    values.forEach((v,i)=>{
      const code = `${rankTok(v)}${suits[i%4]}`;
      const img = document.createElement('img');
      img.src = `${STATIC_BASE}/assets/images/classic/${code}.png`;
      img.alt = code; img.className = 'card'; img.title = `Click to insert ${rankTok(v)}`;
      img.addEventListener('click', () => insertAtCursor(rankTok(v)));
      el.cards.appendChild(img);
    });
  }

  // ---- deal (with robust seq handling) ----
  async function deal({advanceCounter = true} = {}){
    if (competitionOver) return;

    clearPanels();
    if (el.cards) el.cards.innerHTML = '';
    if (el.question) el.question.textContent = 'Dealing…';
    revealedThisQuestion = false;

    const themeVal = safeValue(el.theme, 'classic');
    const levelVal = safeValue(el.level, 'easy');

    // use nextSeq for the call; do NOT mutate counters until the response is OK
    const seqToSend = nextSeq;

    try{
      const r = await fetch(`${API_BASE}/next?theme=${encodeURIComponent(themeVal)}&level=${encodeURIComponent(levelVal)}&seq=${seqToSend}&client_id=${encodeURIComponent(CLIENT_ID)}&guest_id=${encodeURIComponent(GUEST_ID)}`);
      if (!r.ok) {
        const err = await r.json().catch(()=>({}));
        throw new Error(err.error || `HTTP ${r.status}`);
      }
      const data = await r.json();

      // compute display seq:
      let displaySeq;
      if (Number.isFinite(data.seq)) {
        displaySeq = (data.seq >= 1) ? data.seq : (data.seq + 1); // tolerate 0-based server
      } else {
        displaySeq = seqToSend; // fall back to what we sent
      }

      // only advance local counters if caller allows (loadCaseById uses advanceCounter=false)
      if (advanceCounter) {
        handCounter = displaySeq;
        nextSeq     = handCounter + 1;
      }

      // header text + cards
      if (el.question) {
        const qText = Array.isArray(data.question) ? data.question.join(', ') : (data.question ?? '');
        el.question.textContent = `Q${displaySeq} [#${data.case_id ?? ''}] — Cards: ${qText}`;
      }
      current = data || {};
      if (el.answer) { el.answer.value=''; el.answer.focus(); }
      paintCardsFromPayload(data);
      timerStart();

      // pool done messaging supported
      if (data.pool_done && el.msg) {
        const unfinished = (data.unfinished || []).map(id=>`#${id}`).join(', ');
        el.msg.textContent = unfinished ? `✅ All questions in your pool are done. Unfinished: ${unfinished}` : `✅ All questions in your pool are done.`;
        el.msg.className = 'status status-success';
      }
    }catch(e){
      if (el.question) el.question.textContent = '';
      showError(`Failed to get a new question. ${e.message || e}`);
    }
  }

  // ---- check / help ----
  async function check(){
    if(!current) return;
    const expr = el.answer ? el.answer.value.trim() : '';
    if(!expr) return;
    try{
      const r = await fetch(`${API_BASE}/check`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ values: current.values, answer: preprocess(expr), client_id: CLIENT_ID, guest_id: GUEST_ID })
      });
      const res = await r.json();
      if(res.ok){
        if (el.feedback){ el.feedback.textContent='✓'; el.feedback.className='answer-feedback success-icon'; }
        if (el.msg){ el.msg.textContent = (res.kind==='no-solution') ? 'Correct: no solution' : '24! Correct!'; el.msg.className = 'status status-success'; }
        timerStop(); addToTotalTime();
        // first interaction counts as played; solved++
        if (!revealedThisQuestion) { stats.played++; }
        stats.solved++; updateStats();

        // tiny celebration
        try { confettiBurst(); } catch {}

        if (autoDealEnabled) setTimeout(()=>deal({advanceCounter:true}), 1200);
      } else {
        if (el.feedback){ el.feedback.textContent='✗'; el.feedback.className='answer-feedback error-icon'; }
        let msg = res.reason || 'Try again!';
        if (typeof res.value === 'number') msg += ` (got ${res.value})`;
        if (el.msg){ el.msg.textContent = msg; el.msg.className = 'status status-error'; }
        if (!revealedThisQuestion) { stats.played++; updateStats(); }
      }
    }catch{ showError('Error checking answer'); }
  }

  async function help(all=false){
    if(!current) return;
    try{
      const r = await fetch(`${API_BASE}/help`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ values: current.values, all, client_id: CLIENT_ID, guest_id: GUEST_ID })
      });
      if(!r.ok) throw new Error('help http ' + r.status);
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
      if (!revealedThisQuestion) { stats.played++; stats.revealed++; revealedThisQuestion = true; updateStats(); }
    }catch{ if (el.solutionPanel) el.solutionPanel.style.display='block'; if (el.solutionMsg) el.solutionMsg.textContent='Error loading help'; }
  }

  // ---- load by Case ID (does NOT advance Q counter) ----
  async function loadCaseById(){
    const val = ($('#caseIdInput') && $('#caseIdInput').value) || '';
    const id = parseInt(val, 10);
    if (!val || Number.isNaN(id) || id < 1 || id > 1820) { showError('Please enter a Case ID (1–1820)'); return; }

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

      // DO NOT advance counters here; just paint and label as the current hand
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

  // ---- restart / exit ----
  async function restartGame(){
    if(!confirm('Restart and reset all stats?')) return;
    try {
      const r = await fetch(`${API_BASE}/restart`, { method:'POST' });
      const j = await r.json();
      // reset local mirrors + counters
      current = null;
      revealedThisQuestion = false;
      handCounter = 0;
      nextSeq = 1;
      stats.played = stats.solved = stats.revealed = stats.skipped = stats.totalTime = 0;
      updateStats();
      if (el.cards) el.cards.innerHTML='';
      if (el.question) el.question.textContent='';
      clearPanels();
      // fresh deal will show Q1
      deal({advanceCounter:true});
    } catch (e) {
      showError('Could not restart.');
    }
  }

  async function exitGame(){
    if(!confirm('Exit and see your session summary?')) return;
    try {
      // ask backend for summary and redirect target
      const r = await fetch(`${API_BASE}/exit`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ client_id: CLIENT_ID, guest_id: GUEST_ID }) });
      if (!r.ok) throw new Error('exit http '+r.status);
      const j = await r.json();
      if (j && j.ok && j.next_url) {
        window.location.href = j.next_url;
      } else {
        // no redirect—just go home
        window.location.href = '/';
      }
    } catch {
      window.location.href = '/';
    }
  }

  // ---- operator panel / buttons / shortcuts ----
  on($('#ops'), 'click', (e)=>{
    const tgt = e.target;
    if(!(tgt instanceof HTMLButtonElement)) return;
    const op = tgt.dataset.op;
    if(op==='(') return insertAtCursor('()');
    if(op==='*') return insertAtCursor('*');
    if(op==='/') return insertAtCursor('/');
    insertAtCursor(op);
  });
  on($('#backspace'), 'click', backspaceAtCursor);
  on($('#clear'), 'click', clearAnswer);
  on($('#next'), 'click', ()=>deal({advanceCounter:true}));
  on($('#check'), 'click', check);
  on($('#no'), 'click', ()=>{ if(el.answer){ el.answer.value='no solution'; check(); } });
  on($('#help'), 'click', ()=>help(false));
  on($('#helpAll'), 'click', ()=>help(true));
  on($('#loadCaseBtn'), 'click', loadCaseById);
  const caseIdEl = $('#caseIdInput');
  if (caseIdEl) on(caseIdEl, 'keydown', (e)=>{ if (e.key==='Enter'){ e.preventDefault(); loadCaseById(); }});

  on(el.restart, 'click', restartGame);
  on(el.exit, 'click', exitGame);

  document.addEventListener('keydown',(e)=>{
    if (e.target === el.answer && e.key === 'Enter') { e.preventDefault(); check(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k==='d') { e.preventDefault(); deal({advanceCounter:true}); }
    else if (k==='n'){ e.preventDefault(); if(el.answer){ el.answer.value='no solution'; check(); } }
    else if (k==='h' && e.shiftKey){ e.preventDefault(); help(true); }
    else if (k==='h'){ e.preventDefault(); help(false); }
    else if (k==='r'){ e.preventDefault(); restartGame(); }
    else if (k==='x'){ e.preventDefault(); exitGame(); }
  });

  // ---- settings / auto-deal ----
  const autoDealSaved = localStorage.getItem('autoDeal');
  if (autoDealSaved !== null) {
    const v = (autoDealSaved === 'true');
    const cb = $('#autoDeal');
    if (cb) { cb.checked = v; }
    autoDealEnabled = v;
  } else {
    const cb = $('#autoDeal');
    if (cb) cb.checked = true;
    autoDealEnabled = true;
    localStorage.setItem('autoDeal','true');
  }
  on($('#autoDeal'),'change',()=> {
    const v = $('#autoDeal').checked;
    localStorage.setItem('autoDeal', String(v));
    autoDealEnabled = v;
  });

  // ---- little celebration on correct answer ----
  function confettiBurst(){
    const N = 20;
    for (let i=0;i<N;i++){
      const s = document.createElement('span');
      s.className = 'confetti-bit';
      s.style.left = (50 + (Math.random()*40-20)) + 'vw';
      s.style.top = '20vh';
      s.style.transform = `rotate(${Math.random()*360}deg)`;
      s.style.animationDuration = (0.8 + Math.random()*0.6) + 's';
      document.body.appendChild(s);
      setTimeout(()=>s.remove(), 1200);
    }
  }

  // ---- go ----
  // Make sure we deal *once* on load, and that first label is Q1.
  // We leave handCounter=0; nextSeq=1; the first successful deal will display Q1.
  updateStats();
  setTimeout(()=>deal({advanceCounter:true}), 0);
})();

