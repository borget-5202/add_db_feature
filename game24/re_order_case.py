#!/usr/bin/env python3
"""
Reorder 24-point cases so that all items with solutions come first (stable),
followed by all items with no solutions (stable). Then renumber case_id
sequentially starting from 1.

Usage:
    python3 reorder_cases.py adjust_answers_fixed.json
"""

from __future__ import annotations
from pathlib import Path
import sys, json
from typing import Any

def has_solution(item: dict[str, Any]) -> bool:
    """Return True if item['solutions'] exists and contains at least one non-empty string."""
    sols = item.get("solutions", [])
    if not isinstance(sols, list):
        return False
    return any(isinstance(s, str) and s.strip() for s in sols)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 reorder_cases.py <input.json>")
        sys.exit(2)

    in_path = Path(sys.argv[1])
    if not in_path.exists():
        print(f"ERROR: {in_path} not found.")
        sys.exit(2)

    out_path = in_path.with_name(in_path.stem + "_reordered.json")
    report_path = in_path.with_name(in_path.stem + "_reorder_report.tsv")

    # Load JSON
    with in_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("ERROR: Top-level JSON must be a list.")
        sys.exit(1)

    # Stable partition
    with_solutions, no_solutions = [], []
    for idx, item in enumerate(data):
        (with_solutions if has_solution(item) else no_solutions).append((idx, item))

    new_data = [it for _, it in with_solutions] + [it for _, it in no_solutions]

    # Renumber case_id sequentially starting at 1
    for new_idx, item in enumerate(new_data, start=1):
        item["case_id"] = new_idx

    # Write new JSON
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    # Write report
    with report_path.open("w", encoding="utf-8") as rep:
        rep.write("new_index\tnew_case_id\told_index\told_case_id\thas_solution\n")
        for new_idx, (old_idx, item) in enumerate(with_solutions + no_solutions, start=1):
            old_case_id = item.get("case_id", "")
            rep.write(f"{new_idx}\t{new_idx}\t{old_idx}\t{old_case_id}\t{has_solution(item)}\n")

    print(f"Done. Wrote reordered JSON to: {out_path}")
    print(f"Report with mapping: {report_path}")
    print(f"Counts -> with solutions: {len(with_solutions)}, no solutions: {len(no_solutions)}")

if __name__ == "__main__":
    main()

