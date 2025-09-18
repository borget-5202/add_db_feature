(() => {
  'use strict';

  // ---------- Config ----------
  const API_BASE = window.GAME24_API_BASE || '/count_by_2s/api';
  const FIRST    = window.__FIRST_PAYLOAD__ || null;

  const $  = (q) => document.querySelector(q);
  const on = (el, ev, fn) => el && el.addEventListener(ev, fn);

  // DOM refs
  const el = {
    level:         $('#level'),
    autoDeal:      $('#autoDeal'),

    question:      $('#question'),
    cards:         $('#cards'),
    answer:        $('#answer'),
    feedback:      $('#answerFeedback'),
    solutionPanel: $('#solutionPanel'),
    solutionMsg:   $('#solutionMsg'),
    msg:           $('#msg'),
    timer:         $('#timer'),

    played:        $('#played'),
    solved:        $('#solved'),
    revealed:      $('#revealed'),
    total:         $('#totalTime'),

    // buttons
    backspace:     $('#backspace'),
    clear:         $('#clear'),
    check:         $('#check'),
    next:          $('#next'),
    help:          $('#help'),
    restart:       $('#restart'),
    exit:          $('#exit'),

    // optional modals in your template
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

  // ---------- Local stats (client-owned) ----------
  const stats = {
    played: 0,
    solved: 0,
    revealed: 0,
    skipped: 0,
    totalTime: 0,   // seconds
  };

  function resetStats(){
    stats.played = stats.solved = stats.revealed = stats.skipped = 0;
    stats.totalTime = 0;
    updateStatsUI();
  }

  function updateStatsUI(){
    if (el.played)   el.played.textContent   = `Played: ${stats.played}`;
    if (el.solved)   el.solved.textContent   = `Solved: ${stats.solved}`;
    if (el.revealed) el.revealed.textContent = `Revealed: ${stats.revealed}`;
    if (el.total) {
      const m = String(Math.floor(stats.totalTime/60)).padStart(2,'0');
      const s = String(stats.totalTime%60).padStart(2,'0');
      el.total.textContent = `Time: ${m}:${s}`;
    }
  }

  // ---------- Session state ----------
  let current      = null;   // last payload from server
  let uiQ          = 0;      // UI question counter (0-based). We display Q{uiQ+1}
  let countedThisPuzzle = false; // ensure `played` increments once per puzzle

  // timers
  let tStart   = 0, tTick = null; // puzzle timer
  let nextTimer = null;           // pending auto-deal timer

  // auto-deal setting
  let autoDealOn = el.autoDeal ? !!el.autoDeal.checked : true;

  // ---------- Utilities ----------
  async function fetchJSON(url, opts, retries = 1, backoff = 250) {
    for (let i = 0; i <= retries; i++) {
      try {
        const r = await fetch(url, opts);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return await r.json();
      } catch (e) {
        if (i === retries) throw e;
        await new Promise(res => setTimeout(res, backoff * (i + 1)));
      }
    }
  }

  function fmtTimer(ms) {
    const T = Math.max(0, Math.floor(ms));
    const t = Math.floor((T % 1000) / 100);
    const s = Math.floor(T / 1000) % 60;
    const m = Math.floor(T / 60000);
    return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${t}`;
  }

  function timerStart() {
    timerStop();
    tStart = performance.now();
    if (el.timer) el.timer.textContent = '00:00.0';
    tTick = setInterval(() => {
      if (el.timer) el.timer.textContent = fmtTimer(performance.now() - tStart);
    }, 100);
  }

  function timerStop() {
    if (tTick) { clearInterval(tTick); tTick = null; }
  }

  function addElapsedToTotal() {
    if (!tStart) return;
    const secs = Math.floor((performance.now() - tStart)/1000);
    stats.totalTime += secs;
    tStart = 0;
    updateStatsUI();
  }

  function cancelNextDeal(){ if (nextTimer) { clearTimeout(nextTimer); nextTimer = null; } }
  function scheduleNextDeal(){
    cancelNextDeal();
    if (autoDealOn) nextTimer = setTimeout(() => { nextTimer = null; deal(); }, 900);
  }

  function clearPanels() {
    if (el.feedback){ el.feedback.textContent = ''; el.feedback.className = 'answer-feedback'; }
    if (el.msg){ el.msg.textContent = ''; el.msg.className = 'status'; }
    if (el.solutionPanel) el.solutionPanel.style.display = 'none';
    if (el.solutionMsg) el.solutionMsg.textContent = '';
  }

  function clearAnswer() { if (el.answer){ el.answer.value = ''; el.answer.focus(); } }

  function backspace() {
    if (!el.answer) return;
    el.answer.value = el.answer.value.slice(0, -1);
    el.answer.focus();
  }

  function paintCards(images) {
    if (!el.cards) return;
    el.cards.innerHTML = '';
    (images || []).forEach(c => {
      const img = document.createElement('img');
      img.src = c.url;
      img.alt = c.code;
      img.className = 'card';
      el.cards.appendChild(img);
    });
  }

  function showModal(id){
    const m = (typeof id === 'string') ? document.getElementById(id) : id;
    if (m) m.style.display = 'flex';
  }
  function hideModal(id){
    const m = (typeof id === 'string') ? document.getElementById(id) : id;
    if (m) m.style.display = 'none';
  }

  // ---------- Render payload ----------
  function handlePayload(data) {
    current = data || {};
    countedThisPuzzle = false;     // allow `played` once per new puzzle

    // label: Q1, Q2, ...
    const shownQ = (uiQ|0) + 1;
    const qText = Array.isArray(data?.question) ? data.question.join(', ')
                  : (data?.question ?? '');
    if (el.question) el.question.textContent = `Q${shownQ} [#${data?.case_id ?? ''}] — Cards: ${qText}`;
    uiQ++; // advance AFTER drawing

    paintCards(data?.images || []);
    if (el.answer){ el.answer.value = ''; el.answer.focus(); }

    clearPanels();
    timerStart();

    const lvl = (el.level?.value || data?.difficulty || '').toLowerCase();
    if (data?.pool_done && (lvl === 'custom' || lvl === 'competition')) {
      if (el.msg){ el.msg.textContent = 'All cases used. Pool reset.'; el.msg.className = 'status status-info'; }
    }
  }

  // ---------- API calls ----------
  async function deal() {
    cancelNextDeal();         // avoid stray next after restart
    clearAnswer();
    if (el.question) el.question.textContent = 'Dealing…';
    try {
      const levelVal = el.level ? el.level.value : 'easy';
      const data = await fetchJSON(`${API_BASE}/next?level=${encodeURIComponent(levelVal)}&seq=${uiQ}`);
      handlePayload(data);
    } catch (e) {
      if (el.question) el.question.textContent = '';
      if (el.msg){ el.msg.textContent = 'Failed to get a new question. Please try again.'; el.msg.className = 'status status-error'; }
    }
  }

  async function check() {
    if (!current) return;
    const raw = (el.answer?.value || '').trim();
    if (!raw) {
      if (el.msg){ el.msg.textContent = 'Type the final number.'; el.msg.className = 'status status-warning'; }
      return;
    }
    try {
      const res = await fetchJSON(`${API_BASE}/check`, {
        method: 'POST',
        headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ values: current.values, answer: raw })
      });

      // first check on this puzzle? count as played
      if (!countedThisPuzzle) { stats.played += 1; countedThisPuzzle = true; }

      if (res.ok) {
        stats.solved += 1;
        addElapsedToTotal();
        updateStatsUI();

        if (el.feedback){ el.feedback.textContent = '✓'; el.feedback.className = 'answer-feedback success-icon'; }
        if (el.msg){ el.msg.textContent = 'Correct!'; el.msg.className = 'status status-success'; }
        scheduleNextDeal();   // honor Auto-Deal
      } else {
        if (el.feedback){ el.feedback.textContent = '✗'; el.feedback.className = 'answer-feedback error-icon'; }
        if (el.msg){ el.msg.textContent = res.reason || 'Try again!'; el.msg.className = 'status status-error'; }
      }
    } catch (e) {
      if (el.msg){ el.msg.textContent = 'Error checking answer'; el.msg.className = 'status status-error'; }
    }
  }

  async function help() {
    if (!current) return;
    try {
      const data = await fetchJSON(`${API_BASE}/help`, {
        method: 'POST',
        headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ values: current.values })
      });

      // Show solution
      if (el.solutionPanel) el.solutionPanel.style.display = 'block';
      if (el.solutionMsg) {
        if (data.has_solution && Array.isArray(data.solutions)) {
          el.solutionMsg.innerHTML = data.solutions.map(s => `<div>${s}</div>`).join('');
        } else {
          el.solutionMsg.textContent = 'No stored solution.';
        }
      }

      // if player asks for help first time on this puzzle, count as played + revealed
      if (!countedThisPuzzle) { stats.played += 1; countedThisPuzzle = true; }
      stats.revealed += 1;
      addElapsedToTotal();
      updateStatsUI();

    } catch (e) {
      if (el.solutionPanel) el.solutionPanel.style.display = 'block';
      if (el.solutionMsg) el.solutionMsg.textContent = 'Error loading help';
    }
  }

  // ---------- Restart / Exit ----------
  async function doRestart() {
    hideModal(el.restartModal);
    cancelNextDeal();
    timerStop();

    // reset local stats + UI sequence
    resetStats();
    uiQ = 0;

    try {
      // Your backend may or may not serve a 'first' payload; we just deal()
      await fetchJSON(`${API_BASE}/restart`, { method: 'POST' }).catch(()=>{});
    } catch (_) {}

    deal();  // fetch first puzzle -> shows Q1
  }

  function showSummaryAndGo(statsObj, url) {
    if (el.summaryBackdrop && el.summaryBody && el.summaryOk && el.summaryClose) {
      el.summaryBody.innerHTML = renderSummary(statsObj);
      showModal(el.summaryBackdrop);
      const go = () => { hideModal(el.summaryBackdrop); window.location.href = url; };
      el.summaryOk.onclick = go;
      el.summaryClose.onclick = go;
      setTimeout(go, 1500);
    } else {
      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:9999';
      overlay.innerHTML = `<div style="background:#fff;padding:20px 24px;border-radius:12px;max-width:420px">
        <h3>Session Summary</h3>
        ${renderSummary(statsObj)}
        <div style="text-align:right"><button id="__sum_ok">OK</button></div>
      </div>`;
      document.body.appendChild(overlay);
      document.getElementById('__sum_ok').onclick = () => { window.location.href = url; };
      setTimeout(() => { window.location.href = url; }, 1500);
    }
  }

  function renderSummary(s){
    const m = Math.floor(s.totalTime/60), sec = s.totalTime%60;
    const acc = s.played ? Math.round((s.solved/s.played)*100) : 0;
    return `
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:10px 0 16px">
        <div><strong>Played:</strong> ${s.played}</div>
        <div><strong>Solved:</strong> ${s.solved}</div>
        <div><strong>Revealed:</strong> ${s.revealed}</div>
        <div><strong>Skipped:</strong> ${s.skipped}</div>
        <div><strong>Accuracy:</strong> ${acc}%</div>
        <div><strong>Time:</strong> ${m}:${String(sec).padStart(2,'0')}</div>
      </div>`;
  }

  async function doExit() {
    hideModal(el.exitModal);
    cancelNextDeal();
    timerStop();

    // make sure we include the last puzzle’s time if user exits mid-puzzle
    addElapsedToTotal();

    // Send local stats to backend; backend will store them in session.meta
    let resp;
    try {
      resp = await fetchJSON(`${API_BASE}/exit`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ stats })
      });
    } catch (e) {
      // If anything fails, still show summary and go home
      showSummaryAndGo(stats, '/');
      return;
    }

    const nextUrl = (resp && resp.next_url) ? resp.next_url : '/';
    showSummaryAndGo(stats, nextUrl);
  }

  // ---------- Wire UI ----------
  on(el.clear,     'click', () => { clearAnswer(); });
  on(el.backspace, 'click', () => { backspace(); });
  on(el.check,     'click', () => { check(); });
  on(el.next,      'click', () => { stats.skipped += 1; updateStatsUI(); deal(); });
  on(el.help,      'click', () => { help(); });

  on(el.restart,   'click', () => { cancelNextDeal(); showModal(el.restartModal || 'restartModal'); });
  on(el.exit,      'click', () => { cancelNextDeal(); showModal(el.exitModal || 'exitModal'); });

  on(el.restartConfirm, 'click', doRestart);
  on(el.restartCancel,  'click', () => hideModal(el.restartModal || 'restartModal'));
  on(el.restartClose,   'click', () => hideModal(el.restartModal || 'restartModal'));

  on(el.exitConfirm, 'click', doExit);
  on(el.exitCancel,  'click', () => hideModal(el.exitModal || 'exitModal'));
  on(el.exitClose,   'click', () => hideModal(el.exitModal || 'exitModal'));

  on(el.autoDeal, 'change', (e) => { autoDealOn = !!e.target.checked; });

  on(el.level, 'change', () => {
    // changing difficulty does not reset stats; fetch a fresh question
    deal();
  });

  document.addEventListener('keydown', (e) => {
    if (el.answer && e.target === el.answer && e.key === 'Enter') { e.preventDefault(); check(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === 'd') { e.preventDefault(); deal(); }
    if (k === 'h') { e.preventDefault(); help(); }
    if (k === 'r') { e.preventDefault(); cancelNextDeal(); showModal(el.restartModal || 'restartModal'); }
    if (k === 'x') { e.preventDefault(); cancelNextDeal(); showModal(el.exitModal || 'exitModal'); }
    if (k === 'backspace' && document.activeElement !== el.answer) { e.preventDefault(); backspace(); }
  });

  // ---------- Boot ----------
  resetStats();
  uiQ = 0;
  if (FIRST) {
    handlePayload(FIRST);        // shows Q1 immediately
  } else {
    deal();                      // fetch first puzzle; sends seq=0
  }
})();

