"""Structured scenes for the sample figures (source redraws and variant figures)."""
import math


def label(element_id, object_id, at, text, sub=None, size=14, anchor='middle'):
    runs = [{'text': text}] + ([{'text': sub, 'script': 'sub'}] if sub else [])
    return {'id': element_id, 'kind': 'label', 'object_id': object_id, 'label_id': element_id,
            'at': at, 'anchor': anchor, 'size': size, 'runs': runs}


def triangle(ab, bc):
    """Isosceles triangle ABC (AB=AC=ab, BC=bc), median AD and DE ⊥ AB, to scale."""
    h = math.sqrt(ab ** 2 - (bc / 2) ** 2)
    scale = 220 / max(bc, h)
    ox, oy = 90, 40 + h * scale

    def p(x, y):
        return [round(ox + x * scale, 2), round(oy - y * scale, 2)]
    a, b, c, d = (bc / 2, h), (0, 0), (bc, 0), (bc / 2, 0)
    # Foot of the perpendicular from D to AB.
    ux, uy = (a[0] - b[0]) / ab, (a[1] - b[1]) / ab
    t = (d[0] - b[0]) * ux + (d[1] - b[1]) * uy
    e = (b[0] + t * ux, b[1] + t * uy)
    # Right-angle mark at E, inside the angle between ED and EA.
    m = 10 / scale
    vx, vy = (d[0] - e[0]), (d[1] - e[1])
    vl = math.hypot(vx, vy)
    vx, vy = vx / vl, vy / vl
    corner1 = (e[0] + ux * m, e[1] + uy * m)
    corner2 = (corner1[0] + vx * m, corner1[1] + vy * m)
    corner3 = (e[0] + vx * m, e[1] + vy * m)
    objects = [{'id': 'ABC', 'kind': 'triangle'}, {'id': 'AD', 'kind': 'segment'},
               {'id': 'DE', 'kind': 'segment'}]
    names = [('A', a, [0, -10]), ('B', b, [-12, 6]), ('C', c, [12, 6]), ('D', d, [0, 20]), ('E', e, [-14, -2])]
    labels = [{'id': f'p{n}', 'target': 'DE' if n == 'E' else 'AD' if n == 'D' else 'ABC', 'text': n}
              for n, _, _ in names]
    structure = {'objects': objects, 'labels': labels, 'arrows': [], 'connections': [],
                 'facts': {'AB_equals_AC': True, 'D_midpoint_BC': True, 'DE_perpendicular_AB': True,
                           'proportion': f'AB:BC={ab}:{bc}'}}
    elements = [{'id': 'ABC', 'kind': 'polygon', 'object_id': 'ABC', 'points': [p(*a), p(*b), p(*c)]},
                {'id': 'AD', 'kind': 'line', 'object_id': 'AD', 'points': [p(*a), p(*d)]},
                {'id': 'DE', 'kind': 'line', 'object_id': 'DE', 'points': [p(*d), p(*e)]},
                {'id': 'DE-mark', 'kind': 'polyline', 'object_id': 'DE',
                 'points': [p(*corner1), p(*corner2), p(*corner3)], 'stroke_width': 1}]
    for name, point, offset in names:
        x, y = p(*point)
        elements.append(label(f'p{name}', 'DE' if name == 'E' else 'AD' if name == 'D' else 'ABC',
                              [round(x + offset[0], 2), round(y + offset[1], 2)], name))
    width = round(bc * scale + 180)
    return {'width': max(width, 300), 'height': round(h * scale + 90), 'structure': structure,
            'elements': elements}, structure


def circuit():
    """Series loop: battery, switch, R1, R2, ammeter; voltmeter across R2."""
    objects = [{'id': 'B', 'kind': 'battery'}, {'id': 'S', 'kind': 'switch', 'params': {'state': 'open'}},
               {'id': 'R1', 'kind': 'resistor'}, {'id': 'R2', 'kind': 'resistor'},
               {'id': 'A', 'kind': 'ammeter'}, {'id': 'V', 'kind': 'voltmeter'},
               {'id': 'j1', 'kind': 'node'}, {'id': 'j2', 'kind': 'node'}]
    labels = [{'id': 'lR1', 'target': 'R1', 'runs': [{'text': 'R', 'script': 'normal'}, {'text': '1', 'script': 'sub'}]},
              {'id': 'lR2', 'target': 'R2', 'runs': [{'text': 'R', 'script': 'normal'}, {'text': '2', 'script': 'sub'}]},
              {'id': 'lS', 'target': 'S', 'text': 'S'}]
    connections = [['B', 'S'], ['S', 'A'], ['A', 'j2'], ['j2', 'R2'], ['R2', 'j1'], ['j1', 'R1'], ['R1', 'B'],
                   ['V', 'j1'], ['V', 'j2']]
    structure = {'objects': objects, 'labels': labels, 'arrows': [], 'connections': connections,
                 'facts': {'series': ['B', 'S', 'A', 'R2', 'R1'], 'voltmeter_across': 'R2', 'switch': 'open'}}
    elements = [
        {'id': 'B', 'kind': 'component', 'type': 'battery', 'object_id': 'B', 'at': [70, 40], 'params': {'cells': 2}},
        {'id': 'S', 'kind': 'component', 'type': 'switch', 'object_id': 'S', 'at': [180, 40], 'params': {'state': 'open'}},
        {'id': 'A', 'kind': 'component', 'type': 'ammeter', 'object_id': 'A', 'at': [260, 110], 'orientation': 'v'},
        {'id': 'R2', 'kind': 'component', 'type': 'resistor', 'object_id': 'R2', 'at': [190, 180]},
        {'id': 'R1', 'kind': 'component', 'type': 'resistor', 'object_id': 'R1', 'at': [70, 180]},
        {'id': 'V', 'kind': 'component', 'type': 'voltmeter', 'object_id': 'V', 'at': [190, 240]},
        {'id': 'j1', 'kind': 'junction', 'object_id': 'j1', 'at': [140, 180]},
        {'id': 'j2', 'kind': 'junction', 'object_id': 'j2', 'at': [240, 180]},
        {'id': 'w1', 'kind': 'wire', 'from': 'B.b', 'to': 'S.a'},
        {'id': 'w2', 'kind': 'wire', 'from': 'S.b', 'to': 'A.a', 'route': 'hv'},
        {'id': 'w3', 'kind': 'wire', 'from': 'A.b', 'to': 'j2', 'route': 'vh'},
        {'id': 'w4', 'kind': 'wire', 'from': 'j2', 'to': 'R2.b'},
        {'id': 'w5', 'kind': 'wire', 'from': 'R2.a', 'to': 'j1'},
        {'id': 'w6', 'kind': 'wire', 'from': 'j1', 'to': 'R1.b'},
        {'id': 'w7', 'kind': 'wire', 'from': 'R1.a', 'to': 'B.a', 'route': 'manual', 'via': [[20, 180], [20, 40]]},
        {'id': 'w8', 'kind': 'wire', 'from': 'V.a', 'to': 'j1', 'route': 'hv'},
        {'id': 'w9', 'kind': 'wire', 'from': 'V.b', 'to': 'j2', 'route': 'hv'},
        label('lR1', 'R1', [70, 165], 'R', '1'), label('lR2', 'R2', [190, 165], 'R', '2'),
        label('lS', 'S', [180, 25], 'S'),
    ]
    return {'width': 'auto', 'height': 'auto', 'fit': {'margin': 14}, 'structure': structure,
            'elements': elements}, structure
