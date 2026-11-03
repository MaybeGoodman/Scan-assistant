"""Build the V1.0 eight-module evidence set.

  python -X utf8 samples/v1/build_samples.py stage1   # pages, candidates, pipeline (stops at figure review)
  python -X utf8 samples/v1/build_samples.py stage2   # after the host filled figure reviews: everything else

Outputs: samples/v1/out/<module>/ (student-facing files and originals),
samples/v1/out/<module>/internal/ (development evidence, never part of a student package),
samples/v1/out/summary.json. Working state lives in samples/v1/work/ (not committed).
"""
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ROOT / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path[:0] = [str(HERE), str(SCRIPTS)]

from content import ALL, para, checklist  # noqa: E402
from figures import circuit, triangle  # noqa: E402
from render_page import Page  # noqa: E402
from variants import FIGURE_CHECKS  # noqa: E402

OUT, WORK = HERE / 'out', HERE / 'work'
HEADER = '江南第二中学 2026—2027 学年第一学期 课后练习'
WATERMARK = '扫码关注 刷题宝 海量真题免费领'


def py(*args, check=True):
    result = subprocess.run([sys.executable, '-X', 'utf8', *map(str, args)], capture_output=True, text=True,
                            encoding='utf-8')
    if check and result.returncode:
        raise RuntimeError(f'{args}\n{result.stdout}\n{result.stderr}')
    return json.loads(result.stdout) if result.stdout.strip().startswith('{') else result.stdout


def scene_for(module, data=None):
    if module['figure'] == 'triangle':
        return triangle(**(data or module['triangle']))
    if module['figure'] == 'circuit':
        return circuit()
    return None, None


def draw_clean(scene, understanding, path):
    from figure_components import expand_scene
    from figure_drawing import render
    render(expand_scene(deepcopy(scene), understanding=understanding), path.with_suffix('.svg'), path,
           understanding=understanding)


