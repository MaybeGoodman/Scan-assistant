"""Expand host-described components, wires and junctions into the existing black/white primitives.

The host still decides what the original figure contains (understanding) and where each part
goes; this module only turns "a lamp at (x, y)" or "a wire from B1.b to S1.a" into lines,
circles and labels, optionally fits the canvas to the content, and then hands the result to the
unchanged validate_scene/validate_structure/render. It never infers scientific content.

Standard sizes (scene units, size=1, orientation "h"; the local origin is the component centre,
except axes, whose origin is the axis origin):
  Circuit symbols follow the textbook style of docs/style-reference/circuit-sample.png
  (REQUIREMENTS 19.1), all drawn with CIRCUIT_STROKE:
  lamp r=12 with an x reaching the circle; resistor 36x12; rheostat 48x12 with a 24-high slider
  ending in a solid arrowhead touching the body; battery: per cell a short thick line then a long
  thin line, 6 apart, no link wires, 8 leads; switch: hollow pivot circle at -16, lead ends at +16,
  open blade rises ~28 degrees; switch_spdt pivot at -16, contacts at +16/-12 and +16/+12;
  ammeter/voltmeter/motor r=15.5 with an upright serif letter; junction default r=2;
  meter_dial arc radius 60 over 210-330 degrees;
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
EXTENDED = {'component', 'wire', 'junction', 'data_curve'}
ROUTES = {'direct', 'hv', 'vh', 'manual'}
WIRE_KEYS = {'id', 'kind', 'from', 'to', 'route', 'via', 'connection', 'stroke_width', 'dash', 'arrow'}
COMPONENT_KEYS = {'id', 'kind', 'type', 'object_id', 'at', 'orientation', 'size', 'params'}
DATA_CURVE_KEYS = {'id', 'kind', 'axes', 'object_id', 'points', 'stroke_width', 'dash', 'arrow', 'markers'}
CIRCUIT_STROKE = 1.0       # wires and circuit symbols share one width; only the battery's short line is thicker
CIRCUIT_TYPES = {'lamp', 'resistor', 'rheostat', 'battery', 'switch', 'switch_spdt', 'ammeter', 'voltmeter', 'motor'}
PHYSICAL_ELECTRICAL_TYPES = {
    'phys_meter', 'phys_knife_switch', 'phys_rheostat', 'phys_rotary_rheostat',
    'phys_lamp_holder', 'phys_battery', 'phys_resistor', 'binding_post',
}
JUNCTION_KEYS = {'id', 'kind', 'at', 'object_id', 'radius'}
COMPONENT_TEMPLATE_VERSION = '1.3.0'


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
        self.items, self.terminals, self.meta = [], {}, {}

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

    def text(self, name, at, value, size=15, anchor='middle', centre=True, style=None):
        """Fixed component text. With centre=True, at is the visual centre and the baseline is placed
        below it after rotation, so letters stay centred and upright in rotated components.
        style: 'upright' / 'italic', or None for the automatic convention (letters italic, digits upright)."""
        fields = dict(at=list(at), size=size, anchor=anchor, symbol=True, baseline=size * .35 if centre else 0)
        if style:
            fields['style'] = style
        self.add(name, 'label', **fields, **runs_of(value, name))


def letter_meter(parts, letter, subscript, size=20):
    """Meter: circle r=15.5 (about 1.3 lamp diameters) with an upright serif letter (19.1, 25.1)."""
    parts.circle('circle', (0, 0), 15.5, width=CIRCUIT_STROKE)
    value = letter if not subscript else [{'text': letter}, {'text': str(subscript), 'script': 'sub'}]
    parts.text('letter', (0, 0), value, size, style='upright')
    parts.terminals.update(a=(-15.5, 0), b=(15.5, 0))


def c_lamp(p, _):
    d = 12 * math.sqrt(.5)
    p.circle('circle', (0, 0), 12, width=CIRCUIT_STROKE)
    p.line('x1', (-d, -d), (d, d), width=CIRCUIT_STROKE)
    p.line('x2', (-d, d), (d, -d), width=CIRCUIT_STROKE)
    p.terminals.update(a=(-12, 0), b=(12, 0))


def c_resistor(p, _):
    p.add('body', 'rect', at=[-18, -6], width=36, height=12, stroke_width=CIRCUIT_STROKE)
    p.terminals.update(a=(-18, 0), b=(18, 0))


def c_rheostat(p, q):
    slider = num(q.get('slider', .5), 'rheostat.slider')
    if not 0 <= slider <= 1:
        raise ValueError('rheostat.slider 应在 0–1 之间')
    x = -24 + 48 * slider
    p.add('body', 'rect', at=[-24, -6], width=48, height=12, stroke_width=CIRCUIT_STROKE)
    # Slider: a vertical line one lamp-diameter high ending in a slim solid arrowhead whose tip touches the body.
    p.line('slider', (x, -30), (x, -15), width=CIRCUIT_STROKE)
    p.add('slider_head', 'polygon', points=[[x, -6], [x - 3, -16], [x + 3, -16]], fill='black', stroke_width=.5)
    p.terminals.update(a=(-24, 0), b=(24, 0), p=(x, -30))


def c_battery(p, q):
    cells = q.get('cells', 1)
    if type(cells) is not int or not 1 <= cells <= 6:
        raise ValueError('battery.cells 应为 1–6 的整数')
    positive = q.get('positive', 'a')
    if positive not in {'a', 'b'}:
        raise ValueError('battery.positive 只能为 a 或 b')
    # Textbook cell (19.1): long thin line = positive, short thick line = negative, 6 apart; cells sit
    # side by side at the same pitch with no link wires; leads touch the outermost lines.
    inner = 12 * cells - 6
    half = inner / 2 + 8
    left = -half + 8
    for k in range(cells):
        x0, x1 = left + 12 * k, left + 12 * k + 6
        long_x, short_x = (x0, x1) if positive == 'a' else (x1, x0)
        p.line(f'long{k + 1}', (long_x, -10.5), (long_x, 10.5), width=CIRCUIT_STROKE)
        p.line(f'short{k + 1}', (short_x, -5.5), (short_x, 5.5), width=3 * CIRCUIT_STROKE)
    p.line('lead_a', (-half, 0), (left, 0), width=CIRCUIT_STROKE)
    p.line('lead_b', (left + inner, 0), (half, 0), width=CIRCUIT_STROKE)
    if q.get('mark_positive'):
        p.text('plus', ((-half + 4) if positive == 'a' else (half - 4), -16), '+', 12, style='upright')
    p.terminals.update(a=(-half, 0), b=(half, 0))


PIVOT_R = 3          # hollow pivot circle of a switch (19.1)
BLADE_ANGLE = 28     # degrees above the lead line when open
BLADE_LENGTH = 32    # about the pivot-to-lead gap, as in the reference figure


def contact(p, name, at):
    p.circle(name, at, 2.2, fill='black', width=1)


def pivot(p, at=(-16, 0)):
    p.circle('pivot', at, PIVOT_R, fill='white', width=CIRCUIT_STROKE)


def blade(p, angle, length=BLADE_LENGTH, start=(-16, 0)):
    """Blade from the pivot circle's edge; angle in degrees, negative y is up."""
    t = math.radians(angle)
    x0, y0 = start[0] + PIVOT_R * math.cos(t), start[1] + PIVOT_R * math.sin(t)
    p.line('blade', (round(x0, 4), round(y0, 4)),
           (round(x0 + length * math.cos(t), 4), round(y0 + length * math.sin(t), 4)), width=CIRCUIT_STROKE)


