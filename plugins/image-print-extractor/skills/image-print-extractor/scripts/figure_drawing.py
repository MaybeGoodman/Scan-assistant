"""Render host-understood diagrams as white/black SVG and PNG; never infer a scene."""
from copy import deepcopy
import functools
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
from _common import sha256

SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)
KINDS = {'line', 'polyline', 'polygon', 'circle', 'ellipse', 'rect', 'arc', 'curve', 'label'}
CHECKS = ('subject_count','connections','labels','arrow_directions','relative_positions',
          'geometry','coordinates','black_white','completeness','no_unrelated_elements','scientific_meaning')
MIN_PNG = (200, 150)  # Smallest accepted figure PNG (width, height) in pixels.
STYLES = {'italic', 'upright'}
# Label typography (REQUIREMENTS 25.1): bundled OFL serif first, then system serif fonts, then the
# former sans-serif list as a flagged fallback. CJK runs keep the system CJK fonts.
FONT_DIR = Path(__file__).resolve().parent.parent / 'assets' / 'fonts'
SERIF_FONTS = {
    'upright': [FONT_DIR / 'STIXTwoText-Regular.ttf', 'C:/Windows/Fonts/times.ttf',
                '/usr/share/texmf/fonts/opentype/public/lm/lmroman10-regular.otf',
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
                '/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf'],
    'italic': [FONT_DIR / 'STIXTwoText-Italic.ttf', 'C:/Windows/Fonts/timesi.ttf',
               '/usr/share/texmf/fonts/opentype/public/lm/lmroman10-italic.otf',
               '/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf',
               '/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf'],
}
SANS_FONTS = ['C:/Windows/Fonts/arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
              '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf', 'DejaVuSans.ttf']
CJK_FONTS = ['C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simsun.ttc',
             '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']
SVG_FONT_FAMILY = 'STIX Two Text,Times New Roman,Latin Modern Roman,Liberation Serif,Noto Sans CJK SC,Microsoft YaHei,serif'
# Multi-letter tokens that are set upright even though they are all letters (units, function names).
UPRIGHT_WORDS = {'cm', 'mm', 'km', 'kg', 'mL', 'ml', 'min', 'Pa', 'kPa', 'Hz', 'kW', 'kN', 'sin', 'cos', 'tan',
                 'lg', 'ln', 'log', 'max', 'const'}
ELEMENTS = {
    'H', 'He', 'Li', 'Be', 'B', 'C', 'N', 'O', 'F', 'Ne', 'Na', 'Mg', 'Al', 'Si', 'P', 'S', 'Cl', 'Ar',
    'K', 'Ca', 'Sc', 'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn', 'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr',
    'Rb', 'Sr', 'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd', 'In', 'Sn', 'Sb', 'Te', 'I', 'Xe',
    'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd', 'Tb', 'Dy', 'Ho', 'Er', 'Tm', 'Yb', 'Lu',
    'Hf', 'Ta', 'W', 'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg', 'Tl', 'Pb', 'Bi', 'Po', 'At', 'Rn',
    'Fr', 'Ra', 'Ac', 'Th', 'Pa', 'U', 'Np', 'Pu', 'Am', 'Cm', 'Bk', 'Cf', 'Es', 'Fm', 'Md', 'No', 'Lr',
    'Rf', 'Db', 'Sg', 'Bh', 'Hs', 'Mt', 'Ds', 'Rg', 'Cn', 'Nh', 'Fl', 'Mc', 'Lv', 'Ts', 'Og',
}
SUB_SCALE, SUB_SHIFT, SUP_SHIFT = .7, .25, -.4


def number(value):
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError('Coordinates and dimensions must be finite numbers')
    return float(value)


def point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('A point must contain x and y')
    return tuple(number(v) for v in value)


def label_runs(element):
    if ('text' in element) == ('runs' in element):
        raise ValueError('A label needs exactly one of text or runs')
    runs = element.get('runs', [{'text': element.get('text'), 'script': 'normal'}])
    if not isinstance(runs, list) or not runs:
        raise ValueError('Label runs must not be empty')
    for run in runs:
        if (not isinstance(run, dict) or not isinstance(run.get('text'), str)
                or not run['text'] or '\n' in run['text']
                or run.get('script', 'normal') not in {'normal', 'sub', 'sup'}
                or run.get('style', 'upright') not in STYLES
                or set(run) - {'text', 'script', 'style'}):
            raise ValueError('Invalid label run')
    if element.get('style', 'upright') not in STYLES:
        raise ValueError('Label style must be italic or upright')
    # Content only: style is typography and never part of the source-label comparison.
    return [{'text': run['text'], 'script': run.get('script', 'normal')} for run in runs]


def auto_style(text):
    """Textbook convention: letter symbols italic; digits, units, punctuation and CJK upright."""
    stripped = text.strip()
    if not stripped or stripped in UPRIGHT_WORDS:
        return 'upright'
    if all(('A' <= c <= 'Z') or ('a' <= c <= 'z') or ('α' <= c <= 'ω') for c in stripped):
        return 'italic'
    return 'upright'


def _element_tokens(word):
    """Return IUPAC element tokens if word consists solely of element symbols, else None."""
    if not word or word in UPRIGHT_WORDS or not ('A' <= word[0] <= 'Z'):
        return None
    tokens = re.findall(r'[A-Z][a-z]?', word)
    if ''.join(tokens) != word or any(tok not in ELEMENTS for tok in tokens):
        return None
    return tokens


