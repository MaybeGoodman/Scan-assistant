"""Expand host-described components, wires and junctions into the existing black/white primitives.

The host still decides what the original figure contains (understanding) and where each part
goes; this module only turns "a lamp at (x, y)" or "a wire from B1.b to S1.a" into lines,
circles and labels, optionally fits the canvas to the content, and then hands the result to the
unchanged validate_scene/validate_structure/render. It never infers scientific content.

Standard sizes (scene units, size=1, orientation "h"; the local origin is the component centre,
except axes, whose origin is the axis origin):
  lamp r=12; resistor 36x14; rheostat 44x14 with slider 13 above; battery 12 per cell + 8 leads;
  switch contacts 32 apart, open blade rises 13; switch_spdt 32 wide, contacts +-12;
  ammeter/voltmeter/motor r=13; meter_dial arc radius 60 over 210-330 degrees;
  beaker 60x72; test_tube 16x78; flask bulb r=28, neck 14 wide; alcohol_lamp 52 wide;
  iron_stand base 90x10, rod 132 high; thermometer tube 8 wide, 105 long, bulb r=7;
  asbestos_net 70x6; axes 160x110 by default.
"""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import sys

ORIENTATIONS = {'h': (0, False), 'h-flip': (0, True), 'v': (90, False), 'v-flip': (90, True)}
EXTENDED = {'component', 'wire', 'junction'}
ROUTES = {'direct', 'hv', 'vh', 'manual'}
WIRE_KEYS = {'id', 'kind', 'from', 'to', 'route', 'via', 'connection', 'stroke_width', 'dash', 'arrow'}
COMPONENT_KEYS = {'id', 'kind', 'type', 'object_id', 'at', 'orientation', 'size', 'params'}
JUNCTION_KEYS = {'id', 'kind', 'at', 'object_id', 'radius'}


def num(value, what):
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError(f'{what} 必须是有限数值')
    return float(value)


def pt(value, what):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f'{what} 必须是 [x, y]')
    return [num(value[0], what), num(value[1], what)]


def runs_of(value, what):
    """A label value may be plain text or runs with sub/sup, like scene labels."""
    if isinstance(value, str) and value:
        return {'text': value}
    if isinstance(value, list) and value and all(isinstance(r, dict) and isinstance(r.get('text'), str) for r in value):
        return {'runs': deepcopy(value)}
    raise ValueError(f'{what} 必须是非空文字或 runs 列表')


# ---------------------------------------------------------------- local drawing helpers
class Parts:
    def __init__(self):
        self.items, self.terminals = [], {}

    def add(self, name, kind, **fields):
        self.items.append((name, dict(kind=kind, **fields)))

    def line(self, name, *points, width=1.5, arrow=None, dash=None):
        fields = {'points': [list(p) for p in points], 'stroke_width': width}
        if arrow:
            fields['arrow'] = arrow
        if dash:
            fields['dash'] = dash
        self.add(name, 'line' if len(points) == 2 else 'polyline', **fields)

    def circle(self, name, center, radius, fill=None, width=1.5):
        fields = {'center': list(center), 'radius': radius, 'stroke_width': width}
        if fill:
            fields['fill'] = fill
        self.add(name, 'circle', **fields)

    def text(self, name, at, value, size=15, anchor='middle', centre=True):
        """Fixed component text. With centre=True, at is the visual centre and the baseline is placed
        below it after rotation, so letters stay centred and upright in rotated components."""
        self.add(name, 'label', at=list(at), size=size, anchor=anchor, symbol=True,
                 baseline=size * .35 if centre else 0, **runs_of(value, name))


def letter_meter(parts, letter, subscript, size=15):
    parts.circle('circle', (0, 0), 13)
    value = letter if not subscript else [{'text': letter}, {'text': str(subscript), 'script': 'sub'}]
    parts.text('letter', (0, 0), value, size)
    parts.terminals.update(a=(-13, 0), b=(13, 0))


def c_lamp(p, _):
    d = 12 * math.sqrt(.5)
    p.circle('circle', (0, 0), 12)
    p.line('x1', (-d, -d), (d, d))
    p.line('x2', (-d, d), (d, -d))
    p.terminals.update(a=(-12, 0), b=(12, 0))


def c_resistor(p, _):
    p.add('body', 'rect', at=[-18, -7], width=36, height=14, stroke_width=1.5)
    p.terminals.update(a=(-18, 0), b=(18, 0))


