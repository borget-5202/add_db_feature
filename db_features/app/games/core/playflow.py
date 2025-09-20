# app/games/core/playflow.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Callable
from time import time

Outcome = str  # 'solved_no_help'|'solved_with_help'|'skipped'|'revealed_no_attempt'|'revealed_after_attempts'|'unsolved_exit'

@dataclass
class PlayInstance:
    case_id: int
    started_at_ms: int = field(default_factory=lambda: int(time() * 1000))
    ended_at_ms: Optional[int] = None
    attempts: int = 0
    incorrect_attempts: int = 0
    helped: bool = False
    skipped: bool = False
    solved: bool = False
    final_outcome: Optional[Outcome] = None

    def mark_end(self, outcome: Outcome):
        if self.ended_at_ms is None:
            self.ended_at_ms = int(time() * 1000)
        self.final_outcome = outcome

@dataclass
class Playflow:
    """Reusable session brain for any game/puzzle type."""
    session_uuid: str
    started_at_ms: int = field(default_factory=lambda: int(time() * 1000))
    current: Optional[PlayInstance] = None
    items: Dict[int, PlayInstance] = field(default_factory=dict)  # case_id -> PlayInstance

    # ---- lifecycle ----
    def start_puzzle(self, case_id: int):
        # If a previous puzzle is hanging, finalize it as unsolved_exit
        if self.current and not self.current.final_outcome:
            self.current.mark_end('unsolved_exit')
        pi = PlayInstance(case_id=case_id)
        self.items[case_id] = pi
        self.current = pi

    def submit(self, correct: bool):
        if not self.current:
            return
        self.current.attempts += 1
        if correct:
            self.current.solved = True
            outcome = 'solved_with_help' if self.current.helped else 'solved_no_help'
            self.current.mark_end(outcome)
        else:
            self.current.incorrect_attempts += 1

    def help(self):
        if not self.current:
            return
        self.current.helped = True

    def skip(self):
        if not self.current:
            return
        if not self.current.final_outcome:
            self.current.skipped = True
            self.current.mark_end('skipped')
        self.current = None

    def reveal_finalize_if_needed(self):
        """Call when exiting if the current puzzle was helped or untouched."""
        if not self.current or self.current.final_outcome:
            return
        if self.current.helped:
            outcome = 'revealed_after_attempts' if self.current.attempts > 0 else 'revealed_no_attempt'
            self.current.mark_end(outcome)
        else:
            self.current.mark_end('unsolved_exit')

    # ---- selection helper ----
    def eligible_next_filter(self) -> Callable[[int], bool]:
        """Return a predicate for puzzles that have NOT been finalized this session."""
        finished = {cid for cid, it in self.items.items() if it.final_outcome}
        return lambda case_id: case_id not in finished

    # ---- readout ----
    def summary(self, finalize: bool = True) -> Dict:
        from html import escape
        # Close any dangling current puzzle politely
        if finalize and self.current and not self.current.final_outcome:
            self.reveal_finalize_if_needed()
    
        totals = dict(solved=0, helped=0, incorrect=0, skipped=0)
        per_puzzle: List[Dict] = []
    
        buckets = dict(
            solved_ids=[],
            solved_no_help_ids=[],
            solved_with_help_ids=[],
            helped_ids=[],
            incorrect_ids=[],
            skipped_ids=[],
            revealed_no_attempt_ids=[],
            revealed_after_attempts_ids=[],
            unsolved_exit_ids=[],
            first_try_correct_ids=[],
            struggle_before_solve_ids=[],
        )
    
        for cid, it in self.items.items():
            if it.solved: totals['solved'] += 1
            if it.helped: totals['helped'] += 1
            if it.incorrect_attempts > 0: totals['incorrect'] += 1
            if it.skipped: totals['skipped'] += 1
    
            if it.solved:
                buckets['solved_ids'].append(cid)
                if it.helped: buckets['solved_with_help_ids'].append(cid)
                else: buckets['solved_no_help_ids'].append(cid)
                if it.attempts == 1: buckets['first_try_correct_ids'].append(cid)
                if it.incorrect_attempts > 0: buckets['struggle_before_solve_ids'].append(cid)
            if it.helped: buckets['helped_ids'].append(cid)
            if it.incorrect_attempts > 0: buckets['incorrect_ids'].append(cid)
            if it.skipped: buckets['skipped_ids'].append(cid)
    
            if it.final_outcome == 'revealed_no_attempt':
                buckets['revealed_no_attempt_ids'].append(cid)
            elif it.final_outcome == 'revealed_after_attempts':
                buckets['revealed_after_attempts_ids'].append(cid)
            elif it.final_outcome == 'unsolved_exit':
                buckets['unsolved_exit_ids'].append(cid)
    
            per_puzzle.append(dict(
                case_id=cid,
                final_outcome=it.final_outcome,
                attempts=it.attempts,
                incorrect_attempts=it.incorrect_attempts,
                helped=it.helped,
                skipped=it.skipped,
                solved=it.solved,
                started_at_ms=it.started_at_ms,
                ended_at_ms=it.ended_at_ms,
                # include level if you added it earlier:
                level=getattr(it, "level", None)
            ))
    
        # sort every id list ascending for readability
        for k, arr in buckets.items():
            arr.sort()
    
        def f(ids: List[int]) -> str:
            return ", ".join(str(x) for x in ids) if ids else "—"
    
        # Pretty text block (good for logs or plain UI)
        report_lines = [
            "Totals",
            f"  Solved:   {totals['solved']}",
            f"  Helped:   {totals['helped']}",
            f"  Incorrect:{totals['incorrect']}",
            f"  Skipped:  {totals['skipped']}",
            "",
            "Case IDs",
            f"  Solved (no help) [{len(buckets['solved_no_help_ids'])}]: {f(buckets['solved_no_help_ids'])}",
            f"  Solved (with help) [{len(buckets['solved_with_help_ids'])}]: {f(buckets['solved_with_help_ids'])}",
            f"  Helped (any) [{len(buckets['helped_ids'])}]: {f(buckets['helped_ids'])}",
            f"  Incorrect (had wrong attempts) [{len(buckets['incorrect_ids'])}]: {f(buckets['incorrect_ids'])}",
            f"  Skipped [{len(buckets['skipped_ids'])}]: {f(buckets['skipped_ids'])}",
            f"  Revealed no attempt [{len(buckets['revealed_no_attempt_ids'])}]: {f(buckets['revealed_no_attempt_ids'])}",
            f"  Revealed after attempts [{len(buckets['revealed_after_attempts_ids'])}]: {f(buckets['revealed_after_attempts_ids'])}",
            f"  Unsolved exit [{len(buckets['unsolved_exit_ids'])}]: {f(buckets['unsolved_exit_ids'])}",
            f"  First-try correct [{len(buckets['first_try_correct_ids'])}]: {f(buckets['first_try_correct_ids'])}",
            f"  Struggled but solved [{len(buckets['struggle_before_solve_ids'])}]: {f(buckets['struggle_before_solve_ids'])}",
        ]
        report_text = "\n".join(report_lines)
    
        # Minimal clean HTML snippet (drop-in to your panel)
        def chip_list(ids: List[int]) -> str:
            if not ids: return "<span class='muted'>—</span>"
            return " ".join(f"<span class='chip'>{escape(str(i))}</span>" for i in ids)
    
        report_html = f"""
    <section class="ps-report">
      <div class="ps-totals">
        <div><b>Solved</b> {totals['solved']}</div>
        <div><b>Helped</b> {totals['helped']}</div>
        <div><b>Incorrect</b> {totals['incorrect']}</div>
        <div><b>Skipped</b> {totals['skipped']}</div>
      </div>
      <div class="ps-buckets">
        <div><b>Solved (no help)</b> [{len(buckets['solved_no_help_ids'])}] {chip_list(buckets['solved_no_help_ids'])}</div>
        <div><b>Solved (with help)</b> [{len(buckets['solved_with_help_ids'])}] {chip_list(buckets['solved_with_help_ids'])}</div>
        <div><b>Helped (any)</b> [{len(buckets['helped_ids'])}] {chip_list(buckets['helped_ids'])}</div>
        <div><b>Incorrect (had wrong attempts)</b> [{len(buckets['incorrect_ids'])}] {chip_list(buckets['incorrect_ids'])}</div>
        <div><b>Skipped</b> [{len(buckets['skipped_ids'])}] {chip_list(buckets['skipped_ids'])}</div>
        <div><b>Revealed no attempt</b> [{len(buckets['revealed_no_attempt_ids'])}] {chip_list(buckets['revealed_no_attempt_ids'])}</div>
        <div><b>Revealed after attempts</b> [{len(buckets['revealed_after_attempts_ids'])}] {chip_list(buckets['revealed_after_attempts_ids'])}</div>
        <div><b>Unsolved exit</b> [{len(buckets['unsolved_exit_ids'])}] {chip_list(buckets['unsolved_exit_ids'])}</div>
        <div><b>First-try correct</b> [{len(buckets['first_try_correct_ids'])}] {chip_list(buckets['first_try_correct_ids'])}</div>
        <div><b>Struggled but solved</b> [{len(buckets['struggle_before_solve_ids'])}] {chip_list(buckets['struggle_before_solve_ids'])}</div>
      </div>
    </section>""".strip()
    
        return dict(
            session_uuid=self.session_uuid,
            started_at_ms=self.started_at_ms,
            ended_at_ms=int(time() * 1000),
            totals=totals,
            per_puzzle=per_puzzle,
            buckets=buckets,
            report_text=report_text,   # NEW
            report_html=report_html,   # NEW
        )
