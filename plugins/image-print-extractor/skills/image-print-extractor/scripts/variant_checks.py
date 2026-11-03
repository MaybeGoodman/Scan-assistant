"""Deterministic checks for generated questions (R09, D06). No third-party dependency.

Each check is a dict with ``kind`` and ``item`` (the subquestion it verifies, or "all").
The functions return (ok, detail). They only verify what the host wrote down; the
host's own independent solving is recorded with kind ``semantic`` and compared with
the stated answer, so a candidate's self-declaration alone never counts as a pass.

Kinds:
  arith       {"expr": "3*(2+4)/9", "expect": "2", "tolerance": 0}
  substitute  {"equation": "2*x+3 = 11", "vars": {"x": "4"}}
  roots       {"expr": "x**2-5*x+6", "var": "x", "claimed": ["2","3"], "interval": [-100, 100]}
  units       {"expr": "m*g*h", "units": {"m": "kg", "g": "m/s^2", "h": "m"}, "expect": "J"}
  balance     {"equation": "2KClO3 -> 2KCl + 3O2"}  (element and charge conservation)
  choice      {"options": {"A": "...", ...}, "answer": "B" | ["A","C"], "multi": false}
  evidence    {"quote": "..."}  (quote must occur in the student text of the candidate)
  semantic    {"independent_answer": "...", "method": "..."}  (must equal the stated answer)
  rubric      {"criteria": [...], "satisfied": true}  (open tasks; at least three criteria)
"""
import ast
import math
import re
from fractions import Fraction

FUNCTIONS = {'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan, 'log': math.log,
             'ln': math.log, 'exp': math.exp, 'abs': abs, 'log10': math.log10, 'log2': math.log2}
CONSTANTS = {'pi': math.pi, 'e': math.e}


class CheckError(ValueError):
    pass


def _value(text):
    if isinstance(text, (int, float)):
        return Fraction(text) if isinstance(text, int) else text
    if not isinstance(text, str):
        raise CheckError('数值必须是字符串或数字')
    return evaluate(text, {})


