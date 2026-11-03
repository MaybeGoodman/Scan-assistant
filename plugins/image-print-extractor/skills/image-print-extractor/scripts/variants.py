"""Similar-question generation ledger: init -> submit (verify) -> status -> deliver (R06–R10).

The host model writes each candidate (student-facing blocks plus internal answers,
solution and checks) as a JSON file. This script never invents or solves questions;
it enforces the contract around them:

* only confirmed, complete source questions with no open review items are used;
* every candidate keeps the source's subquestion count, order and dependencies,
  shared material and required figures, and differs from the source and its siblings;
* every subquestion is covered by an independent solve (semantic) or a rubric, all
  deterministic checks pass, and the module checklist is fully confirmed;
* a failed candidate frees its slot until the bounded retry budget is used up;
* delivery projects only verified candidates, keeps answers in a separate internal
  folder, audits the student Word file and reports any shortfall per source question.

Usage:
  variants.py init <reviewed.json> --run-id g1 --question q18 [--question q19] [--count 3]
                   [--difficulty same|easier|harder] [--max-attempts 3] [--module M05]
                   [--learner "..."] [--scope-override "..."]
  variants.py submit --ledger <ledger> --candidate <file>
  variants.py status --ledger <ledger>
  variants.py deliver --ledger <ledger> --format chat|docx|both --output-dir <dir> [--word-confirmed]
"""
import argparse
import difflib
import hashlib
import json
import re
import shutil
import sys
from copy import deepcopy
from pathlib import Path

from content_blocks import reviewed_blocks
from pdf_batches import replace_atomic, write_new
from questions import ANSWER_ROLES, glyphs, question_blocks, review_items, delivery_status, validate_questions
from subjects import DIFFICULTIES, DIFFICULTY_LABELS, describe, module
from variant_checks import DETERMINISTIC, run_check

RUN_ID = re.compile(r'[A-Za-z0-9_-]{1,32}')
DEFAULT_COUNT, DEFAULT_ATTEMPTS = 3, 3
SOURCE_REPLICA, SIBLING_DUPLICATE = 0.98, 0.95
MODULE_KINDS = {'M01': {'arith', 'substitute', 'roots'}, 'M05': {'arith', 'substitute', 'roots'},
                'M02': {'units', 'arith', 'substitute'}, 'M06': {'units', 'arith', 'substitute'},
                'M03': {'balance', 'arith'}, 'M07': {'balance', 'arith'},
                'M04': {'choice', 'evidence'}, 'M08': {'choice', 'evidence'}}
DESIGN_KEYS = ('knowledge_points', 'method', 'question_type', 'difficulty', 'difficulty_evidence',
               'difference_from_source', 'difference_from_siblings')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def norm(text):
    return re.sub(r'\s+', '', text)


def student_text(blocks):
    values = []

    def visit(item):
        for key in ('text', 'latex'):
            if isinstance(item.get(key), str):
                values.append(item[key])
        for key in ('runs', 'cells'):
            for child in item.get(key, []) or []:
                visit(child)
    for block in blocks:
        visit(block)
    return norm(''.join(values))


def ledger_path(base, run_id):
    return Path(base) / f'{run_id}-gen' / f'{run_id}.gen.json'


def source_question(document, qid):
    question = next((q for q in document.get('questions', []) or [] if q.get('question_id') == qid), None)
    if question is None:
        raise ValueError(f'源文档中没有题目 {qid}')
    return question