def looks_chemical(runs):
    """Element symbols stay upright. Recognised: two-letter IUPAC element symbols (Na, Cl, Fe),
    multi-element groups before a numeric subscript (CO₂, SO₄), or an element followed by a numeric
    subscript and another element (H₂O, H₂SO₄, Ca(OH)₂). Math/physics labels like v₀t, R₁+R₂, x²+y,
    F₁=F₂, AB₁ stay italic. Single-letter formulas such as O₂ still need style: "upright"."""
    for index, run in enumerate(runs):
        text, script = run['text'], run.get('script', 'normal')
        if script == 'normal':
            for word in re.findall(r'[A-Za-z]+', text):
                tokens = _element_tokens(word)
                if tokens and any(len(tok) == 2 for tok in tokens):
                    return True
            following = runs[index + 1] if index + 1 < len(runs) else None
            if (following and following.get('script', 'normal') == 'sub'
                    and following['text'].strip().isdigit()):
                cleaned = re.sub(r'^[\s\d()\[\]·]+|[\s()\[\]·]+$', '', text)
                tokens = _element_tokens(cleaned)
                if tokens and len(tokens) >= 2:
                    return True
        elif script == 'sub' and text.strip().isdigit() and 0 < index < len(runs) - 1:
            prev, nxt = runs[index - 1], runs[index + 1]
            if prev.get('script', 'normal') == 'normal' and nxt.get('script', 'normal') == 'normal':
                prev_tail = re.sub(r'[\s)\]]+$', '', prev['text'])
                nxt_head = re.sub(r'^[\s(\[·]+', '', nxt['text'])
                prev_match = re.search(r'[A-Za-z]+$', prev_tail)
                nxt_match = re.match(r'[A-Za-z]+', nxt_head)
                if prev_match and nxt_match and _element_tokens(prev_match[0]) and _element_tokens(nxt_match[0]):
                    return True
    return False


def label_styles(element):
    """Per-run style: run.style, else element.style, else the automatic convention."""
    runs = element.get('runs', [{'text': element.get('text')}])
    default = element.get('style') or ('upright' if looks_chemical(runs) else None)
    return [run.get('style') or default or auto_style(run['text']) for run in runs]


def samples(element):
    kind = element['kind']
    if kind in {'line', 'polyline', 'polygon'}:
        points = [point(p) for p in element['points']]
        return points+[points[0]] if kind=='polygon' else points
    if kind == 'curve':
        p = [point(v) for v in element['points']]
        return [tuple((1-t)**3*p[0][a] + 3*(1-t)**2*t*p[1][a]
                      + 3*(1-t)*t*t*p[2][a] + t**3*p[3][a] for a in (0, 1))
                for t in (i / 160 for i in range(161))]
    if kind in {'circle', 'ellipse', 'arc'}:
        x, y = point(element['center'])
        rx = number(element.get('radius', element.get('rx', 0)))
        ry = number(element.get('radius', element.get('ry', 0)))
        start, end = (number(element.get('start', 0)), number(element.get('end', 360)))
        return [(x + rx*math.cos(math.radians(start+(end-start)*i/180)),
                 y + ry*math.sin(math.radians(start+(end-start)*i/180))) for i in range(181)]
    if kind == 'rect':
        x, y = point(element['at'])
        w, h = number(element['width']), number(element['height'])
        return [(x,y), (x+w,y), (x+w,y+h), (x,y+h), (x,y)]
    return [point(element['at'])]


def arrow_triangle(points, width, start=False):
    tip, back = (points[0], points[1]) if start else (points[-1], points[-2])
    dx, dy = tip[0]-back[0], tip[1]-back[1]
    length = math.hypot(dx, dy)
    if length < 1e-8:
        raise ValueError('Arrow direction must not be zero')
    ux, uy = dx/length, dy/length
    size = max(7, width*4)
    return [tip, (tip[0]-size*ux+size*.4*uy, tip[1]-size*uy-size*.4*ux),
            (tip[0]-size*ux-size*.4*uy, tip[1]-size*uy+size*.4*ux)]


