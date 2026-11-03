"""Inspect a saved .docx for answer leaks and check it against the JSON it came from.

Used after every student-mode export (R05/R10, section 6.3): body, tables, OMML,
headers/footers, comments, tracked changes, hidden text, custom XML, embedded
objects, picture descriptions and document properties are all scanned. The
consistency check confirms the Word file and the chat text were produced from the
same reviewed content (same text runs in the same order, same picture count).
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


def consistency(path, document):
    """Every plain text run of the JSON appears in the Word body in the same order."""
    result = audit(path, student=False)
    body = _norm(''.join(result['body']))
    position, missing = 0, []
    for value in expected_text_runs(document):
        found = body.find(value, position)
        if found < 0:
            missing.append(value[:24])
        else:
            position = found + len(value)
    images = sum(1 for b in document.get('blocks', []) if b.get('type') == 'image')
    problems = [f'Word 中缺少或顺序不一致：{m}' for m in missing]
    if images != result['pictures']:
        problems.append(f'图片数量不一致：JSON {images}，Word {result["pictures"]}')
    return {'ok': not problems, 'problems': problems}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('docx')
    parser.add_argument('--forbidden', help='JSON list of strings that must not appear')
    parser.add_argument('--against', help='Reviewed JSON the document was exported from')
    parser.add_argument('--original', action='store_true', help='Original-answer mode: skip student-only checks')
    args = parser.parse_args()
    forbidden = json.loads(Path(args.forbidden).read_text(encoding='utf-8')) if args.forbidden else []
    report = audit(args.docx, forbidden, student=not args.original)
    report.pop('body')
    if args.against:
        report['consistency'] = consistency(args.docx, json.loads(Path(args.against).read_text(encoding='utf-8')))
        report['ok'] = report['ok'] and report['consistency']['ok']
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