def gate(document, qid):
    """Reasons that stop a source question from being used for generation (R11, 4.1.5)."""
    question = source_question(document, qid)
    reasons = []
    if question.get('review_status', 'needs_review') != 'confirmed':
        reasons.append('题目结构与归属尚未确认')
    completeness = question.get('completeness') or {'complete': True}
    if completeness.get('complete') is False:
        reasons.append(f'原题不完整：{completeness.get("missing", [])}')
    # Review keys carry full-document locations, so evaluate the whole document and keep
    # the items that sit inside this question's blocks (stem, figures, materials, subquestions).
    owned = {id(block) for block in question_blocks(document, qid)}
    _, open_items = delivery_status(review_items(document))
    for item in open_items:
        match = re.match(r'blocks\[(\d+)\]', item['location'])
        if match and id(document['blocks'][int(match[1])]) in owned:
            reasons.append(f'{item["location"]}：{item["detail"]}')
    # F03: every block the question needs -- shared materials included -- must be present.
    # A missing passage is never guessed during generation.
    materials = {m.get('material_id'): m for m in document.get('materials', []) or []}
    wanted = []
    for mid in question.get('materials', []) or []:
        material_blocks = (materials.get(mid) or {}).get('blocks', []) or []
        if not material_blocks:
            reasons.append(f'共享材料 {mid} 没有任何题面块')
        wanted += [(f'共享材料 {mid}', b) for b in material_blocks]
    wanted += [(f'题目 {qid}', b) for b in question.get('blocks', []) or []]
    for sub in question.get('subquestions', []) or []:
        wanted += [(f'小问 {sub.get("subquestion_id")}', b) for b in sub.get('blocks', []) or []]
    present = {b.get('id') for b in document['blocks']}
    for owner, block_id in wanted:
        if block_id not in present:
            reasons.append(f'{owner} 引用的块 {block_id} 不在文档中（缺页、缺语篇或未处理的插图）')
    return reasons


def init(source, run_id, questions, *, count=DEFAULT_COUNT, difficulty='same', max_attempts=DEFAULT_ATTEMPTS,
         module_code=None, learner=None, scope_override=None):
    source = Path(source).resolve()
    if not RUN_ID.fullmatch(run_id or ''):
        raise ValueError('run-id 只能包含字母、数字、下划线和连字符，长度 1–32')
    if difficulty not in DIFFICULTIES:
        raise ValueError('difficulty 只能为 same、easier、harder')
    if type(count) is not int or not 1 <= count <= 10 or type(max_attempts) is not int or not 1 <= max_attempts <= 10:
        raise ValueError('count 与 max-attempts 必须是 1–10 的整数')
    if not questions or len(set(questions)) != len(questions):
        raise ValueError('至少指定一道题，且不能重复')
    document = read_json(source)
    reviewed_blocks(document)
    validate_questions(document)
    path = ledger_path(source.parent, run_id)
    if path.parent.exists():
        raise FileExistsError(f'run-id {run_id} 已使用：{path.parent}')
    targets, blocked = [], {}
    for qid in questions:
        question = source_question(document, qid)
        code = question.get('module') or module_code
        if code is None:
            raise ValueError(f'题目 {qid} 未标注模块，请用 --module 指定 M01–M08')
        module(code)
        if module_code and question.get('module') and question['module'] != module_code:
            raise ValueError(f'题目 {qid} 标注为 {question["module"]}，与 --module {module_code} 冲突，请先确认范围')
        reasons = gate(document, qid)
        if reasons:
            blocked[qid] = reasons
        targets.append({'question_id': qid, 'number': question.get('number', qid), 'module': code,
                        'subquestions': [{'number': s.get('number'), 'depends_on': [
                            [x.get('subquestion_id') for x in question['subquestions']].index(d)
                            for d in s.get('depends_on', []) or []]} for s in question.get('subquestions', []) or []],
                        'has_materials': bool(question.get('materials')),
                        'has_figures': any(b.get('type') == 'image' for b in question_blocks(document, qid)),
                        'source_text': student_text([b for b in question_blocks(document, qid)
                                                     if b.get('role') not in ANSWER_ROLES]),
                        'target': count, 'slots': {str(i): [] for i in range(1, count + 1)}})
    if blocked:
        lines = [f'{qid}：' + '；'.join(reasons) for qid, reasons in blocked.items()]
        raise ValueError('以下原题暂不能用于生成，请先补充或复核：\n' + '\n'.join(lines))
    ledger = {'schema_version': 1, 'run_id': run_id, 'base': str(source.parent),
              'source': {'file': source.name, 'sha256': sha256(source)},
              'difficulty': difficulty, 'max_attempts': max_attempts,
              'task_context': {'learner': learner, 'scope_override': scope_override,
                               'note': '仅作用于本次任务，不保存为长期档案'},
              'targets': targets, 'candidates': []}
    path.parent.mkdir(parents=True)
    (path.parent / 'candidates').mkdir()
    write_new(path, ledger)
    return status(path)