def validate_scene(scene, understanding=None):
    if not isinstance(scene, dict) or set(scene) - {'width','height','elements','structure'}:
        raise ValueError('Unsupported scene field')
    w, h = number(scene['width']), number(scene['height'])
    if not (50 <= w <= 1200 and 50 <= h <= 1200):
        raise ValueError('Canvas dimensions must be between 50 and 1200')
    elements = scene['elements']
    if not isinstance(elements, list) or not 1 <= len(elements) <= 1000:
        raise ValueError('Scene must contain 1 to 1000 elements')
    ids = set()
    allowed = {'id','kind','object_id','points','center','radius','rx','ry','at','width',
               'height','start','end','fill','stroke_width','dash','arrow','text','runs',
               'size','anchor','label_id','connection','symbol','style'}
    for element in elements:
        if not isinstance(element, dict) or set(element) - allowed:
            extra = sorted(set(element) - allowed) if isinstance(element, dict) else []
            raise ValueError(f'Unsupported drawing attribute {extra}; only black/white primitives are allowed')
        eid = element.get('id')
        if not isinstance(eid, str) or not eid or eid in ids:
            raise ValueError(f'Every drawing element must have a unique id（重复或无效：{eid!r}）')
        ids.add(eid)
        if 'symbol' in element and (element['symbol'] is not True or '/' not in eid
                                    or not (element['kind'] == 'label' or element.get('arrow', 'none') != 'none')):
            raise ValueError(f'元素 {eid}：symbol 只用于组件展开产生的固定文字或箭头，不能手写')
        kind = element['kind']
        if kind not in KINDS or element.get('fill', 'none') not in {'none','black','white'}:
            raise ValueError('Unsupported primitive or non-black/white fill')
        stroke = number(element.get('stroke_width', 1.5))
        if not .5 <= stroke <= 12:
            raise ValueError('Line width must be printable')
        if kind in {'line','polyline','polygon','curve'}:
            pts = element.get('points')
            minimum = 3 if kind == 'polygon' else 2
            if (not isinstance(pts, list) or not minimum <= len(pts) <= 2000
                    or kind == 'line' and len(pts) != 2 or kind == 'curve' and len(pts) != 4):
                raise ValueError('Invalid primitive point count')
        if kind in {'circle','ellipse','arc'}:
            for key in (('radius',) if kind == 'circle' else ('rx','ry')):
                if not 0 < number(element[key]) <= 1200:
                    raise ValueError('Invalid radius')
        if kind == 'rect' and any(number(element[k]) <= 0 for k in ('width','height')):
            raise ValueError('Rectangle dimensions must be positive')
        if kind == 'arc' and not 0 < abs(number(element['end'])-number(element['start'])) <= 360:
            raise ValueError('Invalid arc span')
        arrow = element.get('arrow', 'none')
        if arrow not in {'none','start','end','both'} or arrow != 'none' and kind not in {'line','polyline','curve','arc'}:
            raise ValueError('Unsupported arrow')
        dash = element.get('dash', [])
        if not isinstance(dash, list) or len(dash) > 8 or any(not 0 < number(d) <= 100 for d in dash):
            raise ValueError('Invalid dash pattern')
        if kind == 'label':
            label_runs(element)
            if not 8 <= number(element.get('size', 18)) <= 72 or element.get('anchor','start') not in {'start','middle','end'}:
                raise ValueError('Invalid label size or anchor')
        base_pts = samples(element)
        pts = list(base_pts)
        if arrow in {'start','both'}:
            pts += arrow_triangle(base_pts, stroke, True)
        if arrow in {'end','both'}:
            pts += arrow_triangle(base_pts, stroke)
        margin = 0 if kind == 'label' else stroke/2
        if any(not (margin <= x <= w-margin and margin <= y <= h-margin) for x,y in pts):
            box = [round(min(x for x, _ in pts) - margin, 1), round(min(y for _, y in pts) - margin, 1),
                   round(max(x for x, _ in pts) + margin, 1), round(max(y for _, y in pts) + margin, 1)]
            raise ValueError(f'Drawing would be clipped by the canvas：元素 {eid} 越界，外框 {box}，'
                             f'画布 {w:g}×{h:g}；可加 fit 或调整坐标')
    if understanding is not None:
        validate_structure(scene, understanding)
    return scene


UNDERSTANDING_META_KEYS = frozenset({
    'fact_version', 'fact_changes', 'stem_context', 'source_context',
    'evidence', 'design_allowances', 'uncertainties', 'verification_targets',
})


def _structural_view(data):
    return {k: v for k, v in data.items() if k not in UNDERSTANDING_META_KEYS} if isinstance(data, dict) else data


