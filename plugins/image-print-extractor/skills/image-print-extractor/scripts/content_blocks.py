"""Shared typed paragraph content for DOCX and offline HTML exports."""
import re
from _common import BLANK_LATEX, PASTE_TARGETS
from latex_validation import FormulaError, validate_latex


def reviewed_blocks(document):
    """Reject unprocessed selection metadata, preserving legacy reviewed inputs."""
    if 'figure_task' in document or document.get('figure_processing',{}).get('status','completed')!='completed':
        raise ValueError('Complete figure_workflow.py before exporting a figure task')
    blocks = document['blocks']
    if not isinstance(blocks, list):
        raise ValueError('blocks must be a list')

    def check(item):
        if not isinstance(item, dict):
            raise ValueError('Content elements must be objects')
        if 'selection' in item:
            raise ValueError('Run select_content.py before exporting selection candidates')
        if 'redraw' in item:
            from figure_drawing import validate_redraw_metadata
            validate_redraw_metadata(item)
        if 'fallback' in item:
            data = item['fallback']
            digest = data.get('source_sha256') if isinstance(data, dict) else None
            if (item.get('type') != 'image' or not isinstance(data, dict) or set(data) != {'reason', 'source_sha256'}
                    or data['reason'] not in {'failed', 'photo'} or not isinstance(digest, str) or len(digest) != 64
                    or any(c not in '0123456789abcdef' for c in digest)):
                raise ValueError('Invalid original-image fallback metadata')
        for key in ('runs', 'cells'):
            if key in item:
                if not isinstance(item[key], list):
                    raise ValueError(f'{key} must be a list')
                for child in item[key]:
                    check(child)
    for block in blocks:
        check(block)
    return blocks


def parts(item):
    if ('text' in item) == ('runs' in item):
        raise ValueError('Provide exactly one of text or runs for paragraph/cell content')
    values = [{'type': 'text', 'text': item['text']}] if 'text' in item else item['runs']
    if not isinstance(values, list):
        raise ValueError('runs must be a list')
    for part in values:
        if not isinstance(part, dict) or part.get('type') not in {'text', 'math', 'chemistry'}:
            raise ValueError('Each run must have type text, math or chemistry')
        key = 'text' if part['type'] == 'text' else 'latex'
        if not isinstance(part.get(key), str):
            raise ValueError(f'{key} must be a string')
        if part.get('display'):
            raise ValueError('Display expressions must be separate math/chemistry blocks')
    return values


# Markdown would otherwise reinterpret transcribed characters as formatting,
# HTML, links or math delimiters. Backslash escapes keep the visible text unchanged.
MARKDOWN_INLINE = re.compile(r'([\\`*_\[\]<>|~$])')
MARKDOWN_LINE_START = re.compile(r'^(\s{0,3})(#|[-+=]|\d{1,9}(?=[.)]))')
EQUATION_TEXT = re.compile(r'^[\s_＿+＋=＝→↑↓()（）]*$')
EQUATION_TOKENS = re.compile(r'[_＿]{2,}|[_＿]|[\s]+|.')
EQUATION_OPS = {'+': '+', '＋': '+', '=': '=', '＝': '=', '→': r'\rightarrow',
                '↑': r'\uparrow', '↓': r'\downarrow', '(': '(', '（': '(', ')': ')', '）': ')'}


def markdown_text(text, at_line_start):
    lines = MARKDOWN_INLINE.sub(r'\\\1', text).split('\n')
    escaped = []
    for index, line in enumerate(lines):
        if index or at_line_start:
            line = MARKDOWN_LINE_START.sub(
                lambda m: m[1] + (m[2] + '\\' if m[2][0].isdigit() else '\\' + m[2]), line)
        escaped.append(line)
    # A single source line break is a hard break; blank lines stay paragraph breaks.
    result = escaped[0]
    for previous, line in zip(escaped, escaped[1:]):
        result += ('\\\n' if previous.strip() and line.strip() else '\n') + line
    return result


