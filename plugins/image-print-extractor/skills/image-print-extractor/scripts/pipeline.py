"""Thin orchestration of selection, figure workflow and export.

It only calls the existing functions in order and manages file names. Every safety gate
(semantic selection rules, hash-bound visual review, retry limit, export refusal of
unfinished tasks) stays inside those functions. It stops wherever host vision is needed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from select_content import CATEGORIES, SCOPES, select_file
from figure_drawing import CHECKS
from figure_workflow import FALLBACKS, complete, fallback_choice, generate, local_path, plan, review_template, text_document
from pdf_batches import load as load_progress, replace_atomic, status as batch_status, write_new

RUN_ID = re.compile(r'[A-Za-z0-9_-]{1,32}')
FORMATS = ('html', 'docx')
MODES = ('ignore', 'preserve', 'redraw')
MAX_UNBATCHED_PAGES = 5
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff'}
FIGURE_FILE_KEYS = {'understanding', 'redrawable', 'critical_uncertainty', 'simple_schematic',
                    'placeholder_label', 'drawing'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def rel(base, path):
    return Path(path).resolve().relative_to(base).as_posix()


class Run:
    """File layout and state for one run id; all outputs are created exclusively."""

    def __init__(self, base, run_id):
        self.base, self.id = Path(base).resolve(), run_id
        self.work = self.base / f'{run_id}-work'
        self.state_path = self.work / f'{run_id}.state.json'

    def at(self, name):
        return self.base / f'{self.id}.{name}'

    def inwork(self, name):
        return self.work / f'{self.id}.{name}'

    def images(self):
        return self.base / f'{self.id}-images'

    def save(self, state):
        if self.state_path.exists():
            replace_atomic(self.state_path, state)
        else:
            write_new(self.state_path, state)


def load_run(state_path):
    state_path = Path(state_path).resolve()
    state = read_json(state_path)
    if state.get('schema_version') != 1:
        raise ValueError('流水线状态文件格式无效')
    run = Run(state['base'], state['run_id'])
    if run.state_path != state_path:
        raise ValueError('状态文件位置与记录不一致')
    candidates = run.base / state['inputs']['candidates']
    if sha256(candidates) != state['inputs']['candidates_sha256']:
        raise ValueError('candidates.json 在本次运行开始后被修改，请用新的 run-id 从 run 重新开始')
    return run, state


def pdf_page_count(path):
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise ValueError('检查 PDF 页数需要 pypdfium2，请先安装技能目录下的 requirements.txt') from exc
    with pdfium.PdfDocument(str(path)) as pdf:
        return len(pdf)


def check_source(document, source, base):
    """Long PDFs must arrive through a complete pdf_batches run; this checks provenance, not content."""
    if source is None:
        raise ValueError('必须用 --source 指定本次处理的原始附件（PDF 或图片）')
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError(f'--source 不是文件：{source}')
    digest, suffix = sha256(source), source.suffix.lower()
    provenance = document.get('provenance')
    if suffix in IMAGE_SUFFIXES:
        if provenance is not None:
            raise ValueError('candidates.json 的 provenance 来自 PDF 分批，但 --source 是图片')
        return {'source': str(source), 'source_sha256': digest}
    if suffix != '.pdf':
        raise ValueError(f'--source 只支持 PDF 或图片：{source.name}')
    pages = pdf_page_count(source)
    if provenance is None:
        if pages > MAX_UNBATCHED_PAGES:
            raise ValueError(f'该 PDF 共 {pages} 页，须先用 pdf_batches.py 分批处理并 merge 后再运行 pipeline')
        return {'source': str(source), 'source_sha256': digest, 'source_page_count': pages}
    if not isinstance(provenance, dict) or provenance.get('tool') != 'pdf_batches' or provenance.get('schema_version') != 1:
        raise ValueError('candidates.json 的 provenance 格式无效')
    if provenance.get('source_sha256') != digest:
        raise ValueError('candidates.json 不是由这份 PDF 分批得到的（源文件哈希不一致）')
    if provenance.get('source_page_count') != pages:
        raise ValueError('candidates.json 记录的总页数与 PDF 不一致')
    progress = local_path(base, provenance.get('progress', ''))
    if not progress.is_file() or sha256(progress) != provenance.get('progress_sha256'):
        raise ValueError(f'进度文件缺失或在合并后被修改：{provenance.get("progress")}')
    ledger = load_progress(progress)
    unfinished = [b['batch'] for b in ledger['batches'] if b['status'] != 'done']
    if unfinished:
        raise ValueError(f'进度文件中仍有未完成批次：{unfinished}')
    if ledger.get('source_sha256') != digest or ledger.get('selected_pages') != provenance.get('selected_pages'):
        raise ValueError('进度文件与 candidates.json 的源文件或所选页不一致')
    return {'source': str(source), 'source_sha256': digest, 'source_page_count': pages,
            'progress': rel(base, progress), 'selected_pages': provenance['selected_pages']}


def inline_figure_files(document, base):
    """Copy per-figure files into the figure source, so later steps see the 0.6.0 structure."""
    task = document.get('figure_task')
    records = {}
    for figure in (task or {}).get('figures', []):
        if not isinstance(figure, dict) or 'figure_file' not in figure:
            continue
        fid = figure.get('figure_id')
        path = local_path(base, figure.pop('figure_file'))
        data = read_json(path)
        if not isinstance(data, dict) or not data or set(data) - FIGURE_FILE_KEYS:
            raise ValueError(f'插图 {fid} 的 figure_file 只能包含 {sorted(FIGURE_FILE_KEYS)}')
        both = sorted(set(data) & set(figure))
        if both:
            raise ValueError(f'插图 {fid} 的字段 {both} 同时出现在 candidates.json 和 figure_file 中')
        figure.update(data)
        records[fid] = {'path': rel(base, path), 'sha256': sha256(path)}
    return document, records


def reconcile_figures(document):
    """Drop figure entries whose image block selection already removed; nothing is redrawn for them."""
    task = document.get('figure_task')
    if not isinstance(task, dict) or not isinstance(task.get('figures'), list):
        return document, []
    present = {b.get('figure_id') for b in document['blocks'] if b.get('type') == 'image'}
    removed = [f.get('figure_id') for f in task['figures'] if f.get('figure_id') not in present]
    task['figures'] = [f for f in task['figures'] if f.get('figure_id') in present]
    return document, removed


def export_result(run, state, source):
    options = state['options']
    output = Path(options['output']).resolve()
    if options['format'] == 'html':
        from export_page import export
        export(source, output)
    else:
        from export_docx import export_docx
        export_docx(source, output, word_confirmed=options['word_confirmed'] is True,
                    report_path=run.inwork('word.review.json'))
    state.update(status='completed', output=str(output),
                 next_action='交付 output；如有失败插图，只简短说明对应位置无法可靠重绘')
    return state


def awaiting(state, run, ledger, attempt):
    template = run.inwork(f'reviews{attempt}.template.json')
    write_new(template, review_template(ledger))
    filled = run.inwork(f'reviews{attempt}.json')
    rows = read_json(template)['reviews']
    state.update(status='awaiting_review', attempt=attempt,
                 view_files=[row['view_files'] for row in rows])
    state['files'].update(ledger=rel(run.base, run.inwork(f'attempt{attempt}.json')),
                          review_template=rel(run.base, template), reviews=rel(run.base, filled))
    state['next_action'] = (f'逐图查看 view_files 中的原图、PNG 和 SVG，按实际比较结果填写模板中的 status 和全部 checks，'
                            f'另存为 {rel(run.base, filled)}，然后运行 pipeline.py review')
    return state


def finish_figures(run, state, result, ledger, attempt):
    figures_output = run.at('figures-reviewed.json')
    write_new(figures_output, result)
    state['files']['figures_reviewed'] = rel(run.base, figures_output)
    processing = result.get('figure_processing', {})
    state['failed_figures'] = processing.get('failed_figures', [])
    for key in ('skipped_photos', 'fallback_figures', 'fallback_errors'):
        if processing.get(key):
            state[key] = processing[key]
    state.pop('view_files', None)
    return export_result(run, state, figures_output)


def run_command(candidates, run_id, *, source, scope='main', preserve=(), include_handwriting=False,
                image_mode=None, image_fallback=None, fmt='html', word_confirmed=False, font=None, output):
    candidates = Path(candidates).resolve()
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError('run-id 只能包含字母、数字、下划线和连字符，长度 1–32')
    if fmt not in FORMATS:
        raise ValueError('format 只能为 html 或 docx')
    if fmt == 'docx' and word_confirmed is not True:
        raise ValueError('生成 Word 前必须已得到用户确认，并传入 --word-confirmed')
    if fmt == 'docx' and Path(output).suffix.lower() != '.docx':
        raise ValueError('docx 模式的 --output 必须以 .docx 结尾')
    if image_mode not in (None, *MODES):
        raise ValueError('未知的 image-mode')
    if image_fallback is not None:
        fallback_choice(image_mode, image_fallback)
    if scope not in SCOPES or not set(preserve) <= CATEGORIES:
        raise ValueError('未知的 scope 或 preserve 类别')
    run = Run(candidates.parent, run_id)
    used = [p for p in (run.work, run.at('reviewed.json'), run.images()) if p.exists()]
    if used:
        raise FileExistsError(f'run-id {run_id} 已在该目录使用过：{used[0]}，请换一个 run-id')
    document = read_json(candidates)
    if 'figure_task' in document and image_mode is None:
        raise ValueError('候选含插图任务，必须传 --image-mode，且取值来自用户的实际选择')
    origin = check_source(document, source, run.base)
    state = {'schema_version': 1, 'run_id': run_id, 'base': str(run.base),
             'options': {'scope': scope, 'preserve': sorted(set(preserve)),
                         'include_handwriting': include_handwriting, 'image_mode': image_mode,
                         'image_fallback': image_fallback,
                         'format': fmt, 'word_confirmed': word_confirmed is True, 'font': font,
                         'output': str(Path(output).resolve())},
             'inputs': {'candidates': rel(run.base, candidates), 'candidates_sha256': sha256(candidates), **origin},
             'status': 'running', 'step': 'select', 'attempt': 0, 'files': {}}
    run.work.mkdir(parents=True)
    run.save(state)
    return guarded(run, state, lambda: _run(run, state, candidates))


def _run(run, state, candidates):
    options = state['options']
    reviewed = run.at('reviewed.json')
    report = run.inwork('selection.review.json')
    select_file(candidates, reviewed, report, scope=options['scope'], preserve=options['preserve'],
                include_handwriting=options['include_handwriting'])
    state['files'].update(reviewed=rel(run.base, reviewed), selection_report=rel(run.base, report))
    state['selection_needs_review'] = read_json(report)['needs_review']
    document = read_json(reviewed)
    if 'figure_task' not in document:
        state['step'] = 'export'
        return export_result(run, state, reviewed)
    document, removed = reconcile_figures(document)
    state['figures_removed_by_selection'] = removed
    document, figure_files = inline_figure_files(document, run.base)
    if figure_files:
        state['files']['figure_files'] = figure_files
    source = run.at('figure-source.json')
    write_new(source, document)
    state['files']['figure_source'] = rel(run.base, source)
    state['step'] = 'figures'
    decision = plan(document, mode=options['image_mode'])
    text_output = run.at('text-reviewed.json')
    write_new(text_output, text_document(document))
    state['files']['text_reviewed'] = rel(run.base, text_output)
    state['uncertain_figures'] = decision.get('uncertain_figures', [])
    ledger = generate(document, run.base, run.images(), mode=options['image_mode'], font_path=options['font'],
                      image_fallback=options.get('image_fallback'))
    write_new(run.inwork('attempt1.json'), ledger)
    if any(r['state'] == 'awaiting_validation' for r in ledger['records']):
        return awaiting(state, run, ledger, 1)
    result, ledger = complete(ledger, [], run.base)
    write_new(run.inwork('reviewed1.json'), ledger)
    state['attempt'] = 1
    state['step'] = 'export'
    return finish_figures(run, state, result, ledger, 1)


def check_filled(reviews):
    """Refuse unfilled rows up front: complete() would otherwise record them as permanent failures."""
    rows = reviews.get('reviews') if isinstance(reviews, dict) else reviews
    if not isinstance(rows, list) or not rows:
        raise ValueError('复核文件必须包含非空的 reviews 列表')
    for row in rows:
        fid = row.get('figure_id') if isinstance(row, dict) else None
        if row.get('status') not in {'pass', 'minor_issue', 'major_issue', 'unreliable'}:
            raise ValueError(f'插图 {fid} 的 status 未填写或无效；请看图后填写 pass/minor_issue/major_issue/unreliable')
        checks = row.get('checks')
        if not isinstance(checks, dict) or set(checks) != set(CHECKS) or any(type(v) is not bool for v in checks.values()):
            raise ValueError(f'插图 {fid} 的 checks 必须对全部 {len(CHECKS)} 项逐一填写 true/false')
        if not isinstance(row.get('notes'), list):
            raise ValueError(f'插图 {fid} 的 notes 必须为列表')


def review_command(state_path, reviews_path):
    run, state = load_run(state_path)
    if state['status'] != 'awaiting_review':
        raise ValueError(f'当前状态为 {state["status"]}，不能执行 review')
    return guarded(run, state, lambda: _review(run, state, Path(reviews_path).resolve()), resumable=True)


def _review(run, state, reviews_path):
    attempt = state['attempt']
    template = run.base / state['files']['review_template']
    if reviews_path == template.resolve():
        raise ValueError('不得直接提交模板文件；请填写后另存为新文件')
    reviews = read_json(reviews_path)
    check_filled(reviews)
    ledger = read_json(run.base / state['files']['ledger'])
    result, ledger = complete(ledger, reviews, run.base)
    if ledger['status'] == 'awaiting_validation':
        state['missing_reviews'] = ledger['pending_reviews']
        state['next_action'] = f'复核缺少以下插图：{ledger["pending_reviews"]}；补齐后重新运行 pipeline.py review'
        return state
    state.pop('missing_reviews', None)
    reviewed_ledger = run.inwork(f'reviewed{attempt}.json')
    write_new(reviewed_ledger, ledger)
    state['files']['reviewed_ledger'] = rel(run.base, reviewed_ledger)
    if ledger['status'] == 'needs_retry':
        state.update(status='needs_retry', needs_retry=ledger['needs_retry'])
        state['next_action'] = (f'为插图 {ledger["needs_retry"]} 各写一个只含 {{"drawing": ...}} 的新文件（放在 candidates.json 目录内），'
                                '不改 understanding、来源、关联和正文，然后运行 pipeline.py retry --drawing <figure_id>=<文件>'
                                '（每张图一个 --drawing）')
        return state
    state['step'] = 'export'
    state.pop('needs_retry', None)
    return finish_figures(run, state, result, ledger, attempt)


def retry_command(state_path, source=None, drawings=None):
    run, state = load_run(state_path)
    if state['status'] != 'needs_retry':
        raise ValueError(f'当前状态为 {state["status"]}，不能执行 retry')
    if (source is None) == (not drawings):
        raise ValueError('retry 需要 --source 或 --drawing 二选一')
    if source is not None:
        return guarded(run, state, lambda: _retry(run, state, Path(source).resolve()), resumable=True)
    return guarded(run, state, lambda: _retry(run, state, patch_drawings(run, state, drawings)), resumable=True)


def parse_drawings(values):
    drawings = {}
    for value in values:
        fid, sep, path = value.partition('=')
        if not sep or not fid or not path:
            raise ValueError(f'--drawing 格式应为 <figure_id>=<文件>：{value}')
        if fid in drawings:
            raise ValueError(f'插图 {fid} 重复提供 --drawing')
        drawings[fid] = path
    return drawings


def patch_drawings(run, state, drawings):
    """Replace only the drawing of figures that need a retry; generate() still rejects other changes."""
    wanted = set(state.get('needs_retry', []))
    extra, missing = sorted(set(drawings) - wanted), sorted(wanted - set(drawings))
    if extra:
        raise ValueError(f'插图 {extra} 不在 needs_retry 中，不能替换')
    if missing:
        raise ValueError(f'needs_retry 中的插图 {missing} 未提供 --drawing')
    document = read_json(run.base / state['files']['figure_source'])
    figures = {f['figure_id']: f for f in document['figure_task']['figures']}
    for fid, path in drawings.items():
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(run.base):
            raise ValueError(f'--drawing 文件必须位于 candidates.json 所在目录内：{path}')
        data = read_json(resolved)
        if not isinstance(data, dict) or set(data) != {'drawing'} or not isinstance(data['drawing'], dict):
            raise ValueError(f'{path} 只能包含 {{"drawing": {{...}}}}')
        figures[fid]['drawing'] = data['drawing']
    target = run.at(f'figure-source.a{state["attempt"] + 1}.json')
    write_new(target, document)
    return target.resolve()


def resume(directory):
    """Read-only overview of runs and PDF batches below a work directory, for continuing after an interruption."""
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError(f'不是目录：{directory}')
    runs, batches = [], []
    for path in sorted({*directory.glob('*-work/*.state.json'), *directory.glob('*/*-work/*.state.json')}):
        try:
            state = read_json(path)
            row = {'run_id': state['run_id'], 'status': state['status'], 'next_action': state.get('next_action'),
                   'state': str(path)}
            for key in ('needs_retry', 'missing_reviews', 'error'):
                if key in state:
                    row[key] = state[key]
            runs.append(row)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            runs.append({'state': str(path), 'error': f'无法读取：{exc}'})
    for path in sorted({*directory.glob('progress.json'), *directory.glob('*/progress.json')}):
        try:
            info = batch_status(path)
            batches.append({'progress': str(path), 'done_pages': info['done_pages'], 'total_pages': info['total_pages'],
                            'complete': info['complete'], 'next_batch': info['next_batch']})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            batches.append({'progress': str(path), 'error': f'无法读取：{exc}'})
    runs.sort(key=lambda row: row.get('status') == 'completed')
    return {'runs': runs, 'batches': batches}


def _retry(run, state, source):
    if source.parent != run.base:
        raise ValueError('修正后的源文件必须与 candidates.json 位于同一目录，以保持图片相对路径')
    previous = read_json(run.base / state['files']['reviewed_ledger'])
    document = read_json(source)
    attempt = state['attempt'] + 1
    # generate() enforces: same task, mode and text; unchanged understanding/association; retry limit.
    ledger = generate(document, run.base, run.images(), mode=state['options']['image_mode'],
                      previous=previous, font_path=state['options']['font'],
                      image_fallback=state['options'].get('image_fallback'))
    write_new(run.inwork(f'attempt{attempt}.json'), ledger)
    state['files']['figure_source'] = rel(run.base, source)
    state.pop('needs_retry', None)
    if any(r['state'] == 'awaiting_validation' for r in ledger['records']):
        return awaiting(state, run, ledger, attempt)
    result, ledger = complete(ledger, [], run.base)
    write_new(run.inwork(f'reviewed{attempt}.json'), ledger)
    state['attempt'] = attempt
    return finish_figures(run, state, result, ledger, attempt)


def guarded(run, state, action, *, resumable=False):
    """Record failures in the state file. review/retry failures keep the resumable status."""
    snapshot = json.loads(json.dumps(state))
    try:
        state = action()
    except Exception as exc:
        failed = snapshot if resumable else state
        failed['error'] = {'step': failed.get('step'), 'message': str(exc)}
        if not resumable:
            failed.update(status='error', next_action='按 error 信息修复输入后，用新的 run-id 重新运行 pipeline.py run')
        run.save(failed)
        raise
    state.pop('error', None)
    run.save(state)
    return state


def summary(state):
    keys = ('status', 'run_id', 'next_action', 'output', 'view_files', 'needs_retry', 'missing_reviews',
            'failed_figures', 'skipped_photos', 'fallback_figures', 'fallback_errors',
            'figures_removed_by_selection', 'uncertain_figures', 'selection_needs_review', 'error')
    result = {k: state[k] for k in keys if k in state}
    result['state'] = str(Path(state['base']) / f'{state["run_id"]}-work' / f'{state["run_id"]}.state.json')
    return result


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('run')
    p.add_argument('candidates')
    p.add_argument('--source', required=True, help='Original attachment (PDF or image) the candidates came from')
    p.add_argument('--run-id', required=True)
    p.add_argument('--scope', choices=sorted(SCOPES), default='main')
    p.add_argument('--preserve', action='append', choices=sorted(CATEGORIES), default=[])
    p.add_argument('--include-handwriting', action='store_true')
    p.add_argument('--image-mode', choices=MODES)
    p.add_argument('--image-fallback', choices=FALLBACKS,
                   help='redraw only: keep the original crop for failed figures and photos (original)')
    p.add_argument('--format', choices=FORMATS, required=True)
    p.add_argument('--word-confirmed', action='store_true', help='Use only after the user explicitly chose Word')
    p.add_argument('--font', help='Font supporting figure labels')
    p.add_argument('--output', required=True, help='HTML output directory or .docx file')
    p = sub.add_parser('review')
    p.add_argument('--state', required=True)
    p.add_argument('--reviews', required=True)
    p = sub.add_parser('retry')
    p.add_argument('--state', required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--source', help='Corrected copy of the whole figure source (0.6.0 style)')
    group.add_argument('--drawing', action='append', help='<figure_id>=<file with {"drawing": ...}>; repeatable')
    p = sub.add_parser('resume')
    p.add_argument('directory')
    p = sub.add_parser('status')
    p.add_argument('--state', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'run':
            state = run_command(args.candidates, args.run_id, source=args.source, scope=args.scope, preserve=args.preserve,
                                include_handwriting=args.include_handwriting, image_mode=args.image_mode,
                                image_fallback=args.image_fallback,
                                fmt=args.format, word_confirmed=args.word_confirmed, font=args.font,
                                output=args.output)
        elif args.command == 'review':
            state = review_command(args.state, args.reviews)
        elif args.command == 'retry':
            state = retry_command(args.state, args.source, parse_drawings(args.drawing) if args.drawing else None)
        elif args.command == 'resume':
            print(json.dumps(resume(args.directory), ensure_ascii=False, indent=2))
            return
        else:
            state = read_json(args.state)
    except Exception as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(summary(state), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
