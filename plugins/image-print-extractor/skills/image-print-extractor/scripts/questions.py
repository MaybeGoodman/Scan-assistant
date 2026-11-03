"""V1.0 question layer, output modes and delivery gate on top of reviewed blocks.

Everything here is additive metadata. A 0.8.1 reviewed document (blocks only) still
exports exactly as before in ``original`` mode. The host supplies the semantics
(which blocks form question 18, which run is the printed answer); this module only
validates those references, projects the student view and collects review items.

Block / run / cell fields used (all optional):
  id    stable block id, required for blocks referenced by ``questions``
  role  semantic role. Answer roles are removed in student mode; ``uncertain`` is a
        review item. Missing role means ordinary question content.

Document fields used (all optional):
  questions   [{question_id, number, module, question_type, blocks, materials,
                subquestions:[{subquestion_id, number, blocks, depends_on}],
                source_spans, review_status, completeness:{complete, missing}}]
  materials   [{material_id, blocks}]  shared passages / data used by several questions
  review_resolutions  [{key, resolution: confirmed|accepted, by, note}]
"""
import hashlib
import json
import re
from copy import deepcopy

QUESTION_ROLES = frozenset({'stem', 'material', 'option', 'subquestion', 'answer_space', 'figure',
                            'instruction', 'source', 'title', 'other'})
ANSWER_ROLES = frozenset({'answer', 'analysis', 'solution', 'filled_answer', 'answer_mark', 'scoring'})
ROLES = QUESTION_ROLES | ANSWER_ROLES | {'uncertain'}
MODES = ('original', 'student')
REVIEW_STATUS = ('confirmed', 'needs_review', 'unresolved', 'failed')
DELIVERY = ('draft', 'final', 'partial', 'blocked')
MODULES = ('M01', 'M02', 'M03', 'M04', 'M05', 'M06', 'M07', 'M08')
RESOLUTIONS = ('confirmed', 'accepted')
# Labels that usually introduce answer material. Used only to flag unannotated content
# for review in student mode; nothing is ever deleted because of a keyword.
ANSWER_LABEL = re.compile(r'^\s*[【\[（(]?\s*(答案|解析|解答|详解|点拨|评分|参考答案|故选|答)\s*[】\]）)]?\s*[:：]?')


class QuestionError(ValueError):
    pass


def _texts(item):
    """Yield (path, string) for every transcribed string inside a block/run/cell."""
    if 'text' in item and isinstance(item['text'], str):
        yield 'text', item['text']
    if 'latex' in item and isinstance(item['latex'], str):
        yield 'latex', item['latex']
    for key in ('runs', 'cells'):
        for index, child in enumerate(item.get(key, []) or []):
            if isinstance(child, dict):
                for path, text in _texts(child):
                    yield f'{key}[{index}].{path}', text


def visible_text(item):
    return ''.join(text for _, text in _texts(item))


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:12]


def check_roles(document):
    for block in document.get('blocks', []):
        stack = [block]
        while stack:
            item = stack.pop()
            if 'role' in item and item['role'] not in ROLES:
                raise QuestionError(f'未知的内容角色：{item["role"]}')
            for key in ('runs', 'cells'):
                stack.extend(child for child in item.get(key, []) or [] if isinstance(child, dict))


def block_index(document):
    ids = {}
    for position, block in enumerate(document.get('blocks', [])):
        if 'id' in block:
            if not isinstance(block['id'], str) or not block['id']:
                raise QuestionError('块 id 必须是非空字符串')
            if block['id'] in ids:
                raise QuestionError(f'块 id 重复：{block["id"]}')
            ids[block['id']] = position
    return ids


