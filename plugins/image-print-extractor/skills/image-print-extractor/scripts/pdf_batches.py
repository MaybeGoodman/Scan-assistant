"""Batch progress ledger for long PDFs: split pages, register host results, merge in page order.

This only organizes host-reviewed JSON; it performs no OCR, classification or text repair.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

MAX_BATCH_SIZE = 20
TASK_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def replace_atomic(path, value):
    """The progress ledger is state, so it alone is updated in place via a fresh temporary file."""
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def inside(base, path):
    base, path = Path(base).resolve(), Path(path).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f'文件必须位于进度文件目录内：{path}')
    return path.relative_to(base).as_posix()


def init(manifest, progress, *, batch_size=5, task_id='current-file'):
    manifest, progress = Path(manifest).resolve(), Path(progress).resolve()
    if progress.exists():
        raise FileExistsError(f'进度文件已存在：{progress}')
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f'批次大小无效：{batch_size}，应为 1–{MAX_BATCH_SIZE}')
    if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
        raise ValueError(f'任务标识无效：{task_id}')
    pages = read_json(manifest)
    selected = pages.get('selected_pages') or [entry['page'] for entry in pages.get('pages', [])]
    for key in ('source_page_count', 'source_sha256'):
        if key not in pages:
            raise ValueError(f'pages.json 缺少 {key}，请用 0.6.0 及以上的 prepare_pdf.py 重新生成')
    if not selected or selected != sorted(set(selected)):
        raise ValueError('pages.json 的 selected_pages 必须为非空升序页码')
    rendered = [entry['page'] for entry in pages.get('pages', [])]
    if rendered != selected:
        raise ValueError('pages.json 的 selected_pages 与已渲染页面不一致')
    state = {'schema_version': 1, 'task_id': task_id,
             'pages_manifest': os.path.relpath(manifest, progress.parent).replace(os.sep, '/'),
             'source_sha256': pages['source_sha256'], 'source_page_count': pages['source_page_count'],
             'selected_pages': selected, 'batch_size': batch_size,
             'batches': [{'batch': index + 1, 'pages': selected[start:start + batch_size], 'status': 'pending'}
                         for index, start in enumerate(range(0, len(selected), batch_size))]}
    write_new(progress, state)
    return state


def load(progress):
    state = read_json(progress)
    if state.get('schema_version') != 1 or not isinstance(state.get('batches'), list):
        raise ValueError('进度文件格式无效')
    return state


def status(progress):
    state = load(progress)
    done = [b for b in state['batches'] if b['status'] == 'done']
    pending = [b for b in state['batches'] if b['status'] != 'done']
    return {'task_id': state['task_id'],
            'done_pages': sum(len(b['pages']) for b in done),
            'total_pages': len(state['selected_pages']),
            'done_batches': [b['batch'] for b in done],
            'next_batch': {'batch': pending[0]['batch'], 'pages': pending[0]['pages']} if pending else None,
            'complete': not pending}


def image_ids(blocks):
    return [b['figure_id'] for b in blocks if isinstance(b, dict) and b.get('type') == 'image' and 'figure_id' in b]


def commit(progress, batch, blocks_file):
    progress, blocks_file = Path(progress).resolve(), Path(blocks_file).resolve()
    state = load(progress)
    relative = inside(progress.parent, blocks_file)
    entry = next((b for b in state['batches'] if b['batch'] == batch), None)
    if entry is None:
        raise ValueError(f'第 {batch} 批不存在')
    if entry['status'] != 'pending':
        raise ValueError(f'第 {batch} 批已提交；如需更正，请人工确认后处理，不要重复提交')
    data = read_json(blocks_file)
    if data.get('batch') != batch or data.get('pages') != entry['pages']:
        raise ValueError(f'第 {batch} 批的 batch/pages 与进度记录 {entry["pages"]} 不一致')
    blocks, figures = data.get('blocks'), data.get('figures', [])
    if not isinstance(blocks, list) or not blocks:
        raise ValueError(f'第 {batch} 批 blocks 必须为非空列表')
    if not all(isinstance(b, dict) for b in blocks):
        raise ValueError(f'第 {batch} 批 blocks 中每项必须是对象')
    if not isinstance(figures, list) or not all(isinstance(f, dict) for f in figures):
        raise ValueError(f'第 {batch} 批 figures 必须为对象列表')
    for figure in figures:
        if figure.get('source_page') not in entry['pages']:
            raise ValueError(f'第 {batch} 批图片 {figure.get("figure_id")} 的 source_page 不属于本批页码')
    for index, block in enumerate(blocks):
        if index and block.get('join_previous'):
            raise ValueError(f'第 {batch} 批 blocks[{index}]：join_previous 只能用于批次首个 block')
    if batch == state['batches'][0]['batch'] and blocks[0].get('join_previous'):
        raise ValueError('第 1 批不能使用 join_previous')
    block_figures = image_ids(blocks)
    listed = [f.get('figure_id') for f in figures]
    if sorted(block_figures) != sorted(listed) or len(set(listed)) != len(listed):
        raise ValueError(f'第 {batch} 批：带 figure_id 的 image 块与 figures 必须一一对应')
    entry.update(status='done', blocks_file=relative, blocks_sha256=sha256(blocks_file))
    replace_atomic(progress, state)
    return entry


def as_runs(block):
    if 'runs' in block:
        return deepcopy(block['runs'])
    return [{'type': 'text', 'text': block.get('text', '')}]


def merge(progress, output):
    progress, output = Path(progress).resolve(), Path(output).resolve()
    state = load(progress)
    if output.parent != progress.parent:
        raise ValueError('合并输出必须与进度文件位于同一目录，以保持图片相对路径')
    if output.exists():
        raise FileExistsError(f'输出已存在：{output}')
    unfinished = [b['batch'] for b in state['batches'] if b['status'] != 'done']
    if unfinished:
        raise ValueError(f'仍有未完成批次：{unfinished}')
    blocks, figures, owners = [], [], {}
    for entry in state['batches']:
        path = progress.parent / entry['blocks_file']
        if sha256(path) != entry['blocks_sha256']:
            raise ValueError(f'第 {entry["batch"]} 批文件在提交后被修改：{entry["blocks_file"]}')
        data = read_json(path)
        for index, block in enumerate(deepcopy(data['blocks'])):
            if block.pop('join_previous', False):
                previous = blocks[-1] if blocks else None
                if not previous or previous.get('type') != 'text' or block.get('type') != 'text':
                    raise ValueError(f'第 {entry["batch"]} 批 join_previous：前后两块都必须是 text')
                if 'selection' in previous and 'selection' in block and previous['selection'] != block['selection']:
                    raise ValueError(f'第 {entry["batch"]} 批 join_previous：两块的 selection 不一致')
                selection = previous.get('selection', block.get('selection'))
                runs = as_runs(previous) + as_runs(block)
                previous.pop('text', None)
                previous['runs'] = runs
                if selection is not None:
                    previous['selection'] = selection
                continue
            if 'id' in block:
                if block['id'] in owners:
                    raise ValueError(f'block id 冲突：{block["id"]}（第 {owners[block["id"]]} 批与第 {entry["batch"]} 批）')
                owners[block['id']] = entry['batch']
            blocks.append(block)
        figures.extend(deepcopy(data.get('figures', [])))
    result = {'blocks': blocks}
    if figures:
        result['figure_task'] = {'schema_version': 1, 'task_id': state['task_id'],
                                 'page_count': state['source_page_count'], 'scan_complete': True,
                                 'figures': figures}
    write_new(output, result)
    return result


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init')
    p.add_argument('manifest', help='pages.json from prepare_pdf.py')
    p.add_argument('--progress', required=True)
    p.add_argument('--batch-size', type=int, default=5)
    p.add_argument('--task-id', default='current-file')
    p = sub.add_parser('status')
    p.add_argument('progress')
    p = sub.add_parser('commit')
    p.add_argument('progress')
    p.add_argument('--batch', type=int, required=True)
    p.add_argument('--blocks', required=True)
    p = sub.add_parser('merge')
    p.add_argument('progress')
    p.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            result = init(args.manifest, args.progress, batch_size=args.batch_size, task_id=args.task_id)
            result = status(args.progress)
        elif args.command == 'status':
            result = status(args.progress)
        elif args.command == 'commit':
            commit(args.progress, args.batch, args.blocks)
            result = status(args.progress)
        else:
            merge(args.progress, args.output)
            result = {'output': args.output, 'complete': True}
    except (ValueError, FileExistsError, OSError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
