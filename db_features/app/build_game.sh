#!/usr/bin/env bash
# Usage:
#   ./build_game.sh missing_addend "Missing Addend"
#   ./build_game.sh my_new_game "My New Game"
#
# This creates:
#   app/games/<game>/__init__.py
#   app/games/<game>/<game>_routes.py
#   app/games/<game>/templates/<game>/play.html
#   app/games/<game>/static/js/<game>_script.js
#
# Notes:
# - It reuses your shared CSS via games_assets_bp (style.css).
# - Routes load puzzles from app.v_game_case_map (by game_key).
# - Frontend keeps the same layout/flow/settings as Sum4.
# - Minimal differences are isolated to each game folder.

cd /home/biqia/merge_games/projects/wholegame/
set -euo pipefail

GAME_KEY_RAW="${1:-}"
GAME_TITLE="${2:-}"

if [[ -z "$GAME_KEY_RAW" || -z "$GAME_TITLE" ]]; then
  echo "ERROR: need game_key and Title."
  echo "Example: ./build_game.sh missing_addend \"Missing Addend\""
  exit 1
fi

# folder-safe and python-safe names
GAME_KEY="$GAME_KEY_RAW"                             # used in DB app.games.game_key and queries
PKG_NAME="${GAME_KEY_RAW}"                           # python package dir under app/games/
BP_NAME="${GAME_KEY_RAW}"                            # Flask blueprint (import name)
ROUTES_PY="${BP_NAME}_routes.py"                     # routes file
JS_NAME="${BP_NAME}_script.js"                       # static js
TPL_DIR="app/games/${PKG_NAME}/templates/${BP_NAME}"
JS_DIR="app/games/${PKG_NAME}/static/js"
PKG_DIR="app/games/${PKG_NAME}"

mkdir -p "${TPL_DIR}"
mkdir -p "${JS_DIR}"

# __init__.py
cat > "${PKG_DIR}/__init__.py" <<PY
from flask import Blueprint

bp = Blueprint("${BP_NAME}", __name__, url_prefix="/games/${BP_NAME}",
               template_folder="templates", static_folder="static")

from . import ${ROUTES_PY%.py}  # noqa: E402,F401
PY

# routes
cat > "${PKG_DIR}/${ROUTES_PY}" <<'PY'
# Auto-generated game routes
from __future__ import annotations
import time, json, logging, random
from typing import Dict, Any, Optional, List
from flask import request, render_template, jsonify, make_response
from sqlalchemy import text
from flask_login import login_required
from app import db
from . import bp

# ---- GAME CONFIG ----
GAME_KEY = "{{GAME_KEY}}"
GAME_TITLE = "{{GAME_TITLE}}"

logger = logging.getLogger(GAME_KEY)
logger.setLevel(logging.INFO)

def _now_ms() -> int:
    import time
    return int(time.time() * 1000)

# Session bucket (process memory; OK for single-instance dev)
SESSIONS: Dict[str, Dict[str, Any]] = {}

def _sid() -> str:
    # Same cookie name convention as your other games
    sid = request.cookies.get("session_id")
    if not sid:
        sid = f"s_{random.randrange(1, 1_000_000_000)}"
    SESSIONS.setdefault(sid, {
        "overall_stats": {
            "played": 0, "solved": 0, "incorrect": 0, "skipped": 0,
            "total_time_ms": 0, "total_attempts": 0
        },
        "current_hand": None,
        "history": []
    })
    return sid

def _state() -> Dict[str, Any]:
    return SESSIONS[_sid()]

def _fetch_game_row() -> Dict[str, Any]:
    row = db.session.execute(
        text("SELECT id, title, metadata FROM app.games WHERE game_key=:k"),
        {"k": GAME_KEY}
    ).mappings().first()
    if not row:
        # Fallback to the provided title if DB isn't populated yet
        return {"id": None, "title": GAME_TITLE, "metadata": None}
    return dict(row)