def validate_questions(document):
    """Validate the optional question index; returns a list of missing-reference notes."""
    if not isinstance(document, dict) or not isinstance(document.get('blocks'), list):
        raise QuestionError('文档必须包含 blocks 列表')
    check_roles(document)
    ids = block_index(document)
    image_mode = (document.get('figure_processing') or {}).get('image_mode')
    missing = []

    def refs(owner, values, what='blocks'):
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise QuestionError(f'{owner} 的 {what} 必须是字符串列表')
        positions = []
        for value in values:
            if value not in ids:
                missing.append({'owner': owner, 'block': value, 'ignored_image_mode': image_mode == 'ignore'})
            else:
                positions.append(ids[value])
        if positions != sorted(positions):
            raise QuestionError(f'{owner} 的块引用顺序与正文阅读顺序不一致')
        return set(values)

    materials = {}
    for material in document.get('materials', []) or []:
        mid = material.get('material_id')
        if not isinstance(mid, str) or mid in materials:
            raise QuestionError('materials 的 material_id 缺失或重复')
        materials[mid] = refs(f'材料 {mid}', material.get('blocks', []))
    owners, seen = {}, set()
    for question in document.get('questions', []) or []:
        qid = question.get('question_id')
        if not isinstance(qid, str) or not qid or qid in seen:
            raise QuestionError('questions 的 question_id 缺失或重复')
        seen.add(qid)
        if 'module' in question and question['module'] not in MODULES:
            raise QuestionError(f'题目 {qid} 的 module 必须为 M01–M08')
        if question.get('review_status', 'needs_review') not in REVIEW_STATUS:
            raise QuestionError(f'题目 {qid} 的 review_status 无效')
        used = refs(f'题目 {qid}', question.get('blocks', []))
        for mid in question.get('materials', []) or []:
            if mid not in materials:
                raise QuestionError(f'题目 {qid} 引用了不存在的材料 {mid}')
        sub_ids = []
        for sub in question.get('subquestions', []) or []:
            sid = sub.get('subquestion_id')
            if not isinstance(sid, str) or not sid or sid in sub_ids:
                raise QuestionError(f'题目 {qid} 的小问 id 缺失或重复')
            for dep in sub.get('depends_on', []) or []:
                if dep not in sub_ids:
                    raise QuestionError(f'小问 {sid} 只能依赖排在它前面的小问，{dep} 不满足')
            sub_ids.append(sid)
            used |= refs(f'小问 {sid}', sub.get('blocks', []))
        for block_id in used:
            if block_id in owners and owners[block_id] != qid:
                raise QuestionError(f'块 {block_id} 同时属于题目 {owners[block_id]} 和 {qid}；共享内容请放入 materials')
            owners[block_id] = qid
        completeness = question.get('completeness', {'complete': True, 'missing': []})
        if not isinstance(completeness, dict) or type(completeness.get('complete')) is not bool:
            raise QuestionError(f'题目 {qid} 的 completeness.complete 必须是布尔值')
    return missing


def question_blocks(document, question_id):
    """Ordered blocks of one complete question: shared materials, stem, then subquestions."""
    ids = block_index(document)
    question = next((q for q in document.get('questions', []) or [] if q.get('question_id') == question_id), None)
    if question is None:
        raise QuestionError(f'找不到题目 {question_id}')
    materials = {m['material_id']: m for m in document.get('materials', []) or []}
    wanted = []
    for mid in question.get('materials', []) or []:
        wanted += materials[mid].get('blocks', [])
    wanted += question.get('blocks', [])
    for sub in question.get('subquestions', []) or []:
        wanted += sub.get('blocks', [])
    ordered = []
    for block_id in wanted:
        if block_id in ids and block_id not in ordered:
            ordered.append(block_id)
    return [document['blocks'][ids[b]] for b in ordered]


