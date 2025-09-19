# app/games/core/card_utils/expression_utils.py

import ast
import re
from typing import Dict, Any

_RANK_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9_.])([AaJjQqKkTt])(?![A-Za-z0-9_.])')
_RANK_TOKEN_MAP = {"A":"1","J":"11","Q":"12","K":"13","T":"10"}
_RANK_MAP = {"A": "1", "T": "10", "J": "11", "Q": "12", "K": "13"}

class DepthVisitor(ast.NodeVisitor):
    def __init__(self): self.max_depth = 0
    def generic_visit(self, node, depth=0):
        self.max_depth = max(self.max_depth, depth)
        for child in ast.iter_child_nodes(node):
            self.generic_visit(child, depth+1)

def preprocess_ranks(expr: str) -> str:
    """Preprocess rank tokens in expressions."""
    return _RANK_TOKEN_RE.sub(lambda m: _RANK_TOKEN_MAP[m.group(1).upper()], expr)

def normalize_expr_for_eval(expr: str) -> str:
    """
    Convert rank tokens and common math glyphs into plain arithmetic.
    """
    if not isinstance(expr, str):
        return expr
    s = expr.strip()

    # unify common glyphs first
    s = (s.replace("×", "*").replace("x", "*").replace("X", "*")
           .replace("÷", "/")
           .replace("–", "-").replace("—", "-").replace("−", "-"))

    # replace rank letters as whole tokens using word boundaries
    def repl(m):
        ch = m.group(1).upper()
        return _RANK_MAP.get(ch, ch)

    s = re.sub(r"\b([ATJQKatjqk])\b", repl, s)
    s = re.sub(r"\s+", "", s)
    return s

def score_expression_complexity(expr: str) -> int:
    """Score the complexity of a mathematical expression."""
    expr = preprocess_ranks(expr).replace("^", "**").strip()
    try:
        tree = ast.parse(expr, mode="eval")
    except Exception:
        return 999
    
    ops = {ast.Add:0, ast.Sub:0, ast.Mult:0, ast.Div:0, ast.Pow:0}
    counts = {k: 0 for k in ops}
    node_count = 0
    
    class Visitor(ast.NodeVisitor):
        def visit_BinOp(self, node):
            nonlocal node_count
            node_count += 1
            op = type(node.op)
            if op in counts: counts[op] += 1
            self.generic_visit(node)
        def visit_UnaryOp(self, node):
            nonlocal node_count; node_count += 1; self.generic_visit(node)
        def visit_Constant(self, node):
            nonlocal node_count; node_count += 1
        def generic_visit(self, node):
            nonlocal node_count; node_count += 1; super().generic_visit(node)
    
    Visitor().visit(tree)
    dv = DepthVisitor(); dv.generic_visit(tree)
    
    score = 0
    score += counts[ast.Add] + counts[ast.Sub] + counts[ast.Mult]
    score += counts[ast.Div] * 2
    score += counts[ast.Pow] * 3
    score += dv.max_depth * 2
    score += max(0, len(expr)//6)
    
    if counts[ast.Div] >= 2: score += 2
    if counts[ast.Pow] >= 1 and (counts[ast.Div] >= 1 or dv.max_depth >= 4): score += 2
    return int(score)
