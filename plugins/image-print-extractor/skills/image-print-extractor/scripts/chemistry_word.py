"""Render validated chemistry LaTeX directly in Word (V1.0, R03 / D03).

The chat and JSON representation stays canonical LaTeX source. For Word, a small
parser of the documented chemistry subset builds an explicit tree, then:

* simple formulas (element symbols, coefficients, sub/superscripts, plain arrows,
  gas/precipitate marks, hydrate dots) become native Word rich text with
  sub/superscript runs, so a teacher can retype them like ordinary text;
* structures that rich text cannot show faithfully (conditions above/below an
  arrow, nuclide prescripts, oxidation states set over an element, fractions)
  become Office Math (OMML) built directly from the tree. Every run is OMML "normal
  text" (m:nor) so symbols stay upright in Word and in LibreOffice, and reaction
  conditions use limUpp/limLow over a long arrow (widely supported) instead of groupChr.

Nothing is balanced, corrected or reinterpreted; unsupported input raises
ChemistryRenderError so the exporter can keep the source text and mark the item
for review instead of guessing.
"""
from formulas import node, run as math_run
from latex_validation import validate_latex


class ChemistryRenderError(ValueError):
    """The validated source uses a construct this renderer does not draw faithfully."""


SYMBOLS = {
    'rightarrow': '→', 'longrightarrow': '⟶', 'leftarrow': '←', 'longleftarrow': '⟵',
    'leftrightarrow': '↔', 'rightleftharpoons': '⇌', 'leftrightharpoons': '⇋',
    'updownarrow': '↕', 'uparrow': '↑', 'downarrow': '↓', 'triangle': '△', 'Delta': 'Δ',
    'delta': 'δ', 'cdot': '·', 'times': '×', 'circ': '°', 'degree': '°', 'pm': '±', 'mp': '∓',
    'quad': ' ', 'qquad': '  ',
}
ESCAPED = {',': ' ', ';': ' ', ':': ' ', '!': '', ' ': ' ', '{': '{', '}': '}',
           '|': '|', '%': '%', '&': '&', '#': '#', '_': '_', '\\': ''}
X_ARROWS = {'xrightarrow': '→', 'xleftarrow': '←'}
SPACED = set('+=→⟶←⟵↔⇌⇋')
LONG = {'→': '⟶', '←': '⟵'}


def tokenize(source):
    tokens, i = [], 0
    while i < len(source):
        char = source[i]
        if char == '\\':
            j = i + 1
            while j < len(source) and source[j].isalpha():
                j += 1
            if j == i + 1:
                tokens.append(('esc', source[i + 1]))
                i += 2
            else:
                tokens.append(('cmd', source[i + 1:j]))
                i = j
            continue
        tokens.append(('char', char))
        i += 1
    return tokens


