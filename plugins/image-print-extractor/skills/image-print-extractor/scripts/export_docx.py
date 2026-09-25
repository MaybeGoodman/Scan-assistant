"""Export reviewed blocks to real DOCX after explicit Word confirmation."""
import argparse
import json
from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt
from docx.oxml.ns import qn
from PIL import Image
from export_page import image_source, table_html


def export_docx(source, output, *, word_confirmed=False):
    if word_confirmed is not True:
        raise ValueError('Confirm Word output with the user first')
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.suffix.lower() != '.docx':
        raise ValueError('Output must end in .docx')
    if output.exists():
        raise FileExistsError(output)
    blocks = json.loads(source.read_text(encoding='utf-8'))['blocks']
    if not isinstance(blocks, list):
        raise ValueError('blocks must be a list')
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2)
    section.left_margin = section.right_margin = Cm(2.2)
    style = document.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(11)
    style.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), '宋体')
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.line_spacing = 1.2
    max_width = int(section.page_width - section.left_margin - section.right_margin)
    max_height = int(section.page_height - section.top_margin - section.bottom_margin - Cm(1))
    for block in blocks:
        kind = block['type']
        if kind == 'text':
            if not isinstance(block['text'], str):
                raise ValueError('Text must be a string')
            document.add_paragraph(block['text'])
        elif kind == 'table':
            table_html(block)  # Shared grid validation, including blank and merged cells.
            table = document.add_table(rows=block['rows'], cols=block['cols'])
            table.style = 'Table Grid'
            table.autofit = False
            for column in table.columns:
                column.width = int(max_width / block['cols'])
            for item in block['cells']:
                r, c = item['row'], item['col']
                rs, cs = item.get('rowspan', 1), item.get('colspan', 1)
                cell = table.cell(r, c)
                if rs > 1 or cs > 1:
                    cell = cell.merge(table.cell(r + rs - 1, c + cs - 1))
                cell.text = item['text']
        elif kind == 'image':
            image = image_source(source.parent, block['path'])
            with Image.open(image) as pixels:
                pixels.verify()
            with Image.open(image) as pixels:
                width, height = pixels.size
            display_width = min(max_width, int(max_height * width / height), int(Cm(width / 96 * 2.54)))
            shape = document.add_picture(str(image), width=display_width)
            alt = block.get('alt', '')
            if not isinstance(alt, str):
                raise ValueError('Image alt must be a string')
            shape._inline.docPr.set('descr', alt)
        else:
            raise ValueError(f'Unknown block type: {kind}')
    document.core_properties.author = ''
    document.core_properties.last_modified_by = ''
    document.core_properties.comments = ''
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement if another process wrote meanwhile.
    with output.open('xb') as stream:
        document.save(stream)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--output', required=True)
    parser.add_argument('--word-confirmed', action='store_true',
                        help='Use only after the user explicitly chose Word')
    args = parser.parse_args()
    print(export_docx(args.source, args.output, word_confirmed=args.word_confirmed))