def merge_equation(item, *, blank='underline', failures=None):
    """Merge an equation paragraph/cell into one fenced LaTeX block for AxMath pasting."""
    if blank not in BLANK_LATEX:
        raise ValueError('blank must be underline or escaped')
    values = parts(item)
    if not any(part['type'] in {'chemistry', 'math'} for part in values):
        return None
    if any(part['type'] == 'text' and not EQUATION_TEXT.fullmatch(part['text']) for part in values):
        return None
    blank_token = r'\underline{\qquad}\,' if blank == 'underline' else r'\_\_\_\_\_\_'
    pieces = []

    def append(chunk):
        if not chunk:
            return
        if pieces and re.search(r'\\[A-Za-z]+$', pieces[-1]) and chunk[0].isalpha():
            pieces.append(' ')
        pieces.append(chunk)

    for part in values:
        if part['type'] in {'chemistry', 'math'}:
            append(part['latex'])
            continue
        for token in EQUATION_TOKENS.findall(part['text']):
            if token[0].isspace():
                continue
            if token[0] in '_＿':
                append(blank_token if len(token) >= 2 else r'\_')
            else:
                append(EQUATION_OPS[token])
    merged = ''.join(pieces)
    has_chemistry = any(part['type'] == 'chemistry' for part in values)
    try:
        validate_latex(merged, chemistry=has_chemistry)
    except FormulaError as exc:
        if failures is not None:
            failures.append({'detail': str(exc), 'content': merged})
        return None
    return '```latex\n' + merged + '\n```'


def plain_source(item, *, validate_chemistry=False, markdown=False,
                 paste_target='axmath', blank_latex='underline', merge_failures=None):
    if paste_target not in PASTE_TARGETS:
        raise ValueError('paste_target must be axmath or markdown')
    if blank_latex not in BLANK_LATEX:
        raise ValueError('blank_latex must be underline or escaped')
    if validate_chemistry:
        for part in parts(item):
            if part['type'] == 'chemistry':
                validate_latex(part['latex'], chemistry=True)
    if not markdown:
        return ''.join(part['text'] if part['type'] == 'text' else
                       ('$' + part['latex'] + '$' if part['type'] == 'math' else part['latex'])
                       for part in parts(item))
    if paste_target == 'axmath':
        merged = merge_equation(item, blank=blank_latex, failures=merge_failures)
        if merged is not None:
            return merged
    output = ''
    for part in parts(item):
        if part['type'] == 'text':
            output += markdown_text(part['text'], not output or output.endswith('\n'))
        elif part['type'] == 'math':
            output += '$' + part['latex'] + '$'
        else:
            output += '`' + part['latex'] + '`'
    return output


# Pandoc-style inline math: no space just inside the dollars and no digit right
# after the closing one, so prices such as "$5，总价$20" stay ordinary text.
DOLLAR_MATH = re.compile(r'(?<![\\$])\$(?![\s$])([^$\n]*?)(?<![\s\\])\$(?![\d$])')
LATEX_MARKERS = re.compile(r'[\\^_{}]')
CJK = re.compile('[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]')


def check_word_text(text):
    # Refuse old untyped math instead of silently leaking source into Word.
    if re.search(r'\\[\(\[]|\\(?:frac|sqrt|mathrm|text|begin|sin|cos|sum|int)\b', text):
        raise ValueError('LaTeX found in Word text: migrate it to a typed math or chemistry run')
    for match in DOLLAR_MATH.finditer(text):
        if not CJK.search(match[1]):
            raise ValueError('LaTeX found in Word text: migrate it to a typed math or chemistry run')
    # Any dollar pair around LaTeX syntax is math, whatever its spacing.
    if any(LATEX_MARKERS.search(content) for content in re.findall(r'(?<!\\)\$([^$\n]+)\$', text)):
        raise ValueError('LaTeX found in Word text: migrate it to a typed math or chemistry run')