class Parser:
    def __init__(self, source):
        self.tokens, self.i = tokenize(source), 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self):
        token = self.peek()
        if token is None:
            raise ChemistryRenderError('Unexpected end of chemistry expression')
        self.i += 1
        return token

    def expect(self, char):
        if self.take() != ('char', char):
            raise ChemistryRenderError(f'Expected {char!r} in chemistry expression')

    def group(self):
        """Parse a mandatory {...} argument or a single token."""
        token = self.peek()
        if token == ('char', '{'):
            self.take()
            nodes = self.sequence('}')
            self.expect('}')
            return nodes
        produced = self.atom()
        if produced is None:
            return []
        return produced if isinstance(produced, list) else [produced]

    def optional(self):
        if self.peek() != ('char', '['):
            return []
        self.take()
        nodes = self.sequence(']')
        self.expect(']')
        return nodes

    def raw_text(self):
        self.expect('{')
        depth, text = 1, ''
        while True:
            kind, value = self.take()
            if kind == 'char' and value == '{':
                depth += 1
            elif kind == 'char' and value == '}':
                depth -= 1
                if not depth:
                    return text
            text += ESCAPED.get(value, value) if kind == 'esc' else ('\\' + value if kind == 'cmd' else value)

    def sequence(self, stop=None):
        nodes = []
        while True:
            token = self.peek()
            if token is None or (stop and token == ('char', stop)):
                return nodes
            if token in {('char', '^'), ('char', '_')}:
                if not nodes:
                    raise ChemistryRenderError('Script without a base')
                nodes[-1] = self.scripts(nodes[-1])
                continue
            produced = self.atom()
            if produced is not None:
                nodes.extend(produced) if isinstance(produced, list) else nodes.append(produced)

    def scripts(self, base):
        sub = sup = None
        if base[0] == 'script':
            base, sub, sup = base[1], base[2], base[3]
        else:
            base = [base]
        while self.peek() in {('char', '^'), ('char', '_')}:
            mark = self.take()[1]
            argument = self.group()
            if mark == '_':
                if sub is not None:
                    raise ChemistryRenderError('Double subscript')
                sub = argument
            else:
                if sup is not None:
                    raise ChemistryRenderError('Double superscript')
                sup = [('t', '−') if n == ('t', '-') else n for n in argument]
        return ('script', base, sub, sup)

    def atom(self):
        kind, value = self.take()
        if kind == 'char':
            if value == '{':
                nodes = self.sequence('}')
                self.expect('}')
                if not nodes and self.peek() in {('char', '^'), ('char', '_')}:
                    _, _, sub, sup = self.scripts(('t', ''))
                    base = self.atom()
                    if base is None:
                        raise ChemistryRenderError('Prescript without a following symbol')
                    return ('pre', sub or [], sup or [], base if isinstance(base, list) else [base])
                return nodes
            if value in ' \t\r\n':
                return None  # Spaces are not significant in LaTeX math mode.
            if value in '}]':
                raise ChemistryRenderError('Unbalanced group')
            if value == '&':
                raise ChemistryRenderError('Alignment is not supported in chemistry')
            return ('t', value)
        if kind == 'esc':
            if value == '\\':
                raise ChemistryRenderError('Line breaks are not supported in chemistry')
            return ('t', ESCAPED.get(value, value))
        if value == 'mathrm':
            return self.group()
        if value == 'text':
            return ('text', self.raw_text())
        if value in X_ARROWS:
            below = self.optional()
            above = self.group()
            return ('arrow', X_ARROWS[value], above, below)
        if value in {'overset', 'underset'}:
            mark = self.group()
            base = self.group()
            return ('over' if value == 'overset' else 'under', base, mark)
        if value == 'frac':
            return ('frac', self.group(), self.group())
        if value in {'left', 'right'}:
            kind, delimiter = self.take()
            if delimiter == '.':
                return None
            return ('t', ESCAPED.get(delimiter, delimiter) if kind == 'esc' else delimiter)
        if value in SYMBOLS:
            return ('t', SYMBOLS[value])
        raise ChemistryRenderError('Chemistry construct not drawn in Word: \\' + value)


def parse(source):
    validate_latex(source, chemistry=True)
    parser = Parser(source)
    nodes = parser.sequence()
    if parser.peek() is not None:
        raise ChemistryRenderError('Unbalanced chemistry expression')
    if not nodes:
        raise ChemistryRenderError('Empty chemistry expression')
    return nodes


def flat(nodes):
    return nodes is not None and all(n[0] in {'t', 'text'} for n in nodes)


def is_simple(nodes):
    for item in nodes:
        if item[0] in {'t', 'text'}:
            continue
        if item[0] == 'script' and flat(item[1]) and (item[2] is None or flat(item[2])) and (
                item[3] is None or flat(item[3])):
            continue
        return False
    return True