def validate_structure(scene, expected):
    """Check declared source invariants plus actual labels/arrows/geometry; visual review is separate."""
    if not isinstance(expected, dict) or not expected.get('objects'):
        raise ValueError('A structured source understanding is required')
    actual_struct = scene.get('structure')
    if actual_struct != expected:
        if not isinstance(actual_struct, dict) or _structural_view(actual_struct) != _structural_view(expected):
            raise ValueError('Candidate structure differs from source understanding')
        # Any metadata key that IS present in scene.structure must still match expected
        for key in UNDERSTANDING_META_KEYS:
            if key in actual_struct and actual_struct[key] != expected.get(key):
                raise ValueError('Candidate structure differs from source understanding')
    objects = expected['objects']
    if not isinstance(objects, list) or any(not isinstance(o, dict) or not o.get('id') for o in objects):
        raise ValueError('Invalid source objects')
    ids = {o['id'] for o in objects}
    drawn = {e.get('object_id') for e in scene['elements']} - {None}
    if len(ids) != len(objects):
        raise ValueError('Object count or identity differs from source：原图理解中对象 id 重复')
    if drawn != ids:
        raise ValueError(f'Object count or identity differs from source：原图理解有而图中缺少 {sorted(ids - drawn)}；'
                         f'图中多出 {sorted(drawn - ids)}')
    for obj in objects:
        shapes=[e for e in scene['elements'] if e.get('object_id')==obj['id'] and e['kind']!='label']
        if obj.get('kind')=='circle' and (not any(e['kind']=='circle' for e in shapes) or any(e['kind']=='ellipse' for e in shapes)):
            raise ValueError('A source circle must not become an ellipse')
        if obj.get('kind')=='square' and not any(e['kind']=='rect' and abs(e['width']-e['height'])<=.005*max(e['width'],e['height']) for e in shapes):
            raise ValueError('A source square must preserve equal side lengths')
    by_id = {e['id']: e for e in scene['elements']}
    labels = expected.get('labels', [])
    # Fixed component text (meter letters, scale numbers) comes from component params, not source labels.
    actual_labels = [e for e in scene['elements'] if e['kind'] == 'label' and not e.get('symbol')]
    if len(labels) != len(actual_labels):
        wanted = sorted(str(label.get('id')) for label in labels)
        have = sorted(str(e.get('label_id')) for e in actual_labels)
        raise ValueError(f'Label count differs from source：原图理解 {len(labels)} 个，图中 {len(actual_labels)} 个；'
                         f'缺少 {sorted(set(wanted) - set(have))}，多出 {sorted(set(have) - set(wanted))}')
    for label in labels:
        matches = [e for e in actual_labels if e.get('label_id') == label['id']]
        if (len(matches) != 1 or matches[0].get('object_id') != label['target']
                or label_runs(matches[0]) != label_runs(label)):
            raise ValueError(f'Label content, script or target differs from source：标注 {label["id"]}')
    connections = expected.get('connections', [])
    for connection in connections:
        if not isinstance(connection, list) or len(connection) != 2 or not set(connection) <= ids:
            raise ValueError('Unknown connection endpoint')
    actual_connections = [e['connection'] for e in scene['elements'] if 'connection' in e]
    expected_pairs = sorted((str(c[0]), str(c[1])) for c in connections)
    actual_pairs = sorted(
        (str(c[0]), str(c[1])) if isinstance(c, list) and len(c) == 2 else (str(c),)
        for c in actual_connections
    )
    if expected_pairs != actual_pairs:
        missing = [list(c) for c in expected_pairs if expected_pairs.count(c) > actual_pairs.count(c)]
        extra = [list(c) for c in actual_pairs if actual_pairs.count(c) > expected_pairs.count(c)]
        raise ValueError(f'Connection topology differs from source：缺少 {missing}，多出 {extra}')
    arrows = expected.get('arrows', [])
    wanted = {a['element_id'] for a in arrows}
    have = {e['id'] for e in scene['elements'] if e.get('arrow','none') != 'none' and not e.get('symbol')}
    if wanted != have:
        raise ValueError(f'Arrow count differs from source：缺少 {sorted(wanted - have)}，多出 {sorted(have - wanted)}')
    for arrow in arrows:
        element = by_id[arrow['element_id']]
        pts = samples(element)
        dx, dy = point(arrow['direction'])
        if element.get('arrow') == 'both':
            if arrow.get('both') is not True:
                raise ValueError('Unexpected two-ended arrow')
        else:
            p, q = (pts[1],pts[0]) if element.get('arrow') == 'start' else (pts[-2],pts[-1])
            ax, ay = q[0]-p[0], q[1]-p[1]
            if math.hypot(dx,dy) == 0 or ax*dx+ay*dy <= 0 or abs(ax*dy-ay*dx) > .02*math.hypot(ax,ay)*math.hypot(dx,dy):
                raise ValueError('Arrow direction differs from source')
    for relation in expected.get('geometry', []):
        a, b = [by_id[name] for name in relation['elements']]
        kind = relation['kind']
        if kind in {'parallel','perpendicular','equal_length'}:
            pa, pb = samples(a), samples(b)
            va = (pa[-1][0]-pa[0][0],pa[-1][1]-pa[0][1])
            vb = (pb[-1][0]-pb[0][0],pb[-1][1]-pb[0][1])
            la, lb = math.hypot(*va), math.hypot(*vb)
            if la*lb == 0:
                raise ValueError('Degenerate geometry')
            error = abs(va[0]*vb[1]-va[1]*vb[0])/(la*lb) if kind == 'parallel' else abs(va[0]*vb[0]+va[1]*vb[1])/(la*lb) if kind == 'perpendicular' else abs(la-lb)/max(la,lb)
            if error > .005:
                raise ValueError('Geometry invariant violated: '+kind)
        else:
            raise ValueError('Unsupported automatic geometry relation; keep it in source facts and visual review')
    for curve in expected.get('curves',[]):
        pts=samples(by_id[curve['element_id']])
        xd,yd=number(curve.get('x_direction',1)),number(curve.get('y_direction',-1))
        if xd not in {-1,1} or yd not in {-1,1} or curve.get('trend') not in {'increasing','decreasing'}:
            raise ValueError('Unsupported automatic curve trend')
        sign=1 if curve['trend']=='increasing' else -1
        if any((q[0]-p[0])*xd<-.001 or (q[1]-p[1])*yd*sign<-.001 for p,q in zip(pts,pts[1:])):
            raise ValueError('Curve trend differs from source')


@functools.lru_cache(maxsize=128)
def _truetype(path_str, size):
    font = ImageFont.truetype(path_str, size)
    return font, bytes(font.getmask('\U0010ffff'))


def _load(candidates, size, text):
    for candidate in candidates:
        if not candidate:
            continue
        try:
            font, missing = _truetype(str(candidate), size)
            if any(not char.isspace() and bytes(font.getmask(char)) == missing for char in text):
                continue
            return font
        except OSError:
            continue
    return None


def _is_cjk(char):
    return ('\u2e80' <= char <= '\u9fff'
            or '\uf900' <= char <= '\ufaff'
            or '\uff00' <= char <= '\uffef')


def pick_font(size, text, font_path=None, style='upright'):
    """Return (font, fallback). An explicit font_path is final and never falls back. Otherwise CJK
    text uses the system CJK fonts; other text uses the bundled/system serif of the wanted style and
    only then the sans-serif list, which is reported as fallback=True (REQUIREMENTS 25.1)."""
    if font_path:
        font = _load([font_path], size, text)
        if font is None:
            raise ValueError('No font supports the labels; provide --font (CJK labels need a CJK font)')
        return font, False
    if any(_is_cjk(char) for char in text):
        font = _load(CJK_FONTS, size, text)
        if font is None:
            raise ValueError('No font supports the labels; provide --font (CJK labels need a CJK font)')
        return font, False
    if style not in STYLES:
        raise ValueError('Label style must be italic or upright')
    font = _load(SERIF_FONTS[style], size, text)
    if font is not None:
        return font, False
    font = _load(SANS_FONTS, size, text)
    if font is None:
        raise ValueError('No font supports the labels; provide --font (CJK labels need a CJK font)')
    return font, True


def get_font(size, text, font_path=None, style='upright'):
    return pick_font(size, text, font_path, style)[0]