def evaluate(expression, variables):
    """Safely evaluate + - * / ** and listed functions; exact Fractions where possible."""
    if not isinstance(expression, str) or len(expression) > 500:
        raise CheckError('表达式必须是 500 字符以内的字符串')
    expression = expression.strip().replace('^', '**').replace('×', '*').replace('÷', '/')
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as exc:
        raise CheckError(f'无法解析表达式：{expression}') from exc

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return Fraction(node.value) if isinstance(node.value, int) else Fraction(str(node.value))
        if isinstance(node, ast.Name):
            if node.id in variables:
                return variables[node.id]
            if node.id in CONSTANTS:
                return CONSTANTS[node.id]
            raise CheckError(f'未定义的变量 {node.id}')
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise CheckError('除数为零')
                return left / right
            if isinstance(right, Fraction) and right.denominator == 1 and abs(right) <= 64 and isinstance(left, Fraction):
                return left ** int(right)
            return float(left) ** float(right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and len(node.args) == 1:
            return FUNCTIONS[node.func.id](float(walk(node.args[0])))
        raise CheckError(f'不支持的表达式成分：{ast.dump(node)[:60]}')

    return walk(tree)


def close(a, b, tolerance=0):
    if isinstance(a, Fraction) and isinstance(b, Fraction) and not tolerance:
        return a == b
    a, b = float(a), float(b)
    limit = max(float(tolerance), 1e-9 * max(1.0, abs(a), abs(b)))
    return abs(a - b) <= limit


def check_arith(check, _):
    value, expect = evaluate(check['expr'], {}), _value(check['expect'])
    ok = close(value, expect, check.get('tolerance', 0))
    return ok, f'{check["expr"]} = {float(value):g}，期望 {float(expect):g}'


def _variables(raw):
    if not isinstance(raw, dict):
        raise CheckError('vars 必须是对象')
    return {name: _value(value) for name, value in raw.items()}


def check_substitute(check, _):
    lhs, sep, rhs = check['equation'].partition('=')
    if not sep or '=' in rhs:
        raise CheckError('equation 必须恰好含一个等号')
    variables = _variables(check.get('vars', {}))
    left, right = evaluate(lhs, variables), evaluate(rhs, variables)
    ok = close(left, right, check.get('tolerance', 0))
    return ok, f'代入后左边 {float(left):g}，右边 {float(right):g}'


class NotPolynomial(Exception):
    pass


def _poly(expression, var):
    """Exact rational coefficients (lowest degree first) of a polynomial in ``var``.

    Raises NotPolynomial for anything else (division by the variable, roots, functions,
    irrational constants); those cannot be proven complete by this check.
    """
    expression = expression.strip().replace('^', '**').replace('×', '*')
    tree = ast.parse(expression, mode='eval')

    def trim(p):
        while len(p) > 1 and p[-1] == 0:
            p = p[:-1]
        return p

    def mul(a, b):
        out = [Fraction(0)] * (len(a) + len(b) - 1)
        for i, x in enumerate(a):
            for j, y in enumerate(b):
                out[i + j] += x * y
        return trim(out)

    def add(a, b, sign=1):
        out = [Fraction(0)] * max(len(a), len(b))
        for i, x in enumerate(a):
            out[i] += x
        for i, y in enumerate(b):
            out[i] += sign * y
        return trim(out)

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return [Fraction(str(node.value))]
        if isinstance(node, ast.Name):
            if node.id == var:
                return [Fraction(0), Fraction(1)]
            raise NotPolynomial(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand)
            return value if isinstance(node.op, ast.UAdd) else [-c for c in value]
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Pow):
                exponent = walk(node.right)
                if len(exponent) != 1 or exponent[0].denominator != 1 or not 0 <= exponent[0] <= 64:
                    raise NotPolynomial('exponent')
                result, base = [Fraction(1)], walk(node.left)
                for _ in range(int(exponent[0])):
                    result = mul(result, base)
                return result
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return add(left, right)
            if isinstance(node.op, ast.Sub):
                return add(left, right, -1)
            if isinstance(node.op, ast.Mult):
                return mul(left, right)
            if isinstance(node.op, ast.Div) and len(right) == 1 and right[0] != 0:
                return [c / right[0] for c in left]
        raise NotPolynomial(type(node).__name__)

    return trim(walk(tree))


def _peval(p, x):
    total = Fraction(0) if isinstance(x, Fraction) else 0.0
    for c in reversed(p):
        total = total * x + c
    return total


def _pdiv(a, b):
    """Quotient and remainder of exact polynomial division."""
    a = list(a)
    if len(b) == 1:
        return [c / b[0] for c in a], [Fraction(0)]
    q = [Fraction(0)] * max(1, len(a) - len(b) + 1)
    while len(a) >= len(b) and any(a):
        factor = a[-1] / b[-1]
        shift = len(a) - len(b)
        q[shift] = factor
        for i, c in enumerate(b):
            a[i + shift] -= factor * c
        a.pop()
        while len(a) > 1 and a[-1] == 0:
            a.pop()
    return q, a or [Fraction(0)]


def _derivative(p):
    return [i * c for i, c in enumerate(p)][1:] or [Fraction(0)]


def _distinct_real_roots(p, lo, hi):
    """Number of distinct real roots in the closed interval [lo, hi] (Sturm's theorem, exact)."""
    if len(p) == 1:
        return None if p[0] == 0 else 0
    a, b = p, _derivative(p)
    while any(b):
        a, b = b, _pdiv(a, b)[1]
    square_free = _pdiv(p, a)[0]  # p / gcd(p, p') keeps every root once.
    chain = [square_free, _derivative(square_free)]
    while len(chain[-1]) > 1 or chain[-1][0] != 0:
        remainder = _pdiv(chain[-2], chain[-1])[1]
        if not any(remainder):
            break
        chain.append([-c for c in remainder])

    def changes(x):
        signs = [v for v in (_peval(q, x) for q in chain) if v != 0]
        return sum(1 for s, t in zip(signs, signs[1:]) if (s > 0) != (t > 0))
    # Sturm counts roots in (lo, hi]; add a root sitting exactly on lo.
    return changes(lo) - changes(hi) + (1 if _peval(square_free, lo) == 0 else 0)


