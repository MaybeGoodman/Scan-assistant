"""Validated LaTeX subset -> MathML -> native Office Math, with no image fallback."""
import re
from lxml import etree

M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML = 'http://www.w3.org/XML/1998/namespace'

from latex_validation import (FormulaError, validate_latex, MATH_COMMANDS,
                              CHEM_COMMANDS, ENVIRONMENTS, ESCAPES, FUNCTION_NAMES)


def node(tag, *children, **attrs):
    element = etree.Element('{%s}%s' % (M, tag))
    for key, value in attrs.items():
        element.set('{%s}%s' % (M, key), str(value))
    element.extend(children)
    return element


def run(text, style='p', normal=False):
    props = node('rPr', node('sty', val=style))
    if normal:
        props.insert(0, node('nor'))
    font = etree.Element('{%s}rPr' % W)
    fonts = etree.SubElement(font, '{%s}rFonts' % W)
    fonts.set('{%s}ascii' % W, 'Cambria Math')
    fonts.set('{%s}hAnsi' % W, 'Cambria Math')
    fonts.set('{%s}eastAsia' % W, '宋体')
    text_node = node('t')
    text_node.set('{%s}space' % XML, 'preserve')
    text_node.text = text
    return node('r', props, font, text_node)


def local(element):
    return etree.QName(element).localname


def argument(tag, element, variant=None):
    return node(tag, *convert_element(element, variant))


def delimiter(children, begin, end):
    return node('d', node('dPr', node('begChr', val=begin), node('endChr', val=end),
                         node('grow', val='1')), node('e', *children))


def sequence(children, variant=None):
    children = list(children)
    # latex2mathml represents \left/\right and cases as fenced mrow children.
    if children and children[0].get('fence') == 'true':
        first = children.pop(0)
        end = ''
        if children and children[-1].get('fence') == 'true':
            end = ''.join(children.pop().itertext())
        return [delimiter(sequence(children, variant), ''.join(first.itertext()), end)]
    result, i = [], 0
    while i < len(children):
        element = children[i]
        tag = local(element)
        if (i + 2 < len(children) and tag == 'mo' and local(children[i + 1]) in {'mtable', 'mfrac'}
                and local(children[i + 2]) == 'mo'
                and (element.text, children[i + 2].text) in {('(', ')'), ('[', ']'), ('{', '}'), ('|', '|'), ('‖', '‖')}):
            result.append(delimiter(convert_element(children[i + 1], variant), element.text, children[i + 2].text))
            i += 3
            continue
        base = element[0] if tag in {'msub', 'msup', 'msubsup', 'munder', 'mover', 'munderover'} else element
        symbol = ''.join(base.itertext())
        if (symbol in FUNCTION_NAMES or (local(base) == 'mo' and symbol.isalpha() and len(symbol) > 1)):
            if i + 1 < len(children) and local(children[i + 1]) != 'mo':
                result.append(node('func', node('fName', *convert_element(element, variant)),
                                   argument('e', children[i + 1], variant)))
                i += 2
                continue
        if local(base) == 'mo' and symbol in '∑∏∐∫∬∭∮' and len(symbol) == 1:
            lower = upper = None
            if tag in {'msub', 'munder', 'msubsup', 'munderover'}:
                lower = element[1]
            if tag in {'msup', 'mover'}:
                upper = element[1]
            elif tag in {'msubsup', 'munderover'}:
                upper = element[2]
            props = node('naryPr', node('chr', val=symbol),
                         node('limLoc', val='undOvr' if tag in {'munder', 'mover', 'munderover'} else 'subSup'),
                         node('subHide', val='1' if lower is None else '0'),
                         node('supHide', val='1' if upper is None else '0'))
            operand = node('e')
            if i + 1 < len(children) and local(children[i + 1]) != 'mo':
                i += 1
                operand.extend(convert_element(children[i], variant))
            result.append(node('nary', props,
                               node('sub') if lower is None else argument('sub', lower, variant),
                               node('sup') if upper is None else argument('sup', upper, variant), operand))
        else:
            result.extend(convert_element(element, variant))
        i += 1
    return result


