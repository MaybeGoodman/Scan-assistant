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
from export_page import image_source
from figure_drawing import CHECKS, check_black_white, number, render, sha256

PROMPT = '是否需要识别并重新绘制其中的图片？是 / 否'
CORE_TYPES = {'geometry','coordinates','function','motion','force','circuit','optics',
              'apparatus','structure','flowchart','wave','trajectory','biology','illustration'}
TYPES = CORE_TYPES | {'photo','table','formula','watermark','qr','logo','advertisement','decoration','unknown'}
# Requirement examples plus common short variants. Matching stays exact after
# normalization; unrecognized or conflicting replies remain ambiguous.
YES = {'是','可以','需要','继续','要','重绘','帮我画出来','图片也处理','图也生成',
       '好','行','对','嗯','没问题','可','画','重画','都要','需要重绘','要重绘','yes','y','ok','okay'}
NO = {'否','不需要','不用','跳过','只要文字','不要图片','图片忽略',
      '不','不要','不行','不是','不画','不重绘','不用画','不用重绘','不需要重绘','算了','没必要','no','n'}
PRESERVE = {'不用重绘，原图保留','不重绘，保留原图','保留原图','原图保留','用原图','保留原图即可'}
LEADING = '嗯哦噢喔那额呃'
TRAILING = '的了吧啊呀哦呢嘛啦'
SEPARATORS = re.compile(r'[，,、；;。！!？?\s.~～…]+')
MAX_ATTEMPTS = 2


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def text_document(document):
    """A separate, complete text/formula/table result, never modified by figure failure."""
    result = deepcopy(document)
    result.pop('figure_task',None)
    result.pop('figure_processing',None)
    result['blocks'] = [block for block in result['blocks'] if block.get('type')!='image']
    return result


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
        group = figure.get('figure_group_id')
        if group is not None:
            if not isinstance(group,str) or not group or group in groups:
                raise ValueError('Related subfigures must be represented by one combined figure')
            groups.add(group)
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


def eligible(figure):
    return (figure['relation'] in {'main','supporting'}
            and (figure['figure_type'] in CORE_TYPES
                 or figure['figure_type']=='photo' and figure.get('simple_schematic') is True))


def preservable(figure):
    # Candidates have already passed semantic selection, including explicit scope overrides.
    return figure['figure_type'] not in {'table','formula'}


def _reply_word(part):
    """Map one normalized reply fragment to a mode, or None when unknown."""
    for candidate in (part, part.lower()):
        if candidate in YES: return 'redraw'
        if candidate in NO: return 'ignore'
        if candidate in PRESERVE: return 'preserve'
    trimmed = part.lstrip(LEADING).rstrip(TRAILING) or part
    trimmed = trimmed.rstrip(TRAILING) or trimmed
    if trimmed != part:
        return _reply_word(trimmed)
    return None


def reply_mode(response):
    if response is None: return None
    response = response.strip()
    whole = SEPARATORS.sub('，',response).strip('，')
    if whole in PRESERVE: return 'preserve'
    fragments = [p for p in SEPARATORS.split(response) if p]
    modes = {_reply_word(p) for p in fragments}
    # Filler-only fragments such as "嗯" or "好的" may accompany a clear answer.
    fillers = {_reply_word(p) for p in fragments if p.lstrip(LEADING).rstrip(TRAILING) in {'','好','嗯','行','对'}}
    decisive = modes - ({'redraw'} if fillers=={'redraw'} and len(modes)>1 else set())
    if not fragments or None in decisive or len(decisive)!=1:
        raise ValueError('Ambiguous redraw reply; clarify the active image question')
    return decisive.pop()


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


