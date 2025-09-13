# app/games/game24/logic/evaluator.py
import ast
from typing import List, Dict

# These match your original module 1:1  :contentReference[oaicite:1]{index=1}
ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd,
    ast.Load, ast.Name
)

# Your original allows A/T/J/Q/K names; numbers are literal digits in expr
ALLOWED_NAMES: Dict[str, int] = { 'A':1, 'T':10, 'J':11, 'Q':12, 'K':13 }

def _extract_used_numbers(expr: str, allowed_names: Dict[str, int]) -> List[int]:
    """Extract all numbers used in the expression (verbatim copy of your old logic)."""
    numbers: List[int] = []
    tokens = (expr.replace('(', ' ').replace(')', ' ')
                  .replace('+', ' ').replace('-', ' ')
                  .replace('*', ' ').replace('/', ' ')
                  .split())

    for token in tokens:
        if token in allowed_names:
            numbers.append(allowed_names[token])
        elif token.isdigit():
            numbers.append(int(token))
        elif token in ['A', 'T', 'J', 'Q', 'K']:
            numbers.append(allowed_names[token])

    return numbers

def _has_division_by_zero(expr: str) -> bool:
    """Basic “/0” check (same as old)."""
    return '/0' in expr or '/ 0' in expr

def safe_eval(expr: str, input_values: List[int]) -> float:
    """
    Evaluate the expression safely:
      - allow only + - * / (and pow in AST list, though you can forbid by removing ast.Pow)
      - allow rank letters A/T/J/Q/K via ALLOWED_NAMES
      - require that ALL FOUR input numbers are used exactly once (matches your old check)
      - basic division-by-zero guard
    """
    # Parse & validate AST
    tree = ast.parse(expr, mode='eval')
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"Illegal expression: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES:
            raise ValueError(f"Unknown identifier: {node.id}")

    # Compile & eval with a safe globals/locals
    code = compile(tree, "<expr>", "eval")
    result = float(eval(code, {"__builtins__": {}}, ALLOWED_NAMES))

    # Use-all-numbers check
    used_numbers = sorted(_extract_used_numbers(expr, ALLOWED_NAMES))
    input_numbers = sorted(list(map(int, input_values or [])))
    if used_numbers != input_numbers:
        raise ValueError("Must use all 4 input numbers exactly once")

    # Division by zero guard
    if _has_division_by_zero(expr):
        raise ValueError("Division by zero is not allowed")

    return result