def c_rheostat(p, q):
    slider = num(q.get('slider', .5), 'rheostat.slider')
    if not 0 <= slider <= 1:
        raise ValueError('rheostat.slider 应在 0–1 之间')
    x = -22 + 44 * slider
    p.add('body', 'rect', at=[-22, -7], width=44, height=14, stroke_width=1.5)
    p.line('slider', (x, -20), (x, -7), arrow='end')
    p.terminals.update(a=(-22, 0), b=(22, 0), p=(x, -20))


def c_battery(p, q):
    cells = q.get('cells', 1)
    if type(cells) is not int or not 1 <= cells <= 6:
        raise ValueError('battery.cells 应为 1–6 的整数')
    positive = q.get('positive', 'a')
    if positive not in {'a', 'b'}:
        raise ValueError('battery.positive 只能为 a 或 b')
    inner = 12 * cells - 6
    half = inner / 2 + 8
    left = -half + 8
    for k in range(cells):
        x0, x1 = left + 12 * k, left + 12 * k + 6
        long_x, short_x = (x0, x1) if positive == 'a' else (x1, x0)
        p.line(f'long{k + 1}', (long_x, -11), (long_x, 11))
        p.line(f'short{k + 1}', (short_x, -6), (short_x, 6), width=3)
        if k:
            p.line(f'link{k}', (x0 - 6, 0), (x0, 0))
    p.line('lead_a', (-half, 0), (left, 0))
    p.line('lead_b', (left + inner, 0), (half, 0))
    if q.get('mark_positive'):
        p.text('plus', ((-half + 4) if positive == 'a' else (half - 4), -16), '+', 12)
    p.terminals.update(a=(-half, 0), b=(half, 0))


def contact(p, name, at):
    p.circle(name, at, 2.2, fill='black', width=1)


def c_switch(p, q):
    state, side = q.get('state', 'open'), q.get('blade_side', 'up')
    if state not in {'open', 'closed'} or side not in {'up', 'down'}:
        raise ValueError('switch.state 只能为 open/closed，blade_side 只能为 up/down')
    contact(p, 'contact_a', (-16, 0))
    contact(p, 'contact_b', (16, 0))
    lift = -13 if side == 'up' else 13
    p.line('blade', (-16, 0), (16, 0) if state == 'closed' else (11, lift))
    p.terminals.update(a=(-16, 0), b=(16, 0))


def c_switch_spdt(p, q):
    to = q.get('to', 'b')
    if to not in {'b', 'c'}:
        raise ValueError('switch_spdt.to 只能为 b 或 c')
    contact(p, 'contact_a', (-16, 0))
    contact(p, 'contact_b', (16, -12))
    contact(p, 'contact_c', (16, 12))
    p.line('blade', (-16, 0), (14, -11) if to == 'b' else (14, 11))
    p.terminals.update(a=(-16, 0), b=(16, -12), c=(16, 12))


def c_ammeter(p, q):
    letter_meter(p, 'A', q.get('subscript'))


def c_voltmeter(p, q):
    letter_meter(p, 'V', q.get('subscript'))


def c_motor(p, _):
    letter_meter(p, 'M', None)


def polar(r, degrees):
    t = math.radians(degrees)
    return (r * math.cos(t), r * math.sin(t))