def local_path(base, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Figure files must be relative and inside the input directory')
    path = (Path(base)/path).resolve()
    if not path.is_relative_to(Path(base).resolve()):
        raise ValueError('Figure path escapes the input directory')
    return path


def generate(document, base, output_dir, *, mode=None, response=None, previous=None, font_path=None):
    choice = plan(document,mode=mode,response=response)
    if choice['status']=='awaiting_confirmation':
        raise ValueError(PROMPT)
    base, output_dir = Path(base).resolve(),Path(output_dir).resolve()
    if not output_dir.is_relative_to(base):
        raise ValueError('Keep generated figures inside the input directory')
    ledger = {'schema_version':1,'task_id':choice['task_id'],'image_mode':choice['image_mode'],
              'text_hash':fingerprint(text_document(document)),'document':deepcopy(document),'records':[]}
    candidates = figures(document)
    if previous:
        if (previous.get('task_id')!=ledger['task_id'] or previous.get('image_mode')!=ledger['image_mode']
                or previous.get('text_hash')!=ledger['text_hash']):
            raise ValueError('A retry cannot change task, mode or completed text')
        old = {f['figure_id']:{k:v for k,v in f.items() if k!='drawing'} for f in figures(previous['document'])}
        new = {f['figure_id']:{k:v for k,v in f.items() if k!='drawing'} for f in candidates}
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
            if record.get('state') in {'validated','failed'}: continue
            if record['attempts'] and record['attempts'][-1].get('validation_status')!='major_issue':
                raise ValueError('Review the current candidate before trying again')
            if len(record['attempts'])>=MAX_ATTEMPTS:
                raise ValueError('Figure retry limit reached')
            if not figure.get('understanding') or figure.get('redrawable') is not True or figure.get('critical_uncertainty') is not False:
                raise ValueError('Figure structure cannot be reliably understood or redrawn')
            record.update(understood=True,redrawable=True)
            drawing = figure.get('drawing',{})
            structured = figure['figure_type']!='illustration'
            if structured and 'scene' not in drawing:
                raise ValueError('Technical diagrams require structured drawing')
            attempt = len(record['attempts'])+1
            png = output_dir/f'figure-{fid}-a{attempt}.png'
            svg = output_dir/f'figure-{fid}-a{attempt}.svg'
            if 'scene' in drawing:
                hashes = render(drawing['scene'],svg,png,understanding=figure['understanding'],font_path=font_path)
                svg_relative = svg.relative_to(base).as_posix()
                method = 'structured'
            else:
                generated = image_source(base,drawing['generated_png'])
                if generated.resolve()==source.resolve() or sha256(generated)==source_hash:
                    raise ValueError('A crop or copy is not a generated illustration')
                check_black_white(generated)
                png.parent.mkdir(parents=True,exist_ok=True)
                with png.open('xb') as stream: stream.write(generated.read_bytes())
                hashes = {'png_sha256':sha256(png)}
                svg_relative,method = None,'generative'
            check_black_white(png)
            entry = {'attempt':attempt,'png_path':png.relative_to(base).as_posix(),'svg_path':svg_relative,
                     'source_sha256':source_hash,'drawing_method':method,**hashes,'validation_status':'pending'}
            record['attempts'].append(entry)
            record.update(state='awaiting_validation',generated=True,failed=False)
        except (ValueError,KeyError,TypeError,OSError) as exc:
            record.update(state='failed',failed=True,reason=str(exc))
    return ledger


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
    check_black_white(local_path(base,entry['png_path']))
    return status


def complete(ledger, reviews, base):
    ledger = deepcopy(ledger)
    base = Path(base).resolve()
    rows = reviews.get('reviews',[]) if isinstance(reviews,dict) else reviews
    if not isinstance(rows,list): raise ValueError('Reviews must be a list')
    review_map = {}
    for row in rows:
        key = (row['figure_id'],row['attempt'])
        if key in review_map: raise ValueError('Duplicate review')
        review_map[key]=row
    pending,retries = [],[]
    definitions = {f['figure_id']:f for f in figures(ledger['document'])}
    for record in ledger['records']:
        if record['state'] not in {'awaiting_validation','needs_retry','validated'}: continue
        entry = record['attempts'][-1]
        review = review_map.get((record['figure_id'],entry['attempt']))
        if review is None and record['state']=='validated': review=entry['review']
        if review is None:
            pending.append(record['figure_id'])
            continue
        try:
            source = image_source(base,definitions[record['figure_id']]['source_path'])
            if sha256(source)!=record['source_sha256']:
                raise ValueError('Original source changed before visual review')
            status = review_candidate(entry,review,base)
            entry.update(validation_status=status,review=deepcopy(review))
            if status in {'pass','minor_issue'}:
                record.update(state='validated',validated=True,failed=False)
            elif status=='major_issue' and len(record['attempts'])<MAX_ATTEMPTS:
                record.update(state='needs_retry',validated=False)
                retries.append(record['figure_id'])
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
    for block in result['blocks']:
        if block.get('type')!='image':
            blocks.append(block)
            continue
        ordinal+=1
        record = records[block['figure_id']]
        if record['state']=='ignored': continue
        if record['state']=='preserved':
            blocks.append(block)
        elif record['state']=='validated':
            entry = record['attempts'][-1]
            block['path'] = entry['png_path']
            block['svg_path'] = entry['svg_path']
            block['redraw'] = {k:deepcopy(entry[k]) for k in ('source_sha256','png_sha256','drawing_method','review')}
            if 'svg_sha256' in entry: block['redraw']['svg_sha256']=entry['svg_sha256']
            block['figure'] = {k:deepcopy(record[k]) for k in ('figure_id','source_page','source_bbox','parent_block_id','figure_type','figure_group_id')}
            blocks.append(block)
        else:
            # Reader-facing position by document order; the internal id stays in figure_processing.
            blocks.append({'type':'text','text':f'[第{ordinal}张插图：无法可靠重绘]',
                           'layout':deepcopy(block.get('layout',{}))})
    result['blocks']=blocks
    result['figure_processing']={'task_id':ledger['task_id'],'image_mode':ledger['image_mode'],'status':'completed',
                                'failed_figures':[r['figure_id'] for r in ledger['records'] if r['failed']]}
    return result,ledger


def write_json(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)


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
        previous=json.loads(Path(args.previous).read_text(encoding='utf-8')) if args.previous else None
        ledger=generate(document,source.parent,args.output_dir,mode=args.image_mode,response=args.response,
                        previous=previous,font_path=args.font)
        write_json(args.ledger,ledger)
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