def load(path):
    path = Path(path).resolve()
    ledger = read_json(path)
    if ledger.get('schema_version') != 1 or path != ledger_path(ledger['base'], ledger['run_id']).resolve():
        raise ValueError('生成台账格式无效或位置不一致')
    source = Path(ledger['base']) / ledger['source']['file']
    if sha256(source) != ledger['source']['sha256']:
        raise ValueError('源题文件在台账建立后被修改，请用新的 run-id 重新 init')
    return path, ledger


def target_of(ledger, qid):
    target = next((t for t in ledger['targets'] if t['question_id'] == qid), None)
    if target is None:
        raise ValueError(f'台账中没有题目 {qid}')
    return target


def slot_state(ledger, target, slot):
    attempts = [c for c in ledger['candidates'] if c['question_id'] == target['question_id'] and c['slot'] == slot]
    if any(c['status'] == 'passed' for c in attempts):
        return 'passed', attempts
    if len(attempts) >= ledger['max_attempts']:
        return 'exhausted', attempts
    return 'open', attempts


FIGURE_CHECKS = {'consistent_with_text': '图中对象、数据、标注与本题题面一致',
                 'labels_complete': '作答所需的标注、刻度、连接齐全且可辨',
                 'no_answer_content': '图中没有答案、解题痕迹或答案暗示',
                 'print_legible': '黑白打印后线条与文字清楚'}


def figure_review_problem(entry, asset):
    """Why a variant figure's visual review is missing or does not bind the actual file."""
    if entry is None:
        return 'review.figures 中缺少（或重复）该图的视觉复核记录'
    if entry.get('reviewed_by') != 'host_vision' or entry.get('status') != 'pass':
        return '视觉复核必须由宿主实际看图完成（reviewed_by=host_vision）且 status=pass'
    checks = entry.get('checks')
    if not isinstance(checks, dict) or set(checks) != set(FIGURE_CHECKS) or any(v is not True for v in checks.values()):
        return f'视觉复核 checks 必须逐项为 true：{sorted(FIGURE_CHECKS)}'
    if entry.get('sha256') != asset['sha256']:
        return '视觉复核记录的 sha256 与实际 PNG 不一致（复核后图件被修改，或复核的不是这张图）'
    if 'svg_sha256' in asset and entry.get('svg_sha256') != asset['svg_sha256']:
        return '视觉复核记录的 svg_sha256 与实际 SVG 不一致'
    return None