def _project(item, removed, location):
    """Return the student projection of a block/run, or None to drop it."""
    if item.get('role') in ANSWER_ROLES:
        removed.append({'location': location, 'role': item['role'], 'text': visible_text(item)})
        return None
    result = deepcopy(item)
    if 'runs' in result:
        runs = []
        for index, child in enumerate(result['runs']):
            projected = _project(child, removed, f'{location}.runs[{index}]')
            if projected is not None:
                runs.append(projected)
        result['runs'] = runs or [{'type': 'text', 'text': ''}]
    if 'cells' in result:
        cells = []
        for index, cell in enumerate(result['cells']):
            if cell.get('role') in ANSWER_ROLES:
                removed.append({'location': f'{location}.cells[{index}]', 'role': cell['role'],
                                'text': visible_text(cell)})
                cell = {k: deepcopy(v) for k, v in cell.items() if k not in {'text', 'runs', 'role'}}
                cell['text'] = ''  # Keep the grid; only the answer content goes.
            else:
                cell = _project(cell, removed, f'{location}.cells[{index}]')
            cells.append(cell)
        result['cells'] = cells
    if result.get('type') == 'image' and result.get('alt'):
        # Alt text is free description and may name the answer; students get none.
        removed.append({'location': location + '.alt', 'role': 'alt_text', 'text': result['alt']})
        result['alt'] = ''
    return result


def project(document, mode='original'):
    """Return (document_for_mode, removed_items). Original mode is an unchanged copy."""
    if mode not in MODES:
        raise QuestionError('输出模式只能为 original 或 student')
    validate_questions(document)
    if mode == 'original':
        return deepcopy(document), []
    removed, blocks = [], []
    removed_ids = set()
    for index, block in enumerate(document['blocks']):
        projected = _project(block, removed, f'blocks[{index}]')
        if projected is None:
            if 'id' in block:
                removed_ids.add(block['id'])
            continue
        blocks.append(projected)
    result = deepcopy(document)
    result['blocks'] = blocks
    for question in result.get('questions', []) or []:
        question['blocks'] = [b for b in question.get('blocks', []) if b not in removed_ids]
        for sub in question.get('subquestions', []) or []:
            sub['blocks'] = [b for b in sub.get('blocks', []) if b not in removed_ids]
    for material in result.get('materials', []) or []:
        material['blocks'] = [b for b in material.get('blocks', []) if b not in removed_ids]
    result.pop('review_resolutions', None)
    result['output_mode'] = 'student'
    return result, removed


GLYPHS = {'times': '×', 'cdot': '·', 'Omega': 'Ω', 'Delta': 'Δ', 'pi': 'π', 'sqrt': '√', 'leq': '≤', 'geq': '≥',
          'le': '≤', 'ge': '≥', 'rightarrow': '→', 'uparrow': '↑', 'downarrow': '↓', 'alpha': 'α', 'theta': 'θ',
          'angle': '∠', 'triangle': '△', 'perp': '⊥', 'in': '∈', 'infty': '∞', 'pm': '±'}


def glyphs(text):
    """Approximate what a reader sees for a LaTeX/text string, for leak comparison only."""
    text = re.sub(r'\\([A-Za-z]+)', lambda m: GLYPHS.get(m[1], ''), text)
    text = re.sub(r'\\.', '', text)
    return re.sub(r'[{}^_$\s]', '', text)


def forbidden_strings(removed, extra=()):
    """Answer material that must not reappear in a student package.

    Whole answers and their pieces (split at Chinese/English separators and item labels)
    are compared on visible glyphs, so a fragment such as "72 m" quoted in another block
    is still caught. Pieces shorter than three glyphs are skipped (option letters etc.).
    """
    values = set()
    for item in list(removed) + [{'text': value} for value in extra]:
        text = ANSWER_LABEL.sub('', glyphs(item.get('text', '')))
        candidates = [text] + re.split(r'[；;，,。、]|[（(]\d+[）)]|\d+[.．]', text)
        for value in candidates:
            value = value.strip('：:')
            if len(value) >= 3:
                values.add(value)
    return sorted(values)


GIVEN_ROLES = frozenset({'stem', 'material', 'option', 'subquestion', 'answer_space', 'instruction', 'title', 'source'})