def c_meter_dial(p, q):
    ranges = q.get('ranges', [[0, 3]])
    if (not isinstance(ranges, list) or not 1 <= len(ranges) <= 2
            or any(not isinstance(r, list) or len(r) != 2 or num(r[1], 'range') <= num(r[0], 'range') for r in ranges)):
        raise ValueError('meter_dial.ranges 应为 1–2 组 [最小, 最大]')
    major, minor = q.get('major_ticks', 3), q.get('minor_ticks', 10)
    if type(major) is not int or type(minor) is not int or not 1 <= major <= 20 or not 1 <= minor <= 10:
        raise ValueError('meter_dial.major_ticks 应为 1–20，minor_ticks 应为 1–10 的整数')
    radius, a0, a1 = 60, 210, 330
    p.add('scale', 'arc', center=[0, 0], rx=radius, ry=radius, start=a0, end=a1, stroke_width=1.5)
    divisions = major * minor
    for i in range(divisions + 1):
        angle = a0 + (a1 - a0) * i / divisions
        length = 9 if i % minor == 0 else 5
        p.line(f'tick{i}', polar(radius, angle), polar(radius + length, angle), width=1.5 if i % minor == 0 else 1)

    def fmt(value):
        return str(int(value)) if float(value).is_integer() else f'{value:g}'
    for index, (low, high) in enumerate(ranges):
        r = radius + 20 if index == 0 else radius - 13
        for k in range(major + 1):
            angle = a0 + (a1 - a0) * k / major
            p.text(f'value{index}_{k}', polar(r, angle), fmt(low + (high - low) * k / major), 11)
    if 'needle' in q:
        which = q.get('needle_range', 0)
        if type(which) is not int or not 0 <= which < len(ranges):
            raise ValueError('meter_dial.needle_range 超出 ranges')
        low, high = ranges[which]
        value = num(q['needle'], 'meter_dial.needle')
        if not low <= value <= high:
            raise ValueError('meter_dial.needle 超出所选量程')
        angle = a0 + (a1 - a0) * (value - low) / (high - low)
        p.line('needle', polar(radius * .12, angle), polar(radius - 2, angle), width=1.6)
    unit = q.get('unit')
    if unit is not None:
        p.text('unit', (0, 2), unit, 14)
    names = q.get('terminals', [])
    if (not isinstance(names, list) or len(names) > 4 or len(set(names)) != len(names)
            or any(not isinstance(n, str) or not n for n in names)):
        raise ValueError('meter_dial.terminals 应为最多 4 个互不相同的名称，如 ["-", "0.6", "3"]')
    for k, name in enumerate(names):
        x = 0 if len(names) == 1 else -40 + 80 * k / (len(names) - 1)
        p.circle(f'post{k}', (x, 20), 3)
        p.text(f'post{k}_name', (x, 33), name, 11)
        p.terminals[name] = (x, 23)


def liquid_level(q, what):
    if 'liquid' not in q:
        return None
    value = num(q['liquid'], what)
    if not 0 < value < 1:
        raise ValueError(f'{what} 应在 0–1 之间（不含端点）')
    return value


def c_beaker(p, q):
    p.line('wall', (-34, -40), (-30, -36), (-30, 36), (30, 36), (30, -36), (34, -40))
    level = liquid_level(q, 'beaker.liquid')
    if level is not None:
        y = 36 - 72 * level
        p.line('liquid', (-30, y), (30, y))
    p.terminals.update(top=(0, -36), bottom=(0, 36))


def c_test_tube(p, q):
    p.line('left', (-8, -40), (-8, 30))
    p.line('right', (8, -40), (8, 30))
    p.add('bottom', 'arc', center=[0, 30], rx=8, ry=8, start=0, end=180, stroke_width=1.5)
    level = liquid_level(q, 'test_tube.liquid')
    if level is not None:
        if num(q.get('angle', 0), 'test_tube.angle') != 0:
            raise ValueError('倾斜试管的液面请用基础图元按原图绘制（液面应保持水平）')
        y = 38 - 78 * level
        half = 8 if y <= 30 else math.sqrt(max(0, 64 - (y - 30) ** 2))
        p.line('liquid', (-half, y), (half, y))
    p.terminals.update(top=(0, -40), bottom=(0, 38))


def c_flask(p, q):
    r, cy = 28, 10
    neck = 7
    y_join = cy - math.sqrt(r * r - neck * neck)
    angle = math.degrees(math.atan2(y_join - cy, neck))
    # From the right neck joint clockwise round the bottom to the left joint, leaving the neck open.
    p.add('bulb', 'arc', center=[0, cy], rx=r, ry=r, start=angle, end=180 - angle, stroke_width=1.5)
    p.line('neck_left', (-neck, -40), (-neck, y_join))
    p.line('neck_right', (neck, -40), (neck, y_join))
    top = -40
    if q.get('stopper'):
        p.add('stopper', 'rect', at=[-9, -48], width=18, height=10, stroke_width=1.5)
        top = -48
    level = liquid_level(q, 'flask.liquid')
    if level is not None:
        y = cy + r - 2 * r * level
        half = math.sqrt(max(0, r * r - (y - cy) ** 2))
        p.line('liquid', (-half, y), (half, y))
    p.terminals.update(top=(0, top), bottom=(0, cy + r))


def c_alcohol_lamp(p, q):
    p.add('body', 'polygon', points=[[-26, 30], [26, 30], [22, 2], [-22, 2]], stroke_width=1.5)
    p.line('shoulder', (-22, 2), (-8, -6), (8, -6), (22, 2))
    p.add('neck', 'rect', at=[-5, -14], width=10, height=8, stroke_width=1.5)
    p.line('wick', (0, -14), (0, -20))
    top = -20
    if q.get('lit'):
        p.add('flame_left', 'curve', points=[[0, -20], [-10, -26], [-6, -38], [0, -46]], stroke_width=1.5)
        p.add('flame_right', 'curve', points=[[0, -20], [10, -26], [6, -38], [0, -46]], stroke_width=1.5)
        top = -46
    p.terminals.update(top=(0, top), bottom=(0, 30))


