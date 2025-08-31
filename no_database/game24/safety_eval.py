# game24/safety_eval.py
import ast, operator, math

MAX_EXPR_LEN = 200
MAX_AST_NODES = 120
MAX_EXPONENT_ABS = 5          # stricter: exponents must be <= 5 in magnitude
MAX_BASE_FOR_EXP = 100.0      # if |base| is big and exponent >= 3, reject early
MAX_INTERMEDIATE_ABS = 1e9
MAX_EVAL_OPS = 200            # hard cap on operations during evaluation

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

class UnsafeExpression(ValueError): pass

def _count_nodes(tree) -> int:
    return sum(1 for _ in ast.walk(tree))

def _is_int_like(x: float, eps: float = 1e-12) -> bool:
    return abs(x - round(x)) < eps

def safe_eval_bounded(expr: str) -> float:
    if len(expr) > MAX_EXPR_LEN:
        raise UnsafeExpression("Expression too long.")
    expr = expr.replace("^","**").replace("x","*").replace("X","*")

    ops_counter = 0  # global op counter

    def _check_ops():
        nonlocal ops_counter
        ops_counter += 1
        if ops_counter > MAX_EVAL_OPS:
            raise UnsafeExpression("Expression too complex.")

    def _bounded(val: float) -> float:
        if not math.isfinite(val) or abs(val) > MAX_INTERMEDIATE_ABS:
            raise UnsafeExpression("Result too large.")
        return val

    def _eval(node):
        _check_ops()

        if isinstance(node, ast.Expression):
            return _eval(node.body)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return _bounded(float(node.value))
            raise UnsafeExpression("Only numeric constants allowed.")

        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
            res = _ALLOWED_UNARYOPS[type(node.op)](_eval(node.operand))
            return _bounded(res)

        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            left = _eval(node.left)
            right = _eval(node.right)

            if isinstance(node.op, ast.Pow):
                # 1) exponent must be integer and within bounds
                if not _is_int_like(right):
                    raise UnsafeExpression("Exponent must be an integer.")
                if abs(right) > MAX_EXPONENT_ABS:
                    raise UnsafeExpression("Exponent too large.")

                # 2) reject huge bases when exponent >= 3
                if abs(right) >= 3 and abs(left) > MAX_BASE_FOR_EXP:
                    raise UnsafeExpression("Power too large.")

                # 3) log-based magnitude check: |left|**|right| <= MAX_INTERMEDIATE_ABS
                if abs(left) > 0:
                    try:
                        est_log10 = abs(right) * math.log10(abs(left))
                        if est_log10 > math.log10(MAX_INTERMEDIATE_ABS) + 0.5:
                            raise UnsafeExpression("Power result too large.")
                    except ValueError:
                        # log10 domain error (left <= 0) — let pow handle if small
                        pass

            res = _ALLOWED_BINOPS[type(node.op)](left, right)
            return _bounded(res)

        raise UnsafeExpression("Unsupported expression.")

    try:
        tree = ast.parse(expr, mode="eval")
    except Exception as e:
        raise UnsafeExpression(f"Invalid expression: {e}")

    if _count_nodes(tree) > MAX_AST_NODES:
        raise UnsafeExpression("Expression too complex.")

    return float(_eval(tree))