def verify(candidate, target, ledger, siblings):
    """Return (status, results, failures) for one candidate. Pure: never writes files."""
    failures, results = [], []
    base = Path(ledger['base'])
    variant, design, internal, review = (candidate.get(k) for k in ('variant', 'design', 'internal', 'review'))
    if not all(isinstance(x, dict) for x in (variant, design, internal, review)):
        return 'failed', [], ['候选必须包含 variant、design、internal、review 四个对象'], {}
    blocks = variant.get('blocks')
    try:
        reviewed_blocks({'blocks': blocks})
    except (ValueError, KeyError, TypeError) as exc:
        return 'failed', [], [f'题面块无效：{exc}'], {}
    ids = [b.get('id') for b in blocks]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        failures.append('每个题面块都需要唯一 id')
    else:
        # F04: a generated question has no "source" to infer from. Inference brackets, XXX,
        # unresolved expressions, unclear roles or figure placeholders mean it is not verified;
        # the same gate the source question passed through applies here (R09, R11).
        try:
            open_items = review_items({'blocks': blocks})
        except ValueError as exc:
            open_items = [{'location': 'variant', 'detail': str(exc)}]
        for item in open_items:
            failures.append(f'题面含待复核内容，不能计为验证通过：{item["location"]} {item["detail"]}')

    def roles(item):
        yield item.get('role')
        for key in ('runs', 'cells'):
            for child in item.get(key, []) or []:
                yield from roles(child)
    if any(role in ANSWER_ROLES for block in blocks for role in roles(block)):
        failures.append('题面中不得包含答案、解析等答案材料；答案只写在 internal 中')
    for key in ('stem', 'materials'):
        if any(b not in ids for b in variant.get(key, []) or []):
            failures.append(f'{key} 引用了不存在的块')
    by_id = {b.get('id'): b for b in blocks}
    # F01: each block belongs to exactly one owner (stem, shared material or one subquestion).
    # Re-using another part's block must not stand in for a missing subquestion.
    owners = {}
    for key in ('stem', 'materials'):
        for block_id in variant.get(key, []) or []:
            owners.setdefault(block_id, []).append(key)
    subs = variant.get('subquestions', []) or []
    for sub in subs:
        for block_id in sub.get('blocks', []) or []:
            owners.setdefault(block_id, []).append(f'小问 {sub.get("number")}')
    for block_id, claimed in owners.items():
        if len(claimed) > 1:
            failures.append(f'块 {block_id} 被 {"、".join(claimed)} 重复引用；每个小问必须有自己的题面块，'
                            '共享内容请放入 materials')
    expected = target['subquestions']
    if len(subs) != len(expected):
        failures.append(f'小问数量 {len(subs)} 与原题 {len(expected)} 不一致')
    else:
        names = [s.get('number') for s in subs]
        for index, (sub, want) in enumerate(zip(subs, expected)):
            if sub.get('number') != want['number']:
                failures.append(f'第 {index + 1} 小问编号 {sub.get("number")} 与原题 {want["number"]} 不一致')
            deps = [names.index(d) if d in names else -1 for d in sub.get('depends_on', []) or []]
            if sorted(deps) != sorted(want['depends_on']):
                failures.append(f'小问 {sub.get("number")} 的依赖关系与原题不一致')
            if not sub.get('blocks') or any(b not in ids for b in sub['blocks']):
                failures.append(f'小问 {sub.get("number")} 缺少题面块')
            elif not any(by_id[b].get('type') != 'image' and student_text([by_id[b]]) for b in sub['blocks']):
                failures.append(f'小问 {sub.get("number")} 没有可作答的文字题面')
    if target['has_materials'] and not variant.get('materials'):
        failures.append('原题含共享材料，变式也必须提供对应材料')
    images = [b for b in blocks if b.get('type') == 'image']
    if target['has_figures'] and not images:
        failures.append('原题含必要插图，变式缺少对应插图')
    # F02: every figure is bound by hash to its own visual review and frozen at submit, so
    # a file changed after verification can never reach the student package.
    figure_reviews = review.get('figures', []) or []
    if not isinstance(figure_reviews, list) or not all(isinstance(r, dict) for r in figure_reviews):
        failures.append('review.figures 必须是对象列表')
        figure_reviews = []
    assets = []
    for image in images:
        try:
            from export_page import figure_assets
            path, svg = figure_assets(base, image)
            from figure_drawing import check_black_white
            check_black_white(path)
        except (ValueError, OSError, KeyError) as exc:
            failures.append(f'插图 {image.get("id")} 不可用：{exc}')
            continue
        asset = {'id': image.get('id'), 'path': image['path'], 'sha256': sha256(path)}
        if svg is not None:
            asset.update(svg_path=image['svg_path'], svg_sha256=sha256(svg))
        assets.append(asset)
        matching = [r for r in figure_reviews if r.get('id') == image.get('id')]
        problem = figure_review_problem(matching[0] if len(matching) == 1 else None, asset)
        if problem:
            failures.append(f'插图 {image.get("id")}：{problem}')
    for key in DESIGN_KEYS:
        if not design.get(key):
            failures.append(f'design.{key} 未填写')
    if design.get('difficulty') and design['difficulty'] != ledger['difficulty']:
        failures.append(f'难度 {design["difficulty"]} 与请求的 {ledger["difficulty"]} 不一致')
    text = student_text(blocks)
    similarity = difflib.SequenceMatcher(None, text, target['source_text']).ratio()
    if similarity >= SOURCE_REPLICA:
        failures.append(f'与原题几乎相同（相似度 {similarity:.2f}），属于原题复刻')
    sibling_scores = {}
    for sibling in siblings:
        score = difflib.SequenceMatcher(None, text, sibling['text']).ratio()
        sibling_scores[sibling['candidate_id']] = round(score, 3)
        if score >= SIBLING_DUPLICATE:
            failures.append(f'与已通过的 {sibling["candidate_id"]} 近似重复（相似度 {score:.2f}）')
    items = [s['number'] for s in expected] or ['all']
    answers = {a.get('item'): a.get('answer') for a in internal.get('answers', []) or [] if isinstance(a, dict)}
    for item in items:
        if not str(answers.get(item, '')).strip():
            failures.append(f'{item} 缺少内部答案')
    visible = glyphs(text)
    for item, answer in answers.items():
        value = glyphs(str(answer))
        if len(value) >= 3 and value in visible:
            failures.append(f'{item} 的答案出现在学生题面中')
    if not str(internal.get('solution', '')).strip():
        failures.append('internal.solution 未填写（内部求解过程）')
    context = {'student_text': text, 'answers': answers}
    checks = internal.get('checks', []) or []
    for check in checks:
        results.append(run_check(check, context))
    uncertain = False
    for result in results:
        if result['ok'] is None:
            uncertain = True
        elif not result['ok']:
            failures.append(f'{result["kind"]}（{result["item"]}）未通过：{result["detail"]}')
    for item in items:
        covered = [r for r in results if r['item'] in {item, 'all'} and r['kind'] in {'semantic', 'rubric'}]
        if not covered:
            failures.append(f'{item} 没有独立求解（semantic）或开放题标准（rubric）核验')
    kinds = {r['kind'] for r in results if r['ok']}
    if design.get('open_task'):
        if 'rubric' not in kinds:
            failures.append('开放题必须提供 rubric 核验')
    elif not kinds & MODULE_KINDS[target['module']]:
        failures.append(f'{describe(target["module"])} 需要至少一项确定性校验：{sorted(MODULE_KINDS[target["module"]])}')
    checklist = review.get('checklist')
    wanted = module(target['module'])['checklist']
    if not isinstance(checklist, dict) or set(checklist) != set(wanted):
        failures.append(f'review.checklist 必须逐项填写：{sorted(wanted)}')
    else:
        for key, value in checklist.items():
            if value is not True:
                failures.append(f'复核项未通过：{wanted[key]}')
    if not isinstance(review.get('notes'), list):
        failures.append('review.notes 必须为列表')
    record = {'similarity_to_source': round(similarity, 3), 'similarity_to_siblings': sibling_scores,
              'assets': assets}
    if failures:
        return 'failed', results, failures, record
    return ('needs_review' if uncertain else 'passed'), results, failures, record