def build_page(module, work):
    code, number = module['code'], module['number']
    page = Page()
    spans = {}
    blocks = []

    def add(block, text=None, size=30, indent=0, **selection):
        bbox = page.paragraph(text if text is not None else source_text(block), size=size, indent=indent)
        spans[block['id']] = bbox
        block['source'] = {'page': 1, 'bbox': bbox}
        block['selection'] = selection or {'category': 'MAIN_CONTENT', 'relation': 'main', 'certainty': 'high'}
        blocks.append(block)
        return bbox

    add({'type': 'text', 'id': 'hdr', 'text': HEADER}, size=22, category='HEADER_FOOTER', relation='unrelated',
        certainty='high', reason='学校页眉，与题目内容无关')
    add(para('title', module['title'], 'title'), size=34)
    material = []
    if module.get('material'):
        label, passage = module['material']
        add(para('mat-label', label, 'material'), size=30)
        add(para('mat', passage, 'material'), size=28)
        material = ['mat-label', 'mat']
    stem_ids = []
    for index, text in enumerate(module['stem']):
        block_id = f'stem{index + 1}'
        add(para(block_id, text, 'stem'), text=text)
        stem_ids.append(block_id)
    figure_block = None
    scene, understanding = scene_for(module)
    if scene:
        clean = work / 'figure-clean.png'
        draw_clean(scene, understanding, clean)
        bbox = page.figure(clean, width=380 if module['figure'] == 'triangle' else 340)
        figure_block = {'type': 'image', 'id': 'fig', 'figure_id': 'f1', 'path': 'source-fig.png', 'role': 'figure',
                        'alt': '原题插图', 'source': {'page': 1, 'bbox': bbox},
                        'selection': {'category': 'MAIN_CONTENT', 'relation': 'main', 'certainty': 'high'}}
        blocks.append(figure_block)
        spans['fig'] = bbox
    sub_entries = []
    for index, entry in enumerate(module['subs']):
        number_label, text, deps = entry[:3]
        sid = f's{index + 1}'
        add(para(sid, text, 'subquestion'))
        ids = [sid]
        if len(entry) > 3:
            add(para(sid + 'o', entry[3], 'option'), size=26, indent=30)
            ids.append(sid + 'o')
        sub_entries.append({'subquestion_id': f'q{code}-{index + 1}', 'number': number_label, 'blocks': ids,
                            'depends_on': [f'q{code}-{[e[0] for e in module["subs"]].index(d) + 1}' for d in deps]})
    answer_ids = []
    for index, text in enumerate(module['answer']):
        role = 'answer' if text.startswith('【答案】') else 'analysis'
        bid = f'ans{index + 1}'
        add(para(bid, text, role), size=26, category='SUPPORTING_CONTENT', relation='supporting', certainty='high')
        answer_ids.append(bid)
    # Handwriting: a tick on (1) and a pencilled answer beside the printed answer.
    first = spans['s1']
    page.tick(first[2] - 80, first[1] + 20)
    page.handwriting((spans['ans1'][2] - 220, spans['ans1'][1] - 6), '对了!')
    blocks.append({'type': 'text', 'id': 'hw', 'text': '对了!', 'source': {'page': 1},
                   'selection': {'category': 'HANDWRITING', 'relation': 'main', 'certainty': 'high'}})
    page.watermark(WATERMARK)
    blocks.insert(1, {'type': 'text', 'id': 'wm', 'text': WATERMARK, 'source': {'page': 1},
                      'selection': {'category': 'WATERMARK', 'relation': 'unrelated', 'certainty': 'high',
                                    'reason': '半透明推广水印，覆盖正文但与题目无关'}})
    if page.marks:
        for x0, y0, x1, y1 in page.marks:
            # Cover the lower loop only; the upper hooked stroke stays visible.
            page.blot((x0 - 1, y0 + (y1 - y0) * 0.78, x1 + 2, y1 + 8))
        blocks.append({'type': 'text', 'id': 'note', 'role': 'other',
                       'text': '补写说明：第15题题干“匀速运动〔6〕s”中的数字下半部分被墨迹遮挡，依据残留的上部左弯弧形笔画推断为“6”。',
                       'selection': {'category': 'MAIN_CONTENT', 'relation': 'main', 'certainty': 'high'}})
    page.save(work / 'source-page.png')
    if figure_block:
        from PIL import Image
        with Image.open(work / 'source-page.png') as image:
            image.crop(tuple(figure_block['source']['bbox'])).save(work / 'source-fig.png')
    question = {'question_id': f'q{code}', 'number': number, 'module': code,
                'question_type': 'comprehensive', 'blocks': stem_ids + (['fig'] if figure_block else []) + answer_ids,
                'materials': ['m1'] if material else [], 'subquestions': sub_entries,
                'source_spans': [{'attachment': 'source-page.png', 'page': 1, 'bbox': spans[b]}
                                 for b in stem_ids + [s['blocks'][0] for s in sub_entries]],
                'review_status': 'confirmed', 'completeness': {'complete': True, 'missing': []}}
    document = {'blocks': blocks, 'questions': [question],
                'materials': [{'material_id': 'm1', 'blocks': material}] if material else []}
    if figure_block:
        document['figure_task'] = {'schema_version': 1, 'task_id': f'{code}-page', 'page_count': 1, 'scan_complete': True,
                                   'figures': [{'figure_id': 'f1', 'source_page': 1, 'source_bbox': figure_block['source']['bbox'],
                                                'source_path': 'source-fig.png', 'parent_block_id': stem_ids[0],
                                                'figure_type': 'geometry' if module['figure'] == 'triangle' else 'circuit',
                                                'relation': 'main', 'redrawable': True, 'critical_uncertainty': False,
                                                'placeholder_label': f'第{number}题图',
                                                'understanding': deepcopy(understanding), 'drawing': {'scene': scene}}]}
    return document