def check_roots(check, _):
    """Claimed roots satisfy f=0 and, for polynomials, are all the distinct real roots in the interval.

    Completeness is proven exactly (rational coefficients, Sturm sequence), so double roots
    off any grid and roots on the interval ends are counted. For expressions that are not
    polynomials the check cannot prove nothing is missing and returns ``None`` (needs review)
    instead of a pass (F06).
    """
    var, expr = check['var'], check['expr']
    claimed_values = [_value(v) for v in check['claimed']]
    lo, hi = (_value(v) for v in check.get('interval', ['-100', '100']))
    if not lo < hi:
        raise CheckError('interval 必须满足下限小于上限')

    def f(x):
        return evaluate(expr, {var: x})

    for root in claimed_values:
        value = f(root)
        if (value != 0) if isinstance(value, Fraction) else abs(float(value)) > 1e-7 * max(1.0, abs(float(root))):
            return False, f'x={float(root):g} 不满足方程'
    try:
        poly = _poly(expr, var)
    except NotPolynomial:
        return None, ('列出的根代入成立，但该表达式不是多项式，脚本无法证明区间内没有遗漏的根'
                      '（重根、不连续点等），需独立复核')
    if not all(isinstance(v, Fraction) for v in (lo, hi)):
        return None, 'interval 端点必须是有理数才能精确判定根的个数，需独立复核'
    total = _distinct_real_roots(poly, Fraction(lo), Fraction(hi))
    if total is None:
        return False, '表达式恒为 0，不是方程'
    inside = []
    for root in sorted(float(r) for r in claimed_values):
        if lo <= root <= hi and all(abs(root - r) > 1e-9 for r in inside):
            inside.append(root)
    if total != len(inside):
        return False, (f'区间 [{float(lo):g},{float(hi):g}] 内共有 {total} 个不同实根，'
                       f'只列出 {len(inside)} 个，存在遗漏')
    return True, f'列出的根 {sorted(inside)} 均满足且为区间 [{float(lo):g},{float(hi):g}] 内全部 {total} 个不同实根'


BASE = ('m', 'kg', 's', 'A', 'K', 'mol', 'cd')
UNITS = {
    'm': (1, 0, 0, 0, 0, 0, 0), 'kg': (0, 1, 0, 0, 0, 0, 0), 's': (0, 0, 1, 0, 0, 0, 0),
    'A': (0, 0, 0, 1, 0, 0, 0), 'K': (0, 0, 0, 0, 1, 0, 0), 'mol': (0, 0, 0, 0, 0, 1, 0),
    'cd': (0, 0, 0, 0, 0, 0, 1), 'g': (0, 1, 0, 0, 0, 0, 0), 'cm': (1, 0, 0, 0, 0, 0, 0),
    'km': (1, 0, 0, 0, 0, 0, 0), 'mm': (1, 0, 0, 0, 0, 0, 0), 'h': (0, 0, 1, 0, 0, 0, 0),
    'min': (0, 0, 1, 0, 0, 0, 0), 'N': (1, 1, -2, 0, 0, 0, 0), 'J': (2, 1, -2, 0, 0, 0, 0),
    'W': (2, 1, -3, 0, 0, 0, 0), 'Pa': (-1, 1, -2, 0, 0, 0, 0), 'C': (0, 0, 1, 1, 0, 0, 0),
    'V': (2, 1, -3, -1, 0, 0, 0), 'Ohm': (2, 1, -3, -2, 0, 0, 0), 'Ω': (2, 1, -3, -2, 0, 0, 0),
    'T': (0, 1, -2, -1, 0, 0, 0), 'Wb': (2, 1, -2, -1, 0, 0, 0), 'Hz': (0, 0, -1, 0, 0, 0, 0),
    'F': (-2, -1, 4, 2, 0, 0, 0), 'L': (3, 0, 0, 0, 0, 0, 0), 'mL': (3, 0, 0, 0, 0, 0, 0),
    'kWh': (2, 1, -2, 0, 0, 0, 0), '1': (0, 0, 0, 0, 0, 0, 0), '℃': (0, 0, 0, 0, 1, 0, 0),
}