def submit(ledger_file, candidate_file):
    path, ledger = load(ledger_file)
    candidate_file = Path(candidate_file).resolve()
    candidate = read_json(candidate_file)
    target = target_of(ledger, candidate.get('question_id'))
    slot = candidate.get('slot')
    if type(slot) is not int or str(slot) not in target['slots']:
        raise ValueError(f'slot 必须是 1–{target["target"]} 的整数')
    state, attempts = slot_state(ledger, target, slot)
    if state != 'open':
        raise ValueError(f'第 {target["number"]} 题第 {slot} 个变式位置已{"通过" if state == "passed" else "用完重试次数"}')
    attempt = len(attempts) + 1
    candidate_id = f'{target["question_id"]}-v{slot}-a{attempt}'
    stored = path.parent / 'candidates' / f'{candidate_id}.json'
    siblings = [{'candidate_id': c['candidate_id'], 'text': c['text']} for c in ledger['candidates']
                if c['question_id'] == target['question_id'] and c['status'] == 'passed']
    status_value, results, failures, record = verify(candidate, target, ledger, siblings)
    shutil.copyfile(candidate_file, stored)  # Frozen copy; delivery re-checks its hash.
    frozen_dir = path.parent / 'assets' / candidate_id
    base = Path(ledger['base'])
    for asset in record.get('assets', []):
        # Freeze the exact verified bytes; delivery uses these copies, never the editable originals.
        for key, suffix in (('path', '.png'), ('svg_path', '.svg')):
            if key not in asset:
                continue
            frozen = frozen_dir / f'{asset["id"]}{suffix}'
            frozen.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base / asset[key], frozen)
            want = asset['sha256' if key == 'path' else 'svg_sha256']
            if sha256(frozen) != want:
                shutil.rmtree(frozen_dir, ignore_errors=True)
                stored.unlink()
                raise ValueError(f'插图 {asset["id"]} 在验证期间被修改，请重新提交')
            asset['frozen' if key == 'path' else 'svg_frozen'] = frozen.relative_to(base).as_posix()
    entry = {'candidate_id': candidate_id, 'question_id': target['question_id'], 'slot': slot, 'attempt': attempt,
             'file': stored.relative_to(path.parent).as_posix(), 'sha256': sha256(stored), 'status': status_value,
             'checks': results, 'failures': failures, **record,
             'text': student_text(candidate['variant']['blocks']) if isinstance(candidate.get('variant'), dict)
             and isinstance(candidate['variant'].get('blocks'), list) else ''}
    ledger['candidates'].append(entry)
    # Refuse to overwrite a concurrent submission that landed after we read the ledger.
    if len(read_json(path)['candidates']) != len(ledger['candidates']) - 1:
        stored.unlink()
        shutil.rmtree(frozen_dir, ignore_errors=True)
        raise ValueError('台账在本次提交期间被其他调用修改，请重新运行 submit')
    replace_atomic(path, ledger)
    result = status(path)
    result['submitted'] = {k: entry[k] for k in ('candidate_id', 'status', 'failures')}
    return result