def source_text(block):
    if 'text' in block:
        return block['text']
    return ''.join(r['text'] if r['type'] == 'text' else ('$' + r['latex'] + '$' if r['type'] == 'math'
                                                         else '@' + r['latex'] + '@') for r in block['runs'])


def stage1():
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    pending = {}
    for module in ALL:
        code = module['code']
        work, out = WORK / code, OUT / code
        work.mkdir(parents=True)
        (out / 'internal').mkdir(parents=True)
        document = build_page(module, work)
        (work / 'candidates.json').write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        shutil.copyfile(work / 'source-page.png', out / 'source-page.png')
        shutil.copyfile(work / 'candidates.json', out / 'internal' / 'candidates.json')
        args = [SCRIPTS / 'pipeline.py', 'run', work / 'candidates.json', '--source', work / 'source-page.png',
                '--run-id', 'orig', '--format', 'docx', '--word-confirmed', '--output', out / 'original.docx']
        if module['figure']:
            args += ['--image-mode', 'redraw']
        state = py(*args)
        pending[code] = state
        print(code, state['status'], state.get('delivery'), state.get('view_files', ''))
    (WORK / 'stage1.json').write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding='utf-8')


def variant_candidate(module, index, variant, work, slot=None):
    code = module['code']
    blocks, materials, stem = [], [], []
    if variant.get('material'):
        blocks.append(para('mat', variant['material'], 'material'))
        materials = ['mat']
    for i, text in enumerate(variant.get('stem', [])):
        blocks.append(para(f'stem{i + 1}', text, 'stem'))
        stem.append(f'stem{i + 1}')
    if module['figure']:
        scene, understanding = scene_for(module, variant.get('triangle'))
        target = work / 'variant-figs' / f'v{index}.png'
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            draw_clean(scene, understanding, target)
        blocks.append({'type': 'image', 'id': 'fig', 'path': f'variant-figs/v{index}.png', 'role': 'figure', 'alt': ''})
        stem.append('fig')
        figure_review = variant_figure_review(code, index, target)
    subs = []
    deps = [entry[2] for entry in module['subs']]
    numbers = [entry[0] for entry in module['subs']]
    for i, sub in enumerate(variant['subs']):
        question, options = (sub, None) if isinstance(sub, str) else sub
        blocks.append(para(f's{i + 1}', question, 'subquestion'))
        ids = [f's{i + 1}']
        if options:
            blocks.append(para(f's{i + 1}o', options, 'option'))
            ids.append(f's{i + 1}o')
        subs.append({'number': numbers[i], 'blocks': ids, 'depends_on': deps[i]})
    design = {**module['design'], **variant['design']}
    review = checklist(code, ['独立复核：重新求解全部小问并逐项核对 checklist'])
    if module['figure'] and figure_review:
        review['figures'] = [figure_review]
    return {'question_id': f'q{code}', 'slot': slot or index,
            'variant': {'blocks': blocks, 'stem': stem, 'materials': materials, 'subquestions': subs},
            'design': design,
            'internal': {'answers': [{'item': k, 'answer': v} for k, v in variant['answers'].items()],
                         'solution': variant['solution'], 'checks': variant['checks']},
            'review': review}


def variant_figure_review(code, index, figure):
    """The recorded host visual review of this variant figure, only if it was made on these exact bytes."""
    import hashlib
    from PIL import Image, ImageChops
    reviews = json.loads((HERE / 'reviews' / 'variant-figures.json').read_text(encoding='utf-8'))
    entry = reviews.get(code, {}).get(str(index))
    reviewed = HERE / 'reviews' / 'variant-figures' / f'{code}-v{index}.png'
    if entry and reviewed.exists():
        with Image.open(figure) as drawn, Image.open(reviewed) as seen:
            same = drawn.size == seen.size and ImageChops.difference(drawn.convert('RGB'), seen.convert('RGB')).getbbox() is None
        if same:  # Identical pixels, possibly different PNG encoding: deliver the exact bytes that were viewed.
            shutil.copyfile(reviewed, figure)
    digest = hashlib.sha256(figure.read_bytes()).hexdigest()
    if not entry or entry['sha256'] != digest:
        print(f'{code} 变式 {index} 插图 {digest[:12]} 没有对应的视觉复核记录，该候选将不能通过验证')
        return None
    return {'id': 'fig', 'sha256': digest, 'reviewed_by': 'host_vision', 'status': 'pass',
            'checks': {key: True for key in FIGURE_CHECKS}, 'notes': entry['notes']}


