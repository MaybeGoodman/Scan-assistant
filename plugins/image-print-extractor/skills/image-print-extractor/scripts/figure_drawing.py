"""Render host-understood diagrams as white/black SVG and PNG; never infer a scene."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont

SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)
KINDS = {'line', 'polyline', 'polygon', 'circle', 'ellipse', 'rect', 'arc', 'curve', 'label'}
CHECKS = ('subject_count','connections','labels','arrow_directions','relative_positions',
          'geometry','coordinates','black_white','completeness','no_unrelated_elements','scientific_meaning')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
                or set(run) - {'text', 'script'}):
            raise ValueError('Invalid label run')
    return [{'text': run['text'], 'script': run.get('script', 'normal')} for run in runs]


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
               'size','anchor','label_id','connection'}
    for element in elements:
        if not isinstance(element, dict) or set(element) - allowed:
            raise ValueError('Unsupported drawing attribute; only black/white primitives are allowed')
        eid = element.get('id')
        if not isinstance(eid, str) or not eid or eid in ids:
            raise ValueError('Every drawing element must have a unique id')
        ids.add(eid)
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
        pts = samples(element)
        if arrow in {'start','both'}:
            pts += arrow_triangle(samples(element), stroke, True)
        if arrow in {'end','both'}:
            pts += arrow_triangle(samples(element), stroke)
        margin = 0 if kind == 'label' else stroke/2
        if any(not (margin <= x <= w-margin and margin <= y <= h-margin) for x,y in pts):
            raise ValueError('Drawing would be clipped by the canvas')
    if understanding is not None:
        validate_structure(scene, understanding)
    return scene


def validate_structure(scene, expected):
    """Check declared source invariants plus actual labels/arrows/geometry; visual review is separate."""
    if not isinstance(expected, dict) or not expected.get('objects'):
        raise ValueError('A structured source understanding is required')
    if scene.get('structure') != expected:
        raise ValueError('Candidate structure differs from source understanding')
    objects = expected['objects']
    if not isinstance(objects, list) or any(not isinstance(o, dict) or not o.get('id') for o in objects):
        raise ValueError('Invalid source objects')
    ids = {o['id'] for o in objects}
    if len(ids) != len(objects) or {e.get('object_id') for e in scene['elements']} - {None} != ids:
        raise ValueError('Object count or identity differs from source')
    for obj in objects:
        shapes=[e for e in scene['elements'] if e.get('object_id')==obj['id'] and e['kind']!='label']
        if obj.get('kind')=='circle' and (not any(e['kind']=='circle' for e in shapes) or any(e['kind']=='ellipse' for e in shapes)):
            raise ValueError('A source circle must not become an ellipse')
        if obj.get('kind')=='square' and not any(e['kind']=='rect' and abs(e['width']-e['height'])<=.005*max(e['width'],e['height']) for e in shapes):
            raise ValueError('A source square must preserve equal side lengths')
    by_id = {e['id']: e for e in scene['elements']}
    labels = expected.get('labels', [])
    actual_labels = [e for e in scene['elements'] if e['kind'] == 'label']
    if len(labels) != len(actual_labels):
        raise ValueError('Label count differs from source')
    for label in labels:
        matches = [e for e in actual_labels if e.get('label_id') == label['id']]
        if (len(matches) != 1 or matches[0].get('object_id') != label['target']
                or label_runs(matches[0]) != label_runs(label)):
            raise ValueError('Label content, script or target differs from source')
    connections = expected.get('connections', [])
    actual_connections = [e['connection'] for e in scene['elements'] if 'connection' in e]
    if sorted(map(str,connections)) != sorted(map(str,actual_connections)):
        raise ValueError('Connection topology differs from source')
    for connection in connections:
        if not isinstance(connection, list) or len(connection) != 2 or not set(connection) <= ids:
            raise ValueError('Unknown connection endpoint')
    arrows = expected.get('arrows', [])
    if {a['element_id'] for a in arrows} != {e['id'] for e in scene['elements'] if e.get('arrow','none') != 'none'}:
        raise ValueError('Arrow count differs from source')
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


def get_font(size, text, font_path=None):
    cjk = any('\u2e80' <= char <= '\uffff' for char in text)
    candidates = [font_path] if font_path else ([
        'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simsun.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    ] if cjk else []) + [
        'C:/Windows/Fonts/arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf', 'DejaVuSans.ttf',
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            font = ImageFont.truetype(str(candidate), size)
            missing = bytes(font.getmask('\U0010ffff'))
            if any(not char.isspace() and bytes(font.getmask(char)) == missing for char in text):
                continue
            return font
        except OSError:
            continue
    raise ValueError('No font supports the labels; provide --font (CJK labels need a CJK font)')


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
    scene = deepcopy(validate_scene(scene, understanding))
    if type(scale) is not int or not 2 <= scale <= 4:
        raise ValueError('PNG scale must be 2 to 4')
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
    for element in scene['elements']:
        kind,pts = element['kind'],samples(element)
        stroke = element.get('stroke_width',1.5)
        if kind == 'label':
            x,y = pts[0]
            size = element.get('size',18)
            runs = label_runs(element)
            fonts = [get_font(round(size*scale*(1 if r['script']=='normal' else .7)),r['text'],font_path) for r in runs]
            widths = [font.getlength(r['text']) for font,r in zip(fonts,runs)]
            anchor = element.get('anchor','start')
            cursor = x*scale - sum(widths)*({'start':0,'middle':.5,'end':1}[anchor])
            text = ET.SubElement(root,'{'+SVG+'}text',{'x':str(x),'y':str(y),'fill':'black','font-size':str(size),
                'font-family':'Noto Sans CJK SC,Microsoft YaHei,DejaVu Sans,sans-serif','text-anchor':anchor})
            for font,run,width in zip(fonts,runs,widths):
                shift = 0 if run['script']=='normal' else size*scale*(.22 if run['script']=='sub' else -.4)
                box = draw.textbbox((cursor,y*scale+shift),run['text'],font=font,anchor='ls')
                if box[0]<0 or box[1]<0 or box[2]>image.width or box[3]>image.height:
                    raise ValueError('Label would be clipped; enlarge canvas or move the label')
                draw.text((cursor,y*scale+shift),run['text'],font=font,fill='black',anchor='ls')
                span = ET.SubElement(text,'{'+SVG+'}tspan',{'baseline-shift':{'normal':'baseline','sub':'sub','sup':'super'}[run['script']],
                    'font-size':str(size*(1 if run['script']=='normal' else .7))})
                span.text = run['text']
                cursor += width
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
            image.save(stream,format='PNG',dpi=(300,300))
    except Exception:
        for path in created: path.unlink(missing_ok=True)
        raise
    return {'png_sha256':sha256(png_path),'svg_sha256':sha256(svg_path),'size':list(image.size)}


def check_black_white(path):
    with Image.open(path) as image:
        if image.format!='PNG' or image.width<200 or image.height<150:
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
           'text-anchor','baseline-shift'}
    if root.tag!='{'+SVG+'}svg': raise ValueError('Expected SVG root')
    for element in root.iter():
        if element.tag not in {'{'+SVG+'}'+tag for tag in tags} or set(element.attrib)-attrs:
            raise ValueError('SVG supports only local inert drawing primitives')
        for attribute in ('stroke','fill'):
            if element.get(attribute,'none') not in {'black','white','none'}:
                raise ValueError('SVG must use only black and white')
    return path