def c_iron_stand(p, q):
    p.add('base', 'rect', at=[-45, 52], width=90, height=10, stroke_width=1.5)
    p.line('rod', (-25, 52), (-25, -70), width=2)
    for key, name in (('clamp_y', 'clamp'), ('ring_y', 'ring')):
        if key not in q:
            continue
        y = num(q[key], f'iron_stand.{key}')
        if not -68 <= y <= 48:
            raise ValueError(f'iron_stand.{key} 应在 -68–48 之间')
        if name == 'clamp':
            p.line('clamp_arm', (-25, y), (12, y))
            p.add('clamp_jaw', 'rect', at=[12, y - 5], width=8, height=10, stroke_width=1.5)
            p.terminals['clamp'] = (16, y)
        else:
            p.line('ring_arm', (-25, y), (0, y))
            p.add('ring', 'ellipse', center=[20, y], rx=20, ry=4, stroke_width=1.5)
            p.terminals['ring'] = (20, y)
    p.terminals.update(base=(0, 62), top=(-25, -70))


def c_thermometer(p, q):
    low, high = num(q.get('min', 0), 'thermometer.min'), num(q.get('max', 100), 'thermometer.max')
    if high <= low:
        raise ValueError('thermometer.max 必须大于 min')
    y_low, y_high = 40, -55

    def y_of(value):
        return y_low + (y_high - y_low) * (value - low) / (high - low)
    p.line('left', (-4, -60), (-4, 46))
    p.line('right', (4, -60), (4, 46))
    p.add('cap', 'arc', center=[0, -60], rx=4, ry=4, start=180, end=360, stroke_width=1.5)
    p.circle('bulb', (0, 52), 7, fill='black')
    major = q.get('major')
    if major is not None:
        step = num(major, 'thermometer.major')
        count = (high - low) / step
        if step <= 0 or count > 40 or abs(count - round(count)) > 1e-9:
            raise ValueError('thermometer.major 必须整除量程且刻度不超过 40 格')
        for k in range(int(round(count)) + 1):
            value = low + step * k
            y = y_of(value)
            p.line(f'tick{k}', (4, y), (12, y), width=1)
            if q.get('labels', True):
                p.text(f'label{k}', (15, y), f'{value:g}', 10, 'start')
    if 'value' in q:
        value = num(q['value'], 'thermometer.value')
        if not low <= value <= high:
            raise ValueError('thermometer.value 超出量程')
        top = y_of(value)
        p.add('column', 'rect', at=[-2, top], width=4, height=46 - top, fill='black', stroke_width=.5)
    p.terminals.update(top=(0, -64), bulb=(0, 52))


def c_asbestos_net(p, _):
    p.add('net', 'rect', at=[-35, -3], width=70, height=6, stroke_width=1.5)
    p.line('mesh', (-31, 0), (31, 0), width=.8, dash=[3, 2])
    p.terminals.update(top=(0, -3), bottom=(0, 3))


def c_axes(p, q):
    size = q.get('length', [160, 110])
    width, height = pt(size, 'axes.length')
    if width <= 0 or height <= 0:
        raise ValueError('axes.length 必须为正数')
    p.line('x_axis', (0, 0), (width, 0), arrow='end')
    p.line('y_axis', (0, 0), (0, -height), arrow='end')
    p.text('origin', (-9, 11), q.get('origin_label', 'O'), 13)
    if 'x_label' in q:
        p.text('x_label', (width + 6, 0), q['x_label'], 13, 'start')
    if 'y_label' in q:
        p.text('y_label', (6, -height - 6), q['y_label'], 13, 'start')
    p.terminals.update(origin=(0, 0), x_end=(width, 0), y_end=(0, -height))
    for axis in ('x', 'y'):
        ticks = q.get(f'{axis}_ticks', [])
        if not isinstance(ticks, list):
            raise ValueError(f'axes.{axis}_ticks 必须是 [[位置, 文字], ...]')
        for k, tick in enumerate(ticks):
            if not isinstance(tick, list) or len(tick) != 2 or not isinstance(tick[1], str):
                raise ValueError(f'axes.{axis}_ticks 每项应为 [位置, 文字]')
            at = num(tick[0], f'axes.{axis}_ticks')
            limit = width if axis == 'x' else height
            if not 0 < at <= limit:
                raise ValueError(f'axes.{axis}_ticks 位置 {at:g} 超出坐标轴')
            if axis == 'x':
                p.line(f'xtick{k}', (at, 0), (at, -4), width=1)
                if tick[1]:
                    p.text(f'xtick{k}_label', (at, 12), tick[1], 11)
                p.terminals[f'x:{tick[1] or k}'] = (at, 0)
            else:
                p.line(f'ytick{k}', (0, -at), (4, -at), width=1)
                if tick[1]:
                    p.text(f'ytick{k}_label', (-5, -at), tick[1], 11, 'end')
                p.terminals[f'y:{tick[1] or k}'] = (0, -at)