def c_switch(p, q):
    state, side = q.get('state', 'open'), q.get('blade_side', 'up')
    if state not in {'open', 'closed'} or side not in {'up', 'down'}:
        raise ValueError('switch.state 只能为 open/closed，blade_side 只能为 up/down')
    pivot(p)
    if state == 'closed':
        blade(p, 0, 16 + 16 - PIVOT_R)
    else:
        blade(p, -BLADE_ANGLE if side == 'up' else BLADE_ANGLE)
    p.terminals.update(a=(-16 - PIVOT_R, 0), b=(16, 0))


def c_switch_spdt(p, q):
    to = q.get('to', 'b')
    if to not in {'b', 'c'}:
        raise ValueError('switch_spdt.to 只能为 b 或 c')
    pivot(p)
    contact(p, 'contact_b', (16, -12))
    contact(p, 'contact_c', (16, 12))
    angle = math.degrees(math.atan2(-12 if to == 'b' else 12, 32))
    blade(p, angle, math.hypot(32, 12) - PIVOT_R - 2.2)
    p.terminals.update(a=(-16 - PIVOT_R, 0), b=(16, -12), c=(16, 12))


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
    if q.get('base'):
        p.add('base', 'rect', at=[-30, 30], width=60, height=5, stroke_width=1.5)
    level = liquid_level(q, 'alcohol_lamp.liquid')
    if level is not None:
        y = 30 - 28 * level
        half = 26 - 4 * level
        p.line('liquid', (-half, y), (half, y), width=1.1, dash=[4, 2])
    p.line('shoulder', (-22, 2), (-8, -6), (8, -6), (22, 2))
    p.add('neck', 'rect', at=[-5, -14], width=10, height=8, stroke_width=1.5)
    p.line('wick', (0, -14), (0, -20))
    top = -20
    if q.get('lit'):
        p.add('flame_left', 'curve', points=[[0, -20], [-10, -26], [-6, -38], [0, -46]], stroke_width=1.5)
        p.add('flame_right', 'curve', points=[[0, -20], [10, -26], [6, -38], [0, -46]], stroke_width=1.5)
        if q.get('inner_flame'):
            p.add('inner_flame_left', 'curve', points=[[0, -21], [-5, -26], [-3, -33], [0, -37]], stroke_width=1.0)
            p.add('inner_flame_right', 'curve', points=[[0, -21], [5, -26], [3, -33], [0, -37]], stroke_width=1.0)
        top = -46
    bottom = 35 if q.get('base') else 30
    p.terminals.update(top=(0, top), bottom=(0, bottom))


def c_iron_stand(p, q):
    p.add('base', 'rect', at=[-45, 52], width=90, height=10, stroke_width=1.5)
    p.line('rod', (-25, 52), (-25, -70), width=2)
    for key, name in (('clamp_y', 'clamp'), ('clamp2_y', 'clamp2'), ('ring_y', 'ring')):
        if key not in q:
            continue
        y = num(q[key], f'iron_stand.{key}')
        if not -68 <= y <= 48:
            raise ValueError(f'iron_stand.{key} 应在 -68–48 之间')
        if name in {'clamp', 'clamp2'}:
            arm_x = 12 if name == 'clamp' else 32
            p.line(f'{name}_arm', (-25, y), (arm_x, y))
            p.add(f'{name}_jaw', 'rect', at=[arm_x, y - 5], width=8, height=10, stroke_width=1.5)
            p.terminals[name] = (arm_x + 4, y)
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
        p.meta['reading'] = {'kind': 'thermometer', 'min': low, 'max': high, 'value': value,
                             'axis': 'y', 'p_low': [0, y_low], 'p_high': [0, y_high]}
    p.terminals.update(top=(0, -64), bulb=(0, 52))


