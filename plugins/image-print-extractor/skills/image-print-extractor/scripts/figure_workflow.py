"""Task-local figure confirmation, candidate generation and hash-bound visual review.

The host detects/classifies/understands images and compares the real outputs.
This module neither performs OCR nor calls an image/vision service.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from _common import local_path, read_json, sha256, write_new as write_json
from confirmation import reply_mode
from export_page import image_source
from figure_drawing import (
    CHECKS, check_black_white, compose_group_tiles, number, render,
    render_placeholder_tile, verify_unchanged_regions,
)

PROMPT = '是否需要识别并重新绘制其中的图片？是 / 否'
CORE_TYPES = {'geometry','coordinates','function','motion','force','circuit','optics',
              'apparatus','structure','flowchart','wave','trajectory','biology','illustration'}
TYPES = CORE_TYPES | {'photo','table','formula','watermark','qr','logo','advertisement','decoration','unknown'}
SUBFIGURE_ID_RE = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}')
MAX_ATTEMPTS = 2
FALLBACKS = ('placeholder','original')
LABEL_FORBIDDEN = re.compile(r'[\[\]\n\r]')


def allows_generative(item):
    """Only illustration or explicitly approved non-technical photo may use generated_png (V1.1 4.1)."""
    return item.get('figure_type') == 'illustration' or (
        item.get('figure_type') == 'photo' and item.get('allow_generative') is True
    )


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def text_document(document):
    """A separate, complete text/formula/table result, never modified by figure failure."""
    result = deepcopy(document)
    result.pop('figure_task',None)
    result.pop('figure_processing',None)
    result['blocks'] = [block for block in result['blocks'] if block.get('type')!='image']
    return result


def _validate_subfigures(figure, fid):
    subs = figure.get('subfigures')
    if subs is None:
        return
    if not isinstance(subs, list) or not subs:
        raise ValueError(f'插图 {fid} 的 subfigures 必须是非空列表')
    sub_ids = set()
    for sub in subs:
        if not isinstance(sub, dict):
            raise ValueError(f'插图 {fid} 的 subfigures 项必须是对象')
        sid = sub.get('subfigure_id')
        if not isinstance(sid, str) or not SUBFIGURE_ID_RE.fullmatch(sid) or sid in sub_ids:
            raise ValueError(f'插图 {fid} 的 subfigure_id 必须为组内唯一安全标识符：{sid!r}')
        sub_ids.add(sid)
        stype = sub.get('figure_type')
        if stype not in TYPES or stype in {'table', 'formula'}:
            raise ValueError(f'插图 {fid}:{sid} 的 figure_type 无效：{stype!r}')
        sbbox = sub.get('source_bbox')
        if sbbox is not None and (
            not isinstance(sbbox, list) or len(sbbox) != 4
            or not 0 <= number(sbbox[0]) < number(sbbox[2])
            or not 0 <= number(sbbox[1]) < number(sbbox[3])
        ):
            raise ValueError(f'插图 {fid}:{sid} 的 source_bbox 必须具有正面积')
        slabel = sub.get('placeholder_label')
        if slabel is not None and (not isinstance(slabel, str) or not 1 <= len(slabel) <= 20 or LABEL_FORBIDDEN.search(slabel)):
            raise ValueError(f'插图 {fid}:{sid} 的 placeholder_label 必须为 1–20 字且不含方括号或换行')


def figures(document):
    if not isinstance(document,dict) or not isinstance(document.get('blocks'),list):
        raise ValueError('Document must contain blocks')
    task = document.get('figure_task')
    if not isinstance(task,dict) or task.get('schema_version')!=1:
        raise ValueError('A version 1 figure_task is required')
    if (not isinstance(task.get('task_id'),str) or not task['task_id']
            or type(task.get('page_count')) is not int or task['page_count']<1):
        raise ValueError('Task needs task_id and positive page_count')
    if task.get('scan_complete') is not True:
        raise ValueError('Detect the entire current document before deciding whether to ask')
    candidates = task.get('figures')
    if not isinstance(candidates,list):
        raise ValueError('Task figures must be a list')
    ids, groups = set(),set()
    blocks = document['blocks']
    block_ids = [b['id'] for b in blocks if 'id' in b]
    if len(block_ids)!=len(set(block_ids)):
        raise ValueError('Block ids must be unique')
    for figure in candidates:
        fid = figure.get('figure_id') if isinstance(figure,dict) else None
        if not isinstance(fid,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',fid) or fid in ids:
            raise ValueError('Figure ids must be unique safe identifiers')
        ids.add(fid)
        page,bbox = figure.get('source_page'),figure.get('source_bbox')
        if type(page) is not int or not 1<=page<=task['page_count']:
            raise ValueError('Figure page is outside the current document')
        if not isinstance(bbox,list) or len(bbox)!=4 or not 0<=number(bbox[0])<number(bbox[2]) or not 0<=number(bbox[1])<number(bbox[3]):
            raise ValueError('Figure source_bbox must have positive area')
        if figure.get('parent_block_id') not in block_ids:
            raise ValueError('Figure must be associated with an existing parent block')
        if figure.get('figure_type') not in TYPES or figure.get('relation') not in {'main','supporting','unrelated','unknown'}:
            raise ValueError('Invalid figure classification')
        if figure['figure_type'] in {'table','formula'}:
            converted=[b for b in blocks if b.get('id') in figure.get('content_block_ids',[])]
            def expression(item):
                return item.get('type') in {'math','chemistry'} or any(expression(v) for key in ('runs','cells') for v in item.get(key,[]))
            if not converted or not all(b.get('type')=='table' if figure['figure_type']=='table' else expression(b) for b in converted):
                raise ValueError('Table/formula regions must reference their converted native content_block_ids')
        label = figure.get('placeholder_label')
        if label is not None and (not isinstance(label,str) or not 1<=len(label)<=20 or LABEL_FORBIDDEN.search(label)):
            raise ValueError(f'插图 {fid} 的 placeholder_label 必须为 1–20 字且不含方括号或换行')
        group = figure.get('figure_group_id')
        if group is not None:
            if not isinstance(group,str) or not group or group in groups:
                raise ValueError('Related subfigures must be represented by one combined figure')
            groups.add(group)
        _validate_subfigures(figure, fid)
        matches = [b for b in blocks if b.get('type')=='image' and b.get('figure_id')==fid]
        if len(matches)!=1 or matches[0].get('path')!=figure.get('source_path'):
            raise ValueError('Each figure needs one original-position image block matching source_path')
    if any(b.get('type')=='image' and b.get('figure_id') not in ids for b in blocks):
        raise ValueError('New figure tasks must classify every image block')
    def check_selection(item):
        if 'selection' in item:
            raise ValueError('Run select_content.py before processing figures')
        for key in ('runs','cells'):
            for child in item.get(key,[]): check_selection(child)
    for block in blocks: check_selection(block)
    return candidates


def _sub_eligible(sub):
    return (sub['figure_type'] in CORE_TYPES
            or (sub['figure_type'] == 'photo'
                and (sub.get('simple_schematic') is True or sub.get('allow_generative') is True)))


def eligible(figure):
    if figure['relation'] not in {'main', 'supporting'}:
        return False
    if figure.get('subfigures'):
        return any(_sub_eligible(sub) for sub in figure['subfigures'])
    return (figure['figure_type'] in CORE_TYPES
            or (figure['figure_type'] == 'photo'
                and (figure.get('simple_schematic') is True or figure.get('allow_generative') is True)))


def skipped_photo(figure):
    """A main/supporting photo that redraw mode leaves alone; it must not vanish silently."""
    if figure.get('subfigures'):
        return False
    return (figure['relation'] in {'main','supporting'} and figure['figure_type']=='photo'
            and figure.get('simple_schematic') is not True and figure.get('allow_generative') is not True)


def fallback_choice(mode, fallback):
    if fallback is None:
        return 'placeholder'
    if fallback not in FALLBACKS:
        raise ValueError('image_fallback 只能为 placeholder 或 original')
    if fallback=='original' and mode!='redraw':
        raise ValueError('image_fallback 仅适用于 redraw 模式')
    return fallback


def preservable(figure):
    # Candidates have already passed semantic selection, including explicit scope overrides.
    return figure['figure_type'] not in {'table','formula'}


def plan(document, *, mode=None, response=None):
    candidates = figures(document)
    if mode not in {None,'ignore','preserve','redraw'}:
        raise ValueError('Unknown image mode')
    answered = reply_mode(response)
    if mode is not None and answered is not None and mode!=answered:
        raise ValueError('Conflicting current-task image choices')
    choice = mode or answered
    valid = [f['figure_id'] for f in candidates if eligible(f)]
    if choice is None and valid:
        return {'task_id':document['figure_task']['task_id'],'status':'awaiting_confirmation',
                'image_mode':None,'prompt':PROMPT,'figure_ids':valid}
    return {'task_id':document['figure_task']['task_id'],'status':'ready' if valid or choice=='preserve' else 'no_figures',
            'image_mode':choice or 'ignore','prompt':None,'figure_ids':valid,
            'uncertain_figures':[f['figure_id'] for f in candidates if f['relation']=='unknown' or f['figure_type']=='unknown']}


def _strip_drawings(figure):
    """Return figure dict with drawing stripped (including inside subfigures) for retry immutability check."""
    out = {k: deepcopy(v) for k, v in figure.items() if k != 'drawing'}
    if isinstance(out.get('subfigures'), list):
        out['subfigures'] = [{k: v for k, v in s.items() if k != 'drawing'} for s in out['subfigures']]
    return out


def _handwriting_blocks_original(item, ledger_disallow):
    """V1.1 Section 5.1: if output forbids handwriting and item has handwriting, use placeholder unless explicitly excepted."""
    disallow = bool(ledger_disallow or item.get('disallow_handwriting_fallback'))
    if not disallow:
        return False
    return bool(item.get('has_handwriting')) and item.get('allow_handwriting_original_exception') is not True


def _generate_one_item(item, record, fid, subid, base, output_dir, font_path, parent_source_path):
    """Generate one attempt for a single figure or a single subfigure partition."""
    source_rel = item.get('source_path') or parent_source_path
    source = image_source(base, source_rel)
    source_hash = sha256(source)
    if record.get('source_sha256', source_hash) != source_hash:
        raise ValueError('Original figure changed during the task')
    record['source_sha256'] = source_hash
    if record.get('state') in {'validated', 'failed', 'skipped_photo'}:
        return
    if record['attempts'] and record['attempts'][-1].get('validation_status') not in {'major_issue', 'render_error'}:
        raise ValueError('Review the current candidate before trying again')
    if len(record['attempts']) >= MAX_ATTEMPTS:
        raise ValueError('Figure retry limit reached')
    if item.get('figure_type') == 'photo' and item.get('simple_schematic') is not True and item.get('allow_generative') is not True:
        record.update(state='skipped_photo', failed=False)
        return
    # Critical uncertainty or unredrawable goes straight to fallback without consuming attempts (V1.1 5.1)
    if not item.get('understanding') or item.get('redrawable') is not True or item.get('critical_uncertainty') is not False:
        raise ValueError('Figure structure cannot be reliably understood or redrawn')
    record.update(understood=True, redrawable=True)
    drawing = item.get('drawing', {})
    # Cross-host degradation: host explicitly reports image generation tool unavailable (V1.1 4.1)
    if drawing.get('tool_unavailable') is True:
        raise ValueError('tool_unavailable: 当前宿主无可用图像生成工具，已按策略降级')
    structured = not allows_generative(item)
    if structured and 'scene' not in drawing:
        raise ValueError('Technical diagrams require structured drawing')
    attempt = len(record['attempts']) + 1
    stem = f'figure-{fid}-{subid}-a{attempt}' if subid else f'figure-{fid}-a{attempt}'
    png = output_dir / f'{stem}.png'
    svg = output_dir / f'{stem}.svg'
    if 'scene' in drawing:
        try:
            hashes = render(drawing['scene'], svg, png, understanding=item['understanding'], font_path=font_path)
            check_black_white(png)
        except (ValueError, KeyError, TypeError) as exc:
            png.unlink(missing_ok=True)
            svg.unlink(missing_ok=True)
            if attempt < MAX_ATTEMPTS:
                record['attempts'].append({'attempt': attempt, 'source_sha256': source_hash,
                                           'drawing_method': 'structured', 'validation_status': 'render_error', 'error': str(exc)})
                record.update(state='needs_retry', generated=False, failed=False, reason=str(exc))
                return
            raise
        svg_relative = svg.relative_to(base).as_posix()
        method = 'structured'
    else:
        if 'generated_png' not in drawing:
            raise ValueError('Non-technical figure requires scene, generated_png or tool_unavailable')
        generated = image_source(base, drawing['generated_png'])
        if generated.resolve() == source.resolve() or sha256(generated) == source_hash:
            raise ValueError('A crop or copy is not a generated illustration')
        check_black_white(generated)
        png.parent.mkdir(parents=True, exist_ok=True)
        with png.open('xb') as stream:
            stream.write(generated.read_bytes())
        hashes = {'png_sha256': sha256(png)}
        svg_relative, method = None, 'generative'
        check_black_white(png)
    entry = {'attempt': attempt, 'png_path': png.relative_to(base).as_posix(), 'svg_path': svg_relative,
             'source_sha256': source_hash, 'drawing_method': method, **hashes, 'validation_status': 'pending'}
    record['attempts'].append(entry)
    record.update(state='awaiting_validation', generated=True, failed=False)
    record.pop('reason', None)


def _compose_group_if_ready(figure, record, base, output_dir, fallback, disallow_hw, font_path):
    """Once all subfigures are terminal, apply dependency rules and compose the group PNG/SVG."""
    sub_defs = {s['subfigure_id']: s for s in figure['subfigures']}
    sub_recs = record['subfigures']
    if any(sr['state'] in {'awaiting_validation', 'needs_retry', 'pending'} for sr in sub_recs):
        return

    # 1. Dependency-aware failure propagation (V1.1 Section 5.1)
    failed_subs = [sr for sr in sub_recs if sr['state'] in {'failed', 'skipped_photo'}]
    if failed_subs:
        if figure.get('group_dependency') == 'strong' or any(sub_defs[sr['subfigure_id']].get('strong_dependency') for sr in failed_subs):
            record.update(state='failed', failed=True, validated=False,
                          reason='强依赖子图失败，整个图组回退：' + ','.join(sr['subfigure_id'] for sr in failed_subs))
            return
        # Propagate within shared dependency_group
        broken_groups = {sub_defs[sr['subfigure_id']].get('dependency_group') for sr in failed_subs} - {None}
        if broken_groups:
            for sr in sub_recs:
                dg = sub_defs[sr['subfigure_id']].get('dependency_group')
                if dg in broken_groups and sr['state'] == 'validated':
                    sr.update(state='failed', failed=True, validated=False, reason=f'同依赖组 {dg} 中其他子图失败')

    if all(sr['state'] in {'failed', 'skipped_photo'} for sr in sub_recs):
        record.update(state='failed', failed=True, validated=False, reason='图组全部子图失败或跳过')
        return

    # 2. Build tiles for composition
    fid = figure['figure_id']
    comp_attempt = len(record.get('composite_attempts', [])) + 1
    tiles = []
    sub_svgs = {}
    partial_fallbacks = []
    for sr in sub_recs:
        sid = sr['subfigure_id']
        sdef = sub_defs[sid]
        if sr['state'] == 'validated':
            entry = sr['attempts'][-1]
            tile = {'subfigure_id': sid, 'png_path': local_path(base, entry['png_path']),
                    'label': sdef.get('label'), 'is_original_fallback': False}
            if entry.get('svg_path'):
                tile['svg_path'] = local_path(base, entry['svg_path'])
                sub_svgs[sid] = {'svg_path': entry['svg_path'], 'svg_sha256': entry['svg_sha256']}
            tiles.append(tile)
        else:
            reason = 'photo' if sr['state'] == 'skipped_photo' else 'failed'
            use_orig = (fallback == 'original' and not _handwriting_blocks_original(sdef, disallow_hw))
            if use_orig:
                src_rel = sdef.get('source_path') or figure['source_path']
                src_path = image_source(base, src_rel)
                cur_hash = sha256(src_path)
                if sr.get('source_sha256') and cur_hash == sr['source_sha256']:
                    tiles.append({'subfigure_id': sid, 'png_path': src_path,
                                  'label': sdef.get('label'), 'is_original_fallback': True})
                    partial_fallbacks.append({'subfigure_id': sid, 'mode': 'original', 'reason': reason, 'source_sha256': cur_hash})
                    continue
            ph_label = sdef.get('placeholder_label') or sdef.get('label') or sid
            ph_text = f'{ph_label}（照片）：未重绘' if reason == 'photo' else f'{ph_label}：无法可靠重绘'
            ph_png = output_dir / f'figure-{fid}-{sid}-placeholder-c{comp_attempt}.png'
            render_placeholder_tile(ph_text, ph_png, font_path=font_path)
            tiles.append({'subfigure_id': sid, 'png_path': ph_png, 'label': sdef.get('label'), 'is_original_fallback': False})
            partial_fallbacks.append({'subfigure_id': sid, 'mode': 'placeholder', 'reason': reason,
                                      'handwriting_blocked_original': bool(fallback == 'original' and _handwriting_blocks_original(sdef, disallow_hw))})

    all_structured = all('svg_path' in t for t in tiles) and not partial_fallbacks
    comp_png = output_dir / f'figure-{fid}-group-c{comp_attempt}.png'
    comp_svg = (output_dir / f'figure-{fid}-group-c{comp_attempt}.svg') if all_structured else None
    comp = compose_group_tiles(tiles, comp_png, output_svg=comp_svg, layout=figure.get('layout'), font_path=font_path)

    # If this is a local repair, verify pixel-for-pixel identity of untouched subfigures!
    prev_comp = record.get('previous_composite')
    if prev_comp and prev_comp.get('untouched_ids'):
        verify_unchanged_regions(
            local_path(base, prev_comp['png_path']), prev_comp['subfigure_regions'],
            comp_png, comp['subfigure_regions'], prev_comp['untouched_ids'],
        )
        comp['unchanged_regions_verified'] = list(prev_comp['untouched_ids'])

    methods = {sr['attempts'][-1]['drawing_method'] for sr in sub_recs if sr['state'] == 'validated'}
    method = 'hybrid' if len(methods) > 1 or partial_fallbacks else (next(iter(methods)) if methods else 'structured')
    comp_entry = {
        'attempt': comp_attempt,
        'png_path': comp_png.relative_to(base).as_posix(),
        'svg_path': comp_svg.relative_to(base).as_posix() if comp_svg else None,
        'source_sha256': record['source_sha256'],
        'drawing_method': method,
        'png_sha256': comp['png_sha256'],
        'size': comp['size'],
        'subfigure_regions': comp['subfigure_regions'],
        'contains_original_fallback': comp['contains_original_fallback'],
        'partial_fallbacks': partial_fallbacks,
        'validation_status': 'pending',
    }
    if 'svg_sha256' in comp:
        comp_entry['svg_sha256'] = comp['svg_sha256']
    if sub_svgs:
        comp_entry['subfigure_svgs'] = sub_svgs
    if 'unchanged_regions_verified' in comp:
        comp_entry['unchanged_regions_verified'] = comp['unchanged_regions_verified']
    record.setdefault('composite_attempts', []).append(comp_entry)
    record.update(state='awaiting_composite_validation', generated=True, failed=False)


def generate(document, base, output_dir, *, mode=None, response=None, previous=None, font_path=None,
             image_fallback=None, disallow_handwriting_fallback=False):
    choice = plan(document,mode=mode,response=response)
    if choice['status']=='awaiting_confirmation':
        raise ValueError(PROMPT)
    fallback = fallback_choice(choice['image_mode'],image_fallback)
    base, output_dir = Path(base).resolve(),Path(output_dir).resolve()
    if not output_dir.is_relative_to(base):
        raise ValueError('Keep generated figures inside the input directory')
    ledger = {'schema_version':1,'task_id':choice['task_id'],'image_mode':choice['image_mode'],
              'image_fallback':fallback,
              'disallow_handwriting_fallback':bool(disallow_handwriting_fallback),
              'output_dir':output_dir.relative_to(base).as_posix(),
              'text_hash':fingerprint(text_document(document)),'document':deepcopy(document),'records':[]}
    candidates = figures(document)
    if previous:
        if (previous.get('task_id')!=ledger['task_id'] or previous.get('image_mode')!=ledger['image_mode']
                or previous.get('text_hash')!=ledger['text_hash']):
            raise ValueError('A retry cannot change task, mode or completed text')
        if previous.get('image_fallback','placeholder')!=fallback:
            raise ValueError('重试不能改变 image_fallback')
        old = {f['figure_id']: _strip_drawings(f) for f in figures(previous['document'])}
        new = {f['figure_id']: _strip_drawings(f) for f in candidates}
        if old!=new:
            raise ValueError('A correction cannot change source understanding or figure association')
    old_records = {r['figure_id']:r for r in previous['records']} if previous else {}
    for figure in candidates:
        fid = figure['figure_id']
        record = deepcopy(old_records.get(fid,{'figure_id':fid,'figure_type':figure['figure_type'],
            'source_page':figure['source_page'],'source_bbox':figure['source_bbox'],
            'parent_block_id':figure['parent_block_id'],'figure_group_id':figure.get('figure_group_id'),
            'detected':True,'classified':True,'understood':False,'redrawable':False,
            'generated':False,'validated':False,'failed':False,'attempts':[]}))
        ledger['records'].append(record)
        if ledger['image_mode']=='redraw' and skipped_photo(figure):
            try:
                source_hash = sha256(image_source(base,figure['source_path']))
                if record.get('source_sha256',source_hash)!=source_hash:
                    raise ValueError('Original figure changed during the task')
                record.update(state='skipped_photo',source_sha256=source_hash)
            except (ValueError,KeyError,TypeError,OSError) as exc:
                record.update(state='failed',failed=True,reason=str(exc))
            continue
        if ledger['image_mode']=='ignore' or not (preservable(figure) if ledger['image_mode']=='preserve' else eligible(figure)):
            record.update(state='ignored')
            continue
        try:
            source = image_source(base,figure['source_path'])
            source_hash = sha256(source)
            if record.get('source_sha256',source_hash)!=source_hash:
                raise ValueError('Original figure changed during the task')
            record['source_sha256'] = source_hash
            if ledger['image_mode']=='preserve':
                record.update(state='preserved',output_path=figure['source_path'])
                continue
            if record.get('state') in {'validated','failed'}:
                continue
            if figure.get('subfigures'):
                record['is_group'] = True
                old_subs = {s['subfigure_id']: s for s in record.get('subfigures', [])}
                sub_records = []
                for sub in figure['subfigures']:
                    sid = sub['subfigure_id']
                    sr = deepcopy(old_subs.get(sid, {
                        'subfigure_id': sid, 'figure_type': sub['figure_type'],
                        'label': sub.get('label'), 'dependency_group': sub.get('dependency_group'),
                        'understood': False, 'redrawable': False,
                        'generated': False, 'validated': False, 'failed': False, 'attempts': [],
                    }))
                    try:
                        _generate_one_item(sub, sr, fid, sid, base, output_dir, font_path, figure['source_path'])
                    except (ValueError, KeyError, TypeError, OSError) as exc:
                        sr.update(state='failed', failed=True, reason=str(exc))
                    sub_records.append(sr)
                record['subfigures'] = sub_records
                if any(sr['state'] == 'awaiting_validation' for sr in sub_records):
                    record.update(state='awaiting_validation', understood=True, redrawable=True, generated=True, failed=False)
                elif any(sr['state'] == 'needs_retry' for sr in sub_records):
                    record.update(state='needs_retry', generated=False, failed=False,
                                  reason='; '.join(f'{sr["subfigure_id"]}: {sr.get("reason")}' for sr in sub_records if sr['state'] == 'needs_retry'))
                else:
                    _compose_group_if_ready(figure, record, base, output_dir, fallback, disallow_handwriting_fallback, font_path)
            else:
                _generate_one_item(figure, record, fid, None, base, output_dir, font_path, figure['source_path'])
        except (ValueError,KeyError,TypeError,OSError) as exc:
            record.update(state='failed',failed=True,reason=str(exc))
    return ledger


def review_template(ledger):
    """Prefill hashes for awaiting attempts (both single figures and subfigure/composite levels)."""
    defs = {f['figure_id']: f for f in figures(ledger['document'])}
    rows = []
    for record in ledger['records']:
        fid = record['figure_id']
        fdef = defs[fid]
        if record.get('is_group'):
            if record.get('state') == 'awaiting_validation':
                sub_defs = {s['subfigure_id']: s for s in fdef['subfigures']}
                for sr in record.get('subfigures', []):
                    if sr.get('state') != 'awaiting_validation':
                        continue
                    sid = sr['subfigure_id']
                    entry = sr['attempts'][-1]
                    row = {'figure_id': fid, 'subfigure_id': sid, 'attempt': entry['attempt']}
                    row.update({k: entry[k] for k in ('source_sha256', 'png_sha256', 'svg_sha256') if k in entry})
                    row.update(reviewed_by='host_vision', status=None, notes=[], checks={check: None for check in CHECKS})
                    if entry.get('font_fallback'):
                        row['font_fallback'] = True
                        row['notes'].append('font_fallback: 标注未使用衬线字体，状态最高为 minor_issue')
                    src_rel = sub_defs[sid].get('source_path') or fdef['source_path']
                    row['view_files'] = {'source': src_rel, 'png': entry['png_path']}
                    if entry.get('svg_path'):
                        row['view_files']['svg'] = entry['svg_path']
                    rows.append(row)
            elif record.get('state') == 'awaiting_composite_validation':
                entry = record['composite_attempts'][-1]
                row = {'figure_id': fid, 'subfigure_id': None, 'scope': 'group', 'attempt': entry['attempt']}
                row.update({k: entry[k] for k in ('source_sha256', 'png_sha256', 'svg_sha256') if k in entry})
                row.update(reviewed_by='host_vision', status=None, notes=[], checks={check: None for check in CHECKS})
                row['view_files'] = {'source': fdef['source_path'], 'png': entry['png_path']}
                if entry.get('svg_path'):
                    row['view_files']['svg'] = entry['svg_path']
                rows.append(row)
            continue
        if record.get('state')!='awaiting_validation': continue
        entry = record['attempts'][-1]
        row = {'figure_id':fid,'attempt':entry['attempt']}
        row.update({k:entry[k] for k in ('source_sha256','png_sha256','svg_sha256') if k in entry})
        row.update(reviewed_by='host_vision',status=None,notes=[],checks={check:None for check in CHECKS})
        if entry.get('font_fallback'):
            # REQUIREMENTS 25.1: serif label fonts were unavailable; the review may be minor_issue at best.
            row['font_fallback'] = True
            row['notes'].append('font_fallback: 标注未使用衬线字体，状态最高为 minor_issue')
        # view_files only points at what must be looked at; review_candidate never reads it.
        row['view_files'] = {'source':fdef['source_path'],'png':entry['png_path']}
        if entry.get('svg_path'): row['view_files']['svg'] = entry['svg_path']
        rows.append(row)
    return {'reviews':rows}


def review_candidate(entry, review, base):
    if not isinstance(review,dict) or review.get('attempt')!=entry['attempt']:
        raise ValueError('Review must identify the generated attempt')
    for key,path_key in (('source_sha256',None),('png_sha256','png_path'),('svg_sha256','svg_path')):
        if key not in entry: continue
        if review.get(key)!=entry[key]:
            raise ValueError('Visual review does not match '+key)
        if path_key and sha256(local_path(base,entry[path_key]))!=entry[key]:
            raise ValueError('Candidate file changed after review')
    status = review.get('status')
    if status not in {'pass','minor_issue','major_issue','unreliable'}:
        raise ValueError('Unknown visual validation status')
    checks = review.get('checks',{})
    if set(checks)!=set(CHECKS) or any(type(v) is not bool for v in checks.values()):
        raise ValueError('Visual review must explicitly assess every critical check')
    if review.get('reviewed_by')!='host_vision' or not isinstance(review.get('notes'),list):
        raise ValueError('Review must come from host comparison of original and candidate')
    if status in {'pass','minor_issue'} and not all(checks.values()):
        raise ValueError('Critical visual failures cannot pass as minor issues')
    if entry.get('font_fallback') and status=='pass':
        raise ValueError('标注字体已降级（font_fallback），复核状态最高为 minor_issue')
    if not entry.get('contains_original_fallback'):
        check_black_white(local_path(base,entry['png_path']))
    return status


def complete(ledger, reviews, base, *, font_path=None):
    ledger = deepcopy(ledger)
    base = Path(base).resolve()
    rows = reviews.get('reviews',[]) if isinstance(reviews,dict) else reviews
    if not isinstance(rows,list): raise ValueError('Reviews must be a list')
    review_map = {}
    for row in rows:
        key = (row['figure_id'], row.get('subfigure_id'), row['attempt'])
        if key in review_map: raise ValueError('Duplicate review')
        review_map[key]=row
    pending,retries = [],[]
    definitions = {f['figure_id']:f for f in figures(ledger['document'])}
    fallback = ledger.get('image_fallback','placeholder')
    disallow_hw = ledger.get('disallow_handwriting_fallback', False)
    out_dir = local_path(base, ledger['output_dir']) if ledger.get('output_dir') else (base / 'images')

    for record in ledger['records']:
        fid = record['figure_id']
        fdef = definitions[fid]
        if record.get('is_group'):
            if record['state'] in {'ignored', 'preserved', 'failed', 'skipped_photo', 'validated'}:
                continue
            sub_defs = {s['subfigure_id']: s for s in fdef['subfigures']}
            if record['state'] in {'awaiting_validation', 'needs_retry'}:
                for sr in record['subfigures']:
                    sid = sr['subfigure_id']
                    if sr['state'] not in {'awaiting_validation', 'needs_retry', 'validated'}:
                        continue
                    entry = sr['attempts'][-1]
                    if sr['state'] == 'needs_retry' and entry.get('validation_status') == 'render_error':
                        retries.append(f'{fid}:{sid}')
                        continue
                    review = review_map.get((fid, sid, entry['attempt']))
                    if review is None and sr['state'] == 'validated':
                        review = entry['review']
                    if review is None:
                        pending.append(f'{fid}:{sid}')
                        continue
                    try:
                        src_rel = sub_defs[sid].get('source_path') or fdef['source_path']
                        if sha256(image_source(base, src_rel)) != sr['source_sha256']:
                            raise ValueError('Original source changed before visual review')
                        status = review_candidate(entry, review, base)
                        entry.update(validation_status=status, review=deepcopy(review))
                        if status in {'pass', 'minor_issue'}:
                            sr.update(state='validated', validated=True, failed=False)
                        elif status == 'major_issue' and len(sr['attempts']) < MAX_ATTEMPTS:
                            sr.update(state='needs_retry', validated=False)
                            retries.append(f'{fid}:{sid}')
                        else:
                            sr.update(state='failed', failed=True, validated=False, reason='Visual review: ' + status)
                    except (ValueError, OSError, KeyError, TypeError) as exc:
                        sr.update(state='failed', failed=True, validated=False, reason=str(exc))
                if any(sr['state'] == 'awaiting_validation' for sr in record['subfigures']):
                    record['state'] = 'awaiting_validation'
                    continue
                if any(sr['state'] == 'needs_retry' for sr in record['subfigures']):
                    record['state'] = 'needs_retry'
                    continue
                try:
                    _compose_group_if_ready(fdef, record, base, out_dir, fallback, disallow_hw, font_path)
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    record.update(state='failed', failed=True, validated=False, reason=str(exc))
                    continue

            if record['state'] == 'awaiting_composite_validation':
                comp_entry = record['composite_attempts'][-1]
                review = review_map.get((fid, None, comp_entry['attempt']))
                if review is None:
                    pending.append(fid)
                    continue
                try:
                    if sha256(image_source(base, fdef['source_path'])) != record['source_sha256']:
                        raise ValueError('Original source changed before visual review')
                    status = review_candidate(comp_entry, review, base)
                    comp_entry.update(validation_status=status, review=deepcopy(review))
                    if status in {'pass', 'minor_issue'}:
                        record.update(state='validated', validated=True, failed=False)
                    else:
                        record.update(state='failed', failed=True, validated=False, reason='Composite review: ' + status)
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    record.update(state='failed', failed=True, validated=False, reason=str(exc))
            continue

        if record['state'] not in {'awaiting_validation','needs_retry','validated'}: continue
        entry = record['attempts'][-1]
        if record['state']=='needs_retry' and entry.get('validation_status')=='render_error':
            retries.append(fid)
            continue
        review = review_map.get((fid, None, entry['attempt']))
        if review is None and record['state']=='validated': review=entry['review']
        if review is None:
            pending.append(fid)
            continue
        try:
            source = image_source(base,fdef['source_path'])
            if sha256(source)!=record['source_sha256']:
                raise ValueError('Original source changed before visual review')
            status = review_candidate(entry,review,base)
            entry.update(validation_status=status,review=deepcopy(review))
            if status in {'pass','minor_issue'}:
                record.update(state='validated',validated=True,failed=False)
            elif status=='major_issue' and len(record['attempts'])<MAX_ATTEMPTS:
                record.update(state='needs_retry',validated=False)
                retries.append(fid)
            else:
                record.update(state='failed',failed=True,validated=False,reason='Visual review: '+status)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            record.update(state='failed',failed=True,validated=False,reason=str(exc))
    ledger['pending_reviews'],ledger['needs_retry'] = pending,retries
    ledger['status'] = 'awaiting_validation' if pending else 'needs_retry' if retries else 'completed'
    if pending or retries: return None,ledger
    result = deepcopy(ledger['document'])
    result.pop('figure_task')
    records = {r['figure_id']:r for r in ledger['records']}
    blocks=[]
    ordinal=0
    used_fallback, fallback_errors = [], {}
    for block in result['blocks']:
        if block.get('type')!='image':
            blocks.append(block)
            continue
        record = records[block['figure_id']]
        if record['state']=='ignored': continue
        # Reader-facing order counts only positions that remain visible in the document.
        ordinal+=1
        fdef = definitions[record['figure_id']]
        if record['state'] in {'failed','skipped_photo'}:
            reason = 'photo' if record['state']=='skipped_photo' else 'failed'
            hw_blocked = _handwriting_blocks_original(fdef, disallow_hw)
            if fallback=='original' and not hw_blocked:
                try:
                    current = sha256(image_source(base,fdef['source_path']))
                    if not record.get('source_sha256') or current!=record['source_sha256']:
                        raise ValueError('原图在回退前被修改或无法核对')
                    block.pop('svg_path',None)
                    block['fallback'] = {'reason':reason,'source_sha256':current}
                    blocks.append(block)
                    used_fallback.append(record['figure_id'])
                    continue
                except (ValueError,OSError,KeyError) as exc:
                    fallback_errors[record['figure_id']] = str(exc)
            label = fdef.get('placeholder_label') or f'第{ordinal}张插图'
            text = f'[{label}（照片）：未重绘]' if reason=='photo' else f'[{label}：无法可靠重绘]'
            placeholder = {'type':'text','text':text,'layout':deepcopy(block.get('layout',{}))}
            # V1.0: keep the block id/role so question indexes and review gates still find the figure.
            for key in ('id','role'):
                if key in block: placeholder[key]=block[key]
            ph_meta = {'figure_id':record['figure_id'],'reason':reason}
            if hw_blocked and fallback == 'original':
                ph_meta['handwriting_blocked_original'] = True
            placeholder['figure_placeholder'] = ph_meta
            blocks.append(placeholder)
            continue
        if record['state']=='preserved':
            blocks.append(block)
        elif record['state']=='validated':
            entry = record['composite_attempts'][-1] if record.get('is_group') else record['attempts'][-1]
            block['path'] = entry['png_path']
            block['svg_path'] = entry['svg_path']
            block['redraw'] = {k:deepcopy(entry[k]) for k in ('source_sha256','png_sha256','drawing_method','review')}
            for opt in ('svg_sha256', 'font_fallback', 'contains_original_fallback', 'partial_fallbacks',
                        'subfigure_svgs', 'subfigure_regions', 'unchanged_regions_verified'):
                if entry.get(opt):
                    block['redraw'][opt] = deepcopy(entry[opt])
            block['figure'] = {k:deepcopy(record[k]) for k in ('figure_id','source_page','source_bbox','parent_block_id','figure_type','figure_group_id')}
            if record.get('is_group'):
                block['figure']['subfigures'] = [
                    {'subfigure_id': sr['subfigure_id'], 'state': sr['state'], 'label': sr.get('label')}
                    for sr in record['subfigures']
                ]
            blocks.append(block)
        else:
            raise ValueError(f'插图 {record["figure_id"]} 处于未完成状态 {record["state"]}')
    result['blocks']=blocks
    result['figure_processing']={'task_id':ledger['task_id'],'image_mode':ledger['image_mode'],'status':'completed',
                                'image_fallback':fallback,
                                'failed_figures':[r['figure_id'] for r in ledger['records'] if r['failed']],
                                'skipped_photos':[r['figure_id'] for r in ledger['records'] if r['state']=='skipped_photo'],
                                'fallback_figures':used_fallback}
    if ledger.get('task_version'):
        result['figure_processing']['task_version'] = ledger['task_version']
    if fallback_errors:
        result['figure_processing']['fallback_errors']=fallback_errors
    return result,ledger


def prepare_repair(previous_ledger, base, output_dir, *, targets, updated_drawings=None,
                   fact_correction=None, font_path=None):
    """Create a new task-version ledger repairing only specified figure/subfigure targets (V1.1 Section 5.2).

    - Untouched figures and untouched subfigures reuse their validated outputs directly without regenerating.
    - Targeted figure/subfigure(s) receive a fresh MAX_ATTEMPTS=2 budget.
    - Appearance repair locks understanding unchanged; fact_correction requires reason + evidence and increments fact_version.
    """
    if previous_ledger.get('status') != 'completed':
        raise ValueError('只能对已完成交付的台账发起局部返修')
    if not targets:
        raise ValueError('局部返修必须指定至少一个目标（figure_id 或 figure_id:subfigure_id）')
    updated_drawings = updated_drawings or {}
    base, output_dir = Path(base).resolve(), Path(output_dir).resolve()
    if not output_dir.is_relative_to(base):
        raise ValueError('Keep generated figures inside the input directory')

    doc = deepcopy(previous_ledger['document'])
    fig_map = {f['figure_id']: f for f in doc['figure_task']['figures']}
    rec_map = {r['figure_id']: deepcopy(r) for r in previous_ledger['records']}

    # Parse targets into {fid: set_of_subids_or_None}
    parsed = {}
    for target in targets:
        fid, sep, sid = target.partition(':')
        if fid not in fig_map:
            raise ValueError(f'局部返修目标不存在：{target}')
        if sep:
            subs = {s['subfigure_id'] for s in fig_map[fid].get('subfigures', [])}
            if sid not in subs:
                raise ValueError(f'局部返修子图目标不存在：{target}')
            parsed.setdefault(fid, set()).add(sid)
        else:
            parsed[fid] = None

    if fact_correction is not None:
        if (not isinstance(fact_correction, dict)
                or not isinstance(fact_correction.get('reason'), str) or not fact_correction['reason'].strip()
                or not isinstance(fact_correction.get('evidence'), str) or not fact_correction['evidence'].strip()
                or not isinstance(fact_correction.get('updates'), dict) or not fact_correction['updates']):
            raise ValueError('事实纠正必须提供 reason、evidence 和 updates')
        for tkey in fact_correction['updates']:
            if tkey not in targets:
                raise ValueError(f'事实纠正目标 {tkey} 不在本次返修目标 {targets} 中')

    new_version = int(previous_ledger.get('task_version', 1)) + 1
    new_ledger = {
        'schema_version': 1,
        'task_id': previous_ledger['task_id'],
        'task_version': new_version,
        'parent_task_version': int(previous_ledger.get('task_version', 1)),
        'repaired_targets': list(targets),
        'image_mode': previous_ledger['image_mode'],
        'image_fallback': previous_ledger.get('image_fallback', 'placeholder'),
        'disallow_handwriting_fallback': previous_ledger.get('disallow_handwriting_fallback', False),
        'output_dir': output_dir.relative_to(base).as_posix(),
        'text_hash': previous_ledger['text_hash'],
        'document': doc,
        'records': [],
    }
    if fact_correction is not None:
        new_ledger['fact_correction'] = {'reason': fact_correction['reason'], 'evidence': fact_correction['evidence'],
                                         'targets': sorted(fact_correction['updates'])}

    for figure in doc['figure_task']['figures']:
        fid = figure['figure_id']
        record = rec_map[fid]
        new_ledger['records'].append(record)
        if fid not in parsed:
            continue  # Untouched figure: keep validated record verbatim

        sub_targets = parsed[fid]
        if sub_targets is not None:
            if not record.get('is_group'):
                raise ValueError(f'插图 {fid} 不是图组，不能按子图返修')
            prev_comp_entry = record['composite_attempts'][-1] if record.get('composite_attempts') else None
            untouched = [sr['subfigure_id'] for sr in record['subfigures']
                         if sr['subfigure_id'] not in sub_targets and sr['state'] == 'validated']
            if prev_comp_entry:
                record['previous_composite'] = {
                    'png_path': prev_comp_entry['png_path'],
                    'subfigure_regions': prev_comp_entry['subfigure_regions'],
                    'untouched_ids': untouched,
                }
            record['composite_attempts'] = []
            record.update(state='pending', validated=False, failed=False)
            sub_def_map = {s['subfigure_id']: s for s in figure['subfigures']}
            for sr in record['subfigures']:
                sid = sr['subfigure_id']
                if sid not in sub_targets:
                    continue  # Untouched subfigure: NEVER regenerate!
                tkey = f'{fid}:{sid}'
                sdef = sub_def_map[sid]
                if fact_correction and tkey in fact_correction['updates']:
                    old_ver = int((sdef.get('understanding') or {}).get('fact_version', 1))
                    new_u = deepcopy(fact_correction['updates'][tkey])
                    new_u['fact_version'] = old_ver + 1
                    changes = list((sdef.get('understanding') or {}).get('fact_changes', []))
                    changes.append({'version': old_ver + 1, 'reason': fact_correction['reason'],
                                    'evidence': fact_correction['evidence'], 'target': tkey})
                    new_u['fact_changes'] = changes
                    sdef['understanding'] = new_u
                if tkey in updated_drawings:
                    sdef['drawing'] = deepcopy(updated_drawings[tkey])
                sr.update(state='pending', validated=False, failed=False, generated=False, attempts=[])
                sr.pop('reason', None)
                try:
                    _generate_one_item(sdef, sr, fid, sid, base, output_dir, font_path, figure['source_path'])
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    sr.update(state='failed', failed=True, reason=str(exc))
            if any(sr['state'] == 'awaiting_validation' for sr in record['subfigures']):
                record['state'] = 'awaiting_validation'
            elif any(sr['state'] == 'needs_retry' for sr in record['subfigures']):
                record['state'] = 'needs_retry'
            else:
                _compose_group_if_ready(figure, record, base, output_dir, new_ledger['image_fallback'],
                                        new_ledger['disallow_handwriting_fallback'], font_path)
        else:
            if fact_correction and fid in fact_correction['updates']:
                old_ver = int((figure.get('understanding') or {}).get('fact_version', 1))
                new_u = deepcopy(fact_correction['updates'][fid])
                new_u['fact_version'] = old_ver + 1
                changes = list((figure.get('understanding') or {}).get('fact_changes', []))
                changes.append({'version': old_ver + 1, 'reason': fact_correction['reason'],
                                'evidence': fact_correction['evidence'], 'target': fid})
                new_u['fact_changes'] = changes
                figure['understanding'] = new_u
            if fid in updated_drawings:
                figure['drawing'] = deepcopy(updated_drawings[fid])
            record.update(state='pending', validated=False, failed=False, generated=False, attempts=[])
            record.pop('reason', None)
            try:
                _generate_one_item(figure, record, fid, None, base, output_dir, font_path, figure['source_path'])
            except (ValueError, KeyError, TypeError, OSError) as exc:
                record.update(state='failed', failed=True, reason=str(exc))
    return new_ledger



def main():
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('plan','generate','complete'):
        p=sub.add_parser(command)
        p.add_argument('source',help='Reviewed document with host figure_task annotations')
        if command!='complete':
            p.add_argument('--image-mode',choices=['ignore','preserve','redraw'])
            p.add_argument('--response',help='Actual reply to the active image question')
        if command=='plan': p.add_argument('--text-output',help='Save independent text/formula/table result')
        elif command=='generate':
            p.add_argument('--output-dir',required=True)
            p.add_argument('--ledger',required=True)
            p.add_argument('--previous',help='Reviewed ledger of the first failed attempt')
            p.add_argument('--font',help='Font supporting the original labels')
            p.add_argument('--review-template',help='Also write a review template with prefilled hashes and null judgements')
            p.add_argument('--image-fallback',choices=FALLBACKS,
                           help='redraw only: placeholder (default) or original crop for failed figures and photos')
        else:
            p.add_argument('--ledger',required=True)
            p.add_argument('--reviews',required=True)
            p.add_argument('--next-ledger',required=True)
            p.add_argument('--output',required=True)
    args=parser.parse_args()
    source=Path(args.source).resolve()
    document=json.loads(source.read_text(encoding='utf-8'))
    if args.command=='plan':
        result=plan(document,mode=args.image_mode,response=args.response)
        if args.text_output: write_json(args.text_output,text_document(document))
        print(json.dumps(result,ensure_ascii=False,indent=2))
    elif args.command=='generate':
        if Path(args.ledger).exists(): raise FileExistsError(args.ledger)
        if args.review_template and Path(args.review_template).exists(): raise FileExistsError(args.review_template)
        previous=json.loads(Path(args.previous).read_text(encoding='utf-8')) if args.previous else None
        ledger=generate(document,source.parent,args.output_dir,mode=args.image_mode,response=args.response,
                        previous=previous,font_path=args.font,image_fallback=args.image_fallback)
        write_json(args.ledger,ledger)
        if args.review_template: write_json(args.review_template,review_template(ledger))
        print(json.dumps({'ledger':args.ledger,'states':{r['figure_id']:r['state'] for r in ledger['records']}},ensure_ascii=False))
    else:
        if Path(args.next_ledger).exists() or Path(args.output).exists(): raise FileExistsError('Output already exists')
        if Path(args.output).resolve().parent!=source.parent:
            raise ValueError('Final JSON must stay beside the source to preserve image paths')
        ledger=json.loads(Path(args.ledger).read_text(encoding='utf-8'))
        if ledger['task_id']!=document['figure_task']['task_id'] or ledger['text_hash']!=fingerprint(text_document(document)):
            raise ValueError('Ledger does not match the current task')
        reviews=json.loads(Path(args.reviews).read_text(encoding='utf-8'))
        result,ledger=complete(ledger,reviews,source.parent)
        write_json(args.next_ledger,ledger)
        if result is not None: write_json(args.output,result)
        print(json.dumps({'status':ledger['status'],'needs_retry':ledger['needs_retry'],'pending_reviews':ledger['pending_reviews'],
                          'output':args.output if result is not None else None},ensure_ascii=False))


if __name__=='__main__': main()