ANY = frozenset(ORIENTATIONS)
UPRIGHT = frozenset({'h', 'h-flip'})   # apparatus may be mirrored but never laid on its side
FIXED = frozenset({'h'})               # scales and axes would read backwards if mirrored or rotated
# type: (builder, allowed params, allowed orientations)
COMPONENTS = {
    'lamp': (c_lamp, set(), ANY), 'resistor': (c_resistor, set(), ANY),
    'rheostat': (c_rheostat, {'slider'}, ANY),
    'battery': (c_battery, {'cells', 'positive', 'mark_positive'}, ANY),
    'switch': (c_switch, {'state', 'blade_side'}, ANY), 'switch_spdt': (c_switch_spdt, {'to'}, ANY),
    'ammeter': (c_ammeter, {'subscript'}, ANY), 'voltmeter': (c_voltmeter, {'subscript'}, ANY),
    'motor': (c_motor, set(), ANY),
    'meter_dial': (c_meter_dial, {'ranges', 'major_ticks', 'minor_ticks', 'needle', 'needle_range', 'unit',
                                  'terminals'}, FIXED),
    'beaker': (c_beaker, {'liquid'}, UPRIGHT), 'test_tube': (c_test_tube, {'liquid', 'angle'}, UPRIGHT),
    'flask': (c_flask, {'liquid', 'stopper'}, UPRIGHT), 'alcohol_lamp': (c_alcohol_lamp, {'lit'}, UPRIGHT),
    'iron_stand': (c_iron_stand, {'clamp_y', 'ring_y'}, UPRIGHT),
    'thermometer': (c_thermometer, {'min', 'max', 'major', 'value', 'labels'}, UPRIGHT),
    'asbestos_net': (c_asbestos_net, set(), UPRIGHT),
    'axes': (c_axes, {'length', 'x_label', 'y_label', 'origin_label', 'x_ticks', 'y_ticks'}, FIXED),
}


# ---------------------------------------------------------------- placement
class Placement:
    """size, optional x-mirror, rotation (degrees, screen coordinates) and translation."""

    def __init__(self, at, size, rotation, mirror, owner):
        self.at, self.size, self.rotation, self.mirror, self.owner = at, size, rotation % 360, mirror, owner
        t = math.radians(self.rotation)
        self.cos, self.sin = round(math.cos(t), 12), round(math.sin(t), 12)

    def point(self, value):
        x, y = value[0] * self.size, value[1] * self.size
        if self.mirror:
            x = -x
        return [round(self.at[0] + x * self.cos - y * self.sin, 4), round(self.at[1] + x * self.sin + y * self.cos, 4)]

    def right_angle(self):
        return self.rotation % 90 == 0

    def element(self, name, item):
        kind = item['kind']
        out = deepcopy(item)
        for key in ('points',):
            if key in out:
                out[key] = [self.point(v) for v in out[key]]
        for key in ('center', 'at'):
            if key in out and kind != 'rect':
                out[key] = self.point(out[key])
        if kind == 'label':
            out['size'] = max(8, min(72, round(out.get('size', 18) * self.size, 2)))
            out['at'][1] = round(out['at'][1] + out.pop('baseline', 0) * self.size, 4)
        if kind == 'circle':
            out['radius'] = round(out['radius'] * self.size, 4)
        if kind in {'ellipse', 'arc'}:
            rx, ry = out['rx'] * self.size, out['ry'] * self.size
            if abs(rx - ry) > 1e-9 and not self.right_angle():
                raise ValueError(f'组件 {self.owner} 的椭圆部件只能按 90° 的整数倍旋转')
            if self.rotation % 180 == 90:
                rx, ry = ry, rx
            out['rx'], out['ry'] = round(rx, 4), round(ry, 4)
        if kind == 'arc':
            start, end = out['start'], out['end']
            if self.mirror:
                start, end = 180 - end, 180 - start
            out['start'], out['end'] = round(start + self.rotation, 6), round(end + self.rotation, 6)
        if kind == 'rect':
            if not self.right_angle():
                raise ValueError(f'组件 {self.owner} 含矩形部件，只能按 90° 的整数倍旋转')
            x, y = out['at']
            corners = [self.point(c) for c in ((x, y), (x + out['width'], y), (x, y + out['height']),
                                                (x + out['width'], y + out['height']))]
            xs, ys = [c[0] for c in corners], [c[1] for c in corners]
            out['at'] = [min(xs), min(ys)]
            out['width'], out['height'] = round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4)
        return out