def summary_line(target, passed):
    missing = target['target'] - passed
    line = f'第{target["number"]}题目标 {target["target"]} 道，验证通过 {passed} 道'
    return line + (f'，缺 {missing} 道' if missing else '')


def status(ledger_file):
    path, ledger = load(ledger_file)
    rows, waiting = [], []
    for target in ledger['targets']:
        slots = {}
        for slot in range(1, target['target'] + 1):
            state, attempts = slot_state(ledger, target, slot)
            slots[slot] = state
            if state == 'open':
                waiting.append({'question_id': target['question_id'], 'slot': slot,
                                'attempts_left': ledger['max_attempts'] - len(attempts),
                                'last_failures': attempts[-1]['failures'] if attempts else []})
        passed = sum(1 for s in slots.values() if s == 'passed')
        rows.append({'question_id': target['question_id'], 'number': target['number'], 'module': target['module'],
                     'target': target['target'], 'passed': passed,
                     'exhausted': sum(1 for s in slots.values() if s == 'exhausted'),
                     'summary': summary_line(target, passed)})
    if waiting:
        run_status = 'awaiting_candidates'
        action = ('为以下位置各写一份候选（只替换失败的变式，保持题组一致）后运行 variants.py submit：'
                  + '；'.join(f'{w["question_id"]} 第{w["slot"]}道（剩余 {w["attempts_left"]} 次）' for w in waiting))
    else:
        run_status = 'ready_to_deliver'
        action = '运行 variants.py deliver 交付；' + '；'.join(r['summary'] for r in rows)
    return {'status': run_status, 'ledger': str(path), 'difficulty': DIFFICULTY_LABELS[ledger['difficulty']],
            'questions': rows, 'waiting': waiting, 'next_action': action}


def frozen_figure(base, entry, asset):
    """Paths of the frozen, verified copy of one figure; refuses any changed or unbound file (F02)."""
    name = entry['candidate_id']
    if not asset or 'frozen' not in asset:
        raise ValueError(f'候选 {name} 的插图没有在提交时冻结并绑定哈希（可能来自旧台账），请用新的 run-id 重新生成')
    pairs = [('frozen', 'path', 'sha256')] + ([('svg_frozen', 'svg_path', 'svg_sha256')] if 'svg_frozen' in asset else [])
    for frozen, original, digest in pairs:
        if sha256(base / asset[frozen]) != asset[digest]:
            raise ValueError(f'候选 {name} 的插图 {asset["id"]} 冻结副本在验证后被修改，不能交付')
        current = base / asset[original]
        if not current.is_file() or sha256(current) != asset[digest]:
            raise ValueError(f'候选 {name} 的插图 {asset["id"]}（{asset[original]}）在验证后被修改或删除，'
                             '原验证失效，不能交付；请修正后重新提交该变式')
    return {'path': asset['frozen'], **({'svg_path': asset['svg_frozen']} if 'svg_frozen' in asset else {})}