def layout_label(element, font_path=None, scale=1):
    """Shared by render and canvas fitting: fonts, per-run x offsets, baseline shifts (in scaled pixels).
    Returns {'x', 'y', 'runs': [{'text','script','style','font','dx','dy','width'}], 'fallback'}."""
    x, y = point(element['at'])
    size = element.get('size', 18)
    runs, styles = label_runs(element), label_styles(element)
    laid, fallback, widths = [], False, []
    for run, style in zip(runs, styles):
        run_size = max(1, round(size * scale * (1 if run['script'] == 'normal' else SUB_SCALE)))
        font, fell = pick_font(run_size, run['text'], font_path, style)
        fallback = fallback or fell
        widths.append(font.getlength(run['text']))
        laid.append({**run, 'style': style, 'font': font, 'width': widths[-1],
                     'dy': 0 if run['script'] == 'normal' else size * scale * (SUB_SHIFT if run['script'] == 'sub' else SUP_SHIFT)})
    cursor = x * scale - sum(widths) * {'start': 0, 'middle': .5, 'end': 1}[element.get('anchor', 'start')]
    for run in laid:
        run['dx'] = cursor
        cursor += run['width']
    return {'x': x, 'y': y, 'size': size, 'runs': laid, 'fallback': fallback}


def dashed_segments(points, dash):
    if not dash:
        return [points]
    result, index, remaining, visible = [], 0, dash[0], True
    for p,q in zip(points,points[1:]):
        length = math.dist(p,q)
        if not length:
            continue
        offset = 0
        while offset < length-1e-8:
            step = min(remaining,length-offset)
            if visible:
                result.append([(p[0]+(q[0]-p[0])*offset/length,p[1]+(q[1]-p[1])*offset/length),
                               (p[0]+(q[0]-p[0])*(offset+step)/length,p[1]+(q[1]-p[1])*(offset+step)/length)])
            offset += step
            remaining -= step
            if remaining < 1e-8:
                index = (index+1)%len(dash)
                remaining, visible = dash[index], not visible
    return result


def render(scene, svg_path, png_path, *, understanding=None, scale=3, font_path=None):
    from figure_components import expand_scene
    scene = expand_scene(scene, understanding=understanding, font_path=font_path)
    scene = deepcopy(validate_scene(scene, understanding))
    if type(scale) is not int or not 2 <= scale <= 4:
        raise ValueError('PNG scale must be 2 to 4')
    # Small valid canvases are upscaled (at most 4x) to reach the PNG size that
    # check_black_white requires, instead of failing after rendering.
    scale = max(scale, math.ceil(MIN_PNG[0] / scene['width']), math.ceil(MIN_PNG[1] / scene['height']))
    svg_path, png_path = Path(svg_path), Path(png_path)
    if svg_path.exists() or png_path.exists() or svg_path.resolve() == png_path.resolve():
        raise FileExistsError('Drawing outputs must be separate new files')
    w,h = scene['width'],scene['height']
    root = ET.Element('{'+SVG+'}svg', {'width':str(w),'height':str(h),'viewBox':f'0 0 {w} {h}'})
    ET.SubElement(root,'{'+SVG+'}rect',{'width':'100%','height':'100%','fill':'white'})
    image = Image.new('RGB',(round(w*scale),round(h*scale)),'white')
    draw = ImageDraw.Draw(image)
    def scaled(pts):
        return [(round(x*scale),round(y*scale)) for x,y in pts]
    font_fallback = False
    for element in scene['elements']:
        kind,pts = element['kind'],samples(element)
        stroke = element.get('stroke_width',1.5)
        if kind == 'label':
            laid = layout_label(element, font_path, scale)
            font_fallback = font_fallback or laid['fallback']
            x,y,size = laid['x'],laid['y'],laid['size']
            text = ET.SubElement(root,'{'+SVG+'}text',{'x':str(x),'y':str(y),'fill':'black','font-size':str(size),
                'font-family':SVG_FONT_FAMILY,'text-anchor':element.get('anchor','start')})
            for run in laid['runs']:
                origin = (run['dx'], y*scale+run['dy'])
                box = draw.textbbox(origin,run['text'],font=run['font'],anchor='ls')
                if box[0]<0 or box[1]<0 or box[2]>image.width or box[3]>image.height:
                    raise ValueError(f'Label would be clipped; enlarge canvas or move the label：元素 {element["id"]}，'
                                     f'外框 {[round(v / scale, 1) for v in box]}，画布 {w:g}×{h:g}')
                draw.text(origin,run['text'],font=run['font'],fill='black',anchor='ls')
                attrs = {'baseline-shift':{'normal':'baseline','sub':'sub','sup':'super'}[run['script']],
                         'font-size':str(size*(1 if run['script']=='normal' else SUB_SCALE))}
                if run['style'] == 'italic':
                    attrs['font-style'] = 'italic'
                span = ET.SubElement(text,'{'+SVG+'}tspan',attrs)
                span.text = run['text']
            continue
        if kind in {'polygon','rect','circle','ellipse'} and element.get('fill','none') != 'none':
            draw.polygon(scaled(pts),fill=element['fill'])
        paths = dashed_segments(pts,element.get('dash',[]))
        for path in paths:
            draw.line(scaled(path),fill='black',width=max(1,round(stroke*scale)),joint='curve')
        attrs = {'id':element['id'],'fill':element.get('fill','none'),'stroke':'black','stroke-width':str(stroke),'stroke-linejoin':'round','stroke-linecap':'round'}
        if element.get('dash'):
            attrs['stroke-dasharray'] = ' '.join(map(str,element['dash']))
        if kind == 'curve':
            p = [point(v) for v in element['points']]
            attrs['d'] = f'M {p[0][0]} {p[0][1]} C '+ ' '.join(f'{x} {y}' for x,y in p[1:])
            ET.SubElement(root,'{'+SVG+'}path',attrs)
        elif kind in {'circle','ellipse'}:
            x,y = point(element['center'])
            attrs.update(cx=str(x),cy=str(y))
            if kind == 'circle': attrs['r']=str(element['radius'])
            else: attrs.update(rx=str(element['rx']),ry=str(element['ry']))
            ET.SubElement(root,'{'+SVG+'}'+kind,attrs)
        else:
            attrs['points']=' '.join(f'{x},{y}' for x,y in pts)
            ET.SubElement(root,'{'+SVG+'}'+('polygon' if kind=='polygon' else 'polyline'),attrs)
        for start in ([True,False] if element.get('arrow')=='both' else [True] if element.get('arrow')=='start' else [False] if element.get('arrow')=='end' else []):
            triangle = arrow_triangle(pts,stroke,start)
            draw.polygon(scaled(triangle),fill='black')
            ET.SubElement(root,'{'+SVG+'}polygon',{'points':' '.join(f'{x},{y}' for x,y in triangle),'fill':'black'})
    # Hard two-color raster; text antialiasing is thresholded after high-resolution drawing.
    image = image.convert('L').point(lambda p: 255 if p>=160 else 0).convert('RGB')
    svg_path.parent.mkdir(parents=True,exist_ok=True)
    png_path.parent.mkdir(parents=True,exist_ok=True)
    created=[]
    try:
        with svg_path.open('xb') as stream:
            created.append(svg_path)
            stream.write(ET.tostring(root,encoding='utf-8',xml_declaration=True))
        with png_path.open('xb') as stream:
            created.append(png_path)
            # Keep the physical size independent of the upscale: 100 scene units per inch.
            dpi = 100 * scale
            image.save(stream,format='PNG',dpi=(dpi,dpi))
    except Exception:
        for path in created: path.unlink(missing_ok=True)
        raise
    result = {'png_sha256':sha256(png_path),'svg_sha256':sha256(svg_path),'size':list(image.size)}
    if font_fallback:
        result['font_fallback'] = True  # serif fonts unavailable; review may not pass as 'pass'
    return result