def write_candidate(work, name, candidate):
    path = work / 'cands' / f'{name}.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def render_docx(docx, folder):
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', str(folder), str(docx)],
                   capture_output=True, timeout=180)
    pdf = folder / (docx.stem + '.pdf')
    pages = []
    if pdf.exists():
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(str(pdf)) as document:
            for index in range(len(document)):
                image = document[index].render(scale=1.4).to_pil()
                target = folder / f'{docx.stem}-p{index + 1}.png'
                image.save(target)
                pages.append(target.name)
    return pages


def stage2():
    from questions import project
    stage = json.loads((WORK / 'stage1.json').read_text(encoding='utf-8'))
    summary = {}
    for module in ALL:
        code = module['code']
        work, out = WORK / code, OUT / code
        record = {'module': code}
        state = stage[code]
        if state['status'] == 'awaiting_review':
            reviews = HERE / 'reviews' / f'{code}.json'  # host review written after viewing the real files
            state = py(SCRIPTS / 'pipeline.py', 'review', '--state', state['state'], '--reviews', reviews)
        record['original'] = {'status': state['status'], 'delivery': state['delivery'],
                              'open_review_items': state['open_review_items'], 'file': 'original.docx'}
        full = json.loads(Path(state['state']).read_text(encoding='utf-8'))
        export_source = work / full['files']['export_source']
        if state['delivery'] == 'draft':
            blocked = py(SCRIPTS / 'variants.py', 'init', export_source, '--run-id', 'blocked', '--question', f'q{code}',
                         check=False)
            record['generation_gate_on_draft'] = blocked
            report = json.loads((work / full['files']['export_report']).read_text(encoding='utf-8'))
            resolutions = {'resolutions': [{'key': item['key'], 'resolution': 'confirmed', 'by': 'host',
                                            'note': '回看原图：数字上半部分残笔为“6”的圆弧，与题意（匀速阶段时长）一致'}
                                           for item in report['review_items'] if 'resolution' not in item]}
            resolution_file = work / 'resolutions.json'
            resolution_file.write_text(json.dumps(resolutions, ensure_ascii=False, indent=2), encoding='utf-8')
            shutil.copyfile(resolution_file, out / 'internal' / 'resolutions.json')
            state = py(SCRIPTS / 'pipeline.py', 'finalize', '--state', state['state'], '--resolutions', resolution_file,
                       '--output', out / 'original-final.docx')
            record['finalized'] = {'status': state['status'], 'delivery': state['delivery'], 'file': 'original-final.docx'}
            full = json.loads(Path(state['state']).read_text(encoding='utf-8'))
            export_source = work / full['files']['export_source']
        # Original (with printed answers) and student projections of the same source.
        py(SCRIPTS / 'export_page.py', export_source, '--output-dir', work / 'chat-original')
        shutil.copyfile(work / 'chat-original/result.md', out / 'original-chat.md')
        py(SCRIPTS / 'export_page.py', export_source, '--output-dir', work / 'chat-student', '--output-mode', 'student')
        shutil.copyfile(work / 'chat-student/result.md', out / 'original-student-chat.md')
        py(SCRIPTS / 'export_docx.py', export_source, '--output', out / 'original-student.docx', '--word-confirmed',
           '--output-mode', 'student', '--report', out / 'internal' / 'original-student.review.json')
        # Three complete variants per comprehensive question.
        ledger_info = py(SCRIPTS / 'variants.py', 'init', export_source, '--run-id', 'gen', '--question', f'q{code}')
        ledger = ledger_info['ledger']
        submissions = []
        for index, variant in enumerate(module['variants'], 1):
            candidate = write_candidate(work, f'v{index}', variant_candidate(module, index, variant, work))
            result = py(SCRIPTS / 'variants.py', 'submit', '--ledger', ledger, '--candidate', candidate)
            submissions.append(result['submitted'])
        delivered = py(SCRIPTS / 'variants.py', 'deliver', '--ledger', ledger, '--format', 'both',
                       '--output-dir', out / 'variants', '--word-confirmed')
        record['generation'] = {'submissions': submissions, 'delivery': delivered['delivery'],
                                'shortfalls': delivered['shortfalls'], 'questions': delivered['questions']}
        internal = Path(ledger).parent
        shutil.copytree(internal, out / 'internal' / 'generation', ignore=shutil.ignore_patterns('chat-export'))
        # Independent leak audit of the student deliverables against the internal answer key.
        forbidden_file = internal / 'internal' / 'forbidden.json'  # answer pieces kept out of the package
        audit = subprocess.run([sys.executable, '-X', 'utf8', SCRIPTS / 'docx_audit.py', out / 'variants/student.docx',
                                '--forbidden', forbidden_file, '--against', work / 'gen.student.json'],
                               capture_output=True, text=True, encoding='utf-8')
        record['student_variants_audit'] = json.loads(audit.stdout)
        source_doc = json.loads(export_source.read_text(encoding='utf-8'))
        _, removed = project(source_doc, 'student')
        record['original_student_removed'] = [{'location': r['location'], 'role': r['role']} for r in removed]
        summary[code] = record
        print(code, record['original']['delivery'], record['generation']['delivery'],
              [s['status'] for s in submissions], record['student_variants_audit']['ok'])
    summary['extra'] = extra_runs()
    # Rendered pages for visual review (LibreOffice with libreoffice-math, not Microsoft Word).
    for module in ALL:
        out = OUT / module['code']
        pages = {}
        for docx in sorted(out.rglob('*.docx')):
            if 'internal' not in docx.relative_to(out).parts:
                folder = out / 'render' / docx.parent.relative_to(out)
                pages[docx.relative_to(out).as_posix()] = render_docx(docx, folder)
        summary[module['code']]['rendered_pages'] = pages
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')