def convert_element(element, inherited_variant=None):
    tag = local(element)
    variant = element.get('mathvariant', inherited_variant)
    if tag in {'math', 'mrow', 'mstyle', 'mpadded'}:
        return sequence(element, variant)
    if tag in {'mi', 'mn', 'mo', 'mtext'}:
        text = ''.join(element.itertext())
        if tag == 'mtext':
            text = text.replace('\u00a0', ' ')
        if '\\' in text:
            raise FormulaError('Unconverted command in MathML')
        styles = {'normal': 'p', 'bold': 'b', 'italic': 'i', 'bold-italic': 'bi'}
        style = styles.get(variant, 'i' if tag == 'mi' and len(text) == 1 else 'p')
        result = run(text, style, tag == 'mtext')
        if variant in {'double-struck', 'script'}:
            result[0].insert(0, node('scr', val={'double-struck': 'double-struck', 'script': 'script'}[variant]))
        return [result]
    if tag == 'mspace':
        if element.get('linebreak'):
            raise FormulaError('Use an array/aligned environment for multiline math')
        width = element.get('width', '0em')
        spaces = {'0em': '', '0.167em': '\u2009', '0.222em': '\u205f', '0.278em': '\u2005',
                  '0.333em': '\u2004', '1em': '\u2003', '2em': '\u2003\u2003'}
        if width not in spaces:
            raise FormulaError('Unsupported mathematical spacing: ' + width)
        return [run(spaces[width])] if spaces[width] else []
    if tag == 'mfrac':
        props = node('fPr', node('type', val='noBar' if element.get('linethickness') == '0' else 'bar'))
        return [node('f', props, argument('num', element[0], variant), argument('den', element[1], variant))]
    if tag in {'msqrt', 'mroot'}:
        degree = node('deg') if tag == 'msqrt' else argument('deg', element[1], variant)
        content = node('e', *sequence(element, variant)) if tag == 'msqrt' else argument('e', element[0], variant)
        return [node('rad', node('radPr', node('degHide', val='1' if tag == 'msqrt' else '0')), degree, content)]
    if tag in {'msub', 'msup', 'msubsup'}:
        if tag == 'msub':
            return [node('sSub', argument('e', element[0], variant), argument('sub', element[1], variant))]
        if tag == 'msup':
            return [node('sSup', argument('e', element[0], variant), argument('sup', element[1], variant))]
        return [node('sSubSup', argument('e', element[0], variant), argument('sub', element[1], variant),
                     argument('sup', element[2], variant))]
    if tag in {'mover', 'munder', 'munderover'}:
        if tag == 'munderover':
            lower = node('limLow', argument('e', element[0], variant), argument('lim', element[1], variant))
            return [node('limUpp', node('e', lower), argument('lim', element[2], variant))]
        upper = tag == 'mover'
        mark = ''.join(element[1].itertext())
        if local(element[1]) == 'mo' and mark in {'→', '^', 'ˆ', '~', '˜', '˙', '¨', '¯', '‾', '―', '_', '⏞', '⏟'}:
            if mark in {'¯', '‾', '―', '_'}:
                return [node('bar', node('barPr', node('pos', val='top' if upper else 'bot')),
                             argument('e', element[0], variant))]
            if mark in {'⏞', '⏟'}:
                return [node('groupChr', node('groupChrPr', node('chr', val=mark),
                                             node('pos', val='top' if upper else 'bot')),
                             argument('e', element[0], variant))]
            if upper:
                combining = {'→': '\u20d7', '^': '\u0302', 'ˆ': '\u0302', '~': '\u0303',
                             '˜': '\u0303', '˙': '\u0307', '¨': '\u0308'}[mark]
                return [node('acc', node('accPr', node('chr', val=combining)), argument('e', element[0], variant))]
        return [node('limUpp' if upper else 'limLow', argument('e', element[0], variant),
                     argument('lim', element[1], variant))]
    if tag == 'mtable':
        rows = list(element)
        if not rows or any(local(row) != 'mtr' for row in rows):
            raise FormulaError('Unsupported or empty mathematical table')
        columns = max(len(row) for row in rows)
        if not columns:
            raise FormulaError('Empty matrix')
        column_props = []
        for index in range(columns):
            alignments = {row[index].get('columnalign', 'center') for row in rows if index < len(row)}
            if len(alignments) > 1:
                raise FormulaError('Inconsistent matrix column alignment')
            alignment = alignments.pop()
            if alignment not in {'left', 'right', 'center'}:
                raise FormulaError('Unsupported matrix alignment')
            column_props.append(node('mc', node('mcPr', node('count', val=1), node('mcJc', val=alignment))))
        matrix = node('m', node('mPr', node('mcs', *column_props)))
        for row in rows:
            if any(local(cell) != 'mtd' for cell in row):
                raise FormulaError('Unsupported matrix cell')
            cells = [node('e', *sequence(cell, variant)) for cell in row]
            cells.extend(node('e') for _ in range(columns - len(cells)))
            matrix.append(node('mr', *cells))
        return [matrix]
    if tag == 'mfenced':
        return [delimiter(sequence(element, variant), element.get('open', '('), element.get('close', ')'))]
    raise FormulaError('Unsupported mathematical structure: ' + tag)


def to_omml(source, *, display=False):
    validate_latex(source)
    try:
        from latex2mathml.converter import convert
    except ImportError as exc:
        raise RuntimeError('Install latex2mathml from the skill requirements before Word math export') from exc
    # These are layout normalizations, not algebra or source-content corrections.
    normalized = source.replace(r'\begin{aligned}', r'\begin{array}{rl}').replace(r'\end{aligned}', r'\end{array}')
    normalized = normalized.replace(r'\begin{gathered}', r'\begin{array}{c}').replace(r'\end{gathered}', r'\end{array}')
    if display and r'\textstyle' not in source:
        normalized = re.sub(r'\\(lim|limsup|liminf|min|max|sup|inf)\s*_',
                            lambda m: '\\' + m[1] + r'\limits_', normalized)
    # latex2mathml special-cases single upright letters; use text for literal units.
    normalized = re.sub(r'\\mathrm\{([A-Za-z0-9 /]+)\}', lambda m: r'\text{' + m[1] + '}', normalized)
    try:
        mathml = convert(normalized, display='block' if display else 'inline')
        root = etree.fromstring(mathml.encode('utf-8'), etree.XMLParser(resolve_entities=False, no_network=True))
        result = node('oMath', *convert_element(root))
        if not result.xpath('.//m:t | .//m:nary', namespaces={'m': M}):
            raise FormulaError('Conversion produced an empty formula')
        return result
    except FormulaError:
        raise
    except Exception as exc:
        raise FormulaError(f'LaTeX conversion failed: {type(exc).__name__}: {exc}') from exc
