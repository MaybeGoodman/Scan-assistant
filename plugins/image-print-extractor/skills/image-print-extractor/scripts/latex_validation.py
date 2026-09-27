"""Dependency-free LaTeX source checks shared by export formats."""
import re

# This is an explicit input contract, not all commands understood by latex2mathml.
MATH_COMMANDS = set('''frac dfrac tfrac sqrt binom dbinom tbinom
left right langle rangle lbrace rbrace lvert rvert lVert rVert vert Vert
lfloor rfloor lceil rceil vec overrightarrow overline underline hat widehat bar
tilde widetilde dot ddot overbrace underbrace overset underset
sum prod coprod int iint iiint oint lim limsup liminf limits nolimits
sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh log ln exp
min max sup inf det gcd operatorname mathrm mathit mathbf mathbb mathcal text
begin end quad qquad thinspace displaystyle textstyle
alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa
lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega
Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
infty partial nabla ell hbar Re Im
pm mp times div cdot ast circ degree bullet
le leq ge geq ne neq approx equiv sim simeq cong propto
in notin ni subset subseteq supset supseteq cup cap setminus emptyset varnothing
forall exists neg land lor wedge vee to rightarrow leftarrow leftrightarrow
Rightarrow Leftarrow Leftrightarrow mapsto uparrow downarrow
cdots ldots vdots ddots angle triangle perp parallel mid colon'''.split())
CHEM_COMMANDS = set('''mathrm text frac sqrt left right cdot times
rightarrow longrightarrow leftarrow longleftarrow leftrightarrow rightleftharpoons
leftrightharpoons updownarrow uparrow downarrow triangle Delta delta
xrightarrow xleftarrow overset underset mathop limits quad qquad
circ degree pm mp'''.split())
ENVIRONMENTS = {'matrix', 'pmatrix', 'bmatrix', 'Bmatrix', 'vmatrix', 'Vmatrix',
                'array', 'cases', 'aligned', 'gathered'}
ESCAPES = set('\\{}|,;:! %&#_')
FUNCTION_NAMES = set('sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh log ln exp min max sup inf det gcd lim limsup liminf'.split())


class FormulaError(ValueError):
    """A formula needs source review; never silently emit source as Office Math."""


def validate_latex(source, *, chemistry=False):
    if not isinstance(source, str) or not source.strip():
        raise FormulaError('LaTeX must be a nonempty string without math delimiters')
    if len(source) > 20000:
        raise FormulaError('Expression exceeds 20000 characters; split at source boundaries')
    allowed = CHEM_COMMANDS if chemistry else MATH_COMMANDS
    depth, i = 0, 0
    while i < len(source):
        char = source[i]
        if char == '\\':
            if i + 1 == len(source):
                raise FormulaError('Trailing backslash')
            match = re.match(r'\\([A-Za-z]+)', source[i:])
            if match:
                command = match[1]
                if command not in allowed:
                    raise FormulaError('Unsupported LaTeX command: \\' + command)
                i += len(match[0])
                continue
            if source[i + 1] not in ESCAPES:
                raise FormulaError('Unsupported escape: ' + source[i:i + 2])
            i += 2
            continue
        if char == '{':
            depth += 1
            if depth > 80:
                raise FormulaError('Expression nesting exceeds 80 levels')
        elif char == '}':
            depth -= 1
            if depth < 0:
                raise FormulaError('Unmatched closing brace')
        elif char in '$%' or (ord(char) < 32 and char not in '\n\r\t'):
            raise FormulaError('Math delimiters, comments or control characters are not allowed')
        i += 1
    if depth:
        raise FormulaError('Unmatched opening brace')
    stack = []
    for match in re.finditer(r'\\(begin|end)\s*\{([^{}]+)\}', source):
        action, env = match.groups()
        if env not in ENVIRONMENTS:
            raise FormulaError('Unsupported environment: ' + env)
        if action == 'begin':
            stack.append(env)
        elif not stack or stack.pop() != env:
            raise FormulaError('Mismatched environments')
    if stack:
        raise FormulaError('Unclosed environment')
    for spec in re.findall(r'\\begin\{array\}\s*\{([^{}]*)\}', source):
        if not re.fullmatch(r'[lcr]+', spec):
            raise FormulaError('Array columns must use only l, c and r')
    if chemistry:
        # Check only classified chemistry; ordinary prose is never guessed from strings.
        if re.search('[\u2070-\u209f\u00b2\u00b3\u00b9]', source):
            raise FormulaError('Use LaTeX superscripts/subscripts, not Unicode script characters')
        if re.search('[→←⇌⇄↑↓·]', source):
            raise FormulaError('Use LaTeX commands for chemical arrows and hydrate dots')
        # Exempt explicit prose conditions such as \text{pH7}; nested text remains
        # subject to manual review rather than attempting chemical interpretation.
        chemical = re.sub(r'\\text\{[^{}]*\}', '', source)
        if re.search(r'[A-Za-z)\]]\s*[0-9]', re.sub(r'\\[A-Za-z]+', '', chemical)):
            raise FormulaError('Use explicit LaTeX subscripts for chemical composition numbers')
        if re.search(r'[A-Za-z]', chemical) and not re.search(r'\\mathrm\s*\{', chemical):
            raise FormulaError('Chemical symbols require upright LaTeX using \\mathrm{...}')
    return source