def expand_component(element, understanding_kinds, understanding_params):
    cid = element['id']
    unknown = set(element) - COMPONENT_KEYS
    if unknown:
        raise ValueError(f'组件 {cid} 含不支持的字段 {sorted(unknown)}')
    ctype = element.get('type')
    if ctype not in COMPONENTS:
        raise ValueError(f'组件 {cid} 的 type={ctype!r} 不在组件库中；可用：{sorted(COMPONENTS)}')
    oid = element.get('object_id')
    if not isinstance(oid, str) or not oid:
        raise ValueError(f'组件 {cid} 必须指定 object_id')
    builder, allowed, orientations = COMPONENTS[ctype]
    params = element.get('params', {})
    if not isinstance(params, dict) or set(params) - allowed:
        raise ValueError(f'组件 {cid}（{ctype}）的 params 只能包含 {sorted(allowed)}')
    if understanding_kinds is not None:
        kind = understanding_kinds.get(oid)
        if kind in COMPONENTS and kind != ctype:
            raise ValueError(f'组件 {cid} 的 type={ctype} 与原图理解 kind={kind} 不一致')
        declared = understanding_params.get(oid) or {}
        for key, value in declared.items():
            if params.get(key) != value:
                raise ValueError(f'组件 {cid} 的 {key}={params.get(key)!r} 与原图理解 {value!r} 不一致')
    orientation = element.get('orientation', 'h')
    if orientation not in orientations:
        raise ValueError(f'组件 {cid}（{ctype}）的 orientation 只能为 {sorted(orientations)}')
    size = num(element.get('size', 1), f'组件 {cid} 的 size')
    if not .5 <= size <= 3:
        raise ValueError(f'组件 {cid} 的 size 应在 0.5–3 之间')
    rotation, mirror = ORIENTATIONS[orientation]
    if ctype == 'test_tube':
        angle = num(params.get('angle', 0), 'test_tube.angle')
        if not -90 <= angle <= 90:
            raise ValueError('test_tube.angle 应在 -90–90 之间')
        rotation += angle
    parts = Parts()
    builder(parts, params)
    place = Placement(pt(element.get('at'), f'组件 {cid} 的 at'), size, rotation, mirror, cid)
    expanded = []
    for name, item in parts.items:
        out = place.element(name, item)
        out['id'] = f'{cid}/{name}'
        out['object_id'] = oid
        if out.get('arrow') and out['kind'] != 'label':
            out['symbol'] = True
        expanded.append(out)
    terminals = {name: place.point(at) for name, at in parts.terminals.items()}
    return expanded, terminals


def wire_points(start, end, route, via):
    stops = [start, *via, end]
    points = [stops[0]]
    for q in stops[1:]:
        p = points[-1]
        if route in {'hv', 'vh'} and p[0] != q[0] and p[1] != q[1]:
            points.append([q[0], p[1]] if route == 'hv' else [p[0], q[1]])
        points.append(q)
    unique = [points[0]]
    for q in points[1:]:
        if q != unique[-1]:
            unique.append(q)
    if len(unique) < 2:
        raise ValueError('导线起点与终点重合')
    return unique