def rich_segments(nodes):
    """Return [(text, None|'subscript'|'superscript')] with adjacent runs merged."""
    segments = []

    def add(text, align=None):
        if not text:
            return
        if segments and segments[-1][1] == align:
            segments[-1] = (segments[-1][0] + text, align)
        else:
            segments.append((text, align))

    def text_of(items):
        return ''.join(n[1] for n in items)

    for item in nodes:
        if item[0] == 't' and item[1] in SPACED:
            # Office Math spaces binary/relation operators; plain text needs explicit spaces.
            add(' ' + item[1] + ' ')
        elif item[0] in {'t', 'text'}:
            add(item[1])
        else:
            add(text_of(item[1]))
            if item[2]:
                add(text_of(item[2]), 'subscript')
            if item[3]:
                add(text_of(item[3]), 'superscript')
    return segments


def omml_children(nodes):
    result, buffer = [], ''

    def flush():
        nonlocal buffer
        if buffer:
            result.append(math_run(buffer, 'p', True))
            buffer = ''

    for item in nodes:
        kind = item[0]
        if kind == 't':
            buffer += item[1]
            continue
        flush()
        if kind == 'text':
            result.append(math_run(item[1], 'p', True))  # Chinese or prose conditions
        elif kind == 'script':
            base = node('e', *omml_children(item[1]))
            sub = node('sub', *omml_children(item[2])) if item[2] is not None else None
            sup = node('sup', *omml_children(item[3])) if item[3] is not None else None
            if sub is not None and sup is not None:
                result.append(node('sSubSup', base, sub, sup))
            elif sub is not None:
                result.append(node('sSub', base, sub))
            else:
                result.append(node('sSup', base, sup))
        elif kind == 'pre':
            result.append(node('sPre', node('sub', *omml_children(item[1])),
                               node('sup', *omml_children(item[2])), node('e', *omml_children(item[3]))))
        elif kind in {'over', 'under'}:
            tag = 'limUpp' if kind == 'over' else 'limLow'
            result.append(node(tag, node('e', *omml_children(item[1])), node('lim', *omml_children(item[2]))))
        elif kind == 'arrow':
            _, glyph, above, below = item
            core = math_run(LONG.get(glyph, glyph) if (above or below) else glyph, 'p', True)
            if above:
                core = node('limUpp', node('e', core), node('lim', *omml_children(above)))
            if below:
                core = node('limLow', node('e', core), node('lim', *omml_children(below)))
            result.append(core)
        elif kind == 'frac':
            result.append(node('f', node('fPr', node('type', val='bar')),
                               node('num', *omml_children(item[1])), node('den', *omml_children(item[2]))))
        else:
            raise ChemistryRenderError('Unknown chemistry node: ' + kind)
    flush()
    return result


def to_omml(nodes):
    return node('oMath', *omml_children(nodes))


def add_chemistry(paragraph, latex, *, display=False):
    """Append chemistry to a python-docx paragraph; return 'rich_text' or 'omml'."""
    nodes = parse(latex)
    if is_simple(nodes):
        for text, align in rich_segments(nodes):
            piece = paragraph.add_run(text)
            if align == 'subscript':
                piece.font.subscript = True
            elif align == 'superscript':
                piece.font.superscript = True
        return 'rich_text'
    formula = to_omml(nodes)
    if display:
        paragraph._p.append(node('oMathPara', node('oMathParaPr', node('jc', val='center')), formula))
    else:
        paragraph._p.append(formula)
    return 'omml'


def plain_text(latex):
    """Linear reading of the rendered chemistry, used by consistency and leak checks."""
    def walk(nodes):
        text = ''
        for item in nodes:
            kind = item[0]
            if kind in {'t', 'text'}:
                text += item[1]
            elif kind == 'script':
                text += walk(item[1]) + walk(item[2] or []) + walk(item[3] or [])
            elif kind == 'pre':
                text += walk(item[2]) + walk(item[1]) + walk(item[3])
            elif kind in {'over', 'under'}:
                text += walk(item[1]) + walk(item[2])
            elif kind == 'arrow':
                text += walk(item[2]) + item[1] + walk(item[3])
            elif kind == 'frac':
                text += walk(item[1]) + '/' + walk(item[2])
        return text
    return walk(parse(latex))