def check_black_white(path):
    with Image.open(path) as image:
        if image.format!='PNG' or image.width<MIN_PNG[0] or image.height<MIN_PNG[1]:
            raise ValueError('Expected a sufficiently large PNG')
        rgb=image.convert('RGBA')
        colors=rgb.getcolors(3)
        if not colors or any(color not in {(0,0,0,255),(255,255,255,255)} for _,color in colors):
            raise ValueError('Figure must be opaque pure white and black')
        if {color for _,color in colors}!={(0,0,0,255),(255,255,255,255)}:
            raise ValueError('Figure must contain both white background and black content')
    return True


def validate_redraw_metadata(block):
    data=block.get('redraw')
    if not isinstance(data,dict): raise ValueError('Invalid redraw metadata')
    review=data.get('review',{})
    checks=review.get('checks',{})
    if (review.get('status') not in {'pass','minor_issue'} or review.get('reviewed_by')!='host_vision'
            or set(checks)!=set(CHECKS) or any(v is not True for v in checks.values())):
        raise ValueError('Redrawn images require a complete passing host visual review')
    for key in ('source_sha256','png_sha256'):
        value=data.get(key)
        if (not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value)
                or review.get(key)!=value):
            raise ValueError('Redraw review must bind source and generated hashes')
    if block.get('svg_path') and (not data.get('svg_sha256') or review.get('svg_sha256')!=data['svg_sha256']):
        raise ValueError('SVG review hash is missing or mismatched')


def safe_svg(path):
    data=Path(path).read_bytes()
    if len(data)>2_000_000 or b'<!' in data:
        raise ValueError('SVG declarations and external entities are forbidden')
    root=ET.fromstring(data)
    tags={'svg','rect','polygon','polyline','path','circle','ellipse','text','tspan'}
    attrs={'width','height','viewBox','fill','stroke','stroke-width','stroke-linejoin','stroke-linecap',
           'stroke-dasharray','id','points','d','cx','cy','r','rx','ry','x','y','font-size','font-family',
           'text-anchor','baseline-shift','font-style'}
    if root.tag!='{'+SVG+'}svg': raise ValueError('Expected SVG root')
    for element in root.iter():
        if element.tag not in {'{'+SVG+'}'+tag for tag in tags} or set(element.attrib)-attrs:
            raise ValueError('SVG supports only local inert drawing primitives')
        for attribute in ('stroke','fill'):
            if element.get(attribute,'none') not in {'black','white','none'}:
                raise ValueError('SVG must use only black and white')
    return path


def check_print_readability(scene, *, font_path=None, target_width_mm=80.0, min_label_mm=1.4):
    """Deterministic print-readability check at equivalent print width (V1.1 Section 5.3)."""
    from figure_components import check_label_overlaps, expand_scene
    expanded = expand_scene(scene, font_path=font_path)
    width = number(expanded['width'])
    mm_per_unit = target_width_mm / width
    labels = [e for e in expanded['elements'] if isinstance(e, dict) and e.get('kind') == 'label']
    min_size = min((number(e.get('size', 18)) for e in labels), default=None)
    min_mm = round(min_size * mm_per_unit, 2) if min_size is not None else None
    overlaps = check_label_overlaps(expanded['elements'], font_path=font_path)
    issues = []
    if overlaps:
        issues.append(f'存在重叠标注：{overlaps}')
    if min_mm is not None and min_mm < min_label_mm:
        issues.append(f'最小标注在 {target_width_mm:g} mm 宽度下仅 {min_mm:.2f} mm（低于 {min_label_mm:g} mm 阈值）')
    return {
        'ok': not issues,
        'target_width_mm': target_width_mm,
        'canvas_size': [expanded['width'], expanded['height']],
        'min_label_mm': min_mm,
        'label_overlaps': overlaps,
        'issues': issues,
    }