def expand_scene(scene, *, understanding=None, font_path=None):
    """Return a new scene containing only figure_drawing primitives; the input is not modified."""
    if not isinstance(scene, dict) or not isinstance(scene.get('elements'), list):
        return scene
    if not any(isinstance(e, dict) and e.get('kind') in EXTENDED for e in scene['elements']) and 'fit' not in scene:
        return scene  # 0.6.0 scenes pass through untouched
    scene = deepcopy(scene)
    kinds = params = None
    if isinstance(understanding, dict) and isinstance(understanding.get('objects'), list):
        kinds = {o.get('id'): o.get('kind') for o in understanding['objects'] if isinstance(o, dict)}
        params = {o.get('id'): o.get('params') for o in understanding['objects'] if isinstance(o, dict)}
    for element in scene['elements']:
        eid = element.get('id') if isinstance(element, dict) else None
        if isinstance(eid, str) and '/' in eid:
            raise ValueError(f'元素 id 不能包含 "/"（保留给组件展开）：{eid}')
    terminals, owners, junctions = {}, {}, {}
    elements = []
    for element in scene['elements']:
        if not isinstance(element, dict):
            elements.append(element)
            continue
        if element.get('kind') == 'component':
            parts, points = expand_component(element, kinds, params)
            elements.extend(parts)
            terminals[element['id']] = points
            owners[element['id']] = element['object_id']
        elif element.get('kind') == 'junction':
            unknown = set(element) - JUNCTION_KEYS
            if unknown:
                raise ValueError(f'节点 {element.get("id")} 含不支持的字段 {sorted(unknown)}')
            at = pt(element.get('at'), f'节点 {element.get("id")} 的 at')
            dot = {'id': element['id'], 'kind': 'circle', 'center': at,
                   'radius': num(element.get('radius', 2.5), '节点半径'), 'fill': 'black', 'stroke_width': 1}
            if element.get('object_id'):
                dot['object_id'] = element['object_id']
            junctions[element['id']] = (at, element.get('object_id'))
            elements.append(dot)
        else:
            elements.append(element)

    def end(value, wid):
        if isinstance(value, list):
            return pt(value, f'导线 {wid} 的端点'), None
        if not isinstance(value, str) or not value:
            raise ValueError(f'导线 {wid} 的端点应为 "组件.端子"、节点 id 或 [x, y]')
        if value in junctions:
            return junctions[value]
        cid, _, name = value.partition('.')
        if cid not in terminals:
            raise ValueError(f'导线 {wid} 引用了不存在的组件或节点：{cid}')
        if name not in terminals[cid]:
            raise ValueError(f'导线 {wid} 引用了组件 {cid} 不存在的端子 {name!r}；可用：{sorted(terminals[cid])}')
        return terminals[cid][name], owners[cid]

    result = []
    for element in elements:
        if not isinstance(element, dict) or element.get('kind') != 'wire':
            result.append(element)
            continue
        wid = element.get('id')
        unknown = set(element) - WIRE_KEYS
        if unknown:
            raise ValueError(f'导线 {wid} 含不支持的字段 {sorted(unknown)}')
        (start, a), (stop, b) = end(element.get('from'), wid), end(element.get('to'), wid)
        route = element.get('route', 'hv')
        if route not in ROUTES:
            raise ValueError(f'导线 {wid} 的 route 只能为 {sorted(ROUTES)}')
        via = element.get('via', [])
        if not isinstance(via, list):
            raise ValueError(f'导线 {wid} 的 via 必须是点列表')
        points = wire_points(start, stop, 'direct' if route == 'manual' else route,
                             [pt(v, f'导线 {wid} 的 via') for v in via])
        connection = element.get('connection')
        if connection is None:
            if a is None or b is None:
                raise ValueError(f'导线 {wid} 有一端不是带 object_id 的组件端子或节点，必须写 connection')
            if a == b:
                raise ValueError(f'导线 {wid} 两端属于同一对象 {a}，请写明 connection 或检查端点')
            connection = [a, b]
        out = {'id': wid, 'kind': 'line' if len(points) == 2 else 'polyline', 'points': points,
               'connection': connection, 'stroke_width': element.get('stroke_width', 1.5)}
        for key in ('dash', 'arrow'):
            if key in element:
                out[key] = element[key]
        result.append(out)
    scene['elements'] = result
    if 'fit' in scene:
        fit_canvas(scene, font_path)
    return scene