def c_clinical_thermometer(p, q):
    """Horizontal clinical thermometer (default 35–42 ℃, 0.1 ℃ minor ticks); never prints the reading answer."""
    low, high = num(q.get('min', 35), 'clinical_thermometer.min'), num(q.get('max', 42), 'clinical_thermometer.max')
    if high <= low:
        raise ValueError('clinical_thermometer.max 必须大于 min')
    major = num(q.get('major', 1), 'clinical_thermometer.major')
    minor = q.get('minor', 10)
    if type(minor) is not int or not 1 <= minor <= 10:
        raise ValueError('clinical_thermometer.minor 应为 1–10 的整数')
    count = (high - low) / major
    if major <= 0 or count > 20 or abs(count - round(count)) > 1e-9:
        raise ValueError('clinical_thermometer.major 必须整除量程且主刻度不超过 20 格')
    x_low, x_high = -120.0, 125.0

    def x_of(val):
        return x_low + (x_high - x_low) * (val - low) / (high - low)

    # Metallic bulb on left + constriction neck + glass body + rounded right tip
    p.add('bulb', 'polygon', points=[[-168, -5], [-146, -5], [-146, 5], [-168, 5]], fill='black', stroke_width=1.2)
    p.circle('bulb_cap', (-168, 0), 5, fill='black', width=1.2)
    p.line('top_wall', (-146, -13), (138, -13), width=1.4)
    p.line('bottom_wall', (-146, 13), (138, 13), width=1.4)
    p.line('left_wall', (-146, -13), (-146, 13), width=1.4)
    p.add('right_cap', 'arc', center=[138, 0], rx=13, ry=13, start=-90, end=90, stroke_width=1.4)
    # Capillary & constriction bend
    p.line('constriction', (-146, 0), (-140, 0), (-137, -3), (-134, 0), (-120, 0), width=1.2)
    p.line('capillary_top', (-120, -2), (134, -2), width=0.7)
    p.line('capillary_bot', (-120, 2), (134, 2), width=0.7)

    # Ticks: major (1.0), mid (0.5 if minor is even), minor (0.1)
    total_minor = int(round(count)) * minor
    for i in range(total_minor + 1):
        val = low + (high - low) * i / total_minor
        x = round(x_of(val), 4)
        is_major = (i % minor == 0)
        is_mid = (minor % 2 == 0 and i % (minor // 2) == 0 and not is_major)
        length = 9 if is_major else (6.5 if is_mid else 4)
        w = 1.2 if is_major else (0.9 if is_mid else 0.7)
        p.line(f'tick{i}', (x, -2), (x, -2 - length), width=w)
        if is_major and q.get('labels', True):
            p.text(f'label{i}', (x, 8), f'{val:g}', 10, 'middle', style='upright')

    unit = q.get('unit', '℃')
    if unit:
        p.text('unit', (-133, 8), unit, 9, 'middle', style='upright')

    if 'value' in q:
        val = num(q['value'], 'clinical_thermometer.value')
        if not low <= val <= high:
            raise ValueError('clinical_thermometer.value 超出量程')
        x_end = round(x_of(val), 4)
        p.add('column', 'rect', at=[-146, -2], width=round(x_end - (-146), 4), height=4, fill='black', stroke_width=0.5)
        p.meta['reading'] = {'kind': 'clinical_thermometer', 'min': low, 'max': high, 'value': val,
                             'axis': 'x', 'p_low': [x_low, 0.0], 'p_high': [x_high, 0.0]}
    p.terminals.update(bulb=(-168, 0), tip=(151, 0))


def c_asbestos_net(p, _):
    p.add('net', 'rect', at=[-35, -3], width=70, height=6, stroke_width=1.5)
    p.line('mesh', (-31, 0), (31, 0), width=.8, dash=[3, 2])
    p.terminals.update(top=(0, -3), bottom=(0, 3))


def _post(p, name, at, label=None, label_dy=12):
    """Reusable physical binding post (knurled double-circle) with exact center anchor."""
    x, y = at
    p.circle(f'{name}_outer', (x, y), 4.0, fill='white', width=1.2)
    p.circle(f'{name}_inner', (x, y), 1.6, fill='black', width=0.8)
    if label:
        p.text(f'{name}_lbl', (x, y + label_dy), label, 10, 'middle', style='upright')


def c_binding_post(p, q):
    _post(p, 'post', (0, 0), q.get('label'))
    p.terminals.update(p=(0, 0))


def c_phys_meter(p, q):
    """Physical pointer ammeter/voltmeter with sloped casing, dial arc, pointer and traceable posts.
    Never invents range numbers unless `ranges` is explicitly supplied."""
    kind = q.get('kind', 'A')
    if kind not in {'A', 'V'}:
        raise ValueError('phys_meter.kind 只能为 A 或 V')
    # Sloped desk-meter casing
    p.add('casing', 'polygon', points=[[-34, -36], [34, -36], [38, 12], [-38, 12]], stroke_width=1.5)
    p.add('panel', 'polygon', points=[[-38, 12], [38, 12], [44, 34], [-44, 34]], stroke_width=1.5)
    p.add('window', 'rect', at=[-28, -30], width=56, height=36, stroke_width=1.1)
    # Dial arc & ticks
    cx, cy, r = 0.0, 4.0, 24.0
    a0, a1 = 215.0, 325.0
    p.add('scale', 'arc', center=[cx, cy], rx=r, ry=r, start=a0, end=a1, stroke_width=1.1)
    major = q.get('major_ticks', 3)
    minor = q.get('minor_ticks', 5)
    if type(major) is not int or type(minor) is not int or not 1 <= major <= 15 or not 1 <= minor <= 10:
        raise ValueError('phys_meter.major_ticks 应为 1–15，minor_ticks 应为 1–10 的整数')
    divs = major * minor
    for i in range(divs + 1):
        ang = a0 + (a1 - a0) * i / divs
        tick_len = 5.0 if i % minor == 0 else 2.8
        p0 = polar(r, ang)
        p1 = polar(r + tick_len, ang)
        p.line(f'tick{i}', (cx + p0[0], cy + p0[1]), (cx + p1[0], cy + p1[1]), width=1.0 if i % minor == 0 else 0.7)
    ranges = q.get('ranges', [])
    if ranges:
        if (not isinstance(ranges, list) or not 1 <= len(ranges) <= 2
                or any(not isinstance(rg, list) or len(rg) != 2 or num(rg[1], 'range') <= num(rg[0], 'range') for rg in ranges)):
            raise ValueError('phys_meter.ranges 应为 1–2 组 [最小, 最大]')
        for idx, (lo, hi) in enumerate(ranges):
            rr = r + 9.5 if idx == 0 else r - 7.5
            for k in range(major + 1):
                ang = a0 + (a1 - a0) * k / major
                pt_lbl = polar(rr, ang)
                val = lo + (hi - lo) * k / major
                txt = str(int(val)) if float(val).is_integer() else f'{val:g}'
                p.text(f'val{idx}_{k}', (cx + pt_lbl[0], cy + pt_lbl[1]), txt, 8, 'middle', style='upright')
    # Needle
    if 'needle' in q:
        which = q.get('needle_range', 0)
        if ranges:
            if type(which) is not int or not 0 <= which < len(ranges):
                raise ValueError('phys_meter.needle_range 超出 ranges')
            lo, hi = ranges[which]
        else:
            lo, hi = 0.0, 1.0
        val = num(q['needle'], 'phys_meter.needle')
        if not lo <= val <= hi:
            raise ValueError('phys_meter.needle 超出所选量程')
        ang = a0 + (a1 - a0) * (val - lo) / (hi - lo)
        p.meta['reading'] = {'kind': 'phys_meter', 'min': lo, 'max': hi, 'value': val, 'a0': a0, 'a1': a1}
    else:
        ang = a0 + (a1 - a0) * 0.22
    tip = polar(r - 1.5, ang)
    p.line('needle', (cx, cy), (cx + tip[0], cy + tip[1]), width=1.2)
    p.circle('pivot', (cx, cy), 2.0, fill='black', width=0.8)
    # Meter letter
    p.text('letter', (4, -6), kind, 13, 'middle', style='upright')
    # Binding posts
    names = q.get('terminals', ['-', 'pos1', 'pos2'])
    if (not isinstance(names, list) or not 2 <= len(names) <= 4 or len(set(names)) != len(names)
            or any(not isinstance(n, str) or not n for n in names)):
        raise ValueError('phys_meter.terminals 应为 2–4 个互不相同的端子名称')
    for k, name in enumerate(names):
        x = -26.0 + 52.0 * k / (len(names) - 1)
        # Only print explicit short labels like '-', '0.6', '3', '15', '+'; generic 'pos1'/'pos2' stay unmarked
        lbl = None if name.startswith('pos') else name
        _post(p, f'post{k}', (x, 22.0), lbl, label_dy=10)
        p.terminals[name] = (x, 22.0)


def c_phys_knife_switch(p, q):
    """Physical single-pole knife switch: insulating plinth stays below terminals so it never looks like a short."""
    state, side = q.get('state', 'open'), q.get('blade_side', 'up')
    if state not in {'open', 'closed'} or side not in {'up', 'down'}:
        raise ValueError('phys_knife_switch.state 只能为 open/closed，blade_side 只能为 up/down')
    # Insulating base plinth below the contact line (open top visually separates the two posts)
    p.line('base_outline', (-34, 6), (-34, 18), (34, 18), (34, 6), width=1.5)
    p.line('base_foot', (-38, 18), (38, 18), width=1.5)
    # Left pivot post (a) and right static contact clip (b)
    _post(p, 'post_a', (-22, 0))
    _post(p, 'post_b', (22, 0))
    p.line('jaw_l', (19, -5), (19, 4), width=1.3)
    p.line('jaw_r', (25, -5), (25, 4), width=1.3)
    if state == 'closed':
        p.line('blade', (-18, 0), (22, 0), width=2.2)
        p.circle('handle', (28, 0), 3.2, fill='black', width=1.0)
    else:
        ang = math.radians(-38 if side == 'up' else 38)
        bx, by = -18 + 38 * math.cos(ang), 38 * math.sin(ang)
        hx, hy = -18 + 43 * math.cos(ang), 43 * math.sin(ang)
        p.line('blade', (-18, 0), (round(bx, 4), round(by, 4)), width=2.2)
        p.circle('handle', (round(hx, 4), round(hy, 4)), 3.2, fill='black', width=1.0)
    p.terminals.update(a=(-22, 0), b=(22, 0))


def c_phys_rheostat(p, q):
    """Physical sliding rheostat with ceramic cylinder, coil windings, metal slide rod, slider P and posts A/B/C/D."""
    slider = num(q.get('slider', 0.5), 'phys_rheostat.slider')
    if not 0 <= slider <= 1:
        raise ValueError('phys_rheostat.slider 应在 0–1 之间')
    # Support legs
    p.line('leg_l', (-48, 18), (-54, 28), (-42, 28), width=1.5)
    p.line('leg_r', (48, 18), (54, 28), (42, 28), width=1.5)
    # Ceramic cylinder & coil windings
    p.add('coil_body', 'rect', at=[-44, -4], width=88, height=22, stroke_width=1.5)
    for k in range(1, 15):
        wx = -44 + k * (88 / 15)
        p.line(f'wind{k}', (round(wx, 3), -4), (round(wx, 3), 18), width=0.7)
    # Top slide rod & end supports
    p.line('post_sup_l', (-48, -20), (-48, 18), width=1.5)
    p.line('post_sup_r', (48, -20), (48, 18), width=1.5)
    p.line('rod', (-48, -20), (48, -20), width=2.0)
    # Slider block P
    sx = round(-36 + 72 * slider, 4)
    p.add('slider_knob', 'rect', at=[sx - 7, -30], width=14, height=10, fill='white', stroke_width=1.4)
    p.line('slider_wiper', (sx, -20), (sx, -4), width=1.6)
    p.add('slider_tip', 'polygon', points=[[sx, -4], [sx - 3, -9], [sx + 3, -9]], fill='black', stroke_width=0.6)
    # 4 binding posts: A, B (bottom coil ends), C, D (top rod ends)
    post_coords = {'A': (-52, 14), 'B': (52, 14), 'C': (-52, -20), 'D': (52, -20)}
    active = q.get('terminals', ['A', 'B', 'C', 'D'])
    if not isinstance(active, list) or not active or set(active) - set(post_coords):
        raise ValueError('phys_rheostat.terminals 只能包含 A、B、C、D')
    for name in active:
        cx, cy = post_coords[name]
        _post(p, f'post_{name}', (cx, cy))
        p.terminals[name] = (cx, cy)
    p.terminals['P'] = (sx, -30)


def c_phys_rotary_rheostat(p, q):
    """Physical rotary potentiometer/rheostat (R10): circular resistance wire, wiper, axle, knob, A/B/C posts."""
    angle = num(q.get('angle', 270), 'phys_rotary_rheostat.angle')
    if not 140 <= angle <= 400:
        raise ValueError('phys_rotary_rheostat.angle 应在 140–400 度之间')
    # Outer housing
    p.circle('casing', (0, 0), 40, width=1.5)
    # Resistive wire arc (140 deg to 400 deg)
    p.add('res_wire', 'arc', center=[0, 0], rx=27, ry=27, start=140, end=400, stroke_width=3.2)
    # Optional knob ring
    if q.get('show_knob', True):
        p.circle('knob', (0, 0), 13, width=1.1)
    # Central axle & wiper arm
    p.circle('axle', (0, 0), 4.5, fill='white', width=1.3)
    p.circle('axle_dot', (0, 0), 1.6, fill='black', width=0.8)
    w_tip = polar(27, angle)
    p.line('wiper', (0, 0), (round(w_tip[0], 4), round(w_tip[1], 4)), width=1.8)
    p.circle('wiper_contact', (round(w_tip[0], 4), round(w_tip[1], 4)), 2.5, fill='black', width=0.8)
    # Internal leads from arc ends and axle to posts A, B, C
    a_arc = polar(27, 140)
    c_arc = polar(27, 400)
    p.line('lead_A', (round(a_arc[0], 4), round(a_arc[1], 4)), (-28, 44), width=1.3)
    p.line('lead_B', (0, 4.5), (0, 48), width=1.3)
    p.line('lead_C', (round(c_arc[0], 4), round(c_arc[1], 4)), (28, 44), width=1.3)
    _post(p, 'post_A', (-28, 44))
    _post(p, 'post_B', (0, 48))
    _post(p, 'post_C', (28, 44))
    w_mid = polar(16, angle)
    wire_ref = polar(27, 210 if angle > 240 else 330)
    p.terminals.update(
        A=(-28, 44), B=(0, 48), C=(28, 44),
        knob=(13, 0), wiper=(round(w_mid[0], 4), round(w_mid[1], 4)),
        wire=(round(wire_ref[0], 4), round(wire_ref[1], 4)),
    )


def c_phys_lamp_holder(p, q):
    """Physical small lamp holder with base, screw socket, glass bulb, filament and binding posts a/b."""
    p.add('base', 'ellipse', center=[0, 14], rx=26, ry=9, stroke_width=1.5)
    p.add('socket', 'rect', at=[-9, -3], width=18, height=14, fill='white', stroke_width=1.4)
    p.line('thread1', (-9, 2), (9, 2), width=0.8)
    p.line('thread2', (-9, 6), (9, 6), width=0.8)
    p.circle('bulb', (0, -17), 14, fill='white', width=1.4)
    p.line('filament', (-4, -3), (-4, -15), (-2, -19), (0, -16), (2, -19), (4, -15), (4, -3), width=1.0)
    _post(p, 'post_a', (-19, 14))
    _post(p, 'post_b', (19, 14))
    if q.get('label'):
        p.text('lbl', (0, 29), q['label'], 11, 'middle')
    p.terminals.update(a=(-19, 14), b=(19, 14))


def c_phys_battery(p, q):
    """Physical cylindrical dry cell(s) / battery box with traceable series polarity and pos/neg posts."""
    cells = q.get('cells', 2)
    if type(cells) is not int or not 1 <= cells <= 4:
        raise ValueError('phys_battery.cells 应为 1–4 的整数')
    positive = q.get('positive', 'a')
    if positive not in {'a', 'b'}:
        raise ValueError('phys_battery.positive 只能为 a 或 b')
    cell_w, cell_h, gap = 36.0, 18.0, 6.0
    total_w = cells * cell_w + (cells - 1) * gap
    left = -total_w / 2
    if q.get('style', 'box') == 'box':
        p.add('box', 'rect', at=[round(left - 8, 4), -16], width=round(total_w + 16, 4), height=32, stroke_width=1.5)
    for k in range(cells):
        x0 = left + k * (cell_w + gap)
        x1 = x0 + cell_w
        p.add(f'cell{k}', 'rect', at=[round(x0, 4), -cell_h / 2], width=cell_w, height=cell_h, stroke_width=1.3)
        # Positive cap on left if positive=='a', else on right
        if positive == 'a':
            p.add(f'cap{k}', 'rect', at=[round(x0 - 3, 4), -4], width=3, height=8, fill='black', stroke_width=0.8)
            p.text(f'plus{k}', (round(x0 + 7, 4), 0), '+', 10, 'middle', style='upright')
            p.text(f'minus{k}', (round(x1 - 7, 4), 0), '-', 10, 'middle', style='upright')
        else:
            p.add(f'cap{k}', 'rect', at=[round(x1, 4), -4], width=3, height=8, fill='black', stroke_width=0.8)
            p.text(f'minus{k}', (round(x0 + 7, 4), 0), '-', 10, 'middle', style='upright')
            p.text(f'plus{k}', (round(x1 - 7, 4), 0), '+', 10, 'middle', style='upright')
        if k > 0:
            p.line(f'link{k}', (round(x0 - gap, 4), 0), (round(x0, 4), 0), width=1.6)
    pa = (round(left - 14, 4), 0.0)
    pb = (round(left + total_w + 14, 4), 0.0)
    p.line('lead_a', (round(left, 4), 0), pa, width=1.3)
    p.line('lead_b', (round(left + total_w, 4), 0), pb, width=1.3)
    _post(p, 'post_a', pa)
    _post(p, 'post_b', pb)
    p.terminals.update(a=pa, b=pb, pos=pa if positive == 'a' else pb, neg=pb if positive == 'a' else pa)


def c_phys_resistor(p, q):
    """Physical fixed resistor board with ceramic resistor body and binding posts a/b."""
    p.add('board', 'rect', at=[-34, -13], width=68, height=26, stroke_width=1.4)
    p.add('body', 'rect', at=[-15, -6], width=30, height=12, fill='white', stroke_width=1.4)
    p.line('lead_a', (-25, 0), (-15, 0), width=1.3)
    p.line('lead_b', (15, 0), (25, 0), width=1.3)
    _post(p, 'post_a', (-25, 0))
    _post(p, 'post_b', (25, 0))
    if q.get('label'):
        p.text('lbl', (0, 0), q['label'], 10, 'middle')
    p.terminals.update(a=(-25, 0), b=(25, 0))


def c_axes(p, q):
    size = q.get('length', [160, 110])
    width, height = pt(size, 'axes.length')
    if width <= 0 or height <= 0:
        raise ValueError('axes.length 必须为正数')
    p.line('x_axis', (0, 0), (width, 0), arrow='end')
    p.line('y_axis', (0, 0), (0, -height), arrow='end')
    p.text('origin', (-9, 11), q.get('origin_label', 'O'), 13)
    if 'x_label' in q:
        x_lbl_pos = pt(q['x_label_pos'], 'axes.x_label_pos') if 'x_label_pos' in q else [width + 6, 0]
        p.text('x_label', x_lbl_pos, q['x_label'], 12, 'start')
    if 'y_label' in q:
        y_lbl_pos = pt(q['y_label_pos'], 'axes.y_label_pos') if 'y_label_pos' in q else [6, -height - 6]
        p.text('y_label', y_lbl_pos, q['y_label'], 12, 'start')
    p.terminals.update(origin=(0, 0), x_end=(width, 0), y_end=(0, -height))

    # Optional data-space mapping for exact data-coordinate plotting (V1.1 Section 4.3 #2)
    x_range = q.get('x_range')
    y_range = q.get('y_range')
    if x_range is not None or y_range is not None:
        if x_range is None or y_range is None:
            raise ValueError('axes.x_range 与 axes.y_range 必须同时指定')
        x0, x1 = pt(x_range, 'axes.x_range')
        y0, y1 = pt(y_range, 'axes.y_range')
        if x1 <= x0 or y1 <= y0:
            raise ValueError('axes.x_range / y_range 必须为递增区间 [最小, 最大]')
        # Reserve 10% headroom before arrow tip so max tick does not collide with arrowhead
        plot_w = num(q.get('plot_width', width * 0.88), 'axes.plot_width')
        plot_h = num(q.get('plot_height', height * 0.88), 'axes.plot_height')
        if not 0 < plot_w <= width or not 0 < plot_h <= height:
            raise ValueError('axes.plot_width / plot_height 超出坐标轴长度')
        p.meta['data_space'] = {'x_range': [x0, x1], 'y_range': [y0, y1],
                                'plot_width': plot_w, 'plot_height': plot_h}

        def fmt_num(v):
            return str(int(round(v))) if abs(v - round(v)) < 1e-9 else f'{v:g}'

        grid = bool(q.get('grid', False))
        for axis, lo, hi, span, major_key, minor_key in (
            ('x', x0, x1, plot_w, 'x_major', 'x_minor'),
            ('y', y0, y1, plot_h, 'y_major', 'y_minor'),
        ):
            if major_key in q:
                step = num(q[major_key], f'axes.{major_key}')
                count = (hi - lo) / step
                if step <= 0 or count > 40 or abs(count - round(count)) > 1e-9:
                    raise ValueError(f'axes.{major_key} 必须整除量程且不超过 40 格')
                n_major = int(round(count))
                for k in range(n_major + 1):
                    val = lo + step * k
                    pos = round(span * k / n_major, 4)
                    if k == 0 and abs(val) < 1e-9:
                        continue  # origin already labelled
                    if axis == 'x':
                        if pos > 0:
                            p.line(f'dx_tick{k}', (pos, 0), (pos, -4), width=1)
                            if grid:
                                p.line(f'dx_grid{k}', (pos, 0), (pos, -plot_h), width=0.5, dash=[2, 2])
                        p.text(f'dx_lbl{k}', (pos, 13), fmt_num(val), 10, 'middle', style='upright')
                        p.terminals[f'x:{fmt_num(val)}'] = (pos, 0)
                    else:
                        if pos > 0:
                            p.line(f'dy_tick{k}', (0, -pos), (4, -pos), width=1)
                            if grid:
                                p.line(f'dy_grid{k}', (0, -pos), (plot_w, -pos), width=0.5, dash=[2, 2])
                        p.text(f'dy_lbl{k}', (-6, -pos), fmt_num(val), 10, 'end', style='upright')
                        p.terminals[f'y:{fmt_num(val)}'] = (0, -pos)
            if minor_key in q:
                mstep = num(q[minor_key], f'axes.{minor_key}')
                mcount = (hi - lo) / mstep
                if mstep <= 0 or mcount > 100 or abs(mcount - round(mcount)) > 1e-9:
                    raise ValueError(f'axes.{minor_key} 必须整除量程且不超过 100 格')
                for k in range(1, int(round(mcount)) + 1):
                    pos = round(span * k / round(mcount), 4)
                    if axis == 'x':
                        p.line(f'dx_mtick{k}', (pos, 0), (pos, -2.5), width=0.7)
                    else:
                        p.line(f'dy_mtick{k}', (0, -pos), (2.5, -pos), width=0.7)

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
    'flask': (c_flask, {'liquid', 'stopper'}, UPRIGHT),
    'alcohol_lamp': (c_alcohol_lamp, {'lit', 'liquid', 'inner_flame', 'base'}, UPRIGHT),
    'iron_stand': (c_iron_stand, {'clamp_y', 'clamp2_y', 'ring_y'}, UPRIGHT),
    'thermometer': (c_thermometer, {'min', 'max', 'major', 'value', 'labels'}, UPRIGHT),
    'clinical_thermometer': (c_clinical_thermometer, {'min', 'max', 'major', 'minor', 'value', 'labels', 'unit'}, FIXED),
    'asbestos_net': (c_asbestos_net, set(), UPRIGHT),
    'axes': (c_axes, {'length', 'x_label', 'y_label', 'x_label_pos', 'y_label_pos', 'origin_label',
                      'x_ticks', 'y_ticks', 'x_range', 'y_range', 'x_major', 'y_major', 'x_minor', 'y_minor',
                      'plot_width', 'plot_height', 'grid'}, FIXED),
    # Physical electrical apparatus (V1.1 Section 4.2)
    'phys_meter': (c_phys_meter, {'kind', 'ranges', 'major_ticks', 'minor_ticks', 'needle', 'needle_range', 'terminals'}, FIXED),
    'phys_knife_switch': (c_phys_knife_switch, {'state', 'blade_side'}, UPRIGHT),
    'phys_rheostat': (c_phys_rheostat, {'slider', 'terminals'}, UPRIGHT),
    'phys_rotary_rheostat': (c_phys_rotary_rheostat, {'angle', 'show_knob'}, FIXED),
    'phys_lamp_holder': (c_phys_lamp_holder, {'label'}, UPRIGHT),
    'phys_battery': (c_phys_battery, {'cells', 'positive', 'style'}, UPRIGHT),
    'phys_resistor': (c_phys_resistor, {'label'}, UPRIGHT),
    'binding_post': (c_binding_post, {'label'}, ANY),
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


def _expand_component_with_meta(element, understanding_kinds, understanding_params):
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
    meta = {'type': ctype, 'object_id': oid, 'version': COMPONENT_TEMPLATE_VERSION}
    if 'data_space' in parts.meta:
        ds = parts.meta['data_space']
        meta['data_space'] = {
            'origin': place.point([0.0, 0.0]),
            'x_range': ds['x_range'], 'y_range': ds['y_range'],
            'plot_width': round(ds['plot_width'] * size, 4),
            'plot_height': round(ds['plot_height'] * size, 4),
        }
    if 'reading' in parts.meta:
        rd = deepcopy(parts.meta['reading'])
        if 'p_low' in rd and 'p_high' in rd:
            rd['p_low'] = place.point(rd['p_low'])
            rd['p_high'] = place.point(rd['p_high'])
        meta['reading'] = rd
    return expanded, terminals, meta


def expand_component(element, understanding_kinds, understanding_params):
    expanded, terminals, _ = _expand_component_with_meta(element, understanding_kinds, understanding_params)
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


def map_data_point(ds, point_xy):
    """Map [data_x, data_y] into canvas coordinates using the axes data-space transform."""
    dx, dy = pt(point_xy, '数据点')
    x0, x1 = ds['x_range']
    y0, y1 = ds['y_range']
    ox, oy = ds['origin']
    cx = ox + (dx - x0) / (x1 - x0) * ds['plot_width']
    cy = oy - (dy - y0) / (y1 - y0) * ds['plot_height']
    return [round(cx, 4), round(cy, 4)]


def _point_to_segment_dist(p, a, b):
    """Euclidean distance from point p to line segment ab."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = p[0] - a[0], p[1] - a[1]
    seg_len2 = vx * vx + vy * vy
    if seg_len2 < 1e-12:
        return math.hypot(wx, wy)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / seg_len2))
    proj_x, proj_y = a[0] + t * vx, a[1] + t * vy
    return math.hypot(p[0] - proj_x, p[1] - proj_y)


def validate_terminal_connections(elements, anchors, understanding):
    """Verify actual rendered wire geometry against declared terminal_connections (V1.1 Section 4.3 #1).

    Checks:
    - Each wire's actual start/end coordinates must land within TOL of a known terminal/junction anchor
      (catches floating/virtual contact '虚接' and wrong terminal '误接邻端').
    - Intermediate segments must not accidentally pass through an unrelated terminal anchor.
    - Multiset of geometrically verified anchor pairs must match understanding['terminal_connections']
      (catches missing wires, wrong terminals, and extra short-circuit bridges '额外跨接').
    - Co-termination at the same terminal/junction is allowed; crossing wires without a junction stay separate.
    """
    expected_raw = understanding.get('terminal_connections')
    if expected_raw is None:
        return
    if not isinstance(expected_raw, list):
        raise ValueError('understanding.terminal_connections 必须是端子对列表')
    tol = 1.5
    pass_through_tol = 2.0
    expected_pairs = []
    for item in expected_raw:
        if isinstance(item, dict):
            a, b = item.get('from'), item.get('to')
        elif isinstance(item, list) and len(item) == 2:
            a, b = item[0], item[1]
        else:
            raise ValueError('terminal_connections 每项必须是 [端子A, 端子B] 或 {"from": ..., "to": ...}')
        if not isinstance(a, str) or not isinstance(b, str) or not a or not b:
            raise ValueError('terminal_connections 端子名必须是非空字符串')
        if a not in anchors:
            raise ValueError(f'terminal_connections 引用了不存在的端子或节点：{a}')
        if b not in anchors:
            raise ValueError(f'terminal_connections 引用了不存在的端子或节点：{b}')
        expected_pairs.append(tuple(sorted((a, b))))

    # Alias map: e.g. phys_battery exposes both 'pos'/'a' at identical coordinates; resolve to declared names
    declared_names = {name for pair in expected_pairs for name in pair}

    def match_anchor(coord, preferred=None):
        if preferred and preferred in anchors and math.dist(coord, anchors[preferred]) <= tol:
            return preferred
        matches = [name for name, pos in anchors.items() if math.dist(coord, pos) <= tol]
        if not matches:
            return None
        # Prefer names that appear in declared terminal_connections (handles aliases like pos/a)
        preferred_matches = [m for m in matches if m in declared_names]
        return preferred_matches[0] if preferred_matches else matches[0]

    wire_elements = [e for e in elements if isinstance(e, dict) and 'connection' in e and e.get('kind') in {'line', 'polyline'}]
    actual_pairs = []
    for wire in wire_elements:
        pts = wire.get('points', [])
        if len(pts) < 2:
            continue
        start_pt, end_pt = pts[0], pts[-1]
        a = match_anchor(start_pt)
        b = match_anchor(end_pt)
        if a is None:
            raise ValueError(f'导线 {wire["id"]} 起点 {start_pt} 悬空/虚接，未到达任何已知端子锚点')
        if b is None:
            raise ValueError(f'导线 {wire["id"]} 终点 {end_pt} 悬空/虚接，未到达任何已知端子锚点')
        if a == b:
            raise ValueError(f'导线 {wire["id"]} 起止两端落在同一端子 {a}')
        # Check intermediate segments do not accidentally pass over an unrelated terminal
        endpoint_coords = (anchors[a], anchors[b])
        for seg_a, seg_b in zip(pts, pts[1:]):
            for name, pos in anchors.items():
                if math.dist(pos, endpoint_coords[0]) <= tol or math.dist(pos, endpoint_coords[1]) <= tol:
                    continue
                if _point_to_segment_dist(pos, seg_a, seg_b) < pass_through_tol:
                    raise ValueError(f'导线 {wire["id"]} 路径误触无关端子 {name}，请改道避开')
        actual_pairs.append(tuple(sorted((a, b))))

    expected_sorted = sorted(expected_pairs)
    actual_sorted = sorted(actual_pairs)
    if expected_sorted != actual_sorted:
        missing = [list(c) for c in expected_sorted if expected_sorted.count(c) > actual_sorted.count(c)]
        extra = [list(c) for c in actual_sorted if actual_sorted.count(c) > expected_sorted.count(c)]
        raise ValueError(f'端子级接线与原图理解不一致：缺少 {missing}，多出/接错 {extra}')


def validate_data_space(elements, data_spaces, readings, understanding):
    """Verify rendered curves and instrument readings against data-space ground truth (V1.1 Section 4.3 #2)."""
    ds_spec = understanding.get('data_space')
    if not isinstance(ds_spec, dict):
        return
    from figure_drawing import samples
    by_id = {e['id']: e for e in elements if isinstance(e, dict) and 'id' in e}

    def point_on_element(el, target_xy, tol):
        pts = samples(el)
        if len(pts) == 1:
            return math.dist(pts[0], target_xy) <= tol
        return any(_point_to_segment_dist(target_xy, a, b) <= tol for a, b in zip(pts, pts[1:]))

    # 1. Key points on curves
    for kp in ds_spec.get('key_points', []):
        axes_id = kp.get('axes') or (next(iter(data_spaces)) if len(data_spaces) == 1 else None)
        if not axes_id or axes_id not in data_spaces:
            raise ValueError(f'data_space.key_points 找不到坐标系 {axes_id}')
        eid = kp.get('element_id')
        if eid not in by_id:
            raise ValueError(f'data_space.key_points 引用了不存在的元素：{eid}')
        target = map_data_point(data_spaces[axes_id], kp['point'])
        tol = num(kp.get('tolerance', 1.2), 'key_point.tolerance')
        if not point_on_element(by_id[eid], target, tol):
            raise ValueError(f'曲线 {eid} 未经过关键数据点 {kp["point"]}（画布期望 {target}）')

    # 2. Coincident segments (e.g. R06 boiling plateau overlap)
    for seg in ds_spec.get('coincident_segments', []):
        axes_id = seg.get('axes') or (next(iter(data_spaces)) if len(data_spaces) == 1 else None)
        if not axes_id or axes_id not in data_spaces:
            raise ValueError(f'data_space.coincident_segments 找不到坐标系 {axes_id}')
        tol = num(seg.get('tolerance', 1.2), 'coincident_segments.tolerance')
        for eid in seg.get('elements', []):
            if eid not in by_id:
                raise ValueError(f'data_space.coincident_segments 引用了不存在的元素：{eid}')
            for dp in seg.get('points', []):
                target = map_data_point(data_spaces[axes_id], dp)
                if not point_on_element(by_id[eid], target, tol):
                    raise ValueError(f'曲线 {eid} 在重合段未经过数据点 {dp}')

    # 3. Instrument readings (actual rendered column / needle geometry vs declared reading)
    for rd_spec in ds_spec.get('readings', []):
        cid = rd_spec.get('component_id')
        expected_val = num(rd_spec.get('value'), 'reading.value')
        tol_val = num(rd_spec.get('tolerance', 0.05), 'reading.tolerance')
        if cid not in readings:
            raise ValueError(f'data_space.readings 找不到仪表/温度计组件：{cid}')
        rd = readings[cid]
        if rd['kind'] in {'thermometer', 'clinical_thermometer'}:
            col = by_id.get(f'{cid}/column')
            if col is None:
                raise ValueError(f'组件 {cid} 缺少液柱图元 {cid}/column')
            lo, hi = rd['min'], rd['max']
            if rd['axis'] == 'x':
                x_low, x_high = rd['p_low'][0], rd['p_high'][0]
                actual_end = col['at'][0] + col['width']
                actual_val = lo + (actual_end - x_low) / (x_high - x_low) * (hi - lo)
            else:
                y_low, y_high = rd['p_low'][1], rd['p_high'][1]
                actual_end = col['at'][1]
                actual_val = lo + (actual_end - y_low) / (y_high - y_low) * (hi - lo)
            if abs(actual_val - expected_val) > tol_val:
                raise ValueError(f'组件 {cid} 实际渲染液柱读数 {actual_val:.3f} 与期望 {expected_val:g} 偏差超过 {tol_val:g}')
        elif rd['kind'] == 'phys_meter':
            needle = by_id.get(f'{cid}/needle')
            if needle is None:
                raise ValueError(f'组件 {cid} 缺少指针图元 {cid}/needle')
            (x0, y0), (x1, y1) = needle['points'][0], needle['points'][-1]
            ang = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360
            a0, a1 = rd['a0'], rd['a1']
            lo, hi = rd['min'], rd['max']
            actual_val = lo + (ang - a0) / (a1 - a0) * (hi - lo)
            if abs(actual_val - expected_val) > tol_val:
                raise ValueError(f'仪表 {cid} 实际渲染指针读数 {actual_val:.3f} 与期望 {expected_val:g} 偏差超过 {tol_val:g}')


def validate_state_checks(elements, understanding, font_path=None):
    """Verify motion/state geometric invariants (relative position + gap, bubble size trend) (V1.1 Section 4.3 #3)."""
    checks = understanding.get('state_checks')
    if not isinstance(checks, list):
        return
    by_id = {e['id']: e for e in elements if isinstance(e, dict) and 'id' in e}

    def obj_box(oid):
        els = [e for e in elements if isinstance(e, dict) and e.get('object_id') == oid and e.get('kind') != 'label']
        if not els and oid in by_id:
            els = [by_id[oid]]
        if not els:
            raise ValueError(f'state_checks 找不到对象或元素：{oid}')
        boxes = [element_box(e, font_path) for e in els]
        return [min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes)]

    for chk in checks:
        kind = chk.get('kind')
        if kind == 'relative_position':
            ba, bb = obj_box(chk['a']), obj_box(chk['b'])
            rel = chk.get('relation')
            min_gap = num(chk.get('min_gap', 0), 'state_check.min_gap')
            if rel == 'left_of':
                gap = bb[0] - ba[2]
                if gap < min_gap:
                    raise ValueError(f'相对位置校验失败：{chk["a"]} 应在 {chk["b"]} 左侧且间隙 ≥ {min_gap:g}（实际 {gap:.1f}）')
            elif rel == 'right_of':
                gap = ba[0] - bb[2]
                if gap < min_gap:
                    raise ValueError(f'相对位置校验失败：{chk["a"]} 应在 {chk["b"]} 右侧且间隙 ≥ {min_gap:g}（实际 {gap:.1f}）')
            elif rel == 'above':
                gap = bb[1] - ba[3]
                if gap < min_gap:
                    raise ValueError(f'相对位置校验失败：{chk["a"]} 应在 {chk["b"]} 上方且间隙 ≥ {min_gap:g}（实际 {gap:.1f}）')
            elif rel == 'below':
                gap = ba[1] - bb[3]
                if gap < min_gap:
                    raise ValueError(f'相对位置校验失败：{chk["a"]} 应在 {chk["b"]} 下方且间隙 ≥ {min_gap:g}（实际 {gap:.1f}）')
            else:
                raise ValueError(f'不支持的 relative_position 关系：{rel}')
        elif kind == 'monotonic_radius':
            eids = chk.get('elements', [])
            if len(eids) < 2:
                raise ValueError('monotonic_radius 至少需要 2 个圆形元素')
            circles = []
            for eid in eids:
                el = by_id.get(eid)
                if not el or el.get('kind') != 'circle':
                    raise ValueError(f'monotonic_radius 元素 {eid} 必须是 circle')
                circles.append((el['center'][1], el['radius'], eid))
            # Sort from bottom (largest y) to top (smallest y) when direction=='up'
            direction = chk.get('direction', 'up')
            circles.sort(key=lambda c: -c[0] if direction == 'up' else c[0])
            trend = chk.get('trend')
            for (_, r0, id0), (_, r1, id1) in zip(circles, circles[1:]):
                if trend == 'increasing' and r1 <= r0:
                    raise ValueError(f'气泡大小趋势错误：上升方向 {id1}(r={r1}) 应大于 {id0}(r={r0})')
                if trend == 'decreasing' and r1 >= r0:
                    raise ValueError(f'气泡大小趋势错误：上升方向 {id1}(r={r1}) 应小于 {id0}(r={r0})')
        else:
            raise ValueError(f'不支持的 state_checks 类型：{kind}')


def check_label_overlaps(elements, font_path=None, pad=0.0):
    """Return list of (id_a, id_b) pairs whose label bounding boxes overlap."""
    labels = [(e['id'], label_box(e, font_path)) for e in elements if isinstance(e, dict) and e.get('kind') == 'label']
    overlaps = []
    for i in range(len(labels)):
        id_a, a = labels[i]
        for j in range(i + 1, len(labels)):
            id_b, b = labels[j]
            if a[0] - pad < b[2] and a[2] + pad > b[0] and a[1] - pad < b[3] and a[3] + pad > b[1]:
                overlaps.append((id_a, id_b))
    return overlaps


def expand_scene(scene, *, understanding=None, font_path=None):
    """Return a new scene containing only figure_drawing primitives; the input is not modified."""
    if not isinstance(scene, dict) or not isinstance(scene.get('elements'), list):
        return scene
    has_v11_checks = isinstance(understanding, dict) and bool(
        set(understanding) & {'terminal_connections', 'data_space', 'state_checks'}
    )
    if (not any(isinstance(e, dict) and e.get('kind') in EXTENDED for e in scene['elements'])
            and 'fit' not in scene and not has_v11_checks):
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
    terminals, owners, junctions, circuit_ids = {}, {}, {}, set()
    data_spaces, readings = {}, {}
    elements = []
    for element in scene['elements']:
        if not isinstance(element, dict):
            elements.append(element)
            continue
        if element.get('kind') == 'component':
            parts, points, meta = _expand_component_with_meta(element, kinds, params)
            elements.extend(parts)
            terminals[element['id']] = points
            owners[element['id']] = element['object_id']
            if 'data_space' in meta:
                data_spaces[element['id']] = meta['data_space']
            if 'reading' in meta:
                readings[element['id']] = meta['reading']
            if element.get('type') in CIRCUIT_TYPES:
                circuit_ids.add(element['id'])
        elif element.get('kind') == 'junction':
            unknown = set(element) - JUNCTION_KEYS
            if unknown:
                raise ValueError(f'节点 {element.get("id")} 含不支持的字段 {sorted(unknown)}')
            at = pt(element.get('at'), f'节点 {element.get("id")} 的 at')
            dot = {'id': element['id'], 'kind': 'circle', 'center': at,
                   'radius': num(element.get('radius', 2 * CIRCUIT_STROKE), '节点半径'), 'fill': 'black', 'stroke_width': 1}
            if element.get('object_id'):
                dot['object_id'] = element['object_id']
            junctions[element['id']] = (at, element.get('object_id'))
            circuit_ids.add(element['id'])
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
        if not isinstance(element, dict):
            result.append(element)
            continue
        if element.get('kind') == 'data_curve':
            eid = element.get('id')
            unknown = set(element) - DATA_CURVE_KEYS
            if unknown:
                raise ValueError(f'数据曲线 {eid} 含不支持的字段 {sorted(unknown)}')
            axes_id = element.get('axes')
            if axes_id not in data_spaces:
                raise ValueError(f'数据曲线 {eid} 引用的坐标系 {axes_id!r} 未定义 x_range/y_range')
            raw_pts = element.get('points')
            if not isinstance(raw_pts, list) or len(raw_pts) < 2:
                raise ValueError(f'数据曲线 {eid} 至少需要 2 个数据点')
            mapped = [map_data_point(data_spaces[axes_id], p) for p in raw_pts]
            out = {'id': eid, 'kind': 'line' if len(mapped) == 2 else 'polyline',
                   'points': mapped, 'stroke_width': element.get('stroke_width', 1.6)}
            if element.get('object_id'):
                out['object_id'] = element['object_id']
            for key in ('dash', 'arrow'):
                if key in element:
                    out[key] = element[key]
            result.append(out)
            if element.get('markers') == 'dot':
                for idx, mp in enumerate(mapped):
                    dot = {'id': f'{eid}/pt{idx}', 'kind': 'circle', 'center': mp, 'radius': 2.2,
                           'fill': 'black', 'stroke_width': 0.8}
                    if element.get('object_id'):
                        dot['object_id'] = element['object_id']
                    result.append(dot)
            continue
        if element.get('kind') != 'wire':
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
        # Circuit wires share the symbol stroke (19.1); apparatus connections keep the general 1.5.
        str_ends = [element[k].partition('.')[0] for k in ('from', 'to') if isinstance(element.get(k), str)]
        default_width = CIRCUIT_STROKE if str_ends and all(e in circuit_ids for e in str_ends) else 1.5
        out = {'id': wid, 'kind': 'line' if len(points) == 2 else 'polyline', 'points': points,
               'connection': connection, 'stroke_width': element.get('stroke_width', default_width)}
        for key in ('dash', 'arrow'):
            if key in element:
                out[key] = element[key]
        result.append(out)
    scene['elements'] = result
    dx, dy = 0.0, 0.0
    if 'fit' in scene:
        _, dx, dy = _fit_canvas_with_shift(scene, font_path)
    # Build shifted anchor/data-space/reading tables for geometric validation
    if isinstance(understanding, dict):
        if 'terminal_connections' in understanding:
            anchors = {}
            for cid, tmap in terminals.items():
                for tname, pos in tmap.items():
                    anchors[f'{cid}.{tname}'] = [round(pos[0] + dx, 4), round(pos[1] + dy, 4)]
            for jid, (pos, _) in junctions.items():
                anchors[jid] = [round(pos[0] + dx, 4), round(pos[1] + dy, 4)]
            validate_terminal_connections(scene['elements'], anchors, understanding)
        if 'data_space' in understanding:
            shifted_ds = {
                cid: {**ds, 'origin': [round(ds['origin'][0] + dx, 4), round(ds['origin'][1] + dy, 4)]}
                for cid, ds in data_spaces.items()
            }
            shifted_rd = {}
            for cid, rd in readings.items():
                rd_copy = deepcopy(rd)
                if 'p_low' in rd_copy and 'p_high' in rd_copy:
                    rd_copy['p_low'] = [round(rd_copy['p_low'][0] + dx, 4), round(rd_copy['p_low'][1] + dy, 4)]
                    rd_copy['p_high'] = [round(rd_copy['p_high'][0] + dx, 4), round(rd_copy['p_high'][1] + dy, 4)]
                shifted_rd[cid] = rd_copy
            validate_data_space(scene['elements'], shifted_ds, shifted_rd, understanding)
        if 'state_checks' in understanding:
            validate_state_checks(scene['elements'], understanding, font_path)
    return scene


def label_box(element, font_path):
    from figure_drawing import layout_label
    from PIL import Image, ImageDraw
    draw = ImageDraw.Draw(Image.new('L', (1, 1)))
    laid = layout_label(element, font_path)
    boxes = [draw.textbbox((run['dx'], laid['y'] + run['dy']), run['text'], font=run['font'], anchor='ls')
             for run in laid['runs']]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def element_box(element, font_path):
    from figure_drawing import arrow_triangle, samples
    if element['kind'] == 'label':
        return label_box(element, font_path)
    base_pts = samples(element)
    points = list(base_pts)
    arrow = element.get('arrow', 'none')
    if arrow in {'start', 'both'}:
        points += arrow_triangle(base_pts, element.get('stroke_width', 1.5), True)
    if arrow in {'end', 'both'}:
        points += arrow_triangle(base_pts, element.get('stroke_width', 1.5))
    half = element.get('stroke_width', 1.5) / 2
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [min(xs) - half, min(ys) - half, max(xs) + half, max(ys) + half]


def shift(element, dx, dy):
    if 'points' in element:
        element['points'] = [[round(x + dx, 4), round(y + dy, 4)] for x, y in element['points']]
    for key in ('center', 'at'):
        if key in element:
            element[key] = [round(element[key][0] + dx, 4), round(element[key][1] + dy, 4)]


def _fit_canvas_with_shift(scene, font_path=None):
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
    return scene, dx, dy


def fit_canvas(scene, font_path=None):
    scene, _, _ = _fit_canvas_with_shift(scene, font_path)
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
