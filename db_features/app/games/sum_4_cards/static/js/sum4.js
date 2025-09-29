// app/games/sum_4_cards/static/js/sum4.js
(function () {
  const $ = (sel) => document.querySelector(sel);
  let envelope = null;
  let server_step = 0;

  async function start() {
    const res = await fetch(`/games/sum_4_cards/api/start`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({}) // you can pass {case_id: N} if you want a specific one
    });
    const data = await res.json();
    if (!data.ok) { throw new Error("start failed"); }
    envelope = data.envelope;
    server_step = envelope.reveal.server_step || 0;
    // keep cards face-down initially
    setFeedback(`Ready. Reveal the first card.`);
  }

  function flip(slot, rank) {
    const el = $(`#card-${slot}`);
    el.classList.remove("face-down");
    el.textContent = String(rank);
  }

  async function revealNext() {
    if (!envelope) return;
    // ask server what to flip now
    const res = await fetch(`/games/sum_4_cards/api/step`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ server_step })
    });
    const data = await res.json();
    if (!data.ok) return;

    (data.reveal || []).forEach((slot) => {
      const rank = envelope.table.cards[slot].rank;
      flip(slot, rank);
    });

    server_step = data.server_step;
    if (data.done) {
      // allow answer input
      $("#btn-reveal").classList.add("hidden");
      $("#answer").classList.remove("hidden");
      $("#btn-finish").classList.remove("hidden");
      setFeedback(`All cards revealed. Enter the total.`);
    } else {
      setFeedback(`Good. Reveal the next card.`);
    }
  }

  async function finish() {
    const answer = Number($("#answer").value);
    if (!Number.isFinite(answer)) {
      setFeedback("Please enter a number.");
      return;
    }
    const res = await fetch(`/games/sum_4_cards/api/finish`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        case_id: envelope.case_id,
        answer,
        envelope  // includes minimal state.start_ms so server can compute elapsed
      })
    });
    const data = await res.json();
    if (data.ok) {
      setFeedback(data.correct ? `✅ Correct!` : `❌ Not quite. Expected ${data.expected}.`);
      $("#btn-finish").disabled = true;
      $("#answer").disabled = true;
    } else {
      setFeedback("Save failed.");
    }
  }

  function setFeedback(msg) { $("#feedback").textContent = msg; }

  // Wire up
  window.addEventListener("DOMContentLoaded", async () => {
    $("#btn-reveal").addEventListener("click", revealNext);
    $("#btn-finish").addEventListener("click", finish);
    await start();
  });
})();

