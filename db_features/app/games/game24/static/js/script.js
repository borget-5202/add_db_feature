(() => {
  'use strict';

  /* =========================
     Config & stable IDs
  ========================= */
  const API_BASE =
    (typeof window !== 'undefined' && window.GAME24_API_BASE) ? window.GAME24_API_BASE :
    (window.location.pathname.includes('/games/game24/') ? '/games/game24/api' : '/game24/api');

  const STATIC_BASE = (typeof window !== 'undefined' && window.GAME24_STATIC_BASE) ? window.GAME24_STATIC_BASE : '';
  const CARD_IMG_BASE = (STATIC_BASE ? (STATIC_BASE + '/cards/') : '/games/assets/cards/');
  const CARD_BACK = (CARD_IMG_BASE.endsWith('/') ? CARD_IMG_BASE + 'back.png' : CARD_IMG_BASE + '/back.png');
  const CARD_VOID = (CARD_IMG_BASE.endsWith('/') ? CARD_IMG_BASE + 'void.png' : CARD_IMG_BASE + '/void.png');

  console.log('[GAME24] Using API_BASE:', API_BASE);

  // === Target init (default 24) + read ?target= ===
  let TARGET = 24;
  if (typeof window.INIT_TARGET !== 'undefined' && window.INIT_TARGET !== null) {
    TARGET = window.INIT_TARGET;
    localStorage.setItem('target_g24', String(TARGET));
  }

  (function initTargetFromURL() {
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
    } catch { }
  })();

  const CLIENT_ID = (() => {
    try {
      const ex = sessionStorage.getItem('client_id');
      if (ex) return ex;
      const id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : 'c_' + Math.random().toString(36).slice(2);
      sessionStorage.setItem('client_id', id);
      return id;
    } catch {
      return 'c_' + Math.random().toString(36).slice(2);
    }
  })();

  const GUEST_ID = (() => {
    try {
      const ex = localStorage.getItem('guest_id');
      if (ex) return ex;
      const id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : 'g_' + Math.random().toString(36).slice(2);
      localStorage.setItem('guest_id', id);
      return id;
    } catch {
      return 'g_' + Math.random().toString(36).slice(2);
    }
  })();

  /* =========================
     DOM refs & helpers
  ========================= */
  const $ = (q) => document.querySelector(q);
  const on = (el, evt, fn) => { if (el) el.addEventListener(evt, fn); };

  const el = {
    theme: $('#theme'),
    level: $('#level'),
    targetSelect: $('#targetSelect'),
    question: $('#question'),
    cards: $('#cards'),
    answer: $('#answer'),
    feedback: $('#answerFeedback'),
    solutionPanel: $('#solutionPanel'),
    solutionMsg: $('#solutionMsg'),
    msg: $('#msg'),
    restart: $('#restart'),
    exit: $('#exit'),
    autoDeal: $('#autoDeal'),
    noBtn: $('#no'),
    ops: $('#ops'),
    backspace: $('#backspace'),
    clear: $('#clear'),
    next: $('#next'),
    check: $('#check'),
    help: $('#help'),
    helpAll: $('#helpAll'),
    casePoolRow: $('#casePoolRow'),
    casePoolInput: $('#casePoolInput'),
    compDurationInput: $('#compDurationInput'),
    saveCasePoolBtn: $('#saveCasePool'),
    caseIdInput: $('#caseIdInput'),
    loadCaseBtn: $('#loadCaseBtn'),
    summaryBackdrop: $('#summaryBackdrop'),
    summaryClose: $('#summaryClose'),
    summaryReport: $('#summary-report'),
    summaryCsv: $('#summaryCsv'),
    summaryExit: $('#summaryExit'),
    summaryResume: $('#summaryResume'),
    timer: $('#timer'),
  };

  // HOW-TO modal elements
  el.howToBtn = document.getElementById('howtoLink') ||
    document.getElementById('howToBtn') ||
    document.querySelector('[data-howto-btn]');

  el.howToBackdrop = document.getElementById('modalBackdrop') ||
    document.getElementById('howToBackdrop') ||
    document.getElementById('howToModal') ||
    document.querySelector('[data-howto-backdrop]');

  el.howToClose = document.getElementById('modalClose') ||
    document.querySelector('#modalBackdrop .close, #howToBackdrop .modal-close, [data-howto-close]');

  // fix restart display issue
  // RESTART modal elements (use the modal you already have in play.html)
  const restartModal    = document.getElementById('restartModal');
  const restartConfirm  = document.getElementById('restartConfirm');
  const restartCancel   = document.getElementById('restartCancel');
  const restartClose    = document.getElementById('restartClose');

  /* =========================
     Modal helpers
  ========================= */
  function showModal(backdrop) {
    if (!backdrop) return;
    backdrop.style.display = 'flex';
    requestAnimationFrame(() => backdrop.classList.add('modal-visible'));
  }

  function hideModal(backdrop) {
    if (!backdrop) return;
    backdrop.classList.remove('modal-visible');
    setTimeout(() => { backdrop.style.display = 'none'; }, 220);
  }

  /* =========================
     Target management
  ========================= */
  const targetSel = document.getElementById('targetSelect');
  const targetCustom = document.getElementById('targetCustom');
  const applyTarget = document.getElementById('applyTarget');

  function setTarget(t) {
    const n = parseInt(t, 10);
    const clamped = Number.isFinite(n) ? Math.max(-100, Math.min(100, n)) : 24;
    window.TARGET = clamped;
    localStorage.setItem('target_g24', String(clamped));
  }

  function initTarget() {
    const qp = new URLSearchParams(location.search);
    const qsTarget = qp.get('target');

    if (qsTarget === 'custom') {
      if (targetSel) targetSel.value = 'custom';
      if (targetCustom) { targetCustom.style.display = ''; targetCustom.focus(); }
      if (applyTarget) applyTarget.style.display = '';
    } else if (qsTarget && !Number.isNaN(parseInt(qsTarget, 10))) {
      setTarget(parseInt(qsTarget, 10));
      if (targetSel) targetSel.value = String(TARGET);
      if (targetCustom) targetCustom.style.display = 'none';
      if (applyTarget) applyTarget.style.display = 'none';
    } else {
      const saved = localStorage.getItem('target_g24');
      if (saved && !Number.isNaN(parseInt(saved, 10))) {
        setTarget(parseInt(saved, 10));
        if (targetSel) targetSel.value = (saved === '10' || saved === '36' || saved === '24') ? saved : 'custom';
        if (targetSel && targetSel.value === 'custom') {
          if (targetCustom) { targetCustom.style.display = ''; targetCustom.value = saved; }
          if (applyTarget) applyTarget.style.display = '';
        }
      } else {
        setTarget(24);
        if (targetSel) targetSel.value = '24';
      }
    }

    if (targetSel) {
      targetSel.addEventListener('change', () => {
        if (targetSel.value === 'custom') {
          if (targetCustom) { targetCustom.style.display = ''; targetCustom.focus(); }
          if (applyTarget) applyTarget.style.display = '';
        } else {
          if (targetCustom) targetCustom.style.display = 'none';
          if (applyTarget) applyTarget.style.display = 'none';
          setTarget(parseInt(targetSel.value, 10));
        }
      });
    }

    if (applyTarget) {
      applyTarget.addEventListener('click', () => {
        const v = parseInt(targetCustom?.value ?? '', 10);
        if (!Number.isNaN(v)) setTarget(v);
      });
    }

    if (targetCustom) {
      targetCustom.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          applyTarget?.click();
        }
      });
    }
  }

  initTarget();

  /* =========================
     State & stats
  ========================= */
  let current = null;
  let handCounter = 0;
  let nextSeq = 1;
  let autoDealEnabled = true;
  let nextTimer = null;
  let helpDisabled = false;
  let revealedThisHand = false;
  let countedPlayedThisHand = false;
  let sessionEnded = false;

  const stats = {
    played: 0,
    solved: 0,
    revealed: 0,
    skipped: 0,
    incorrect: 0,
    totalTime: 0,
    attempts: 0,
    correct: 0,
    dealSwaps: 0
  };

  /* =========================
     Timer
  ========================= */
  let tStart = 0, tTick = null;

  const fmt = (ms) => {
    const T = Math.max(0, Math.floor(ms));
    const t = Math.floor((T % 1000) / 100);
    const s = Math.floor(T / 1000) % 60;
    const m = Math.floor(T / 60000);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${t}`;
  };

  function timerStart() {
    timerStop();
    tStart = performance.now();
    if (el.timer) el.timer.textContent = '00:00.0';
    tTick = setInterval(() => {
      if (el.timer) el.timer.textContent = fmt(performance.now() - tStart);
    }, 100);
  }

  function timerStop() {
    if (tTick) {
      clearInterval(tTick);
      tTick = null;
    }
  }

  function addToTotalTime() {
    if (tStart) {
      stats.totalTime += Math.floor((performance.now() - tStart) / 1000);
      tStart = 0;
      updateStats();
    }
  }

  // Wire How-to modal
  if (el.howToBtn && el.howToBackdrop) {
    el.howToBtn.addEventListener('click', () => showModal(el.howToBackdrop));
    el.howToClose?.addEventListener('click', () => hideModal(el.howToBackdrop));
    el.howToBackdrop.addEventListener('click', (e) => {
      if (e.target === el.howToBackdrop) hideModal(el.howToBackdrop);
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && el.howToBackdrop?.classList.contains('modal-visible')) {
      hideModal(el.howToBackdrop);
    }
  });

  /* =========================
     UI helpers
  ========================= */
  function setCaret(pos) {
    if (!el.answer) return;
    el.answer.selectionStart = el.answer.selectionEnd = pos;
  }

  function insertAtCursor(text) {
    const inp = el.answer;
    if (!inp) return;
    const start = inp.selectionStart ?? inp.value.length;
    const end = inp.selectionEnd ?? inp.value.length;
    const before = inp.value.slice(0, start);
    const after = inp.value.slice(end);
    inp.value = before + text + after;
    let p = start + text.length;
    if (text === '()') { p = start + 1; }
    inp.focus();
    setCaret(p);
  }

  function backspaceAtCursor() {
    const inp = el.answer;
    if (!inp) return;
    const start = inp.selectionStart ?? 0;
    const end = inp.selectionEnd ?? 0;
    if (start === end && start > 0) {
      inp.value = inp.value.slice(0, start - 1) + inp.value.slice(end);
      setCaret(start - 1);
    } else {
      inp.value = inp.value.slice(0, start) + inp.value.slice(end);
      setCaret(start);
    }
    inp.focus();
  }

  function clearAnswer() {
    if (el.answer) {
      el.answer.value = '';
      el.answer.focus();
    }
  }

  function showError(message) {
    if (el.msg) {
      el.msg.textContent = message;
      el.msg.className = 'status status-error';
    }
  }

  function clearPanels() {
    if (el.feedback) {
      el.feedback.textContent = '';
      el.feedback.className = 'answer-feedback';
    }
    if (el.msg) {
      el.msg.textContent = '';
      el.msg.className = 'status';
    }
    if (el.solutionPanel) el.solutionPanel.style.display = 'none';
    if (el.solutionMsg) el.solutionMsg.textContent = '';
  }

  function setGameplayEnabled(enabled) {
    const ids = ['no', 'backspace', 'clear', 'next', 'check', 'help', 'helpAll'];
    ids.forEach(id => {
      const b = document.getElementById(id);
      if (b) {
        b.disabled = !enabled;
        b.classList.toggle('is-disabled', !enabled);
      }
    });
    if (el.ops) {
      [...el.ops.querySelectorAll('button')].forEach(btn => {
        btn.disabled = !enabled;
        btn.classList.toggle('is-disabled', !enabled);
      });
    }
  }

  function getCurrentSettings() {
    const targetSelect = document.getElementById('targetSelect');
    const targetCustom = document.getElementById('targetCustom');

    let currentTarget = TARGET;

    if (targetCustom && targetCustom.style.display !== 'none') {
      const customVal = parseInt(targetCustom.value);
      if (!isNaN(customVal)) {
        currentTarget = customVal;
      }
    } else if (targetSelect) {
      const selectVal = targetSelect.value;
      if (selectVal !== 'custom') {
        currentTarget = parseInt(selectVal);
      }
    }

    const settings = {
      target: currentTarget,
      theme: (el.theme && el.theme.value) ? el.theme.value : 'classic',
      level: (el.level && el.level.value) ? el.level.value : 'easy'
    };

    console.log('🔧 getCurrentSettings() returned:', settings);
    return settings;
  }

  function poolOffPreserveLevel() {
    console.log('🚫 Turning off pool (preserve level):', el?.level?.value);

    fetch(`${API_BASE}/pool`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'off', client_id: CLIENT_ID, guest_id: GUEST_ID })
    }).catch(console.warn);

    autoDealEnabled = true;
    if (el.autoDeal) el.autoDeal.checked = true;
    localStorage.setItem('autoDeal_g24', 'true');

    updateCasePoolUI();
    showPreDeal();
    current = null;
    handCounter = 0;
  }

  /* =========================
     Initialize Settings
  ========================= */
  (function initializeSettings() {
    const savedLevel = localStorage.getItem('level');
    const savedPoolText = localStorage.getItem('casePoolText');
    const qp = new URLSearchParams(location.search);
    const qsLevel = qp.get('level');

    function hasActivePool() {
      if (!savedPoolText) return false;
      const parts = savedPoolText.split(/[\s,\|]+/g).filter(Boolean);
      const validPuzzles = parts.filter(p => {
        const n = parseInt(p, 10);
        return !isNaN(n) && n >= 1 && n <= 1820;
      });
      return validPuzzles.length > 0;
    }

    const hasValidPool = hasActivePool();
    console.log('🔍 Pool check - level:', savedLevel, 'hasValidPool:', hasValidPool, 'poolText:', savedPoolText);

    if ((savedLevel === 'custom' || savedLevel === 'competition') && !hasValidPool) {
      console.log('🔁 Pool mode selected but no pool yet — keeping selection, pool OFF until saved.');
      poolOffPreserveLevel();
    }

    let initialLevel = 'easy';
    if (qsLevel && (qsLevel === 'easy' || qsLevel === 'medium' || qsLevel === 'hard' || qsLevel === 'custom' || qsLevel === 'competition')) {
      initialLevel = qsLevel;
    } else if (savedLevel && (savedLevel === 'easy' || savedLevel === 'medium' || savedLevel === 'hard' || savedLevel === 'custom' || savedLevel === 'competition')) {
      initialLevel = savedLevel;
    }

    if (el.level) el.level.value = initialLevel;
    if (initialLevel !== savedLevel) {
      localStorage.setItem('level', initialLevel);
    }

    const autoDealSaved = localStorage.getItem('autoDeal_g24');
    if (autoDealSaved !== null) {
      autoDealEnabled = (autoDealSaved === 'true');
      if (el.autoDeal) el.autoDeal.checked = autoDealEnabled;
    } else {
      autoDealEnabled = true;
      if (el.autoDeal) el.autoDeal.checked = true;
      localStorage.setItem('autoDeal_g24', 'true');
    }

    updateCasePoolUI();
    console.log('🔧 Initialized settings - level:', initialLevel, 'autoDeal:', autoDealEnabled, 'hasValidPool:', hasValidPool);
  })();

  /* =========================
     Stats UI
  ========================= */
  function updateStats() {
    const w = (id, txt) => {
      const n = document.getElementById(id);
      if (n) n.textContent = txt;
    };
    w('played', `Played: ${stats.played}`);
    w('solved', `Solved: ${stats.solved}`);
    w('revealed', `Revealed: ${stats.revealed}`);
    w('skipped', `Skipped: ${stats.skipped}`);
    w('incorrect', `Incorrect: ${stats.incorrect}`);

    const m = String(Math.floor(stats.totalTime / 60)).padStart(2, '0');
    const s = String(stats.totalTime % 60).padStart(2, '0');
    w('totalTime', `Time: ${m}:${s}`);
  }

  function applyServerStats(s) {
    if (!s) return;
    console.log('Applying server stats:', s);

    if ('played' in s) stats.played = s.played;
    if ('solved' in s) stats.solved = s.solved;
    if ('revealed' in s) stats.revealed = s.revealed;
    if ('skipped' in s) stats.skipped = s.skipped;
    if ('total_time' in s) stats.totalTime = s.total_time;
    if ('answer_attempts' in s) stats.attempts = s.answer_attempts;
    if ('answer_correct' in s) stats.correct = s.answer_correct;
    if ('answer_wrong' in s) stats.incorrect = s.answer_wrong;
    if ('deal_swaps' in s) stats.dealSwaps = s.deal_swaps;

    updateStats();
  }

  function resetLocalStats() {
    stats.played = stats.solved = stats.revealed = stats.skipped =
      stats.incorrect = stats.attempts = stats.correct = stats.dealSwaps = 0;
    stats.totalTime = 0;
    updateStats();
  }

  function resetToEasyMode(opts = {}) {
    const { resetState = true, announce = false } = opts;
    console.log('🔄 Resetting to easy mode...', opts);

    if (el.level) el.level.value = 'easy';
    localStorage.setItem('level', 'easy');

    autoDealEnabled = true;
    if (el.autoDeal) el.autoDeal.checked = true;
    localStorage.setItem('autoDeal_g24', 'true');

    localStorage.removeItem('casePoolText');
    localStorage.removeItem('compDurationMin');

    fetch(`${API_BASE}/pool`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'off', client_id: CLIENT_ID, guest_id: GUEST_ID })
    }).catch(console.warn);

    updateCasePoolUI();
    showPreDeal();

    if (resetState) {
      current = null;
      handCounter = 0;
      nextSeq = 1;
    }

    if (announce && el.msg) {
      el.msg.textContent = 'Switched to Easy mode.';
      el.msg.className = 'status';
    }
  }

  /* =========================
     Cards render
  ========================= */
  const rankTok = (v) => {
    const n = Number(v);
    if (!Number.isNaN(n)) return ({ 1: 'A', 10: 'T', 11: 'J', 12: 'Q', 13: 'K' }[n] || String(n));
    return String(v);
  };

  function paintCardsFromPayload(data) {
    console.log('[DEBUG] paintCardsFromPayload called with data:', data);
    if (!el.cards) return;

    const vals = data.values || [];
    const imgs = data.images || [];
    const slots = [];

    for (let i = 0; i < 4; i++) {
      if (vals[i] == null) {
        slots.push({ type: 'void' });
      } else {
        const it = imgs[i];
        slots.push({
          type: 'face',
          value: vals[i],
          url: (it && it.url) || null,
          code: (it && it.code) || null
        });
      }
    }
    renderSlots(slots);
  }

  function renderSlots(slots) {
    console.log('[DEBUG] renderSlots called with slots:', slots);
    el.cards.innerHTML = '';

    const src = Array.isArray(slots) ? slots.slice() : [];
    const N = Math.max(4, src.length);
    while (src.length < N) src.push({ type: 'back' });

    for (let i = 0; i < N; i++) {
      const s = src[i] || { type: 'back' };
      const img = document.createElement('img');
      img.className = 'card';
      img.decoding = 'async';
      img.loading = 'eager';

      if (s.type === 'back') {
        img.src = CARD_BACK;
        img.alt = 'back';
      } else if (s.type === 'void') {
        img.src = CARD_VOID;
        img.alt = 'void';
      } else if (s.type === 'face') {
        const code = s.code || rankTok(s.value);
        img.src = s.url
          ? s.url
          : (CARD_IMG_BASE.endsWith('/') ? CARD_IMG_BASE + code + '.png'
            : CARD_IMG_BASE + '/' + code + '.png');
        img.alt = code;

        const token = (s?.value != null) ? rankTok(s.value) : (code ? code[0] : '');
        if (token) {
          img.title = `Click to insert ${token}`;
          img.style.cursor = 'pointer';
          img.addEventListener('click', () => insertAtCursor(token));
        }
      } else {
        img.src = CARD_BACK;
        img.alt = 'back';
      }

      el.cards.appendChild(img);
    }

    console.log('[DEBUG] renderSlots appended', el.cards.children.length, 'cards');
  }

  function showPreDeal() {
    renderSlots([{ type: 'back' }, { type: 'back' }, { type: 'back' }, { type: 'back' }]);
    if (el.answer) el.answer.value = '';
    if (el.feedback) el.feedback.textContent = '';
    if (el.msg) {
      el.msg.textContent = 'Ready — press Deal to start.';
      el.msg.className = 'status status-success';
    }
    if (el.question) el.question.textContent = `Target: ${TARGET} — Ready to deal`;

    const nextBtn = document.getElementById('next');
    if (nextBtn) nextBtn.textContent = 'Deal (D)';
  }

  /* =========================
     Deal / sequencing
  ========================= */
  function cancelNextDeal() {
    if (nextTimer) {
      clearTimeout(nextTimer);
      nextTimer = null;
    }
  }

  function scheduleNextDeal() {
    console.log('⏰ scheduleNextDeal called - autoDealEnabled:', autoDealEnabled);

    cancelNextDeal();
    if (sessionEnded || !autoDealEnabled) {
      console.log('⏹️ Not scheduling next deal - session ended or auto-deal disabled');
      return;
    }

    if (current) {
      const isLastPuzzle =
        (current.pool_info && current.pool_info.is_last_puzzle) ||
        (current.pool_info && current.pool_info.remaining === 0) ||
        current.pool_done;

      if (isLastPuzzle) {
        console.log('🚫 Not scheduling - this was the last puzzle in pool');
        autoDealEnabled = false;
        if (el.autoDeal) el.autoDeal.checked = false;

        setTimeout(() => {
          resetToEasyMode();
          if (el.msg) el.msg.textContent = 'Pool completed! Returning to easy mode.';
        }, 2000);
        return;
      }
    }

    if (autoDealEnabled) {
      console.log('✅ Scheduling next deal in 900ms');
      nextTimer = setTimeout(() => {
        console.log('🔄 Next deal timer fired');
        nextTimer = null;
        deal({ advanceCounter: true });
      }, 900);
    }
  }

  async function deal({ advanceCounter = true, caseId = null } = {}) {
    if (sessionEnded) return;

    console.log('=== DEAL DEBUG START ===');
    console.log('advanceCounter:', advanceCounter, 'caseId:', caseId);
    console.log('autoDealEnabled:', autoDealEnabled);
    console.log('current pool_done:', current ? current.pool_done : 'no current');
    console.log('current pool_info:', current ? current.pool_info : 'no pool_info');

    clearPanels();
    if (el.cards) el.cards.innerHTML = '';
    if (el.question) el.question.textContent = 'Dealing…';
    revealedThisHand = false;
    countedPlayedThisHand = false;

    const settings = getCurrentSettings();
    console.log('🎯 deal() sending request with target:', settings.target);

    const themeVal = settings.theme;
    const levelVal = settings.level;
    const seqToSend = nextSeq;

    try {
      const params = new URLSearchParams({
        theme: themeVal,
        level: levelVal,
        seq: String(seqToSend),
        client_id: CLIENT_ID,
        guest_id: GUEST_ID,
        target: String(settings.target)
      });
      if (caseId) params.set('case_id', String(caseId));

      console.log('📡 Fetching from:', `${API_BASE}/next?${params.toString()}`);

      const r = await fetch(`${API_BASE}/next?${params.toString()}`);

      console.log('📥 Response status:', r.status, 'ok:', r.ok);

      if (!r.ok) {
        if (r.status === 403) {
          try {
            const j = await r.json();
            console.log('403 response data:', j);
            if (j && j.competition_over) {
              timerStop();
              addToTotalTime();
              await openSummaryFlow();
              return;
            }
          } catch { }
        }
        let msg = `HTTP ${r.status}`;
        try {
          const j = await r.json();
          if (j?.error) msg = j.error;
        } catch { }
        throw new Error(msg);
      }

      const data = await r.json();
      console.log('📦 Response data:', data);

      console.log('🔍 pool_done:', data.pool_done, 'pool_info:', data.pool_info, 'case_id:', data.case_id, 'has_data:', !!data.values);

      if (data && data.pool_done) {
        console.log('🚨 POOL DONE DETECTED');

        const hasValidPuzzle = data.case_id && data.values && data.values.length > 0;

        if (hasValidPuzzle) {
          console.log('✅ Last puzzle in pool - will display it');
        } else {
          console.log('🏁 Pool completely finished - no more puzzles');
          resetToEasyMode();
          if (el.msg) el.msg.textContent = 'Pool complete! Returning to easy mode.';
          return;
        }
      }

      if (data && (data.stats || data.stats_payload)) {
        console.log('📊 Applying server stats:', data.stats || data.stats_payload);
        applyServerStats(data.stats || data.stats_payload);
      }

      const displaySeq = Number.isFinite(data.seq) ? (data.seq >= 1 ? data.seq : data.seq + 1) : seqToSend;
      if (advanceCounter && !caseId) {
        handCounter = displaySeq;
        nextSeq = handCounter + 1;
      }
      if (caseId && handCounter === 0) {
        handCounter = 1;
      }

      if (el.question) {
        const qText = Array.isArray(data.question) ? data.question.join(', ') : (data.question ?? '');
        const shownSeq = caseId ? handCounter : displaySeq;
        let questionText = `Q${shownSeq} [#${data.case_id ?? (caseId || '')}] — Cards: ${qText} — Target: ${data?.target ?? TARGET}`;

        if (data.pool_info) {
          questionText += ` (${data.pool_info.remaining + 1}/${data.pool_info.total_count})`;

          if (data.pool_info.is_last_puzzle || data.pool_info.remaining === 0) {
            questionText += ' — LAST PUZZLE';
          }
        } else if (data.pool_done) {
          questionText += ' — LAST PUZZLE';
        }

        el.question.textContent = questionText;
      }

      current = data || {};
      if (data.pool_info) {
        current.pool_info = data.pool_info;
      }

      console.log('📋 Current object updated:', {
        case_id: current.case_id,
        values: current.values,
        pool_done: current.pool_done,
        pool_info: current.pool_info
      });

      if (el.answer) {
        el.answer.value = '';
        el.answer.focus();
      }
      paintCardsFromPayload(data);
      timerStart();

      if (typeof data.help_disabled === 'boolean') {
        helpDisabled = data.help_disabled;
        console.log('🛟 Help disabled:', helpDisabled);
      }

      console.log('=== DEAL DEBUG END ===');

    } catch (e) {
      console.error('💥 Deal error:', e);
      if (el.question) el.question.textContent = '';
      showError(`Failed to get a new question from ${API_BASE}. ${e.message || e}`);
    }
  }

  /* =========================
     Answer / Help / Skip
  ========================= */
  const preprocess = (s) =>
    s.replace(/\^/g, '**').replace(/×/g, '*').replace(/∗/g, '*').replace(/·/g, '*')
      .replace(/÷/g, '/').replace(/／/g, '/')
      .replace(/−|—|–/g, '-')
      .replace(/\bA\b/gi, '1').replace(/\bT\b/g, '10').replace(/\bJ\b/gi, '11').replace(/\bQ\b/gi, '12').replace(/\bK\b/gi, '13');

  async function check() {
    if (!current) return;
    console.log('Current object:', current);
    console.log('Current.case_id:', current.case_id);
    console.log('Current.values:', current.values);

    const exprRaw = el.answer ? el.answer.value.trim() : '';
    if (!exprRaw) return;

    try {
      const r = await fetch(`${API_BASE}/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          values: current.values,
          answer: preprocess(exprRaw),
          case_id: current.case_id,
          client_id: CLIENT_ID,
          guest_id: GUEST_ID,
          target: TARGET
        })
      });
      const res = await r.json();

      if (res && (res.stats || res.stats_payload)) applyServerStats(res.stats || res.stats_payload);

      if (res.ok) {
        if (el.feedback) {
          el.feedback.textContent = '✓';
          el.feedback.className = 'answer-feedback success-icon';
        }
        if (el.msg) {
          el.msg.textContent = (res.kind === 'no-solution') ? `Correct: no solution` : `${TARGET}! Correct!`;
          el.msg.className = 'status status-success';
        }
        timerStop();
        addToTotalTime();
        scheduleNextDeal();
      } else {
        if (el.feedback) {
          el.feedback.textContent = '✗';
          el.feedback.className = 'answer-feedback error-icon';
        }
        if (el.msg) {
          el.msg.textContent = res.reason || `Try again!`;
          el.msg.className = 'status status-error';
        }
      }
    } catch (e) {
      showError('Error checking answer');
      console.error(e);
    }
  }

  async function help(all = false) {
    if (!current) return;
    if (helpDisabled) {
      if (el.solutionPanel) el.solutionPanel.style.display = 'block';
      if (el.solutionMsg) el.solutionMsg.textContent = 'Help is disabled in competition mode.';
      return;
    }
    try {
      const r = await fetch(`${API_BASE}/help`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          values: current.values,
          case_id: current.case_id,
          all,
          client_id: CLIENT_ID,
          guest_id: GUEST_ID,
          target: TARGET
        })
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();

      if (Number.isFinite(data?.target)) {
        TARGET = data.target;
        if (typeof targetSel !== 'undefined' && targetSel) {
          const preset = ['10', '24', '36'];
          const s = String(TARGET);
          if (preset.includes(s)) {
            targetSel.value = s;
            if (targetCustom) targetCustom.style.display = 'none';
            if (applyTarget) applyTarget.style.display = 'none';
          } else {
            targetSel.value = 'custom';
            if (targetCustom) {
              targetCustom.style.display = '';
              targetCustom.value = s;
            }
            if (applyTarget) applyTarget.style.display = '';
          }
        }
      }

      if (data && data.stats) applyServerStats(data.stats);

      if (el.msg) { el.msg.textContent = ''; el.msg.className = 'status'; }
      if (el.solutionPanel) el.solutionPanel.style.display = 'block';

      if (!data.has_solution) {
        if (el.solutionMsg) el.solutionMsg.textContent = `No solution for target ${TARGET}.`;
      } else if (all) {
        if (el.solutionMsg) {
          el.solutionMsg.innerHTML = `<strong>Solutions (${data.solutions.length}) for target ${TARGET}:</strong> `;
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
        if (el.solutionMsg) el.solutionMsg.innerHTML = `<strong>Solution (target ${TARGET}):</strong> ${data.solutions?.[0] || data.solution || ''}`;
      }
    } catch (e) {
      if (el.solutionPanel) el.solutionPanel.style.display = 'block';
      if (el.solutionMsg) el.solutionMsg.textContent = 'Error loading help';
    }
  }

  async function skipThenDeal(all = false) {
    try {
      const settings = getCurrentSettings();
      console.log('🔄 skipThenDeal() sending request with:', {
        target: settings.target,
        case_id: current?.case_id,
        values: current?.values
      });

      const r = await fetch(`${API_BASE}/skip`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          values: current.values,
          case_id: current.case_id,
          all,
          client_id: CLIENT_ID,
          guest_id: GUEST_ID,
          target: settings.target
        })
      });
      if (r.ok) {
        const j = await r.json().catch(() => null);
        console.log('Skip response:', j);
        if (j && (j.stats || j.stats_payload)) {
          applyServerStats(j.stats || j.stats_payload);
        }
      }
    } catch (e) { console.warn('skip failed', e); }
    await deal({ advanceCounter: true });
  }

  /* =========================
     Load by Case ID
  ========================= */
  async function loadCaseById() {
    const val = (el.caseIdInput && el.caseIdInput.value) || '';
    const id = parseInt(val, 10);
    if (!val || Number.isNaN(id) || id < 1 || id > 1820) {
      showError('Please enter a valid Case ID (1–1820).');
      return;
    }

    clearPanels();
    if (el.cards) el.cards.innerHTML = '';
    if (el.question) el.question.textContent = `Loading Case #${id}…`;

    try {
      const currentLevel = el.level ? el.level.value : 'easy';
      const wasInPoolMode = (currentLevel === 'custom' || currentLevel === 'competition');

      if (wasInPoolMode) {
        const tempAutoDeal = autoDealEnabled;
        await deal({ advanceCounter: false, caseId: id });
        autoDealEnabled = false;
        if (el.autoDeal) el.autoDeal.checked = false;
      } else {
        await deal({ advanceCounter: false, caseId: id });
      }
    } catch (e) {
      showError(`Failed to load case #${id}. ${e.message || e}`);
    }
  }

  /* =========================
     Restart
  ========================= */
  async function doRestart() {
    try {
      cancelNextDeal();
      timerStop();
      addToTotalTime();
      clearPanels();

      sessionEnded = false;
      current = null;
      handCounter = 0;
      nextSeq = 1;
      autoDealEnabled = true;
      helpDisabled = false;
      revealedThisHand = false;
      countedPlayedThisHand = false;

      setGameplayEnabled(true);

      if (el.question) el.question.textContent = `Target: ${TARGET} — Ready to deal`;
      if (el.answer) el.answer.value = '';
      if (el.solutionPanel) el.solutionPanel.style.display = 'none';
      if (el.feedback) {
        el.feedback.textContent = '';
        el.feedback.className = 'answer-feedback';
      }
      if (el.msg) {
        el.msg.textContent = 'Session restarted — press Deal to start.';
        el.msg.className = 'status status-success';
      }

      poolOffPreserveLevel();
      showPreDeal();
      resetLocalStats();

      if (el.autoDeal) {
        el.autoDeal.checked = true;
        autoDealEnabled = true;
      }

      try {
        const r = await fetch(`${API_BASE}/restart`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: CLIENT_ID,
            guest_id: GUEST_ID,
            target: TARGET
          })
        });
        if (r.ok) {
          const j = await r.json().catch(() => null);
          if (j?.stats) applyServerStats(j.stats);
          current = null;
        }
      } catch (e) {
        console.warn('[GAME24] /restart not available', e);
      }

      if (el.question) el.question.textContent = `Target: ${TARGET} — Ready to deal`;
      if (el.msg) el.msg.textContent = 'Session restarted — press Deal to start.';

      console.log('🔄 Game restarted successfully');

    } catch (e) {
      console.error('[doRestart] failed', e);
      showPreDeal();
      resetLocalStats();
    }
  }
  window.doRestart = doRestart;

  /* =========================
     Confirm modal helper
  ========================= */
  const qs = (q) => document.querySelector(q);
  const confirmEls = {
    backdrop: qs('#confirmBackdrop'),
    title: qs('#confirmTitle'),
    msg: qs('#confirmMsg'),
    ok: qs('#confirmOK'),
    cancel: qs('#confirmCancel'),
  };

  function openConfirm({ title, msg, onOK }) {
    if (confirmEls.title) confirmEls.title.textContent = title || 'Are you sure?';
    if (confirmEls.msg) confirmEls.msg.textContent = msg || '';
    const doClose = () => hideModal(confirmEls.backdrop);
    const handleOK = () => { try { onOK && onOK(); } finally { cleanup(); } };
    const cleanup = () => {
      if (confirmEls.ok) confirmEls.ok.removeEventListener('click', handleOK);
      if (confirmEls.cancel) confirmEls.cancel.removeEventListener('click', doClose);
      doClose();
    };
    if (confirmEls.ok) confirmEls.ok.addEventListener('click', handleOK);
    if (confirmEls.cancel) confirmEls.cancel.addEventListener('click', doClose);
    showModal(confirmEls.backdrop);
  }

  /* =========================
     Summary / Exit flow
  ========================= */
  function showSummaryModalReport(html) {
    if (el.summaryReport) el.summaryReport.innerHTML = html || '<p>No summary.</p>';
    showModal(el.summaryBackdrop);
  }

  const hideSummary = () => hideModal(el.summaryBackdrop);

  async function openSummaryFlow() {
    try {
      const r = await fetch(`${API_BASE}/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: CLIENT_ID, guest_id: GUEST_ID, auto_deal: autoDealEnabled, target: TARGET })
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      window._lastSummary = j;
      const html = j?.play_summary?.report_html || '<p>No summary.</p>';
      if (el.summaryCsv) {
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
    } catch (e) {
      console.error('[openSummaryFlow]', e);
      alert('Could not load summary');
    }
  }
  window.openSummaryFlow = openSummaryFlow;

  let exiting = false;
  async function finalizeFromSummary() {
    if (exiting) return;
    exiting = true;
    try {
      hideSummary?.();
      const r = await fetch(`${API_BASE}/exit`, { method: 'POST' });
      const j = await r.json();
      if (j?.redirect_url) location.href = j.redirect_url;
    } catch (e) {
      exiting = false;
    }
  }

  window.finalizeFromSummary = finalizeFromSummary;

  /* =========================
     Case Pool UI
  ========================= */
  function parseCasePool(text) {
    if (!text) return [];
    const parts = text.split(/[\s,\|]+/g).filter(Boolean);
    const nums = [];
    const seen = new Set();
    for (const p of parts) {
      const n = parseInt(p, 10);
      if (!Number.isFinite(n)) continue;
      if (n < 1 || n > 1820) continue;
      if (seen.has(n)) continue;
      seen.add(n);
      nums.push(n);
      if (nums.length >= 25) break;
    }
    return nums;
  }

  function updateCasePoolUI() {
    const lvl = el.level ? el.level.value : 'easy';
    const isPool = (lvl === 'custom' || lvl === 'competition');

    if (el.casePoolRow) el.casePoolRow.style.display = isPool ? '' : 'none';
    const wrap = el.compDurationInput && el.compDurationInput.parentElement;
    if (wrap) wrap.style.display = (lvl === 'competition') ? '' : 'none';
    if (el.compDurationInput) el.compDurationInput.disabled = (lvl !== 'competition');
    helpDisabled = (lvl === 'competition');

    if (isPool) {
      const savedPoolText = localStorage.getItem('casePoolText');
      if (!savedPoolText || savedPoolText.trim() === '') {
        if (el.msg) el.msg.textContent = 'Set up a puzzle pool and press Save to start.';
      }
    }
  }

  /* =========================
     Event listeners
  ========================= */
  function setupEventListeners() {
    // Operation buttons
    on(el.ops, 'click', (e) => {
      const t = e.target.closest('button[data-op]');
      if (!t) return;
      const op = t.dataset.op;
      if (op === '(') return insertAtCursor('()');
      return insertAtCursor(op);
    });

    // Control buttons
    on(el.backspace, 'click', backspaceAtCursor);
    on(el.clear, 'click', clearAnswer);
    on(el.check, 'click', check);
    on(el.noBtn, 'click', () => {
      if (el.answer) {
        el.answer.value = 'no solution';
        check();
      }
    });
    on(el.help, 'click', () => help(false));
    on(el.helpAll, 'click', () => help(true));

    // Deal / Next
    on(el.next, 'click', async () => {
      try {
        const anyFace = [...el.cards.querySelectorAll('img.card')].some(img => {
          const a = img.getAttribute('alt') || '';
          return a && a !== 'back' && a !== 'void' && a !== '—';
        });
        if (!anyFace) {
          await deal({ advanceCounter: true });
        } else {
          await skipThenDeal();
        }
      } catch (e) {
        console.error(e);
      }
    });

    // Case management
    on(el.loadCaseBtn, 'click', loadCaseById);
    if (el.caseIdInput) {
      el.caseIdInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          loadCaseById();
        }
      });
    }

    // Restart
    on(el.restart, 'click', (e) => {
      e.preventDefault();
      cancelNextDeal();
    
      // Prefer the dedicated Restart modal if it exists
      if (restartModal) {
        const close = () => hideModal(restartModal);
    
        // Bind once per open
        restartConfirm?.addEventListener('click', () => { close(); doRestart(); }, { once: true });
        restartCancel?.addEventListener('click', close, { once: true });
        restartClose?.addEventListener('click',  close, { once: true });
    
        showModal(restartModal);
        return;
      }
    
      // Fallback: inline confirm if the modal is unavailable
      if (confirm('Restart? This will reset counters and start a new session.')) {
        doRestart();
      }
    });


    // Exit now opens Summary first
    on(el.exit, 'click', (e) => {
      e.preventDefault();
      cancelNextDeal();
      openSummaryFlow();
    });

    // Summary modal controls
    on(el.summaryResume, 'click', (e) => {
      e.preventDefault();
      hideSummary();
    });
    on(el.summaryClose, 'click', (e) => {
      e.preventDefault();
      hideSummary();
    });
    on(el.summaryExit, 'click', (e) => {
      e.preventDefault();
      finalizeFromSummary();
    });

    // Level changes
    on(el.level, 'change', () => {
      const newLevel = el.level.value;
      localStorage.setItem('level', newLevel);

      if (newLevel !== 'custom' && newLevel !== 'competition') {
        console.log('🚪 poolOffPreserveLevel , not resetting to easy mode');
        poolOffPreserveLevel();
      } else {
        updateCasePoolUI();
        showPreDeal();
        if (el.question) el.question.textContent = `Target: ${TARGET} — Set up pool and press Save`;
      }
    });

    // Save pool → backend
    on(el.saveCasePoolBtn, 'click', async () => {
      const lvl = el.level ? el.level.value : 'easy';
      if (lvl !== 'custom' && lvl !== 'competition') {
        showError('Select custom or competition first.');
        return;
      }
      const ids = parseCasePool(el.casePoolInput ? el.casePoolInput.value : '');
      if (!ids.length) {
        showError('Enter 1–25 valid Case IDs (1–1820).');
        return;
      }
      if (el.casePoolInput) localStorage.setItem('casePoolText', el.casePoolInput.value);

      const payload = { mode: lvl, case_ids: ids, client_id: CLIENT_ID, guest_id: GUEST_ID };
      if (lvl === 'competition') {
        let mins = 5;
        if (el.compDurationInput) {
          const v = parseInt(el.compDurationInput.value, 10);
          if (Number.isFinite(v)) mins = v;
        }
        mins = Math.max(1, Math.min(60, mins));
        payload.duration_sec = mins * 60;
        localStorage.setItem('compDurationMin', String(mins));
      }

      try {
        showPreDeal();
        if (el.question) el.question.textContent = 'Setting up pool...';

        const r = await fetch(`${API_BASE}/pool`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!r.ok) {
          const er = await r.json().catch(() => ({}));
          throw new Error(er.error || 'Failed to set pool');
        }

        showPreDeal();
        if (el.msg) el.msg.textContent = `Pool saved (${ids.length} case IDs) for ${lvl}. Press Deal to start.`;
        if (el.question) el.question.textContent = `Target: ${TARGET} — Pool ready (${ids.length} puzzles)`;

      } catch (e) {
        showError(e.message);
        showPreDeal();
      }
    });

    // Theme changes
    on(el.theme, 'change', () => {
      localStorage.setItem('theme', el.theme.value);
    });

    // Auto-deal toggle
    on(el.autoDeal, 'change', () => {
      const v = !!el.autoDeal?.checked;
      localStorage.setItem('autoDeal_g24', String(v));
      autoDealEnabled = v;
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      try {
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        const key = e.key || '';
        const k = typeof key === 'string' ? key.toLowerCase() : '';
        if (!k) return;

        if (e.target === el.answer && k === 'enter') {
          e.preventDefault();
          check();
          return;
        }

        if (k === 'd') {
          e.preventDefault();
          skipThenDeal();
        } else if (k === 'n') {
          e.preventDefault();
          if (el.answer) {
            el.answer.value = 'no solution';
            check();
          }
        } else if (k === 'h' && e.shiftKey) {
          e.preventDefault();
          help(true);
        } else if (k === 'h') {
          e.preventDefault();
          help(false);
        } else if (k === 'r') {
          e.preventDefault();
          doRestart();
        } else if (k === 'x') {
          e.preventDefault();
          openSummaryFlow();
        } 
      } catch (error) {
        console.error('Error in keyboard handler:', error);
      }
    });
  }

  /* =========================
     Initialize game
  ========================= */
  function init() {
    console.log('🎮 Initializing game...');

    // Persist some settings on load
    const tSaved = localStorage.getItem('theme');
    if (tSaved && el.theme) el.theme.value = tSaved;
    const lSaved = localStorage.getItem('level');
    if (lSaved && el.level) el.level.value = lSaved;
    const poolSaved = localStorage.getItem('casePoolText');
    if (poolSaved && el.casePoolInput) el.casePoolInput.value = poolSaved;
    const durSaved = localStorage.getItem('compDurationMin');
    if (durSaved && el.compDurationInput) el.compDurationInput.value = durSaved;

    // Setup event listeners
    setupEventListeners();

    // Show initial state
    showPreDeal();
    updateCasePoolUI();
    updateStats();

    console.log('✅ Game initialized');
  }

  // Boot once
  let booted = false;
  async function boot() {
    if (booted) return;
    booted = true;
    updateStats();
    showPreDeal();
  }

  // Start the game
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