def deliver(ledger_file, fmt, output_dir, *, word_confirmed=False):
    path, ledger = load(ledger_file)
    if fmt not in {'chat', 'docx', 'both'}:
        raise ValueError('format 只能为 chat、docx 或 both')
    if fmt != 'chat' and word_confirmed is not True:
        raise ValueError('生成 Word 前必须已得到用户确认，并传入 --word-confirmed')
    current = status(path)
    if current['status'] != 'ready_to_deliver':
        raise ValueError('仍有可重试的变式位置未处理：' + current['next_action'])
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError('输出目录必须为新目录或空目录')
    base = Path(ledger['base'])
    if output_dir == base or output_dir.is_relative_to(path.parent):
        raise ValueError('学生成品目录不能是源目录或生成台账目录（内部记录不得混入学生包）')
    blocks, key_lines, forbidden, shortfalls, delivered = [], [], [], [], {}
    for target in ledger['targets']:
        passed = sorted((c for c in ledger['candidates']
                         if c['question_id'] == target['question_id'] and c['status'] == 'passed'),
                        key=lambda c: c['slot'])
        delivered[target['question_id']] = [c['candidate_id'] for c in passed]
        if len(passed) < target['target']:
            shortfalls.append(summary_line(target, len(passed)))
        if not passed:
            continue
        blocks.append({'type': 'text', 'id': f'{target["question_id"]}-title', 'role': 'title',
                       'text': f'第{target["number"]}题 同类练习', 'layout': {'keep_with_next': True}})
        key_lines.append(f'## 第{target["number"]}题 同类练习（{describe(target["module"])}）')
        for index, entry in enumerate(passed, 1):
            stored = path.parent / entry['file']
            if sha256(stored) != entry['sha256']:
                raise ValueError(f'候选 {entry["candidate_id"]} 在验证后被修改，不能交付')
            candidate = read_json(stored)
            prefix = f'{target["question_id"]}-{index}-'
            blocks.append({'type': 'text', 'id': prefix + 'label', 'role': 'title', 'text': f'同类题 {index}',
                           'layout': {'keep_with_next': True}})
            variant_blocks = candidate['variant']['blocks']
            assets = {a['id']: a for a in entry.get('assets', [])}
            for position, block in enumerate(variant_blocks):
                block = deepcopy(block)
                if block.get('type') == 'image':
                    block.update(frozen_figure(base, entry, assets.get(block.get('id'))))
                block['id'] = prefix + block['id']
                following = variant_blocks[position + 1] if position + 1 < len(variant_blocks) else None
                # Keep a stem with its figure and a subquestion with its options on one page.
                if following and (block.get('role') in {'stem', 'material'} and following.get('type') == 'image'
                                  or block.get('role') == 'subquestion' and following.get('role') == 'option'):
                    block.setdefault('layout', {})['keep_with_next'] = True
                blocks.append(block)
            key_lines.append(f'### 同类题 {index}（{entry["candidate_id"]}）')
            for answer in candidate['internal']['answers']:
                key_lines.append(f'- {answer["item"]}：{answer["answer"]}')
                forbidden.append(str(answer['answer']))
            key_lines.append('')
            key_lines.append('内部求解：' + candidate['internal']['solution'])
            key_lines.append('')
            forbidden.append(candidate['internal']['solution'])
    if not blocks:
        return {'status': 'completed', 'delivery': 'blocked', 'shortfalls': shortfalls,
                'next_action': '没有通过验证的变式可交付；' + '；'.join(shortfalls)}
    internal = path.parent / 'internal'
    internal.mkdir(exist_ok=True)
    student_doc = base / f'{ledger["run_id"]}.student.json'
    if student_doc.exists():
        raise FileExistsError(f'{student_doc} 已存在；每个 run 只交付一次')
    write_new(student_doc, {'blocks': blocks, 'output_mode': 'student'})
    from questions import forbidden_strings, glyphs
    # Each candidate's own answers were already checked against its own text in verify().
    # Across the package, a piece that is given data in another variant (e.g. one variant's
    # answer "BC=16" is another's condition) is not a leak; every other piece must stay out.
    given = glyphs(student_text(blocks))
    forbidden = [value for value in forbidden_strings([], forbidden) if glyphs(value) not in given]
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {'status': 'completed', 'files': {}, 'questions': current['questions'], 'delivered': delivered}
    delivery = 'final'
    from export_page import export_result
    chat_dir = internal / 'chat-export'
    page = export_result(student_doc, chat_dir, output_mode='student')
    chat = output_dir / 'student-chat.md'
    shutil.copyfile(page['markdown'], chat)
    result['files']['chat'] = str(chat)
    if page['delivery'] != 'final':
        delivery = 'draft'
    text = glyphs(chat.read_text(encoding='utf-8').replace('\\', ''))
    leaked = [value for value in forbidden if glyphs(value) in text]
    if leaked:
        chat.unlink()
        raise ValueError('学生聊天文本含内部答案，已撤回：' + '；'.join(v[:20] for v in leaked[:5]))
    (internal / 'forbidden.json').write_text(json.dumps(forbidden, ensure_ascii=False, indent=2), encoding='utf-8')
    if (chat_dir / 'figures').is_dir():
        shutil.copytree(chat_dir / 'figures', output_dir / 'figures')
    if fmt in {'docx', 'both'}:
        from export_docx import export_docx
        from docx_audit import consistency
        word = output_dir / 'student.docx'
        report = internal / 'student.word.review.json'
        export_docx(student_doc, word, word_confirmed=True, report_path=report, output_mode='student',
                    forbidden=forbidden)
        check = consistency(word, read_json(student_doc), source=student_doc)
        if not check['ok']:
            word.unlink()
            raise ValueError('Word 与聊天内容不一致：' + '；'.join(check['problems']))
        if read_json(report)['delivery'] != 'final':
            delivery = 'draft'
        result['files']['docx'] = str(word)
    if fmt == 'docx':
        chat.unlink()
        result['files'].pop('chat')
        shutil.rmtree(output_dir / 'figures', ignore_errors=True)
    (internal / 'answer-key.md').write_text('\n'.join(key_lines) + '\n', encoding='utf-8')
    if delivery == 'final' and shortfalls:
        delivery = 'partial'
    if delivery == 'draft':
        head = '学生文件为带标记的待复核草稿，不是正式成品；复核导出报告中的待复核项后再交付'
    else:
        head = '交付学生文件；' + ('；'.join(shortfalls) if shortfalls else '全部达到目标数量')
    result.update(delivery=delivery, shortfalls=shortfalls, internal=str(internal),
                  next_action=head + '。答案与验证记录在 internal 目录，不随学生文件交付')
    return result


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init')
    p.add_argument('source')
    p.add_argument('--run-id', required=True)
    p.add_argument('--question', action='append', required=True)
    p.add_argument('--count', type=int, default=DEFAULT_COUNT)
    p.add_argument('--difficulty', choices=DIFFICULTIES, default='same')
    p.add_argument('--max-attempts', type=int, default=DEFAULT_ATTEMPTS)
    p.add_argument('--module')
    p.add_argument('--learner', help='Temporary learner notes for this task only')
    p.add_argument('--scope-override', help='Temporary textbook/progress range for this task only')
    p = sub.add_parser('submit')
    p.add_argument('--ledger', required=True)
    p.add_argument('--candidate', required=True)
    p = sub.add_parser('status')
    p.add_argument('--ledger', required=True)
    p = sub.add_parser('deliver')
    p.add_argument('--ledger', required=True)
    p.add_argument('--format', choices=['chat', 'docx', 'both'], required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--word-confirmed', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            result = init(args.source, args.run_id, args.question, count=args.count, difficulty=args.difficulty,
                          max_attempts=args.max_attempts, module_code=args.module, learner=args.learner,
                          scope_override=args.scope_override)
        elif args.command == 'submit':
            result = submit(args.ledger, args.candidate)
        elif args.command == 'status':
            result = status(args.ledger)
        else:
            result = deliver(args.ledger, args.format, args.output_dir, word_confirmed=args.word_confirmed)
    except Exception as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