def label_box(element, font_path):
    from figure_drawing import get_font, label_runs
    from PIL import Image, ImageDraw
    draw = ImageDraw.Draw(Image.new('L', (1, 1)))
    x, y = element['at']
    size = element.get('size', 18)
    runs = label_runs(element)
    fonts = [get_font(max(1, round(size * (1 if r['script'] == 'normal' else .7))), r['text'], font_path) for r in runs]
    widths = [font.getlength(r['text']) for font, r in zip(fonts, runs)]
    cursor = x - sum(widths) * {'start': 0, 'middle': .5, 'end': 1}[element.get('anchor', 'start')]
    boxes = []
    for font, run, width in zip(fonts, runs, widths):
        shift = 0 if run['script'] == 'normal' else size * (.22 if run['script'] == 'sub' else -.4)
        boxes.append(draw.textbbox((cursor, y + shift), run['text'], font=font, anchor='ls'))
        cursor += width
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def element_box(element, font_path):
    from figure_drawing import arrow_triangle, samples
    if element['kind'] == 'label':
        return label_box(element, font_path)
    points = samples(element)
    arrow = element.get('arrow', 'none')
    if arrow in {'start', 'both'}:
        points += arrow_triangle(samples(element), element.get('stroke_width', 1.5), True)
    if arrow in {'end', 'both'}:
        points += arrow_triangle(samples(element), element.get('stroke_width', 1.5))
    half = element.get('stroke_width', 1.5) / 2
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [min(xs) - half, min(ys) - half, max(xs) + half, max(ys) + half]


def shift(element, dx, dy):
    if 'points' in element:
        element['points'] = [[round(x + dx, 4), round(y + dy, 4)] for x, y in element['points']]
    for key in ('center', 'at'):
        if key in element:
            element[key] = [round(element[key][0] + dx, 4), round(element[key][1] + dy, 4)]


def fit_canvas(scene, font_path=None):
    fit = scene.pop('fit')
    if not isinstance(fit, dict) or set(fit) - {'margin'}:
        raise ValueError('fit 只支持 {"margin": 数值}')
    margin = num(fit.get('margin', 12), 'fit.margin')
    if not 2 <= margin <= 100:
        raise ValueError('fit.margin 应在 2–100 之间')
    limits = []
    for key in ('width', 'height'):
        value = scene.get(key, 'auto')
        limits.append(1200 if value == 'auto' else num(value, f'画布 {key}'))
    boxes = [element_box(e, font_path) for e in scene['elements']]
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
    right, bottom = max(b[2] for b in boxes), max(b[3] for b in boxes)
    width, height = math.ceil(right - left + 2 * margin), math.ceil(bottom - top + 2 * margin)
    if width > min(limits[0], 1200) or height > min(limits[1], 1200):
        raise ValueError(f'内容外框 {width}×{height} 超出画布上限 {min(limits[0], 1200):g}×{min(limits[1], 1200):g}，'
                         '请缩小 size 或拆分布局')
    final_w, final_h = max(width, 50), max(height, 50)
    dx = margin - left + (final_w - width) / 2
    dy = margin - top + (final_h - height) / 2
    for element in scene['elements']:
        shift(element, dx, dy)
    scene['width'], scene['height'] = final_w, final_h
    return scene


def next_free(directory, stem, suffix):
    path, index = directory / f'{stem}{suffix}', 2
    while path.exists():
        path, index = directory / f'{stem}-{index}{suffix}', index + 1
    return path


def preview(scene_path, output_dir, *, understanding_path=None, font_path=None):
    """Expand, validate and render to a scratch directory; never part of the reviewed pipeline."""
    from figure_drawing import render
    scene = json.loads(Path(scene_path).read_text(encoding='utf-8'))
    if isinstance(scene, dict) and 'scene' in scene and 'elements' not in scene:
        scene = scene['scene']
    understanding = (json.loads(Path(understanding_path).read_text(encoding='utf-8'))
                     if understanding_path else scene.get('structure'))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    expanded = expand_scene(scene, understanding=understanding, font_path=font_path)
    png, svg = next_free(output_dir, 'preview', '.png'), next_free(output_dir, 'preview', '.svg')
    data = next_free(output_dir, 'expanded', '.json')
    render(expanded, svg, png, understanding=understanding, font_path=font_path)
    with data.open('x', encoding='utf-8') as stream:
        json.dump(expanded, stream, ensure_ascii=False, indent=2)
    return {'png': str(png), 'svg': str(svg), 'expanded': str(data),
            'width': expanded['width'], 'height': expanded['height']}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('preview', help='Render a scene to a scratch folder for a quick look')
    p.add_argument('scene', help='Scene JSON, or a {"scene": ...} drawing')
    p.add_argument('--understanding', help='Source understanding; defaults to scene.structure')
    p.add_argument('--output-dir', required=True)
    p.add_argument('--font')
    sub.add_parser('list', help='List component types and their params')
    args = parser.parse_args()
    try:
        if args.command == 'list':
            result = {name: {'params': sorted(params), 'orientations': sorted(turns)}
                      for name, (_, params, turns) in COMPONENTS.items()}
        else:
            result = preview(args.scene, args.output_dir, understanding_path=args.understanding, font_path=args.font)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