def render_placeholder_tile(label_text, output_png, *, width_px=600, height_px=450, dpi=300, font_path=None):
    """Render a crisp B/W framed placeholder tile for partial subfigure fallback inside a figure group."""
    output_png = Path(output_png)
    if output_png.exists():
        raise FileExistsError(output_png)
    image = Image.new('RGB', (width_px, height_px), 'white')
    draw = ImageDraw.Draw(image)
    pad = 12
    draw.rectangle((pad, pad, width_px - pad, height_px - pad), outline='black', width=3)
    text = f'[{label_text}]' if not (label_text.startswith('[') and label_text.endswith(']')) else label_text
    font_size = max(18, min(32, width_px // max(12, len(text) + 2)))
    font, _ = pick_font(font_size, text, font_path=font_path, style='upright')
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = max(pad + 8, (width_px - tw) // 2)
    ty = max(pad + 8, (height_px - th) // 2)
    draw.text((tx, ty), text, font=font, fill='black')
    image = image.convert('L').point(lambda p: 255 if p >= 160 else 0).convert('RGB')
    output_png.parent.mkdir(parents=True, exist_ok=True)
    with output_png.open('xb') as stream:
        image.save(stream, format='PNG', dpi=(dpi, dpi))
    return {'png_sha256': sha256(output_png), 'size': [width_px, height_px]}


def _shift_svg_element(el, dx, dy, prefix):
    """Return a deep copy of an SVG primitive shifted by (dx, dy) in SVG user units."""
    out = deepcopy(el)
    if 'id' in out.attrib:
        out.attrib['id'] = f'{prefix}__{out.attrib["id"]}'
    tag = out.tag.split('}')[-1]
    if tag in {'rect', 'text'}:
        if 'x' in out.attrib:
            out.attrib['x'] = f'{float(out.attrib["x"]) + dx:g}'
        if 'y' in out.attrib:
            out.attrib['y'] = f'{float(out.attrib["y"]) + dy:g}'
    elif tag in {'circle', 'ellipse'}:
        out.attrib['cx'] = f'{float(out.attrib["cx"]) + dx:g}'
        out.attrib['cy'] = f'{float(out.attrib["cy"]) + dy:g}'
    elif tag in {'polygon', 'polyline'}:
        pairs = []
        for token in out.attrib.get('points', '').split():
            xs, ys = token.split(',')
            pairs.append(f'{float(xs) + dx:g},{float(ys) + dy:g}')
        out.attrib['points'] = ' '.join(pairs)
    elif tag == 'path':
        # Our renderer only emits 'M x y C x1 y1 x2 y2 x3 y3'
        tokens = out.attrib.get('d', '').split()
        shifted = []
        i = 0
        while i < len(tokens):
            if tokens[i] in {'M', 'L', 'C'}:
                cmd = tokens[i]
                shifted.append(cmd)
                i += 1
                count = 3 if cmd == 'C' else 1
                for _ in range(count):
                    shifted.append(f'{float(tokens[i]) + dx:g}')
                    shifted.append(f'{float(tokens[i + 1]) + dy:g}')
                    i += 2
            else:
                shifted.append(tokens[i])
                i += 1
        out.attrib['d'] = ' '.join(shifted)
    return out


def compose_group_tiles(tiles, output_png, *, output_svg=None, layout=None, font_path=None):
    """Compose subfigure tiles into one figure-group PNG (and combined safe SVG if all tiles are structured SVGs).

    Returns {'png_sha256', 'size', 'subfigure_regions': {subid: [x, y, w, h]},
             'svg_sha256' (optional), 'contains_original_fallback': bool}.
    """
    if not tiles:
        raise ValueError('图组至少需要一个子图分区')
    layout = layout or {}
    mode = layout.get('mode', 'horizontal')
    if mode not in {'horizontal', 'vertical', 'grid'}:
        raise ValueError('图组 layout.mode 只能为 horizontal、vertical 或 grid')
    gap = int(layout.get('gap', 36))
    padding = int(layout.get('padding', 24))
    caption_pos = layout.get('caption_position', 'none')
    if caption_pos not in {'none', 'bottom', 'top'}:
        raise ValueError('图组 layout.caption_position 只能为 none、bottom 或 top')

    loaded = []
    has_original_fallback = False
    for tile in tiles:
        p = Path(tile['png_path'])
        with Image.open(p) as im:
            im.load()
            rgb = im.convert('RGB')
            dpi = im.info.get('dpi', (300, 300))[0]
        if tile.get('is_original_fallback'):
            has_original_fallback = True
        loaded.append({**tile, 'image': rgb, 'w': rgb.width, 'h': rgb.height,
                       'dpi': float(dpi) if isinstance(dpi, (int, float)) and 72 <= dpi <= 1200 else 300.0})

    caption_h = 44 if (caption_pos != 'none' and any(t.get('label') for t in loaded)) else 0
    n = len(loaded)
    if mode == 'horizontal':
        cols = n
    elif mode == 'vertical':
        cols = 1
    else:
        cols = int(layout.get('cols', math.ceil(math.sqrt(n))))
        if cols < 1:
            raise ValueError('layout.cols 必须为正整数')
    rows = math.ceil(n / cols)

    col_w = [0] * cols
    row_h = [0] * rows
    for idx, t in enumerate(loaded):
        r, c = divmod(idx, cols)
        col_w[c] = max(col_w[c], t['w'])
        row_h[r] = max(row_h[r], t['h'] + caption_h)

    total_w = padding * 2 + sum(col_w) + gap * (cols - 1)
    total_h = padding * 2 + sum(row_h) + gap * (rows - 1)
    canvas = Image.new('RGB', (total_w, total_h), 'white')
    draw = ImageDraw.Draw(canvas)
    regions = {}

    y_cursor = padding
    for r in range(rows):
        x_cursor = padding
        for c in range(cols):
            idx = r * cols + c
            if idx >= n:
                break
            t = loaded[idx]
            tile_x = x_cursor + (col_w[c] - t['w']) // 2
            tile_y = y_cursor + (caption_h if caption_pos == 'top' else 0) + (row_h[r] - caption_h - t['h']) // 2
            canvas.paste(t['image'], (tile_x, tile_y))
            regions[t['subfigure_id']] = [tile_x, tile_y, t['w'], t['h']]
            if caption_h and t.get('label'):
                lbl = str(t['label'])
                font, _ = pick_font(30, lbl, font_path=font_path, style='upright')
                bbox = draw.textbbox((0, 0), lbl, font=font)
                tw = bbox[2] - bbox[0]
                cx = x_cursor + (col_w[c] - tw) // 2
                cy = y_cursor + 4 if caption_pos == 'top' else (y_cursor + row_h[r] - caption_h + 6)
                draw.text((cx, cy), lbl, font=font, fill='black')
            x_cursor += col_w[c] + gap
        y_cursor += row_h[r] + gap

    if not has_original_fallback:
        canvas = canvas.convert('L').point(lambda p: 255 if p >= 160 else 0).convert('RGB')

    output_png = Path(output_png)
    if output_png.exists():
        raise FileExistsError(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    created = []
    result = {'size': [total_w, total_h], 'subfigure_regions': regions,
              'contains_original_fallback': has_original_fallback}
    try:
        with output_png.open('xb') as stream:
            created.append(output_png)
            canvas.save(stream, format='PNG', dpi=(300, 300))
        result['png_sha256'] = sha256(output_png)

        # Compose combined SVG only when requested AND every tile has a valid structured SVG
        if output_svg is not None and all(t.get('svg_path') for t in loaded) and not has_original_fallback:
            output_svg = Path(output_svg)
            if output_svg.exists():
                raise FileExistsError(output_svg)
            scale = 3.0  # Standard 3x PNG-to-SVG ratio (300 dpi = 100 scene units/inch)
            svg_w, svg_h = round(total_w / scale, 2), round(total_h / scale, 2)
            root = ET.Element('{' + SVG + '}svg', {'width': str(svg_w), 'height': str(svg_h),
                                                    'viewBox': f'0 0 {svg_w} {svg_h}'})
            ET.SubElement(root, '{' + SVG + '}rect', {'width': '100%', 'height': '100%', 'fill': 'white'})
            for t in loaded:
                tx, ty, tw, th = regions[t['subfigure_id']]
                sub_root = ET.fromstring(Path(t['svg_path']).read_bytes())
                sub_w = float(sub_root.attrib['width'])
                sub_scale = tw / sub_w if sub_w > 0 else scale
                dx, dy = tx / sub_scale, ty / sub_scale
                for child in sub_root:
                    # Skip background white full-canvas rect of child SVG
                    if child.tag == '{' + SVG + '}rect' and child.attrib.get('width') == '100%' and child.attrib.get('height') == '100%':
                        continue
                    root.append(_shift_svg_element(child, dx, dy, t['subfigure_id']))
                if caption_h and t.get('label'):
                    lbl = str(t['label'])
                    cx = round((tx + tw / 2) / scale, 2)
                    cy = round(((ty - 10) if caption_pos == 'top' else (ty + th + 28)) / scale, 2)
                    txt_el = ET.SubElement(root, '{' + SVG + '}text', {
                        'x': str(cx), 'y': str(cy), 'fill': 'black', 'font-size': '12',
                        'font-family': SVG_FONT_FAMILY, 'text-anchor': 'middle',
                    })
                    txt_el.text = lbl
            output_svg.parent.mkdir(parents=True, exist_ok=True)
            with output_svg.open('xb') as stream:
                created.append(output_svg)
                stream.write(ET.tostring(root, encoding='utf-8', xml_declaration=True))
            safe_svg(output_svg)
            result['svg_sha256'] = sha256(output_svg)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return result


def verify_unchanged_regions(old_png, old_regions, new_png, new_regions, untouched_ids):
    """Verify pixel-for-pixel identity of untouched subfigures after local repair & re-composition (V1.1 5.2)."""
    with Image.open(old_png) as old_im, Image.open(new_png) as new_im:
        old_rgb = old_im.convert('RGB')
        new_rgb = new_im.convert('RGB')
        for sid in untouched_ids:
            if sid not in old_regions or sid not in new_regions:
                raise ValueError(f'局部返修对比缺少未修改分区 {sid} 的区域信息')
            ox, oy, ow, oh = old_regions[sid]
            nx, ny, nw, nh = new_regions[sid]
            if (ow, oh) != (nw, nh):
                raise ValueError(f'未修改分区 {sid} 尺寸发生变化：{ow}×{oh} -> {nw}×{nh}')
            crop_old = old_rgb.crop((ox, oy, ox + ow, oy + oh))
            crop_new = new_rgb.crop((nx, ny, nx + nw, ny + nh))
            if crop_old.tobytes() != crop_new.tobytes():
                raise ValueError(f'未修改分区 {sid} 的像素内容在局部返修后发生变化')
    return True