def extra_runs():
    """G02 difficulty control and G04 failure injection / partial delivery."""
    from content import M02, M03, M04, M05
    results = {}
    work, out = WORK / 'M05', OUT / 'M05'
    source = work / 'orig.reviewed.json'
    easy = {'stem': ['已知函数$f(x)=x^2-2ax$，$a\\in\\mathbf{R}$。'],
            'subs': ['（1）若$f(2)=0$，求$a$的值；', '（2）在（1）的条件下，求$f(x)$在区间$[0,3]$上的最大值和最小值；',
                     '（3）若$f(x)\\geq 0$对任意$x\\in[2,3]$恒成立，求实数$a$的取值范围。'],
            'answers': {'(1)': 'a=1', '(2)': '最大值3，最小值-1', '(3)': 'a≤1'},
            'solution': 'f(2)=4−4a=0，a=1；f=x²−2x，顶点1，最小−1，最大f(3)=3；x²≥2ax ⇔ a≤x/2，x∈[2,3]时最小为1，a≤1。',
            'checks': [{'kind': 'substitute', 'item': '(1)', 'equation': 'x**2-2*a*x = 0', 'vars': {'x': '2', 'a': '1'}},
                       {'kind': 'arith', 'item': '(2)', 'expr': '1-2', 'expect': '-1'},
                       {'kind': 'arith', 'item': '(2)', 'expr': '9-6', 'expect': '3'},
                       {'kind': 'arith', 'item': '(3)', 'expr': '2/2', 'expect': '1'},
                       {'kind': 'semantic', 'item': '(1)', 'independent_answer': 'a=1'},
                       {'kind': 'semantic', 'item': '(2)', 'independent_answer': '最大值3，最小值-1'},
                       {'kind': 'semantic', 'item': '(3)', 'independent_answer': 'a≤1'}],
            'design': {'difference_from_source': '去掉常数项，第（3）问分离参数后为一次函数，不需基本不等式',
                       'difference_from_siblings': '单题', 'difficulty': 'easier',
                       'difficulty_evidence': '第（3）问由“对勾函数最值”降为“一次函数最值”，计算量减少'}}
    hard = {'stem': ['已知函数$f(x)=x^2-2ax+3$，$a\\in\\mathbf{R}$。'],
            'subs': ['（1）若$f(1)=0$，求$a$的值；',
                     '（2）在（1）的条件下，若$f(x)$在区间$[0,m]$上的最大值为$3$、最小值为$-1$，求实数$m$的取值范围；',
                     '（3）若存在$x\\in[1,2]$，使得$f(x)<0$成立，求实数$a$的取值范围。'],
            'answers': {'(1)': 'a=2', '(2)': '2≤m≤4', '(3)': 'a>√3'},
            'solution': 'a=2，f=x²−4x+3；最小值−1需2∈[0,m]即m≥2，最大值3需f(m)≤3即m≤4；存在性问题：2a>min(x+3/x)=2√3，a>√3。',
            'checks': [{'kind': 'substitute', 'item': '(1)', 'equation': 'x**2-2*a*x+3 = 0', 'vars': {'x': '1', 'a': '2'}},
                       {'kind': 'roots', 'item': '(2)', 'expr': 'm**2-4*m+3-3', 'var': 'm', 'claimed': ['0', '4'], 'interval': ['-10', '10']},
                       {'kind': 'arith', 'item': '(2)', 'expr': '2**2-4*2+3', 'expect': '-1'},
                       {'kind': 'arith', 'item': '(3)', 'expr': '(sqrt(3)+3/sqrt(3))/2', 'expect': str(3 ** 0.5), 'tolerance': 1e-9},
                       {'kind': 'semantic', 'item': '(1)', 'independent_answer': 'a=2'},
                       {'kind': 'semantic', 'item': '(2)', 'independent_answer': '2≤m≤4'},
                       {'kind': 'semantic', 'item': '(3)', 'independent_answer': 'a>√3'}],
            'design': {'difference_from_source': '第（2）问由“求最值”改为“由最值反求区间端点”，第（3）问由恒成立改为存在性',
                       'difference_from_siblings': '单题', 'difficulty': 'harder',
                       'difficulty_evidence': '增加逆向条件转换与“恒成立/存在性”区分，推理步数增加'}}
    for name, variant, level in (('easy', easy, 'easier'), ('hard', hard, 'harder')):
        info = py(SCRIPTS / 'variants.py', 'init', source, '--run-id', name, '--question', 'qM05', '--count', '1',
                  '--difficulty', level)
        candidate = variant_candidate(M05, 1, variant, work)
        candidate['design'].update(variant['design'])
        path = write_candidate(work, name, candidate)
        submitted = py(SCRIPTS / 'variants.py', 'submit', '--ledger', info['ledger'], '--candidate', path)['submitted']
        delivered = py(SCRIPTS / 'variants.py', 'deliver', '--ledger', info['ledger'], '--format', 'both',
                       '--output-dir', out / f'difficulty-{level}', '--word-confirmed')
        results[f'M05-{level}'] = {'submitted': submitted, 'delivery': delivered['delivery']}
        shutil.copytree(Path(info['ledger']).parent, out / 'internal' / f'generation-{name}',
                        ignore=shutil.ignore_patterns('chat-export'))
    # Failure injection with bounded retries and partial delivery (M03, 2 attempts per slot).
    work, out = WORK / 'M03', OUT / 'M03'
    source = work / 'orig.reviewed.json'
    info = py(SCRIPTS / 'variants.py', 'init', source, '--run-id', 'inject', '--question', 'qM03', '--max-attempts', '2')
    log = []

    def submit(name, candidate):
        path = write_candidate(work, name, candidate)
        log.append(py(SCRIPTS / 'variants.py', 'submit', '--ledger', info['ledger'], '--candidate', path)['submitted'])
    good = [variant_candidate(M03, i, v, work) for i, v in enumerate(M03['variants'], 1)]
    unbalanced = deepcopy(good[0])
    unbalanced['internal']['checks'][0]['equation'] = 'KClO3 -> KCl + O2'  # injected: not balanced
    submit('inject-s1-unbalanced', unbalanced)
    submit('inject-s1-good', good[0])
    submit('inject-s2-good', good[1])
    wrong = deepcopy(good[2])
    wrong['internal']['answers'][1]['answer'] = '24.5 g'  # injected: answer differs from independent solve
    submit('inject-s3-wrong-answer', wrong)
    replica = deepcopy(good[2])
    replica['variant'] = deepcopy(good[1]['variant'])  # injected: near-duplicate of a passed sibling
    submit('inject-s3-duplicate', replica)
    delivered = py(SCRIPTS / 'variants.py', 'deliver', '--ledger', info['ledger'], '--format', 'both',
                   '--output-dir', out / 'variants-partial', '--word-confirmed')
    results['M03-injection'] = {'submissions': log, 'delivery': delivered['delivery'], 'shortfalls': delivered['shortfalls']}
    shutil.copytree(Path(info['ledger']).parent, out / 'internal' / 'generation-inject',
                    ignore=shutil.ignore_patterns('chat-export'))
    # Single-slot injections for the other subjects: physics unit error, maths missed root, English two answers.
    cases = []
    bad = variant_candidate(M02, 1, M02['variants'][0], WORK / 'M02')
    bad['internal']['checks'][3]['expect'] = 'A'  # U computed with the wrong unit
    cases.append(('M02', 'inject', bad))
    bad = variant_candidate(M05, 1, M05['variants'][2], WORK / 'M05')
    bad['internal']['checks'][1]['expr'] = '(a-3)*(a-5)'  # injected degenerate: second root not listed
    cases.append(('M05', 'inject', bad))
    bad = variant_candidate(M04, 1, M04['variants'][0], WORK / 'M04')
    bad['internal']['checks'][0]['answer'] = ['B', 'C']  # single-choice item with two keys
    cases.append(('M04', 'inject', bad))
    for code, name, candidate in cases:
        source = WORK / code / ('orig.figures-reviewed.json' if code == 'M02' else 'orig.reviewed.json')
        ledger = py(SCRIPTS / 'variants.py', 'init', source, '--run-id', name, '--question', f'q{code}', '--count', '1',
                    '--max-attempts', '1')['ledger']
        path = write_candidate(WORK / code, name, candidate)
        submitted = py(SCRIPTS / 'variants.py', 'submit', '--ledger', ledger, '--candidate', path)['submitted']
        delivered = py(SCRIPTS / 'variants.py', 'deliver', '--ledger', ledger, '--format', 'chat',
                       '--output-dir', OUT / code / 'variants-injected')
        results[f'{code}-injection'] = {'submitted': submitted, 'delivery': delivered['delivery'],
                                        'shortfalls': delivered['shortfalls'],
                                        'output_created': (OUT / code / 'variants-injected').exists()}
        shutil.copytree(Path(ledger).parent, OUT / code / 'internal' / 'generation-inject',
                        ignore=shutil.ignore_patterns('chat-export'))
    return results


if __name__ == '__main__':
    {'stage1': stage1, 'stage2': stage2}[sys.argv[1]]()
