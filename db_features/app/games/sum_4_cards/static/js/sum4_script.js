/* Sum 4 Cards — frontend (single source of truth = backend)
   - Fix: loud “wrong” feedback (shake + big X)
*/
(() => {
  'use strict';

  // --------------- Config ---------------
  const DEBUG = true; // << flip to false to silence [SUM4] logs
  const API_BASE   = '/games/sum_4_cards/api';
  const BACK_PATH  = '/games/assets/cards/back.png';
  const CARDS_BASE = BACK_PATH.replace(/back\.png$/i, '');
  const DISPLAY_SUIT = 'S'; // fallback suit for images

  // --------------- Small helpers ---------------
  const $ = (q) => document.querySelector(q);
  const on = (el, ev, fn) => el && el.addEventListener(ev, fn);
  const dbg = (...args) => { if (DEBUG) console.log('[SUM4]', ...args); };

  function showEl(sel, display = null) {
    const el = (typeof sel === 'string') ? $(sel) : sel;
    if (!el || !el.style) { if (DEBUG) console.warn('[SUM4] showEl: element not found', sel); return; }
    const isModal = el.id === 'poolCompletionBackdrop' || el.classList?.contains('modal-backdrop');
    el.style.display = display ?? (isModal ? 'flex' : 'block');
    el.style.opacity = '1';
    el.style.pointerEvents = 'auto';
    dbg('showEl:', el.id || el.className, 'display=', el.style.display);
  }
  function hideEl(sel) {
    const el = (typeof sel === 'string') ? $(sel) : sel;
    if (!el || !el.style) { if (DEBUG) console.warn('[SUM4] hideEl: element not found', sel); return; }
    el.style.display = 'none';
    el.style.opacity = '0';
    el.style.pointerEvents = 'none';
    dbg('hideEl:', el.id || el.className);
  }

  // --------------- Local storage ---------------
  const LS = { get:(k,d)=>localStorage.getItem(k)??d, set:(k,v)=>localStorage.setItem(k,v) };
  const loadAutoDeal         = () => LS.get('sum4.auto_deal','1') === '1';
  const saveAutoDeal         = (b) => LS.set('sum4.auto_deal', b?'1':'0');
  const loadShowRunningTotal = () => LS.get('sum4.show_running_total','1') === '1';
  const saveShowRunningTotal = (b) => LS.set('sum4.show_running_total', b?'1':'0');

  // --------------- State ---------------
  let envelope = null;
  let server_step = 0;
  let hasActiveHand = false;
  let isSettingUpPool = false;
  let currentRunningTotal = null;
  let eduFormulaText = '';
  let poolFinished = false;

  // purely UI counters (not authoritative)
  const stats = { played:0, solved:0, helps:0, incorrect:0, skipped:0 };

  // --------------- Timer ---------------
  let tStart = 0, tTick = null;
  const fmt = (ms) => { const s = Math.floor(ms/1000), m = Math.floor(s/60), r = s%60; return `${String(m).padStart(2,'0')}:${String(r).padStart(2,'0')}`; };
  const timerStart = () => { if (tTick) clearInterval(tTick); tStart = performance.now(); const t=$('#timer'); if (t) t.textContent='00:00'; tTick = setInterval(()=>{ const t=$('#timer'); if (t) t.textContent = fmt(performance.now()-tStart); }, 100); };
  const timerStop  = () => { if (tTick) { clearInterval(tTick); tTick = null; } };

  // --------------- UI: message & feedback ---------------
  function feedback(txt, ok = null) {
    const el = $('#answerFeedback');
    if (!el) return;
    if (ok === true) { el.innerHTML = '<span class="big-check">✓</span>'; el.className = 'answer-feedback success-icon'; return; }
    if (ok === false) { el.innerHTML = '<span class="big-x">✗</span>'; el.className = 'answer-feedback error-icon'; return; }
    el.textContent = txt || ''; el.className = 'answer-feedback';
  }

  function msg(txt = '', kind = '') {
    const el = $('#msg');
    if (!el) return;
    const showHint = $('#showRunningTotal')?.checked ?? true;
    const hint = (showHint && hasActiveHand && currentRunningTotal != null)
      ? `<span class="hint-inline">• Hint: ${currentRunningTotal}</span>` : '';
    el.innerHTML = [txt || '', hint].filter(Boolean).join(' ');
    el.className = 'status' + (kind ? ` status-${kind}` : '');
  }

  const updateStats = () => {
    const S = (id, text) => { const el=document.getElementById(id); if (el) el.textContent=text; };
    S('played',   `Played: ${stats.played}`);
    S('solved',   `Solved: ${stats.solved}`);
    S('revealed', `Helped: ${stats.helps}`);   // UI-only
    S('incorrect',`Wrong Attempts: ${stats.incorrect}`); // UI-only
    S('skipped',  `Skipped: ${stats.skipped}`); // UI-only
  };
  const updateProgressHeader = () => {
    const hdr = $('#progressTitle');
    if (!hdr) return;
    const qnum = stats.played;
    const cid = envelope?.case_id ?? '—';
    hdr.textContent = `Q${qnum} [${cid}]`;
  };

  function setInputsEnabled(enabled) {
    $('#check')  && ($('#check').disabled  = !enabled);
    $('#answer') && ($('#answer').disabled = !enabled);
    $('#deal')   && ($('#deal').disabled   = poolFinished ? false : !enabled);
  }

  // --------------- Cards ---------------
  const rankTok = (rank) => (rank===1?'A':rank===10?'T':rank===11?'J':rank===12?'Q':rank===13?'K':String(rank));
  const cardSrcForRank = (rank, suit) => `${CARDS_BASE}${rankTok(rank)}${(suit||DISPLAY_SUIT)}.png`;
  const setCardBack = (i) => { const img = $(`#card-${i}`); if (img) { img.src = BACK_PATH; img.alt = 'Back'; } };
  const setCardFace = (i, rank, suit) => { const img = $(`#card-${i}`); if (img) { img.src = cardSrcForRank(rank, suit); img.alt = `${rankTok(rank)}${suit||DISPLAY_SUIT}`; } };
  const setAllBack = () => { for (let i=0;i<4;i++) setCardBack(i); };

  function flipGroup(indexes) {
    (indexes || []).forEach(i => {
      const c = envelope?.table?.cards?.[i];
      if (c) setCardFace(i, c.rank, c.suit);
    });
    updateFormula();
  }

  // --------------- Formula (in answer placeholder) ---------------
  function updateFormula() {
    const ans = $('#answer');
    if (!envelope) {
      eduFormulaText = '';
      if (ans) ans.placeholder = 'Enter running sum…';
      msg();
      return;
    }
    const rev = envelope.reveal || {};
    const out = new Set();
    (rev.init_reveal || []).forEach(i => out.add(i));
    const plan = rev.groups || [];
    for (let i = 0; i <= Math.min(server_step, plan.length - 1); i++) {
      (plan[i] || []).forEach(ix => out.add(ix));
    }
    const slots = [...out].sort((a,b)=>a-b);
    if (!slots.length) {
      eduFormulaText = '';
      if (ans) ans.placeholder = 'Enter running sum…';
      msg();
      return;
    }
    const nums = slots.map(i => Number(envelope.table.cards[i].rank));
    eduFormulaText = `${nums.join(' + ')} = ?`;
    if (ans) ans.placeholder = eduFormulaText;
    msg(); // refresh hint visibility
  }

  function showFinalFormula() {
    if (!envelope) return;
    const ans = $('#answer');
    const nums = (envelope.table.cards || []).map(c => Number(c.rank));
    const final = `${nums.join(' + ')} = ${nums.reduce((a,b)=>a+b,0)}`;
    eduFormulaText = final;
    if (ans) ans.placeholder = final;
    msg('✅ Correct!', 'success');
  }

  function applyHintUI() {
    const el = $('#msg');
    const base = el ? el.textContent.replace(/• Hint:.*/, '').trim() : '';
    msg(base, '');
  }

  // --------------- Render initial reveal ---------------
  function renderTable(table) {
    if (!table) { setAllBack(); return; }
    const reveal = envelope?.reveal || {};
    const init = Array.isArray(reveal.init_reveal) ? reveal.init_reveal : [];
    setAllBack();
    if (init.length) flipGroup(init);
    updateFormula();
  }

  // --------------- UI reads ---------------
  function currentDifficulty() {
    const v = $('#difficulty')?.value || '';
    return (v && v.toLowerCase()!=='auto') ? v.toLowerCase() : null;
  }
  function currentRevealMode() {
    // Expecting 'two_then_one' | 'one_by_one' | 'all_at_once' (server MODE_MAP)
    const raw = $('#revealMode')?.value || 'two_then_one';
    dbg('UI reveal_mode =>', raw);
    return raw;
  }

  // --------------- Backend-help sync (read-only) ---------------
  function syncHelpCountFrom(resp) {
    if (resp && typeof resp.help_count === 'number') {
      dbg('help_count (server):', resp.help_count);
    }
  }

  // --------------- Core flow calls ---------------
  async function start(caseId = null) {
    try {
      msg('', ''); feedback('');
      resetBoard();

      const payload = {
        case_id: caseId ?? null,
        difficulty: currentDifficulty(),
        reveal_mode: currentRevealMode()
      };
      dbg('START →', payload);
      const res = await fetch(`${API_BASE}/start`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
      });
      const data = await res.json().catch(()=>({}));
      dbg('START ←', data);
      syncHelpCountFrom(data);

      if (!data || data.ok !== true) { msg((data && (data.reason||data.error)) || 'Failed to start','error'); return; }

      if (data.pool_completed) {
        dbg('START says pool_completed');
        poolFinished = true;
        hasActiveHand = false; envelope = null; server_step = 0;
        setAllBack(); updateFormula();
        setInputsEnabled(false);
        await showPoolCompletionModal();
        return;
      }

      if (!data.envelope || !data.envelope.table) { msg('Start OK but missing envelope/table.', 'error'); return; }

      envelope = data.envelope;
      hasActiveHand = true;
      server_step = 0;
      stats.played++; updateStats(); updateProgressHeader();

      renderTable(envelope.table);
      timerStart();
      const q = $('#question'); if (q) q.textContent = `Target Sum: ${data.target ?? '—'}`;
      const ans = $('#answer'); if (ans) ans.focus();

      dbg('ENVELOPE.reveal =', envelope.reveal);

    } catch (err) {
      console.error('START error:', err);
      msg('Failed to start', 'error');
    }
  }

  async function finish(final_answer) {
    try {
      setInputsEnabled(false);
      timerStop();

      const body = { case_id: envelope?.case_id, final_answer };
      dbg('FINISH →', body);
      const res = await fetch(`${API_BASE}/finish`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      const data = await res.json().catch(()=>({}));
      dbg('FINISH ←', data);
      syncHelpCountFrom(data);

      if (!data || data.ok !== true) { msg(data?.reason || 'Finish failed', 'error'); setInputsEnabled(true); return; }

      feedback('', true);
      msg('✅ Correct!', 'success');
      stats.solved++; updateStats();

      if (data.pool_completed) {
        dbg('FINISH says pool_completed');
        poolFinished = true;
        hasActiveHand = false; envelope = null; server_step = 0;
        setAllBack(); updateFormula();
        await showPoolCompletionModal();
        return;
      }

      hasActiveHand = false; envelope = null; server_step = 0;

      if ($('#autoDeal')?.checked && !isSettingUpPool) {
        setTimeout(() => deal(), 400);
      } else {
        setInputsEnabled(true);
      }

    } catch (error) {
      console.error('Finish error:', error);
      msg('Error finishing puzzle', 'error');
      setInputsEnabled(true);
    }
  }

  async function help() {
    try {
      if (!hasActiveHand || !envelope) { msg('No active hand. Press Deal.', 'error'); return; }
      const payload = { action:'help', server_step, envelope };
      dbg('HELP →', payload);
      const res = await fetch(`${API_BASE}/step`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
      });
      const data = await res.json().catch(()=>({}));
      dbg('HELP ←', data);
      syncHelpCountFrom(data);

      if (data.ok) {
        showEl('#solutionPanel');
        const sm = $('#solutionMsg'); if (sm) sm.textContent = (data.expected !== undefined)
          ? `Current sum is ${data.expected}. Enter it and Check.`
          : 'Enter the running total so far.';
        if (data.expected !== undefined) { currentRunningTotal = data.expected; applyHintUI(); }
      } else {
        msg('Help not available for this step.', 'error');
      }
    } catch (error) {
      console.error('Help error:', error);
    }
  }

  async function skip(opts = {}) {
    const suppressAuto = !!opts.suppressAuto;
    try {
      if (!hasActiveHand || !envelope) { dbg('SKIP ignored - no active hand'); return; }
      const body = { case_id: envelope?.case_id };
      dbg('SKIP →', body);
      const res = await fetch(`${API_BASE}/skip`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      const data = await res.json().catch(()=>({}));
      dbg('SKIP ←', data);
      syncHelpCountFrom(data);

      if (!data || !data.ok) { msg('Failed to skip hand','error'); return; }

      stats.skipped++; updateStats();

      hasActiveHand=false; envelope=null; server_step=0;
      setAllBack(); updateFormula();

      if (!suppressAuto && $('#autoDeal')?.checked && !isSettingUpPool) {
        setTimeout(() => deal(), 400);
      }
    } catch (error) {
      console.error('Skip error:', error);
      msg('Error skipping hand', 'error');
    }
  }

  let dealLock = false;
  async function deal() {
    if (dealLock) return;
    if (poolFinished) { await showPoolCompletionModal(); return; }
    dealLock = true;
    try {
      const mode = $('#poolState')?.value || 'single';
      dbg('DEAL: start. hasActiveHand=', hasActiveHand, 'mode=', mode);
      if (hasActiveHand && envelope && !isSettingUpPool) {
        dbg('DEAL: skipping active hand first');
        await skip({ suppressAuto:true });
        await new Promise(r => setTimeout(r, 100));
      }
      await start(null);
    } finally {
      dealLock = false;
    }
  }

  // --------------- Pool UI & Save Pool / Clear Pool ---------------
  function applyPoolUI() {
    const mode = $('#poolState')?.value || 'single';
    (mode==='single') ? showEl('#singleRow') : hideEl('#singleRow');
    (mode!=='single') ? showEl('#poolRow')  : hideEl('#poolRow');
    (mode==='competition') ? showEl('#compWrap') : hideEl('#compWrap');
    const helpBtn = $('#help');
    if (helpBtn) {
      helpBtn.disabled = (mode === 'competition');
      helpBtn.textContent = (mode === 'competition') ? 'Help (Disabled)' : 'Help';
    }
    hideEl('#skip'); // Deal behaves as skip
  }

  async function savePoolHandler() {
    try {
      const mode = ($('#poolState')?.value || 'single');
      if (mode === 'single') { msg('Switch Mode to custom or competition first.', 'error'); return; }

      const raw = ($('#poolInput')?.value || '').trim();
      const ids = raw.split(/[^0-9]+/).map(s=>parseInt(s,10)).filter(n=>Number.isFinite(n));
      if (!ids.length) { msg('Enter at least one case id.', 'error'); return; }

      const body = { mode, ids };
      if (mode === 'competition') {
        const mins = Number($('#compMinutes')?.value || 5);
        if (Number.isFinite(mins) && mins > 0) body.minutes = mins;
      }

      dbg('POOL SAVE →', body);
      const res = await fetch(`${API_BASE}/pool`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
      });
      const data = await res.json().catch(()=>({}));
      dbg('POOL SAVE ←', data);
      syncHelpCountFrom(data);

      if (!data || data.ok !== true) { msg(data?.message || 'Failed to save pool.', 'error'); return; }

      poolFinished = false;
      isSettingUpPool = false;
      hasActiveHand = false;
      envelope = null;
      server_step = 0;
      setAllBack(); updateFormula(); applyPoolUI();

      // FIX: Get total from response and use in message
      const total = Number(data.count ?? data.progress?.total_cases ?? ids.length);
      const tag = (mode === 'custom') ? 'custom' : 'competition';
      msg(`Pool ${tag} mode activated. Total puzzles: ${total}. Click "Deal" to start!`, 'success');

    } catch (err) {
      console.error('savePool error:', err);
      msg('Error saving pool', 'error');
    }
  }

  async function clearPoolHandler() {
    try {
      dbg('POOL CLEAR → /pool (mode=off)');
      const res = await fetch(`${API_BASE}/pool`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'off' })
      });
      const raw = await res.text();
      dbg('POOL CLEAR status:', res.status, 'raw:', raw);

      let data = {}; try { data = JSON.parse(raw); } catch {}
      if (!res.ok || data?.ok !== true) {
        const reason = data?.message || data?.reason || 'Failed to clear pool.';
        console.warn('[SUM4] clearPoolHandler: backend said not ok →', data);
        msg(reason, 'error'); return;
      }

      // Sync UI + state
      const selector = document.querySelector('#poolState');
      if (selector) selector.value = 'single';
      applyPoolUI();

      poolFinished = false; isSettingUpPool = false; hasActiveHand = false;
      envelope = null; server_step = 0;

      const box = document.querySelector('#poolInput'); if (box) box.value = '';
      setAllBack(); updateFormula(); setInputsEnabled(true);
      msg('Pool cleared on server. You are back to Single mode — press Deal to play or set a new pool.', 'success');
    } catch (e) {
      console.error('clearPoolHandler error', e);
      msg('Error clearing pool', 'error');
    }
  }

  // --------------- Summary / Pool completion ---------------
  function debugShape(tag, obj) {
    try { dbg(`shape:${tag}`, Object.keys(obj||{})); } catch {}
  }

  async function fetchPoolSummary() {
    try {
      dbg('POOL SUMMARY →');
      const res = await fetch(`${API_BASE}/pool_summary`, { method:'GET' });
      const status = res.status;
      const text   = await res.text();
      dbg('POOL SUMMARY status:', status, 'raw:', text);
      let data = {};
      try { data = JSON.parse(text); } catch {}
      dbg('POOL SUMMARY ←', data);
      return data;
    } catch (e) {
      console.error('pool_summary error', e);
      return null;
    }
  }

  async function showPoolCompletionModal() {
    try {
      dbg('=== SHOW POOL COMPLETION MODAL START ===');
      const backdrop = $('#poolCompletionBackdrop');
      const box      = $('#poolCompletionBox');
      const body     = $('#poolCompletionBody');

      const data = await fetchPoolSummary();
      dbg('Pool completion report:', data);

      // FIX: Ensure we can handle both response formats
      const summary = data?.summary || data || {};
      const stats   = summary?.stats || summary || {};
      const details = Array.isArray(summary?.details) ? summary.details : [];
      const progress = summary?.progress || {};

      debugShape('pool_summary', summary || {});
      debugShape('pool_summary.stats', stats);
      debugShape('pool_summary.progress', progress);

      if (body && data && data.ok !== false) {
        const total   = Number(stats.total ?? progress.total_cases ?? details.length ?? 0);
        const done    = Number(stats.done ?? progress.completed_cases ?? details.length ?? 0);
        const correct = Number(stats.correct ?? 0);
        const wrong   = Number(stats.incorrect ?? stats.wrong ?? 0);
        const skipped = Number(stats.skipped ?? 0);
        const helped  = Number(stats.helps ?? stats.helped ?? 0);
        const attempted = correct + wrong;
        const acc = attempted > 0 ? Math.round((correct / attempted) * 100) : 0;

        const labelFor = (r) => {
          const x = String(r || '').toLowerCase();
          if (x === 'completed' || x === 'correct' || x === 'true' || x === 'solved') return '✅ Correct';
          if (x === 'wrong' || x === 'false' || x === 'incorrect') return '❌ Wrong';
          if (x === 'skipped') return '⏭️ Skipped';
          return r ?? '—';
        };

        const detailList = details.map(d => `<li>#${d.case_id} — ${labelFor(d.result)}</li>`).join('');
        const timeDisp = stats.time || summary.time || '—';

        const html = [
          `<div><strong>Completed:</strong> ${done} / ${total}</div>`,
          `<div><strong>Correct:</strong> ${correct}</div>`,
          `<div><strong>Wrong Attempts:</strong> ${wrong}</div>`,
          `<div><strong>Skipped:</strong> ${skipped}</div>`,
          `<div><strong>Helped:</strong> ${helped}</div>`,
          `<div><strong>Accuracy:</strong> ${acc}%</div>`,
          `<div><strong>Time:</strong> ${timeDisp}</div>`,
          details.length ? `<hr><div><strong>Puzzles:</strong></div><ol style="margin-left: 16px;">${detailList}</ol>` : ''
        ].join('');

        body.innerHTML = html;
        dbg('POOL MODAL rendered length:', html.length);
      } else if (body) {
        body.textContent = data?.message || 'Pool completed! Great job!';
      }

      if (backdrop) showEl(backdrop);
      if (box) showEl(box, 'block');
      document.body.classList.add('modal-open');

    } catch (e) {
      console.error('showPoolCompletionModal error', e);
      const body = $('#poolCompletionBody');
      if (body) body.textContent = 'Error loading pool summary.';
      if (backdrop) showEl(backdrop);
    }
  }

  async function fetchSessionSummary() {
    try {
      dbg('SESSION SUMMARY →');
      const res = await fetch(`${API_BASE}/summary`, { method: 'POST' });
      const status = res.status;
      const text   = await res.text();
      dbg('SESSION SUMMARY status:', status, 'raw:', text);
      let data = {}; try { data = JSON.parse(text); } catch {}
      dbg('SESSION SUMMARY ←', data);
      return { status, data };
    } catch (e) {
      console.error('summary error', e);
      return { status: 0, data: null };
    }
  }

  async function showSessionSummaryModal() {
    try {
      const { status, data } = await fetchSessionSummary();
      const wrap = document.querySelector('#summary-report');
      const backdrop = document.querySelector('#summaryBackdrop');

      if (wrap) {
        if (data && data.ok) {
          const S  = data.summary || {};
          const st = S.stats || {};
          const played   = st.played ?? '—';
          const solved   = st.solved ?? '—';
          const wrong    = (st.wrong ?? st.incorrect) ?? '—';
          const helps    = (st.helps ?? st.helped)    ?? '—';
          const acc      = (S.accuracy_percent != null) ? `${Math.round(S.accuracy_percent)}%` : '—';
          const timeDisp = S.total_time_formatted || S.session_duration_formatted || '—';
          const sessType = S.session_type || '—';

          const history =
            (Array.isArray(S.history) && S.history) ||
            (Array.isArray(S.recent)  && S.recent)  ||
            (Array.isArray(S.details) && S.details) || [];

          const labelFor = (r) => {
            const x = String(r ?? '').toLowerCase();
            if (['completed','correct','true'].includes(x)) return '✅ Correct';
            if (['wrong','false'].includes(x))              return '❌ Wrong';
            if (x === 'skipped')                            return '⏭️ Skipped';
            return (r != null ? String(r) : '—');
          };
          const toItem = (it) => {
            if (it && typeof it === 'object') {
              const cid = it.case_id ?? it.id ?? it.case ?? '—';
              const res = it.result  ?? it.status ?? it.ok ?? it.outcome ?? null;
              return `<li>#${cid} → ${labelFor(res)}</li>`;
            }
            return `<li>${String(it)}</li>`;
          };

          const lines = [];
          lines.push(`<div><strong>Session:</strong> ${sessType}</div>`);
          lines.push(`<div><strong>Played:</strong> ${played}</div>`);
          lines.push(`<div><strong>Solved:</strong> ${solved}</div>`);
          lines.push(`<div><strong>Wrong Attempts:</strong> ${wrong}</div>`);
          lines.push(`<div><strong>Helps:</strong> ${helps}</div>`);
          lines.push(`<div><strong>Accuracy:</strong> ${acc}</div>`);
          lines.push(`<div><strong>Time:</strong> ${timeDisp}</div>`);

          if (history.length) {
            lines.push('<hr><div><strong>Play History:</strong></div>');
            lines.push('<ol style="margin-left:16px;">' + history.map(toItem).join('') + '</ol>');
          }

          const html = lines.join('');
          wrap.innerHTML = html;
          dbg('SESSION MODAL rendered length:', html.length);
        } else {
          const reason = data?.message || data?.error || `Summary not available. HTTP ${status}`;
          wrap.innerHTML = `<div>${reason}</div>`;
          dbg('SESSION MODAL fallback reason:', reason);
        }
      }

      if (backdrop) showEl(backdrop);
    } catch (e) {
      console.error('showSessionSummaryModal fatal error:', e);
      const wrap = document.querySelector('#summary-report');
      if (wrap) wrap.innerHTML = 'Summary not available (exception).';
      showEl('#summaryBackdrop');
    }
  }

  // --------------- Reset / Restart ---------------
  async function doRestart() {
    try {
      dbg('RESTART → /debug/reset');
      const res = await fetch(`${API_BASE}/debug/reset`, { method:'POST' });
      const text = await res.text();
      let data = {};
      try { data = JSON.parse(text); } catch {}
      dbg('RESTART status/raw:', res.status, text);
      dbg('RESTART ←', data);

      poolFinished = false;
      isSettingUpPool = false;
      hasActiveHand = false;
      envelope = null;
      server_step = 0;
      currentRunningTotal = null;
      stats.played=0; stats.solved=0; stats.helps=0; stats.incorrect=0; stats.skipped=0;
      updateStats();
      setAllBack(); updateFormula();
      msg('Game reset. Ready — press Deal.', 'success');
      hideEl('#restartModal');
      setInputsEnabled(true);
    } catch (e) {
      console.error('restart error', e);
      msg('Failed to reset session', 'error');
    }
  }

  // --------------- Check (step) ---------------
  function shake(el) {
    if (!el) return;
    el.classList.add('shake');
    setTimeout(() => el.classList.remove('shake'), 500);
  }

  async function check() {
    try {
      const ansEl = $('#answer');
      const raw = (ansEl?.value || '').trim();
      if (!raw) { feedback('Enter your running sum.', false); shake(ansEl); return; }
      if (!hasActiveHand || !envelope) { msg('No active hand. Press Deal.', 'error'); return; }

      const payload = { action: 'check', answer: Number(raw), server_step, envelope };
      dbg('CHECK →', payload);
      const res = await fetch(`${API_BASE}/step`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
      });

      let data; try { data = await res.json(); } catch { data = {}; }
      dbg('CHECK ←', data);
      syncHelpCountFrom(data);

      if (!res.ok || data.ok === false) {
        // FIX: Clear any hint and show loud error
        currentRunningTotal = null;
        applyHintUI();
        msg('❌ Incorrect — try again.', 'error');
        feedback('', false);
        shake(ansEl);
        if (ansEl) { ansEl.value = ''; ansEl.focus(); }
        return;
      }

      if (data.expected !== undefined) { currentRunningTotal = data.expected; applyHintUI(); }

      const plan = envelope?.reveal?.groups || [];
      const planLen = plan.length;
      const newStep =
        (typeof data.next_step === 'number') ? data.next_step :
        (typeof data.server_step === 'number') ? data.server_step :
        server_step;
      const isComplete = (data.done === true) || (data.complete === true) || (newStep >= planLen);

      if (isComplete) {
        $('#check') && ($('#check').disabled = true);
        $('#answer') && ($('#answer').disabled = true);
        for (let i = 0; i < planLen; i++) flipGroup(plan[i]);
        feedback('', true);
        showFinalFormula();

        const finalAns = (data.final_answer !== undefined)
          ? Number(data.final_answer)
          : (data.expected !== undefined) ? Number(data.expected)
          : Number(raw);

        await finish(finalAns);
        return;
      }

      server_step = newStep;
      const nextGroup = Array.isArray(plan[server_step]) ? plan[server_step] : null;
      if (nextGroup) flipGroup(nextGroup);
      feedback('', true);
      msg('👍 Keep going…', '');
      if (ansEl) { ansEl.value = ''; ansEl.focus(); }

    } catch (error) {
      console.error('Check error:', error);
      msg('Error checking answer', 'error');
    }
  }

  // --------------- Wiring ---------------
  function wire() {
    // Settings toggles
    const ad  = $('#autoDeal'); if (ad) { ad.checked = loadAutoDeal(); on(ad,'change', () => saveAutoDeal(ad.checked)); }
    const srt = $('#showRunningTotal'); if (srt) { srt.checked = loadShowRunningTotal(); on(srt,'change', () => { saveShowRunningTotal(srt.checked); applyHintUI(); }); }

    // Numpad
    on(document, 'click', (e) => {
      const t = e.target.closest('[data-num],[data-action]');
      if (!t) return;
      const ans = $('#answer');
      if (!ans || ans.disabled) return;
      if (t.hasAttribute('data-num')) { ans.value = (ans.value || '') + String(t.getAttribute('data-num')); ans.focus(); return; }
      const act = t.getAttribute('data-action');
      if (act === 'back')  { ans.value = (ans.value || '').slice(0,-1); ans.focus(); }
      if (act === 'clear') { ans.value = ''; ans.focus(); }
      if (act === 'enter') { $('#check')?.click(); }
    });

    // Hotkeys
    on(document, 'keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); $('#check')?.click(); }
      if (e.key === 'd' || e.key === 'D') { e.preventDefault(); $('#deal')?.click(); }
      if (e.key === 'h' || e.key === 'H') { e.preventDefault(); $('#help')?.click(); }
      if (e.key === 'n' || e.key === 'N') { e.preventDefault(); $('#deal')?.click(); }
    });

    // Core
    on($('#deal'), 'click', deal);
    on($('#help'), 'click', help);
    on($('#check'), 'click', check);

    // Single Go
    on($('#singleGo'), 'click', async () => {
      const v = parseInt(($('#singleCaseId')?.value || '').trim(), 10);
      if (!Number.isFinite(v)) { msg('Please enter a valid case ID', 'error'); return; }
      const inp = $('#singleCaseId'); if (inp) inp.value='';
      await start(v);
    });

    // Exit / Summary
    on($('#exit'), 'click', async () => {
      dbg('EXIT clicked');
      await showSessionSummaryModal();
    });

    // Restart (modal confirm)
    on($('#restart'), 'click', () => { showEl('#restartModal'); });
    on($('#restartConfirm'), 'click', doRestart);
    on($('#restartCancel'), 'click', () => hideEl('#restartModal'));
    on($('#restartClose'), 'click', () => hideEl('#restartModal'));

    // How-to & Wrench
    on($('#btnHowto'), 'click', (e) => { 
      e.preventDefault(); 
      // FIX: Show modal instead of external link
      showEl('#howtoModal');
    });
    
         // === WRENCH MODAL - ENHANCED VERSION ===
     on($('#btnWrench'), 'click', async (e) => {
         e.preventDefault();
         e.stopPropagation();
         
         try {
             const r = await fetch(`${API_BASE}/debug/start`, { method:'POST' });
             const data = await r.json();
             const box = $('#debugSamplesList');
             
             if (box) {
                 const puzzles = data.samples || [];
                 box.innerHTML = createWrenchHTML(puzzles);
                 
                 if (puzzles.length) setupWrenchSearch(puzzles);
                 setupPuzzleClickHandlers();
                 setupCaseIdLoader();
                 setupQuickAccessButtons();
             }
             
             showEl('#debugSamplesModal');
         } catch (err) {
             console.error('Wrench error:', err);
             msg('Failed to load puzzles.', 'error');
         }
     });
     
     function createWrenchHTML(puzzles) {
         return `
             <div class="wrench-header">
                 <div class="wrench-stats">
                     <strong>Puzzle Browser</strong>
                     <div style="font-size: 0.9em; color: #666; margin-top: 4px;">
                         ${puzzles.length} sample puzzles + access to all 1820 cases
                     </div>
                 </div>
                 
                 <div class="wrench-quick-access">
                     <div style="margin-bottom: 12px;">
                         <label style="display: block; margin-bottom: 6px; font-weight: 600;">Quick Access:</label>
                         <div style="display: flex; gap: 8px;">
                             <input type="number" id="wrenchCaseId" placeholder="Case ID (1-1820)" 
                                    min="1" max="1820" style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 4px;">
                             <button id="wrenchLoadCase" class="primary-btn" style="white-space: nowrap;">Load</button>
                         </div>
                     </div>
                     
                     <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 12px;">
                         <button class="quick-case-btn" data-case="1">#1</button>
                         <button class="quick-case-btn" data-case="10">#10</button>
                         <button class="quick-case-btn" data-case="100">#100</button>
                         <button class="quick-case-btn" data-case="500">#500</button>
                         <button class="quick-case-btn" data-case="42">#42</button>
                         <button class="quick-case-btn" data-case="123">#123</button>
                         <button class="quick-case-btn" data-case="777">#777</button>
                         <button class="quick-case-btn" data-case="1820">#1820</button>
                     </div>
                 </div>
                 
                 <div class="wrench-sample-puzzles">
                     <label style="display: block; margin-bottom: 8px; font-weight: 600;">Sample Puzzles:</label>
                     <input type="text" id="wrenchSearch" placeholder="Search sample puzzles..." 
                            style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 12px;">
                 </div>
             </div>
             
             <div id="wrenchPuzzleContainer" class="wrench-puzzle-list">
                 ${puzzles.length ? renderPuzzles(puzzles) : '<p>No sample puzzles available.</p>'}
             </div>
         `;
     }
     
     function setupCaseIdLoader() {
         const caseIdInput = $('#wrenchCaseId');
         const loadButton = $('#wrenchLoadCase');
         if (caseIdInput && loadButton) {
             loadButton.addEventListener('click', () => {
                 const caseId = parseInt(caseIdInput.value);
                 if (caseId >= 1 && caseId <= 1820) {
                     start(caseId);
                     hideEl('#debugSamplesModal');
                     caseIdInput.value = '';
                 } else {
                     msg('Please enter a case ID between 1 and 1820', 'error');
                     caseIdInput.focus();
                 }
             });
             caseIdInput.addEventListener('keypress', (e) => {
                 if (e.key === 'Enter') loadButton.click();
             });
         }
     }
     
     function setupQuickAccessButtons() {
         document.querySelectorAll('.quick-case-btn').forEach(button => {
             button.addEventListener('click', (e) => {
                 const caseId = parseInt(button.getAttribute('data-case'));
                 start(caseId);
                 hideEl('#debugSamplesModal');
             });
         });
     }
     
     function setupWrenchSearch(puzzles) {
         const searchInput = $('#wrenchSearch');
         const container = $('#wrenchPuzzleContainer');
         if (searchInput && container) {
             searchInput.addEventListener('input', (e) => {
                 container.innerHTML = renderPuzzles(puzzles, e.target.value);
                 setupPuzzleClickHandlers();
             });
         }
     }
     
     function setupPuzzleClickHandlers() {
         const container = $('#wrenchPuzzleContainer');
         if (container) {
             container.addEventListener('click', (e) => {
                 const puzzleItem = e.target.closest('.wrench-puzzle-item');
                 if (puzzleItem) {
                     const caseId = puzzleItem.getAttribute('data-case-id');
                     start(parseInt(caseId));
                     hideEl('#debugSamplesModal');
                 }
             });
         }
     }
     
     function renderPuzzles(puzzles, searchTerm = '') {
         const filtered = searchTerm 
             ? puzzles.filter(p => String(p.case_id).includes(searchTerm) || (p.note && p.note.toLowerCase().includes(searchTerm.toLowerCase())))
             : puzzles;
         
         if (filtered.length === 0) return '<p style="text-align: center; color: #666; padding: 20px;">No puzzles found.</p>';
         
         return filtered.map(puzzle => `
             <div class="wrench-puzzle-item" data-case-id="${puzzle.case_id}">
                 <div class="wrench-puzzle-content">
                     <div class="wrench-puzzle-info">
                         <div class="wrench-puzzle-header">
                             <strong class="wrench-case-number">#${puzzle.case_id}</strong>
                             <span class="wrench-case-badge">Case ${puzzle.case_id}</span>
                         </div>
                         ${puzzle.note ? `<div class="wrench-puzzle-note">${puzzle.note}</div>` : ''}
                     </div>
                     <span class="wrench-play-button">Play →</span>
                 </div>
             </div>
         `).join('');
     }
    // Debug samples modal wiring
     on($('#debugSamplesClose'), 'click', () => hideEl('#debugSamplesModal'));
     on($('#debugSamplesGotIt'), 'click', () => hideEl('#debugSamplesModal'));
     on($('#debugSamplesModal'), 'click', (e) => {
         if (e.target.id === 'debugSamplesModal') hideEl('#debugSamplesModal');
     });

    // Pool UI & Save / Clear
    on($('#poolState'), 'change', () => {
      dbg('poolState changed →', $('#poolState')?.value);
      poolFinished = false;
      applyPoolUI();
      hasActiveHand=false; envelope=null; server_step=0; setAllBack(); updateFormula();
      const q=$('#question'); if (q) q.textContent='Ready — press Deal';
      msg('');
    });
    on($('#savePool'), 'click', savePoolHandler);
    on($('#clearPool'), 'click', clearPoolHandler);

    // Pool completion modal buttons - NEW WIRING
    on($('#poolCompletionClose'), 'click', () => {
      hideEl('#poolCompletionBackdrop');
      document.body.classList.remove('modal-open');
      setInputsEnabled(true);
    });
    
    on($('#poolCompletionContinue'), 'click', () => {
      hideEl('#poolCompletionBackdrop');
      document.body.classList.remove('modal-open');
      setInputsEnabled(true);
    });

    on($('#poolCompletionNewPool'), 'click', () => {
      hideEl('#poolCompletionBackdrop');
      document.body.classList.remove('modal-open');
      // Reset to single mode and clear pool
      $('#poolState').value = 'single';
      applyPoolUI();
      clearPoolHandler();
    });

    on($('#poolCompletionSummary'), 'click', () => {
      hideEl('#poolCompletionBackdrop');
      showSessionSummaryModal();
    });

    on($('#poolCompletionBackdrop'), 'click', (e) => {
      if (e.target.id === 'poolCompletionBackdrop') {
        $('#poolCompletionClose')?.click();
      }
    });

    // How-to modal wiring - NEW
    on($('#howtoClose'), 'click', () => hideEl('#howtoModal'));
    on($('#howtoGotIt'), 'click', () => hideEl('#howtoModal'));
    on($('#howtoModal'), 'click', (e) => {
      if (e.target.id === 'howtoModal') hideEl('#howtoModal');
    });

    // Session summary modal buttons
    on($('#summaryClose'), 'click', () => hideEl('#summaryBackdrop'));
    on($('#summaryResume'), 'click', () => { hideEl('#summaryBackdrop'); setInputsEnabled(true); });
    on($('#summaryExit'), 'click', () => { window.location.href = '/'; });

    // Hide Skip in UI (Deal is the skip)
    if ($('#skip')) hideEl('#skip');
  }

  // --------------- Reset & Pre-deal ---------------
  function resetBoard() {
    setAllBack();
    const ans = $('#answer');
    if (ans) { ans.value=''; ans.disabled=false; ans.placeholder='Enter running sum…'; }
    $('#check') && ($('#check').disabled=false);
    feedback('');
    currentRunningTotal = null;
    updateFormula();
    setInputsEnabled(true);
  }

  function showPreDeal() {
    setAllBack(); updateFormula();
    const ans = $('#answer'); if (ans) { ans.value=''; ans.placeholder='Enter running sum…'; ans.focus(); }
    msg('Ready — press Deal to start.', '');
  }

  // --------------- Init ---------------
  document.addEventListener('DOMContentLoaded', () => {
    if (!localStorage.getItem('sum4.auto_deal')) saveAutoDeal(true);
    if (!localStorage.getItem('sum4.show_running_total')) saveShowRunningTotal(true);
    $('#autoDeal') && ($('#autoDeal').checked = loadAutoDeal());
    $('#showRunningTotal') && ($('#showRunningTotal').checked = loadShowRunningTotal());

    wire();
    applyHintUI();
    applyPoolUI();
    updateStats();
    showPreDeal();
    dbg('INIT complete');
  });

  // Global error logging
  window.addEventListener('error', (e) => { console.error('[SUM4 GLOBAL ERROR]:', e.error||e.message, 'at', e.filename, e.lineno); });
  window.addEventListener('unhandledrejection', (e) => { console.error('[SUM4 UNHANDLED REJECTION]:', e.reason); });
})();