def student_leak_strings(projected, removed):
    """Removed answer pieces that must not appear in the student file.

    A piece that is also printed in an explicit question-content block (e.g. the answer
    "10 Ω" when the stem gives "R1=10 Ω") is given data, not a leak. Pieces found in any
    other kept block -- an inference note, an unannotated paragraph -- still count.
    """
    given = glyphs(''.join(visible_text(b) for b in projected.get('blocks', []) if b.get('role') in GIVEN_ROLES))
    return [value for value in forbidden_strings(removed) if glyphs(value) not in given]


def review_items(document, *, mode='original', extra=()):
    """Collect every item that keeps a delivery from being final (R11)."""
    items = []

    def add(kind, location, detail, content=None):
        key = f'{kind}:{location}:{_digest(content if content is not None else detail)}'
        items.append({'key': key, 'kind': kind, 'location': location, 'detail': detail})

    for index, block in enumerate(document.get('blocks', [])):
        location = f'blocks[{index}]'
        stack = [(block, location)]
        while stack:
            item, where = stack.pop()
            for path, text in _texts({k: v for k, v in item.items() if k in {'text', 'latex'}}):
                if text.lstrip().startswith('补写说明'):
                    continue  # The inference list documents markers; the markers themselves are the items.
                if '〔' in text:
                    add('inference', where, '推断补写内容待复核', text)
                if 'XXX' in text:
                    add('unreadable', where, '无法可靠辨认的局部（XXX）', text)
            if item.get('status') == 'unresolved':
                add('expression', where, item.get('reason', '表达式无法可靠识别'), item.get('latex'))
            if item.get('role') == 'uncertain':
                add('role', where, '内容角色无法判清（是否为答案材料）', visible_text(item))
            if mode == 'student' and item.get('role') is None and item.get('type') == 'text' and 'text' in item:
                if ANSWER_LABEL.match(item['text']):
                    add('possible_answer', where, '疑似答案或解析但未标注角色', item['text'])
            for key in ('runs', 'cells'):
                for child_index, child in enumerate(item.get(key, []) or []):
                    if isinstance(child, dict):
                        stack.append((child, f'{where}.{key}[{child_index}]'))
        if block.get('figure_placeholder'):
            info = block['figure_placeholder']
            add('figure', location, f'插图 {info.get("figure_id")} 未能可靠重绘（{info.get("reason")}）', info)
        if mode == 'student' and block.get('type') == 'text' and 'runs' in block and block.get('role') is None:
            first = ''.join(r.get('text', '') for r in block['runs'][:1] if r.get('type') == 'text')
            if ANSWER_LABEL.match(first):
                add('possible_answer', location, '疑似答案或解析但未标注角色', visible_text(block))
    for note in validate_questions(document):
        if not note['ignored_image_mode']:
            add('missing_block', note['owner'], f'引用的块 {note["block"]} 不在文档中', note)
    for question in document.get('questions', []) or []:
        qid = question['question_id']
        if question.get('review_status', 'needs_review') != 'confirmed':
            add('question', f'question:{qid}', f'题目 {qid} 的结构与归属尚未确认', question)
        completeness = question.get('completeness') or {}
        if completeness.get('complete') is False:
            add('incomplete', f'question:{qid}', f'题目 {qid} 不完整：{completeness.get("missing", [])}', completeness)
    for entry in extra:
        add(entry.get('kind', 'export'), entry.get('location', ''), entry.get('detail', ''), entry.get('content'))
    resolved = {r.get('key'): r for r in document.get('review_resolutions', []) or []
                if isinstance(r, dict) and r.get('resolution') in RESOLUTIONS}
    for item in items:
        if item['key'] in resolved:
            item['resolution'] = resolved[item['key']]['resolution']
    return items


def delivery_status(items):
    """final only when every collected item has a recorded resolution."""
    open_items = [item for item in items if 'resolution' not in item]
    return ('draft' if open_items else 'final'), open_items


DRAFT_NOTICE = '【待复核草稿】本文件含 {count} 处待复核内容，复核通过前不得作为正式成品使用。'
