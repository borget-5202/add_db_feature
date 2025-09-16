(() => {
  'use strict';

  const API_BASE = window.GAME24_API_BASE || '/count_by_2s/api';
  const FIRST    = window.__FIRST_PAYLOAD__ || null;

  const $ = (q)=>document.querySelector(q);
  const on = (el, evt, fn) => el && el.addEventListener(evt, fn);

  const el = {
    level: $('#level'),
    question: $('#question'),
    cards: $('#cards'),
    answer: $('#answer'),
    feedback: $('#answerFeedback'),
    solutionPanel: $('#solutionPanel'),
    solutionMsg: $('#solutionMsg'),
    msg: $('#msg'),
    timer: $('#timer'),
    restart: $('#restart'),
    exit: $('#exit'),
    played: $('#played'),
    solved: $('#solved'),
    revealed: $('#revealed'),
    total: $('#totalTime'),
  };
  const btn = {
    clear: $('#clear'),
    next: $('#next'),
    check: $('#check'),
    help: $('#help'),
    backspace: $('#backspace'),
  };

  // --- stats + timer
  const stats = { played:0, solved:0, revealed:0, skipped:0, totalTime:0 };
  let tStart = 0, tTick = null, current = null, currentSeq = 0;

  async function fetchJSON(url, opts, retries = 2, backoffMs = 400) {
    for (let i = 0; i <= retries; i++) {
      try {
        const r = await fetch(url, opts);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return await r.json();
      } catch (e) {
        if (i === retries) throw e;
        await new Promise(res => setTimeout(res, backoffMs * (i + 1)));
      }
    }
  }
  function fmt(ms){
    const T=Math.max(0,Math.floor(ms)), t=Math.floor((T%1000)/100), s=Math.floor(T/1000)%60, m=Math.floor(T/60000);
    return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${t}`;
  }
  function timerStart(){
    timerStop();
    tStart = performance.now();
    el.timer && (el.timer.textContent = '00:00.0');
    tTick = setInterval(()=>{ el.timer && (el.timer.textContent = fmt(performance.now() - tStart)); }, 100);
  }
  function timerStop(){ if (tTick) { clearInterval(tTick); tTick = null; } }
  function addToTotalTime(){
    if (!tStart) return;
    stats.totalTime += Math.floor((performance.now() - tStart) / 1000);
    tStart = 0;
    updateStats();
  }
  function updateStats(){
    el.played  && (el.played.textContent  = `Played: ${stats.played}`);
    el.solved  && (el.solved.textContent  = `Solved: ${stats.solved}`);
    el.revealed&& (el.revealed.textContent= `Revealed: ${stats.revealed}`);
    const m=String(Math.floor(stats.totalTime/60)).padStart(2,'0'),
          s=String(stats.totalTime%60).padStart(2,'0');
    el.total && (el.total.textContent = `Time: ${m}:${s}`);
  }
  function clearPanels(){
    el.feedback && (el.feedback.textContent='', el.feedback.className='answer-feedback');
    el.msg && (el.msg.textContent='', el.msg.className='status');
    if (el.solutionPanel) el.solutionPanel.style.display='none';
    el.solutionMsg && (el.solutionMsg.textContent='');
  }

  // --- paint
  function paintCards(images){
    if (!el.cards) return;
    el.cards.innerHTML = '';
    (images || []).forEach(c=>{
      const img = document.createElement('img');
      img.src = c.url; img.alt = c.code; img.className = 'card';
      el.cards.appendChild(img);
    });
  }
  function handlePayload(data){
  current = data || {};
  currentSeq = Number.isFinite(data?.seq) ? data.seq : 0;

  const qn = (currentSeq|0) + 1;
  const qText = Array.isArray(data?.question) ? data.question.join(', ') : (data?.question ?? '');
  el.question && (el.question.textContent = `Q${qn} [#${data?.case_id ?? ''}] — Cards: ${qText}`);

  paintCards(data?.images || []);
  if (el.answer) { el.answer.value=''; el.answer.focus(); }
  timerStart();

  // ↓↓↓ Only show the reset message for custom/competition ↓↓↓
  const levelNow = (el.level?.value || data?.difficulty || '').toLowerCase();
  if (data?.pool_done && (levelNow === 'custom' || levelNow === 'competition')) {
    if (el.msg) { el.msg.textContent = 'All cases used. Pool reset.'; el.msg.className = 'status status-info'; }
  } else {
    if (el.msg) { el.msg.textContent = ''; el.msg.className = 'status'; }
  }
}

  // --- actions
  async function deal(){
    clearPanels();
    el.cards && (el.cards.innerHTML='');
      el.question && (el.question.textContent='Dealing…');
    try{
      const levelVal = el.level ? el.level.value : 'easy';
      const data = await fetchJSON(`${API_BASE}/next?level=${encodeURIComponent(levelVal)}&seq=${currentSeq}`);
      handlePayload(data);
    }catch(e){
      el.question && (el.question.textContent='');
      el.msg && (el.msg.textContent='Failed to get a new question. Please try again.', el.msg.className='status status-error');
    }
  }

  async function check(){
    if (!current) return;
    const raw = el.answer ? el.answer.value.trim() : '';
    if (!raw){
      el.msg && (el.msg.textContent='Type the final number.', el.msg.className='status status-warning');
      return;
    }
    try{
      const r = await fetch(`${API_BASE}/check`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ values: current.values, answer: raw })
      });
      const res = await r.json();
      if (res.ok){
        el.feedback && (el.feedback.textContent='✓', el.feedback.className='answer-feedback success-icon');
        el.msg && (el.msg.textContent='Correct!', el.msg.className='status status-success');
        stats.played++; stats.solved++; timerStop(); addToTotalTime(); updateStats();
        setTimeout(deal, 900);
      } else {
        el.feedback && (el.feedback.textContent='✗', el.feedback.className='answer-feedback error-icon');
        el.msg && (el.msg.textContent = res.reason || 'Try again!', el.msg.className='status status-error');
        stats.played++; updateStats();
      }
    }catch{
      el.msg && (el.msg.textContent='Error checking answer', el.msg.className='status status-error');
    }
  }

  async function help(){
    if (!current) return;
    try{
      const r = await fetch(`${API_BASE}/help`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ values: current.values })
      });
      const data = await r.json();
      if (el.solutionPanel) el.solutionPanel.style.display='block';
      if (el.solutionMsg) {
        if (data.has_solution && Array.isArray(data.solutions)) {
          el.solutionMsg.innerHTML = data.solutions.map(s=>`<div>${s}</div>`).join('');
        } else {
          el.solutionMsg.textContent = 'No stored solution.';
        }
      }
      stats.played++; stats.revealed++; updateStats();
    }catch{
      if (el.solutionPanel) el.solutionPanel.style.display='block';
      el.solutionMsg && (el.solutionMsg.textContent='Error loading help');
    }
  }

  function clearAnswer(){ el.answer && (el.answer.value='', el.answer.focus()); }
  function backspace(){
    if (!el.answer) return;
    const v = el.answer.value;
    el.answer.value = v.slice(0, -1);
    el.answer.focus();
  }

  async function exitGame(){
    try{
      const payload = { stats };
      const r = await fetch(`${API_BASE}/exit`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload)
      });
      const j = await r.json();
      if (j.ok && j.next_url) window.location.href = j.next_url;
      else window.location.href = '/';
    }catch{
      window.location.href = '/';
    }
  }

  // --- wire
  on(btn.clear, 'click', clearAnswer);
  on(btn.backspace, 'click', backspace);
  on(btn.next,  'click', deal);
  on(btn.check, 'click', check);
  on(btn.help,  'click', help);
  on(el.restart, 'click', ()=>{ stats.played=stats.solved=stats.revealed=stats.skipped=0; stats.totalTime=0; updateStats(); deal(); });
  on(el.exit,    'click', exitGame);

  document.addEventListener('keydown', (e)=>{
    if (e.target === el.answer && e.key === 'Enter'){ e.preventDefault(); check(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === 'backspace' && document.activeElement !== el.answer){ e.preventDefault(); backspace(); }
    if (k === 'd') { e.preventDefault(); deal(); }
    if (k === 'h') { e.preventDefault(); help(); }
    if (k === 'r') { e.preventDefault(); el.restart?.click(); }
    if (k === 'x') { e.preventDefault(); exitGame(); }
  });

  // boot
  updateStats();
  if (FIRST) handlePayload(FIRST); else deal();
})();

