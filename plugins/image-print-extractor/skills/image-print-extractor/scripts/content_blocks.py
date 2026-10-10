"""Shared typed paragraph content for DOCX and offline HTML exports."""
import re
from latex_validation import validate_latex


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


def plain_source(item, *, validate_chemistry=False, markdown=False):
    if validate_chemistry:
        for part in parts(item):
            if part['type'] == 'chemistry':
                validate_latex(part['latex'], chemistry=True)
    if not markdown:
        return ''.join(part['text'] if part['type'] == 'text' else
                       ('$' + part['latex'] + '$' if part['type'] == 'math' else part['latex'])
                       for part in parts(item))
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
