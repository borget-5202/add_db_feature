#!/usr/bin/env python3
"""
Validate 24-point solutions in a JSON dataset.

Usage:
    python3 validate_solutions.py adjust_answers_fixed.json

- Loads the JSON (must be valid JSON).
- For each item, if "solutions" is present and non-empty:
    * Each string is evaluated safely (supports + - * / ^ and parentheses).
    * Checks it equals 24 (within a tiny tolerance).
- Prints a summary and writes a detailed TSV report:
    validation_report.tsv
"""

from __future__ import annotations
from pathlib import Path
import sys, json, ast, math, re
from typing import Any

TOL = 1e-9
REPORT_PATH = Path("validation_report.tsv")

# ---------- Safe math evaluator (supports + - * / ^ and parentheses) ----------
class SafeEval(ast.NodeVisitor):
    ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
    ALLOWED_UNARY = (ast.UAdd, ast.USub)

    def visit(self, node):
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        elif isinstance(node, ast.Num):              # py3.7-
            return float(node.n)
        elif isinstance(node, ast.Constant):         # py3.8+
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError("Non-numeric constant")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, self.ALLOWED_UNARY):
            val = self.visit(node.operand)
            return +val if isinstance(node.op, ast.UAdd) else -val
        elif isinstance(node, ast.BinOp) and isinstance(node.op, self.ALLOWED_BINOPS):
            left = self.visit(node.left)
            right = self.visit(node.right)
            if isinstance(node.op, ast.Add):  return left + right
            if isinstance(node.op, ast.Sub):  return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div):
                if right == 0: raise ZeroDivisionError("division by zero")
                return left / right
            if isinstance(node.op, ast.Pow):  return left ** right
        raise ValueError(f"Disallowed expression: {ast.dump(node, include_attributes=False)}")

def safe_eval(expr: str) -> float:
    # Accept ^ as exponent
    expr = expr.replace("^", "**")
    tree = ast.parse(expr, mode="eval")
    return SafeEval().visit(tree)

def equals_24(value: float, tol: float = TOL) -> bool:
    return math.isfinite(value) and abs(value - 24.0) <= tol

# Quick sanity filter to only attempt evaluation on math-looking strings
MATH_LIKE = re.compile(r'^[0-9\(\)\s\+\-\*\/\^\.]+$')

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_solutions.py <file.json>")
        sys.exit(2)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"ERROR: {json_path} not found.")
        sys.exit(2)

    # Load JSON
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("JSON load FAILED ❌")
        print(f"{type(e).__name__}: {e}")
        sys.exit(1)

    # Validate structure minimally
    if not isinstance(data, list):
        print("Top-level JSON must be a list of items (cases).")
        sys.exit(1)

    total_items = len(data)
    checked = 0
    failures: list[tuple[int, int, str, str]] = []  # (case_id, sol_idx, expr, value_or_error)

    for item in data:
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id", None)
        sols = item.get("solutions", [])
        if not isinstance(sols, list) or len(sols) == 0:
            continue

        for i, s in enumerate(sols):
            if not isinstance(s, str):
                failures.append((case_id, i, str(s), "ERROR: not a string"))
                continue
            expr = s.strip()
            if not expr:
                # ignore truly empty strings
                continue
            # Only attempt evaluation if it looks like a math expression
            if not MATH_LIKE.fullmatch(expr):
                failures.append((case_id, i, expr, "ERROR: not a math expression"))
                continue
            try:
                val = safe_eval(expr)
                checked += 1
                if not equals_24(val):
                    failures.append((case_id, i, expr, f"value={val}"))
            except Exception as e:
                failures.append((case_id, i, expr, f"ERROR: {type(e).__name__}"))

    # Write report
    with REPORT_PATH.open("w", encoding="utf-8") as rep:
        rep.write("case_id\tsolution_index\texpression\tresult\n")
        for cid, idx, expr, res in failures:
            rep.write(f"{cid}\t{idx}\t{expr}\t{res}\n")

    # Summary
    print(f"Validated file: {json_path}")
    print(f"Cases: {total_items}")
    print(f"Solutions evaluated: {checked}")
    if failures:
        print(f"Failures: {len(failures)} ❌")
        print(f"See detailed report: {REPORT_PATH}")
        # Show a few examples inline
        for cid, idx, expr, res in failures[:10]:
            print(f"  case_id={cid}, idx={idx}: {expr} -> {res}")
        sys.exit(1)
    else:
        print("All checked solutions equal 24 ✅")
        print(f"Report (empty but created for consistency): {REPORT_PATH}")

if __name__ == "__main__":
    main()