def dimension(unit):
    """Parse products, quotients and integer powers such as 'kg*m/s^2' or 'm/s²'."""
    unit = unit.replace('²', '^2').replace('³', '^3').replace('·', '*').replace(' ', '')
    if not unit:
        raise CheckError('单位不能为空')
    total, sign = [0] * 7, 1
    for token in re.findall(r'[*/]|[^*/]+', unit):
        if token in '*/':
            sign = 1 if token == '*' else -1
            continue
        name, _, power = token.partition('^')
        power = int(power or 1)
        if name not in UNITS:
            raise CheckError(f'未知单位 {name}')
        for index, value in enumerate(UNITS[name]):
            total[index] += sign * power * value
    return tuple(total)


def check_units(check, _):
    """Dimensional analysis of a product/quotient/power expression of named quantities."""
    dims = {name: dimension(unit) for name, unit in check['units'].items()}
    tree = ast.parse(check['expr'].replace('^', '**'), mode='eval')

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Name):
            if node.id not in dims:
                raise CheckError(f'量 {node.id} 未给出单位')
            return dims[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return (0,) * 7
        if isinstance(node, ast.UnaryOp):
            return walk(node.operand)
        if isinstance(node, ast.BinOp):
            left = walk(node.left)
            if isinstance(node.op, ast.Pow):
                if not isinstance(node.right, ast.Constant):
                    raise CheckError('幂次必须是数字')
                return tuple(v * node.right.value for v in left)
            right = walk(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if left != right:
                    raise CheckError('加减两侧量纲不一致')
                return left
            if isinstance(node.op, ast.Mult):
                return tuple(a + b for a, b in zip(left, right))
            if isinstance(node.op, ast.Div):
                return tuple(a - b for a, b in zip(left, right))
        raise CheckError('单位表达式只支持乘、除、幂和加减')

    got, expect = walk(tree), dimension(check['expect'])
    return got == expect, f'量纲 {got}，期望 {check["expect"]} {expect}'


ELEMENT = re.compile(r'([A-Z][a-z]?)(\d*)')


def _formula_counts(formula):
    """Element counts of one species, with parentheses and hydrate dots."""
    formula = formula.replace('·', '.').replace('•', '.')
    total = {}
    for part in formula.split('.'):
        match = re.match(r'^(\d*)(.*)$', part)
        factor, body = int(match[1] or 1), match[2]
        stack = [{}]
        i = 0
        while i < len(body):
            char = body[i]
            if char in '([':
                stack.append({})
                i += 1
            elif char in ')]':
                j = i + 1
                while j < len(body) and body[j].isdigit():
                    j += 1
                times = int(body[i + 1:j] or 1)
                group = stack.pop()
                for key, value in group.items():
                    stack[-1][key] = stack[-1].get(key, 0) + value * times
                i = j
            else:
                match = ELEMENT.match(body, i)
                if not match:
                    raise CheckError(f'无法解析化学式 {formula}')
                stack[-1][match[1]] = stack[-1].get(match[1], 0) + int(match[2] or 1)
                i = match.end()
        if len(stack) != 1:
            raise CheckError(f'括号不配对：{formula}')
        for key, value in stack[0].items():
            total[key] = total.get(key, 0) + value * factor
    return total


def species(text):
    """'2Fe^3+' -> (2, {'Fe': 1}, 3); 'e-' -> electron; strips (s)/(aq)/↑/↓."""
    text = re.sub(r'\((s|l|g|aq)\)|[↑↓]', '', text.strip())
    match = re.match(r'^(\d+)?\s*(.+)$', text)
    coefficient, body = int(match[1] or 1), match[2]
    charge = 0
    charged = re.match(r'^(.*?)\^?(\d*)([+-])$', body) if ('^' in body or body in {'e-', 'e'}) else None
    if body in {'e-', 'e^-', 'e'}:
        return coefficient, {}, -1
    if charged:
        body, magnitude, sign = charged[1], int(charged[2] or 1), charged[3]
        charge = magnitude if sign == '+' else -magnitude
    return coefficient, _formula_counts(body), charge


def check_balance(check, _):
    equation = check['equation']
    sides = re.split(r'\s*(?:->|→|=|⇌|<=>|==)\s*', equation)
    if len(sides) != 2:
        raise CheckError('方程式必须恰好有一个箭头或等号')
    totals = []
    for side in sides:
        atoms, charge = {}, 0
        for term in re.split(r'\s+\+\s+', side.strip()):
            coefficient, counts, sign = species(term)
            for key, value in counts.items():
                atoms[key] = atoms.get(key, 0) + coefficient * value
            charge += coefficient * sign
        totals.append((atoms, charge))
    (left, lc), (right, rc) = totals
    if left != right:
        diff = {k: (left.get(k, 0), right.get(k, 0)) for k in set(left) | set(right) if left.get(k, 0) != right.get(k, 0)}
        return False, f'元素不守恒：{diff}'
    if lc != rc:
        return False, f'电荷不守恒：左 {lc}，右 {rc}'
    return True, '元素与电荷守恒'


def check_choice(check, _):
    options = check['options']
    if not isinstance(options, dict) or len(options) < 2:
        raise CheckError('options 必须是至少两项的对象')
    texts = [re.sub(r'\s+', '', str(v)) for v in options.values()]
    if any(not t for t in texts):
        return False, '有空选项'
    if len(set(texts)) != len(texts):
        return False, '选项内容重复'
    answer = check['answer']
    answers = answer if isinstance(answer, list) else [answer]
    if not answers or any(a not in options for a in answers) or len(set(answers)) != len(answers):
        return False, f'答案 {answer} 不在选项中或重复'
    if not check.get('multi') and len(answers) != 1:
        return False, '单选题必须恰好一个答案'
    return True, f'答案 {answer} 合法，选项互不重复'


def check_evidence(check, context):
    quote = re.sub(r'\s+', '', check['quote'])
    if len(quote) < 4:
        raise CheckError('证据句至少 4 个字符')
    return quote in context['student_text'], '证据句' + ('已在语篇中定位' if quote in context['student_text'] else '未在语篇中找到')


def normalize_answer(value):
    return re.sub(r'[\s，,。；;：:]+', '', str(value)).lower()


def check_semantic(check, context):
    if check.get('uncertain'):
        return None, '独立复核结论不确定，候选进入待复核'
    item = check['item']
    stated = context['answers'].get(item)
    if stated is None:
        return False, f'没有 {item} 的答案可供对照'
    ok = normalize_answer(stated) == normalize_answer(check['independent_answer'])
    return ok, '独立求解与答案一致' if ok else f'独立求解 {check["independent_answer"]} 与答案 {stated} 不一致'


def check_rubric(check, _):
    criteria = check.get('criteria')
    if not isinstance(criteria, list) or len(criteria) < 3 or any(not str(c).strip() for c in criteria):
        return False, '开放题至少列出 3 条可核验标准'
    return check.get('satisfied') is True, '开放题标准' + ('满足' if check.get('satisfied') is True else '未满足')


CHECKS = {'arith': check_arith, 'substitute': check_substitute, 'roots': check_roots, 'units': check_units,
          'balance': check_balance, 'choice': check_choice, 'evidence': check_evidence,
          'semantic': check_semantic, 'rubric': check_rubric}
DETERMINISTIC = {'arith', 'substitute', 'roots', 'units', 'balance', 'choice', 'evidence'}


def run_check(check, context):
    """Return {'kind', 'item', 'ok': True|False|None, 'detail'}; errors count as failures."""
    if not isinstance(check, dict) or check.get('kind') not in CHECKS:
        return {'kind': check.get('kind') if isinstance(check, dict) else None, 'item': None, 'ok': False,
                'detail': '未知的校验类型'}
    try:
        ok, detail = CHECKS[check['kind']](check, context)
    except (CheckError, KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        ok, detail = False, f'校验无法执行：{type(exc).__name__}: {exc}'
    return {'kind': check['kind'], 'item': check.get('item'), 'ok': ok, 'detail': detail}
