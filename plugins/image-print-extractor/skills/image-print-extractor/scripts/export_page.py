"""Export already-transcribed blocks as offline HTML and Markdown."""
import argparse
import html
import json
import shutil
import struct
from pathlib import Path
from content_blocks import plain_source, reviewed_blocks
from latex_validation import validate_latex


def escape(text):
    if not isinstance(text, str):
        raise ValueError('Text must be a string')
    return html.escape(text).replace('\n', '<br>')


def table_html(block, *, validate_chemistry=False):
    rows, cols = block['rows'], block['cols']
    if any(type(v) is not int or not 1 <= v <= 1000 for v in (rows, cols)):
        raise ValueError('Invalid table dimensions')
    occupied, starts = set(), {}
    for cell in block['cells']:
        r, c = cell['row'], cell['col']
        rs, cs = cell.get('rowspan', 1), cell.get('colspan', 1)
        if any(type(v) is not int for v in (r, c, rs, cs)):
            raise ValueError('Cell coordinates must be integers')
        if not (0 <= r < rows and 0 <= c < cols and rs >= 1 and cs >= 1
                and r + rs <= rows and c + cs <= cols):
            raise ValueError('Cell outside table')
        area = {(y, x) for y in range(r, r + rs) for x in range(c, c + cs)}
        if occupied & area:
            raise ValueError('Overlapping cells')
        occupied.update(area)
        starts[r, c] = f'<td rowspan="{rs}" colspan="{cs}">{escape(plain_source(cell, validate_chemistry=validate_chemistry))}</td>'
    if len(occupied) != rows * cols:
        raise ValueError('Every cell, including blanks, must be explicit')
    return '<table border="1" cellspacing="0" cellpadding="6">' + ''.join(
        '<tr>' + ''.join(starts.get((r, c), '') for c in range(cols)) + '</tr>'
        for r in range(rows)) + '</table>'


def image_source(base, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Image path must stay inside input directory')
    source = (base / path).resolve()
    if not source.is_relative_to(base.resolve()) or source.suffix.lower() != '.png':
        raise ValueError('Only local PNG images are supported')
    data = source.read_bytes()
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ValueError('Invalid PNG header')
    width, height = struct.unpack('>II', data[16:24])
    if not width or not height:
        raise ValueError('Invalid PNG size')
    return source


def export(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    blocks = reviewed_blocks(json.loads(source.read_text(encoding='utf-8')))
    fragments, markdown, copies = [], [], []
    for index, block in enumerate(blocks, 1):
        kind = block['type']
        if kind == 'text':
            text = plain_source(block, validate_chemistry=True)
            fragments.append('<p>' + escape(text) + '</p>')
            markdown.append(plain_source(block, validate_chemistry=True, markdown=True))
        elif kind in {'math', 'chemistry'}:
            latex = block.get('latex')
            if not isinstance(latex, str):
                raise ValueError('latex must be a string')
            if kind == 'chemistry':
                validate_latex(latex, chemistry=True)
            text = '$$' + latex + '$$' if kind == 'math' else latex
            fragments.append('<p>' + escape(text) + '</p>')
            markdown.append('```latex\n' + latex + '\n```' if kind == 'chemistry' else text)
        elif kind == 'table':
            fragments.append(f'<div id="table-{index}">' + table_html(block, validate_chemistry=True) + '</div>')
            markdown.append(f'[表格](result.html#table-{index})')
        elif kind == 'image':
            image = image_source(source.parent, block['path'])
            target = f'figures/figure-{index:02d}.png'
            copies.append((image, target))
            alt = escape(block.get('alt', ''))
            fragments.append(f'<p><img src="{target}" alt="{alt}"></p>')
            markdown.append(f'![]({target})')
        else:
            raise ValueError(f'Unknown block type: {kind}')
    # Validate everything before creating files; never overwrite an existing export.
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Output directory must be new or empty')
    output.mkdir(parents=True, exist_ok=True)
    for image, relative in copies:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, target)
    document = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title></title><style>body{font:16px/1.7 sans-serif;max-width:960px;'
                'margin:32px auto;padding:0 20px}p{white-space:pre-wrap}'
                'table{border-collapse:collapse;margin:16px 0;max-width:100%}'
                'td{border:1px solid #444;white-space:pre-wrap;vertical-align:top;'
                'min-width:2em;font-weight:normal}img{max-width:100%;height:auto}'
                '</style></head><body>' + '\n'.join(fragments) + '</body></html>')
    (output / 'result.html').write_text(document, encoding='utf-8')
    (output / 'result.md').write_text('\n\n'.join(markdown) + '\n', encoding='utf-8')
    return output / 'result.html'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    print(export(args.source, args.output_dir))