def _fetch_case(case_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Source puzzles from app.v_game_case_map joined with puzzle_warehouse,
    same as your Sum4 approach.
    """
    if case_id is None:
        sql = """
        SELECT v.case_id, w.cards_key, w.ranks, w.sum_pips
        FROM app.v_game_case_map v
        JOIN app.puzzle_warehouse w ON w.cards_key = v.cards_key
        WHERE v.game_key = :k AND v.is_active = true
        ORDER BY random()
        LIMIT 1
        """
        row = db.session.execute(text(sql), {"k": GAME_KEY}).mappings().first()
    else:
        sql = """
        SELECT v.case_id, w.cards_key, w.ranks, w.sum_pips
        FROM app.v_game_case_map v
        JOIN app.puzzle_warehouse w ON w.cards_key = v.cards_key
        WHERE v.game_key = :k AND v.case_id = :cid
        """
        row = db.session.execute(text(sql), {"k": GAME_KEY, "cid": case_id}).mappings().first()

    if not row:
        raise RuntimeError(f"No puzzle for {GAME_KEY} (case_id={case_id})")
    return dict(row)

# === Core math for "Missing Addend" variant ==========================
# We reveal cards by groups (server-driven). After each reveal, the player
# must enter the running sum SO FAR (like Sum4), **but** the last step asks
# for the missing addend to hit a specific goal (sum_pips or configurable target).
MODE_GROUPS = {
    "two_then_one": [[0,1],[2],[3]],
    "one_by_one":   [[0],[1],[2],[3]],
    "all_at_once":  [[0,1,2,3]]
}

def _target_for_step(ranks: List[int], step: int, groups: List[List[int]], goal: int) -> Dict[str, int]:
    """
    Returns:
      - running_sum: sum of all revealed cards up to 'step'
      - missing: goal - running_sum  (only meaningful for final prompt, but we include both)
    """
    seen = set()
    for i in range(step + 1):
        for ix in groups[i]:
            seen.add(ix)
    running = sum(int(ranks[i]) for i in sorted(seen))
    return {"running_sum": running, "missing": int(goal) - int(running)}

def _start_envelope(case: Dict[str, Any], groups: List[List[int]]) -> Dict[str, Any]:
    # Shuffle ranks & independent suit shuffle (visual)
    ranks = [int(x) for x in case["ranks"]]
    r_shuf = ranks[:]
    random.shuffle(r_shuf)

    suits = ['S','H','D','C']
    random.shuffle(suits)

    cards = []
    for i, r in enumerate(r_shuf):
        cards.append({"rank": r, "suit": suits[i], "visible": False})

    return {
        "game_key": GAME_KEY,
        "case_id": case["case_id"],
        "table": {"slots": 4, "cards": cards},
        "reveal": {"groups": groups, "server_step": 0, "init_reveal": groups[0] if groups else []},
        "ui_hints": {"show_back_card": False},
    }

# ======================= Routes =======================

@bp.get("/play")
@login_required
def play():
    game = _fetch_game_row()
    return render_template(
        "{{BP_NAME}}/play.html",
        game=game, game_key=GAME_KEY,
        initial_cfg={}
    )

@bp.post("/api/start")
def api_start():
    st = _state()
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case_id")
    reveal_mode = (payload.get("reveal_mode") or "two_then_one").strip()

    case = _fetch_case(case_id)
    groups = MODE_GROUPS.get(reveal_mode, MODE_GROUPS["two_then_one"])
    env = _start_envelope(case, groups)

    # For Missing Addend, the default goal is the full sum of the 4 cards.
    goal = int(case["sum_pips"])
    st["current_hand"] = {
        "case_id": case["case_id"],
        "goal": goal,
        "started_at": _now_ms(),
        "attempts": 0
    }

    resp = {"ok": True, "envelope": env, "goal": goal}
    r = make_response(jsonify(resp))
    if not request.cookies.get("session_id"):
        r.set_cookie("session_id", _sid(), max_age=60*60*24*365, samesite="Lax")
    return r

@bp.post("/api/step")
def api_step():
    """Validate step input. If not last step → expect running sum.
       If last step → expect missing addend to reach goal.
    """
    st = _state()
    payload = request.get_json(silent=True) or {}

    env = payload.get("envelope") or {}
    server_step = int(payload.get("server_step", 0))
    answer = payload.get("answer")

    if answer is None:
        return jsonify({"ok": False, "error": "missing_answer"}), 400

    cards = (env.get("table") or {}).get("cards") or []
    ranks = [int(c.get("rank")) for c in cards]
    groups = (env.get("reveal") or {}).get("groups") or MODE_GROUPS["two_then_one"]
    goal = int(st.get("current_hand", {}).get("goal", 0))

    # compute
    info = _target_for_step(ranks, server_step, groups, goal)
    is_last = (server_step >= len(groups) - 1)

    try:
        ans = int(answer)
    except Exception:
        return jsonify({"ok": False, "error": "bad_answer"}), 400

    expected = info["missing"] if is_last else info["running_sum"]
    correct = (ans == expected)
    st["current_hand"]["attempts"] += 1
    if not correct:
        return jsonify({"ok": True, "correct": False, "expected": expected, "server_step": server_step, "done": False})

    # advance / finish
    next_step = server_step + 1
    if next_step >= len(groups):
        # finished hand
        st["overall_stats"]["played"] += 1
        st["overall_stats"]["solved"] += 1
        st["overall_stats"]["total_attempts"] += st["current_hand"]["attempts"]
        st["history"].append({"case_id": st["current_hand"]["case_id"], "result": "correct"})
        st["current_hand"] = None
        return jsonify({"ok": True, "correct": True, "done": True, "expected": expected})

    # continue; reveal next group on client
    return jsonify({"ok": True, "correct": True, "done": False, "server_step": next_step, "reveal": groups[next_step], "expected": expected})

@bp.post("/api/skip")
def api_skip():
    st = _state()
    cur = st.get("current_hand")
    if cur:
        st["overall_stats"]["played"] += 1
        st["overall_stats"]["skipped"] = st["overall_stats"].get("skipped", 0) + 1
        st["history"].append({"case_id": cur["case_id"], "result": "skipped"})
        st["current_hand"] = None
    return jsonify({"ok": True})

@bp.post("/api/summary")
def api_summary():
    st = _state()
    stats = st.get("overall_stats", {})
    hist = st.get("history", [])
    total = stats.get("played", 0)
    solved = stats.get("solved", 0)
    wrong  = stats.get("incorrect", 0)
    acc = (100.0 * solved / max(1, (solved + wrong)))
    return jsonify({
        "ok": True,
        "summary": {
            "session_type": "single",
            "stats": {"played": total, "solved": solved, "incorrect": wrong},
            "history": hist,
            "accuracy_percent": acc,
        }
    })

@bp.post("/debug/reset")
def api_reset():
    sid = _sid()
    SESSIONS[sid] = {
        "overall_stats": {"played": 0, "solved": 0, "incorrect": 0, "skipped": 0, "total_time_ms": 0, "total_attempts": 0},
        "current_hand": None, "history": []
    }
    return jsonify({"ok": True})
PY
# inject vars
sed -i.bak "s/{{GAME_KEY}}/${GAME_KEY}/g; s/{{GAME_TITLE}}/${GAME_TITLE}/g; s/{{BP_NAME}}/${BP_NAME}/g" "${PKG_DIR}/${ROUTES_PY}"
rm -f "${PKG_DIR}/${ROUTES_PY}.bak"

# template: play.html
cat > "${TPL_DIR}/play.html" <<'HTML'
{% extends "base.html" %}
{% block content %}
<link rel="stylesheet" href="{{ url_for('games_assets_bp.static', filename='css/style.css') }}">

<div class="wrap">
  <header class="game-header">
    <h1 class="game-title">{{ game.title or "Game" }}</h1>
    <p class="game-subtitle">Reveal → enter running sums → finish with the missing addend</p>
  </header>

  <div class="panel">
    <div class="topline">
      <span id="question">Ready — press Deal</span>
      <span id="timer">00:00</span>
      <div class="right-tools">
        <details class="settings">
          <summary>Settings</summary>
          <div class="settings-row">
            <label>
              Reveal Mode
              <select id="revealMode">
                <option value="two_then_one">Step by step (2 + 1 + 1)</option>
                <option value="one_by_one">One by one</option>
                <option value="all_at_once">All at once</option>
              </select>
            </label>
            <label>
              <input type="checkbox" id="autoDeal" checked> Auto-Deal
            </label>
            <label>
              <input type="checkbox" id="showRunningTotal" checked> Show running total hint
            </label>
          </div>
        </details>
      </div>
    </div>

    <div class="board">
      <!-- Cards -->
      <div id="cards" class="cards" data-back="{{ url_for('games_assets_bp.static', filename='cards/back.png') }}">
        <img class="card" id="card-0" alt="back">
        <img class="card" id="card-1" alt="back">
        <img class="card" id="card-2" alt="back">
        <img class="card" id="card-3" alt="back">
      </div>

      <!-- Status -->
      <div id="msg" class="status"></div>

      <!-- Answer box -->
      <div class="answer-container">
        <input id="answer" class="answer-box" type="number" inputmode="numeric"
               placeholder="Enter running sum…" autocomplete="off" />
        <div id="answerFeedback" class="answer-feedback"></div>
      </div>

      <!-- Main actions -->
      <div class="button-row">
        <button id="backBtn">⌫ Back</button>
        <button id="clearBtn">Clear</button>
        <button id="help" class="info-btn">Help</button>
        <button id="deal" class="primary-btn">Deal (D)</button>
      </div>

      <div class="button-row">
        <button id="restart" class="danger-btn">Restart</button>
        <button id="exit" class="secondary-btn">Exit</button>
        <button id="check" class="success-btn">Check (Enter)</button>
      </div>

      <!-- Help / solution -->
      <div id="solutionPanel" class="solution-panel-hidden">
        <div id="solutionMsg"></div>
      </div>

      <!-- Stats -->
      <div class="stats">
        <span id="played">Played: 0</span>
        <span id="solved">Solved: 0</span>
        <span id="revealed">Helped: 0</span>
        <span id="incorrect">Wrong: 0</span>
        <span id="skipped">Skipped: 0</span>
        <span id="totalTime">Time: 00:00</span>
      </div>
    </div>
  </div>
</div>
{% endblock %}
HTML

# JS
cat > "${JS_DIR}/${JS_NAME}" <<'JS'
(() => {
  'use strict';
  const API = location.pathname.replace(/\/play.*$/, '') + '/api';
  const BACK = document.querySelector('#cards')?.dataset.back ||
               '/games/assets/cards/back.png';
  const SUITS = ['S','H','D','C'];

  // --- tiny helpers ---
  const $ = sel => document.querySelector(sel);
  const on = (el,ev,fn)=> el && el.addEventListener(ev,fn);
  const msg = (t='',kind='') => { const m=$('#msg'); if(!m) return; m.textContent=t; m.className='status'+(kind?` status-${kind}`:''); };
  const feedback = (ok=null)=>{ const f=$('#answerFeedback'); if(!f) return;
    if(ok===true){ f.innerHTML='<span class="big-check">✓</span>'; f.className='answer-feedback success-icon'; }
    else if(ok===false){ f.innerHTML='<span class="big-x">✗</span>'; f.className='answer-feedback error-icon'; }
    else { f.textContent=''; f.className='answer-feedback'; }
  };
  const setBack=(i)=>{ const im=$(`#card-${i}`); if(im){ im.src=BACK; im.alt='back'; } };
  const setFace=(i,rank,suit)=>{ const im=$(`#card-${i}`); if(!im) return;
    const tok = (r)=>({1:'A',10:'T',11:'J',12:'Q',13:'K'}[r]||String(r));
    const code = tok(rank) + (suit||'S');
    im.src = `/games/assets/cards/${code}.png`; im.alt=code;
  };
  const setAllBack=()=>{ for (let i=0;i<4;i++) setBack(i); };

  // --- state ---
  let envelope=null, server_step=0, hasActive=false, autoDeal=true;

  function renderInit(){
    setAllBack();
    const init = envelope?.reveal?.init_reveal || [];
    init.forEach(ix=>{
      const c = envelope?.table?.cards?.[ix];
      if (c) setFace(ix, c.rank, c.suit);
    });
    $('#answer')?.focus();
  }

  async function start(){
    msg('Dealing…'); feedback();
    const payload = { reveal_mode: ($('#revealMode')?.value || 'two_then_one') };
    const r = await fetch(`${API}/start`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    const data = await r.json().catch(()=>({}));
    if (!data?.ok || !data?.envelope) { msg(data?.error||'Failed to start','error'); return; }
    envelope = data.envelope; server_step = 0; hasActive = true;
    $('#question').textContent = `Goal: ${data.goal}`;
    $('#answer').placeholder = 'Enter running sum…';
    msg('Your turn!');
    renderInit();
  }

  async function stepCheck(){
    if (!hasActive || !envelope) return;
    const ansRaw = ($('#answer')?.value||'').trim();
    if (!ansRaw) return;
    const body = { envelope, server_step, answer: ansRaw };
    const r = await fetch(`${API}/step`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const data = await r.json().catch(()=>({}));
    if (!data?.ok) { msg(data?.error||'Check failed','error'); return; }

    if (data.correct === false){
      feedback(false);
      msg(`❌ Expected ${data.expected}.`, 'error');
      return;
    }

    // correct
    feedback(true);
    if (data.done){
      msg('✅ Correct! Hand finished.','success');
      hasActive = false; envelope = null; server_step = 0;
      if (autoDeal) setTimeout(()=>deal(), 500);
      return;
    }

    // advance & flip new group
    server_step = data.server_step;
    (data.reveal||[]).forEach(ix=>{
      const c = envelope?.table?.cards?.[ix];
      if (c) setFace(ix, c.rank, c.suit);
    });
    $('#answer').value = '';
    msg(`Good! Running sum was ${data.expected}. Keep going…`, 'success');
  }

  async function skip(){
    await fetch(`${API}/skip`, { method:'POST' });
    hasActive=false; envelope=null; server_step=0; setAllBack(); msg('Skipped.','');
    if (autoDeal) setTimeout(()=>deal(), 400);
  }

  async function deal(){
    if (hasActive) { await skip(); }
    await start();
  }

  // wire
  on($('#deal'),'click',deal);
  on($('#check'),'click',stepCheck);
  on($('#help'),'click',()=> msg('Hint: running sum = add revealed cards; at final step enter the missing addend to reach Goal.','info'));
  on($('#clearBtn'),'click',()=> { const a=$('#answer'); if(a){ a.value=''; a.focus(); } });
  on($('#backBtn'),'click',()=> { const a=$('#answer'); if(!a) return; const s=a.selectionStart??0, e=a.selectionEnd??0; if(s===e&&s>0){ a.value=a.value.slice(0,s-1)+a.value.slice(e); a.setSelectionRange(s-1,s-1);}else{ a.value=a.value.slice(0,s)+a.value.slice(e); a.setSelectionRange(s,s);} a.focus(); });
  on($('#revealMode'),'change',()=>{ /* next hand will use new mode */ });
  on($('#showRunningTotal'),'change',()=>{ /* UI-only, message already concise */ });

  document.addEventListener('keydown', (e)=>{
    if (e.key==='Enter') { e.preventDefault(); stepCheck(); }
    if (e.key.toLowerCase()==='d') { e.preventDefault(); deal(); }
  });

  // first screen
  setAllBack();
  msg('Ready — press Deal','success');
})();
JS

echo ""
echo "✅ Created game scaffold at app/games/${PKG_NAME}"
echo "   - Register blueprint in your app factory (once):"
echo "       from app.games.${PKG_NAME} import bp as ${BP_NAME}_bp"
echo "       app.register_blueprint(${BP_NAME}_bp, name='${BP_NAME}')"
echo ""
echo "   - Add a row in app.games (if not present):"
echo "       INSERT INTO app.games (game_key, name, title) VALUES ('${GAME_KEY}', '${GAME_TITLE}', '${GAME_TITLE}');"
echo ""
echo "Run the app and visit:  /games/${BP_NAME}/play"

