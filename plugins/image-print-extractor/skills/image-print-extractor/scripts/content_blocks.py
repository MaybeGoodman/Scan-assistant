"""Shared typed paragraph content for DOCX and offline HTML exports."""
import re
from latex_validation import validate_latex


def reviewed_blocks(document):
    """Reject unprocessed selection metadata, preserving legacy reviewed inputs."""
    blocks = document['blocks']
    if not isinstance(blocks, list):
        raise ValueError('blocks must be a list')

    def check(item):
        if not isinstance(item, dict):
            raise ValueError('Content elements must be objects')
        if 'selection' in item:
            raise ValueError('Run select_content.py before exporting selection candidates')
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


def plain_source(item, *, validate_chemistry=False, markdown=False):
    if validate_chemistry:
        for part in parts(item):
            if part['type'] == 'chemistry':
                validate_latex(part['latex'], chemistry=True)
    return ''.join(part['text'] if part['type'] == 'text' else
                   ('$' + part['latex'] + '$' if part['type'] == 'math' else ('`' + part['latex'] + '`' if markdown else part['latex']))
                   for part in parts(item))


def check_word_text(text):
    # Refuse old untyped math instead of silently leaking source into Word.
    if re.search(r'(?<!\\)\$[^$\n]+\$|\\[\(\[]|\\(?:frac|sqrt|mathrm|text|begin|sin|cos|sum|int)\b', text):
        raise ValueError('LaTeX found in Word text: migrate it to a typed math or chemistry run')
