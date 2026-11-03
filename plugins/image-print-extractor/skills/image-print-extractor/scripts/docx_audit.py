"""Inspect a saved .docx for answer leaks and check it against the JSON it came from.

Used after every student-mode export (R05/R10, section 6.3): body, tables, OMML,
headers/footers, comments, tracked changes, hidden text, custom XML, embedded
objects, picture descriptions and document properties are all scanned. The
consistency check confirms the Word file shows exactly the reviewed content: it
re-exports the same JSON and compares every body paragraph's text, sub/superscript
marks and OMML structure (fractions, powers, radicals, reaction conditions), plus the
picture bytes when the JSON's location is known.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from zipfile import ZipFile
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
NS = {'w': W, 'm': M, 'wp': WP}
PARSER = etree.XMLParser(resolve_entities=False, no_network=True)
ANSWER_LABEL = re.compile(r'^\s*[【\[（(]?\s*(答案|解析|解答|详解|参考答案|故选)\s*[】\]）)]?\s*[:：]')


def _norm(text):
    return re.sub(r'\s+', '', text or '')


def paragraphs(xml):
    """Text of each w:p, OMML glyphs included, in document order."""
    result = []
    for paragraph in xml.iter('{%s}p' % W):
        result.append(''.join(paragraph.xpath('.//w:t/text() | .//m:t/text()', namespaces=NS)))
    return result


def read_parts(path):
    with ZipFile(path) as package:
        names = package.namelist()
        parts = {name: package.read(name) for name in names}
    return names, parts


def audit(path, forbidden=(), *, student=True):
    """Return {'ok': bool, 'problems': [...], 'body': [paragraph texts]}."""
    names, parts = read_parts(path)
    problems = []
    document = etree.fromstring(parts['word/document.xml'], PARSER)
    body = paragraphs(document)
    if any(name == 'word/comments.xml' or name.startswith('word/comments') for name in names):
        problems.append('文档含批注部件')
    custom_text = []
    for name in names:
        # python-docx's template ships an empty bibliography store; only data-bearing parts matter.
        if name.startswith('customXml/') and name.endswith('.xml') and '/_rels/' not in name:
            root = etree.fromstring(parts[name], PARSER)
            custom_text += [t.strip() for t in root.itertext() if t.strip()]
    if custom_text:
        problems.append('文档含带数据的自定义 XML 部件')
    if any(name.startswith('word/embeddings/') for name in names):
        problems.append('文档含嵌入对象')
    if 'docProps/custom.xml' in names:
        problems.append('文档含自定义属性')
    scanned = list(body) + custom_text
    for name in names:
        if re.fullmatch(r'word/(header|footer|footnotes|endnotes)\d*\.xml', name):
            scanned += paragraphs(etree.fromstring(parts[name], PARSER))
    for tag, label in (('ins', '修订插入'), ('del', '修订删除'), ('vanish', '隐藏文字')):
        if document.xpath(f'//w:{tag}', namespaces=NS):
            problems.append(f'文档含{label}')
    for descr in document.xpath('//wp:docPr', namespaces=NS):
        for attribute in ('descr', 'title'):
            if descr.get(attribute):
                scanned.append(descr.get(attribute))
                if student:
                    problems.append('学生版图片含替代文字')
    if 'docProps/core.xml' in parts:
        core = etree.fromstring(parts['docProps/core.xml'], PARSER)
        scanned += [t for t in core.itertext() if t.strip() and not re.fullmatch(r'[\dT:\-.Z]+', t.strip())]
    from questions import glyphs
    joined = glyphs('\n'.join(scanned))
    for value in forbidden:
        if glyphs(value) and glyphs(value) in joined:
            problems.append(f'出现应移除的答案内容：{value[:24]}')
    if student:
        for text in scanned:
            if ANSWER_LABEL.match(text):
                problems.append(f'疑似答案标签：{text[:24]}')
    return {'ok': not problems, 'problems': problems, 'body': body,
            'pictures': len(document.xpath('//wp:docPr', namespaces=NS))}


def expected_text_runs(document):
    """Plain text runs from the reviewed JSON, in order, for the consistency check."""
    values = []

    def visit(item):
        if item.get('type') == 'text' and isinstance(item.get('text'), str) and 'runs' not in item:
            if _norm(item['text']):
                values.append(_norm(item['text']))
        for child in item.get('runs', []) or []:
            visit(child)
        for child in item.get('cells', []) or []:
            if isinstance(child.get('text'), str) and _norm(child['text']):
                values.append(_norm(child['text']))
            for run in child.get('runs', []) or []:
                visit(run)

    for block in document.get('blocks', []):
        visit(block)
    return values


IMAGE_TOKEN = '⟦图⟧'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _math_signature(element):
    """Structure + text of an OMML subtree: f/num/den, sSup/sup, rad, nary, limits, accents."""
    parts = []
    # Meaningful settings inside *Pr elements (fraction bar, delimiter/accent characters, hidden
    # radical degree, limit placement); all other formatting is ignored.
    semantic = {'chr', 'begChr', 'endChr', 'sepChr', 'type', 'degHide', 'pos', 'limLoc'}

    def visit(item, in_properties):
        name = _local(item.tag)
        if name == 'rPr' and item.tag.startswith('{%s}' % W):
            return  # Word run formatting inside math.
        properties = in_properties or name.endswith('Pr')
        if name == 't':
            parts.append('t:' + (item.text or ''))
        elif name in semantic:
            parts.append(f'{name}={item.get("{%s}val" % M)}')
        elif not properties and name != 'r':
            parts.append(name)
        for child in item:
            visit(child, properties)
    visit(element, False)
    return 'M[' + ' '.join(parts) + ']'


def paragraph_tokens(paragraph):
    """Visible content of one w:p in order: text with sub/superscript marks, OMML, pictures."""
    tokens = []
    for child in paragraph.iter():
        name = _local(child.tag)
        if child.tag in {'{%s}oMath' % M, '{%s}oMathPara' % M}:
            parent = child.getparent()
            if parent is not None and parent.tag == '{%s}oMathPara' % M:
                continue  # Counted through its oMathPara.
            tokens.append(_math_signature(child))
        elif child.tag == '{%s}t' % W:
            if next((a for a in child.iterancestors() if a.tag.startswith('{%s}' % M)), None) is not None:
                continue  # OMML text is part of the math signature.
            run = child.getparent()
            align = run.find('w:rPr/w:vertAlign', NS)
            mark = align.get('{%s}val' % W) if align is not None else ''
            tokens.extend((mark, char) for char in (child.text or '') if not char.isspace())
        elif name == 'drawing':
            tokens.append(IMAGE_TOKEN)
    merged, text = [], []
    for token in tokens:  # Collapse consecutive characters with the same baseline mark.
        if isinstance(token, tuple):
            if text and text[-1][0] == token[0]:
                text[-1] = (token[0], text[-1][1] + token[1])
            else:
                text.append(token)
            continue
        merged += [f'{mark}:{value}' if mark else value for mark, value in text]
        text = []
        merged.append(token)
    merged += [f'{mark}:{value}' if mark else value for mark, value in text]
    return merged


def body_signature(path):
    """[tokens per non-empty body paragraph] and the bytes of each picture in order."""
    names, parts = read_parts(path)
    document = etree.fromstring(parts['word/document.xml'], PARSER)
    rels = {}
    if 'word/_rels/document.xml.rels' in parts:
        for rel in etree.fromstring(parts['word/_rels/document.xml.rels'], PARSER):
            rels[rel.get('Id')] = 'word/' + rel.get('Target').lstrip('/').removeprefix('word/')
    paragraphs_ = []
    for paragraph in document.find('w:body', NS).iter('{%s}p' % W):
        tokens = paragraph_tokens(paragraph)
        if tokens:
            paragraphs_.append(tokens)
    pictures = []
    for blip in document.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}blip'):
        target = rels.get(blip.get('{%s}embed' % R))
        pictures.append(parts.get(target, b''))
    return paragraphs_, pictures


def consistency(path, document, *, source=None, chemistry_format='native'):
    """The Word file shows exactly the reviewed content: text, sub/superscripts, math, pictures.

    The expected body is produced by exporting the same JSON again with the same exporter
    and comparing paragraph signatures, so a changed numerator, denominator, exponent,
    charge, reaction condition or picture is reported (F05). ``source`` is the JSON file's
    path, needed to resolve image paths; without it pictures are compared by count only.
    """
    import hashlib
    import shutil
    import tempfile
    from export_docx import export_docx

    result = audit(path, student=False)
    problems = []
    images = sum(1 for b in document.get('blocks', []) if b.get('type') == 'image')
    mode = 'student' if document.get('output_mode') == 'student' else 'original'
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        if source is not None:
            base = Path(source).resolve().parent
            expected_json = base / f'.consistency-{hashlib.sha256(str(temp).encode()).hexdigest()[:12]}.json'
        else:
            # Without image files the pictures become markers that match the picture token.
            expected_json = temp / 'expected.json'
            document = json.loads(json.dumps(document))
            document['blocks'] = [{'type': 'text', 'text': IMAGE_TOKEN} if b.get('type') == 'image' else b
                                  for b in document.get('blocks', [])]
        try:
            expected_json.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            export_docx(expected_json, temp / 'expected.docx', word_confirmed=True, report_path=temp / 'r.json',
                        output_mode=mode, chemistry_format=chemistry_format)
            want, want_pictures = body_signature(temp / 'expected.docx')
        finally:
            if source is not None:
                expected_json.unlink(missing_ok=True)
    got, got_pictures = body_signature(path)
    for index in range(max(len(want), len(got))):
        a = want[index] if index < len(want) else None
        b = got[index] if index < len(got) else None
        if a != b:
            problems.append(f'第 {index + 1} 段内容与题面不一致：期望 {"".join(a or [])[:60]}，'
                            f'Word 为 {"".join(b or [])[:60]}')
            if len(problems) >= 10:
                break
    if images != result['pictures']:
        problems.append(f'图片数量不一致：JSON {images}，Word {result["pictures"]}')
    elif source is not None and want_pictures != got_pictures:
        problems.append('Word 中的图片与已验证的图件不一致')
    return {'ok': not problems, 'problems': problems}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('docx')
    parser.add_argument('--forbidden', help='JSON list of strings that must not appear')
    parser.add_argument('--against', help='Reviewed JSON the document was exported from')
    parser.add_argument('--original', action='store_true', help='Original-answer mode: skip student-only checks')
    parser.add_argument('--chemistry-format', choices=['native', 'source'], default='native',
                        help='Chemistry format the Word file was exported with (for --against)')
    args = parser.parse_args()
    forbidden = json.loads(Path(args.forbidden).read_text(encoding='utf-8')) if args.forbidden else []
    report = audit(args.docx, forbidden, student=not args.original)
    report.pop('body')
    if args.against:
        against = Path(args.against)
        report['consistency'] = consistency(args.docx, json.loads(against.read_text(encoding='utf-8')), source=against,
                                            chemistry_format=args.chemistry_format)
        report['ok'] = report['ok'] and report['consistency']['ok']
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
