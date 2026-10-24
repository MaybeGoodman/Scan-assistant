"""0.7.0: component library, wires, junctions, canvas fit and located validation errors."""
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
from test_figures import document, scene  # noqa: E402
from figure_components import COMPONENTS, element_box, expand_scene  # noqa: E402
from figure_drawing import check_black_white, render, safe_svg, validate_scene  # noqa: E402
from figure_workflow import generate  # noqa: E402


def understanding(objects, labels=(), connections=(), arrows=()):
    return {'objects': [dict(id=i, **(k if isinstance(k, dict) else {'kind': k})) for i, k in objects],
            'labels': list(labels), 'arrows': list(arrows), 'connections': [list(c) for c in connections]}


def circuit():
    """Battery + open switch, L1 and L2 in parallel, voltmeter across L1 (spec acceptance case A.9-2)."""
    source = understanding(
        [('B', 'battery'), ('S', {'kind': 'switch', 'params': {'state': 'open'}}), ('L1', 'lamp'), ('L2', 'lamp'),
         ('V', 'voltmeter'), ('j1', 'node'), ('j2', 'node')],
        labels=[{'id': 'l1', 'target': 'L1', 'runs': [{'text': 'L', 'script': 'normal'}, {'text': '1', 'script': 'sub'}]}],
        connections=[('B', 'j1'), ('B', 'S'), ('S', 'j2'), ('j1', 'L1'), ('L1', 'j2'), ('j1', 'L2'), ('L2', 'j2'),
                     ('V', 'j1'), ('V', 'j2')])
    elements = [
        {'id': 'B', 'kind': 'component', 'type': 'battery', 'object_id': 'B', 'at': [60, 40], 'params': {'cells': 2}},
        {'id': 'S', 'kind': 'component', 'type': 'switch', 'object_id': 'S', 'at': [160, 40], 'params': {'state': 'open'}},
        {'id': 'L1', 'kind': 'component', 'type': 'lamp', 'object_id': 'L1', 'at': [110, 110]},
        {'id': 'L2', 'kind': 'component', 'type': 'lamp', 'object_id': 'L2', 'at': [110, 170]},
        {'id': 'V', 'kind': 'component', 'type': 'voltmeter', 'object_id': 'V', 'at': [110, 75]},
        {'id': 'j1', 'kind': 'junction', 'at': [20, 110], 'object_id': 'j1'},
        {'id': 'j2', 'kind': 'junction', 'at': [200, 110], 'object_id': 'j2'},
        {'id': 'w1', 'kind': 'wire', 'from': 'B.a', 'to': 'j1'},
        {'id': 'w2', 'kind': 'wire', 'from': 'B.b', 'to': 'S.a'},
        {'id': 'w3', 'kind': 'wire', 'from': 'S.b', 'to': 'j2'},
        {'id': 'w4', 'kind': 'wire', 'from': 'j1', 'to': 'L1.a'},
        {'id': 'w5', 'kind': 'wire', 'from': 'L1.b', 'to': 'j2'},
        {'id': 'w6', 'kind': 'wire', 'from': 'j1', 'to': 'L2.a', 'route': 'vh'},
        {'id': 'w7', 'kind': 'wire', 'from': 'L2.b', 'to': 'j2'},
        {'id': 'w8', 'kind': 'wire', 'from': 'V.a', 'to': 'j1', 'route': 'manual', 'via': [[40, 75], [40, 110]]},
        {'id': 'w9', 'kind': 'wire', 'from': 'V.b', 'to': 'j2', 'route': 'manual', 'via': [[180, 75], [180, 110]]},
        {'id': 'l1', 'kind': 'label', 'object_id': 'L1', 'label_id': 'l1', 'at': [110, 95], 'anchor': 'middle',
         'size': 13, 'runs': [{'text': 'L'}, {'text': '1', 'script': 'sub'}]},
    ]
    return {'width': 240, 'height': 210, 'structure': source, 'elements': elements}, source


class ComponentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def draw(self, value, name='f', source=None):
        return render(value, self.root / f'{name}.svg', self.root / f'{name}.png',
                      understanding=source if source is not None else value['structure'])

    def test_0_6_0_scenes_pass_through_unchanged(self):
        old = scene()
        self.assertIs(expand_scene(old, understanding=old['structure']), old)
        first = self.draw(old, 'a')
        second = render(expand_scene(deepcopy(old)), self.root / 'b.svg', self.root / 'b.png',
                        understanding=old['structure'])
        self.assertEqual(first['png_sha256'], second['png_sha256'])

    def test_component_circuit_passes_structure_and_renders_black_white(self):
        value, source = circuit()
        self.draw(value)
        check_black_white(self.root / 'f.png')
        safe_svg(self.root / 'f.svg')
        expanded = expand_scene(value, understanding=source)
        kinds = {e['kind'] for e in expanded['elements']}
        self.assertFalse(kinds & {'component', 'wire', 'junction'})
        wire = next(e for e in expanded['elements'] if e['id'] == 'w1')
        self.assertEqual(wire['connection'], ['B', 'j1'])
        self.assertTrue(all(len({p[0] for p in pair}) == 1 or len({p[1] for p in pair}) == 1
                            for pair in zip(wire['points'], wire['points'][1:])), 'hv route must be orthogonal')

    def test_type_and_declared_params_must_match_understanding(self):
        value, source = circuit()
        source['objects'][2]['kind'] = 'switch'
        value['structure'] = source
        with self.assertRaisesRegex(ValueError, '组件 L1 的 type=lamp 与原图理解 kind=switch'):
            self.draw(value)
        value, source = circuit()
        value['elements'][1]['params']['state'] = 'closed'
        with self.assertRaisesRegex(ValueError, '组件 S 的 state'):
            self.draw(value)

    def test_symbol_text_is_excluded_from_labels_but_cannot_be_handwritten(self):
        value, source = circuit()
        expanded = expand_scene(value, understanding=source)
        self.assertTrue(any(e.get('symbol') and e['id'] == 'V/letter' for e in expanded['elements']))
        validate_scene(expanded, source)
        forged = deepcopy(expanded)
        forged['elements'].append({'id': 'fake', 'kind': 'label', 'object_id': 'L1', 'at': [10, 200],
                                   'text': 'x', 'symbol': True})
        with self.assertRaisesRegex(ValueError, 'symbol'):
            validate_scene(forged, source)

    def test_slash_ids_are_reserved_for_expansion(self):
        value, _ = circuit()
        value['elements'][-1]['id'] = 'my/label'
        with self.assertRaisesRegex(ValueError, '"/"'):
            self.draw(value)

    def test_wire_endpoints_and_connections(self):
        value, source = circuit()
        value['elements'][9]['to'] = [180, 40]
        with self.assertRaisesRegex(ValueError, '导线 w3 .*connection'):
            expand_scene(value, understanding=source)
        value, source = circuit()
        value['elements'][7]['from'] = 'B.x'
        with self.assertRaisesRegex(ValueError, r"不存在的端子 'x'.*\['a', 'b'\]"):
            expand_scene(value, understanding=source)
        value['elements'][7]['from'] = 'Q.a'
        with self.assertRaisesRegex(ValueError, '不存在的组件或节点：Q'):
            expand_scene(value, understanding=source)

    def test_fit_sets_equal_margins_and_reports_oversize(self):
        value, source = circuit()
        for element in value['elements']:
            for key in ('at',):
                if key in element:
                    element[key] = [element[key][0] + 800, element[key][1] + 800]
            if 'via' in element:
                element['via'] = [[x + 800, y + 800] for x, y in element['via']]
        value.update(width='auto', height='auto', fit={'margin': 16})
        expanded = expand_scene(value, understanding=source)
        boxes = [element_box(e, None) for e in expanded['elements']]
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        right, bottom = max(b[2] for b in boxes), max(b[3] for b in boxes)
        for gap in (left, top, expanded['width'] - right, expanded['height'] - bottom):
            self.assertAlmostEqual(gap, 16, delta=1)
        self.assertNotIn('fit', expanded)
        self.draw(value, 'fit')
        value, source = circuit()
        value.update(width=100, height='auto', fit={'margin': 10})
        with self.assertRaisesRegex(ValueError, '内容外框 .* 超出画布上限 100'):
            expand_scene(value, understanding=source)

    def test_validation_errors_name_elements(self):
        value, source = circuit()
        value['elements'][2]['at'] = [235, 110]
        with self.assertRaisesRegex(ValueError, '元素 L1/circle 越界'):
            self.draw(value, 'clip')
        old = scene()
        old['elements'][0]['object_id'] = 'other'
        with self.assertRaisesRegex(ValueError, r"缺少 \['body'\].*多出 \['other'\]"):
            validate_scene(old, old['structure'])
        old = scene()
        old['elements'].pop()
        with self.assertRaisesRegex(ValueError, r"缺少 \['force-label'\]"):
            validate_scene(old, old['structure'])
        value, source = circuit()
        value['elements'][8]['to'] = 'L2.a'
        with self.assertRaisesRegex(ValueError, r"缺少 \[\"\['B', 'S'\]\"\].*多出 \[\"\['B', 'L2'\]\"\]"):
            self.draw(value, 'conn')

    def test_dial_needle_points_at_value(self):
        source = understanding([('D', 'meter_dial')])
        value = {'width': 'auto', 'height': 'auto', 'fit': {'margin': 10}, 'structure': source, 'elements': [
            {'id': 'D', 'kind': 'component', 'type': 'meter_dial', 'object_id': 'D', 'at': [100, 100],
             'params': {'ranges': [[0, 15], [0, 3]], 'needle': 1.6, 'needle_range': 1, 'unit': 'V',
                        'terminals': ['-', '3', '15']}}]}
        expanded = expand_scene(value, understanding=source)
        needle = next(e for e in expanded['elements'] if e['id'] == 'D/needle')
        (x0, y0), (x1, y1) = needle['points']
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360
        self.assertAlmostEqual(angle, 210 + 120 * 1.6 / 3, delta=.5)
        self.draw(value, 'dial')
        with self.assertRaisesRegex(ValueError, '超出所选量程'):
            value['elements'][0]['params']['needle'] = 4
            expand_scene(value, understanding=source)

    def test_rotated_meter_letter_stays_centred_and_upright(self):
        source = understanding([('A', 'ammeter')])
        for orientation in ('h', 'v', 'h-flip', 'v-flip'):
            value = {'width': 120, 'height': 120, 'structure': source, 'elements': [
                {'id': 'A', 'kind': 'component', 'type': 'ammeter', 'object_id': 'A', 'at': [60, 60],
                 'orientation': orientation}]}
            letter = next(e for e in expand_scene(value, understanding=source)['elements'] if e['id'] == 'A/letter')
            self.assertEqual(letter['at'][0], 60, orientation)
            self.assertAlmostEqual(letter['at'][1], 60 + 15 * .35, delta=.01)

    def test_every_component_renders_in_each_allowed_orientation(self):
        examples = {'rheostat': {'slider': .2}, 'battery': {'cells': 3, 'positive': 'b', 'mark_positive': True},
                    'switch': {'state': 'closed'}, 'switch_spdt': {'to': 'c'}, 'voltmeter': {'subscript': '2'},
                    'meter_dial': {'needle': 2, 'unit': 'A', 'terminals': ['-', '0.6', '3']},
                    'beaker': {'liquid': .4}, 'test_tube': {'liquid': .5}, 'flask': {'liquid': .3, 'stopper': True},
                    'alcohol_lamp': {'lit': True}, 'iron_stand': {'clamp_y': -40, 'ring_y': 10},
                    'thermometer': {'min': -10, 'max': 50, 'major': 10, 'value': 21},
                    'axes': {'x_label': 't/min', 'y_label': [{'text': 'T'}, {'text': '1', 'script': 'sub'}],
                             'x_ticks': [[40, '2']], 'y_ticks': [[50, '20']]}}
        for ctype, (_, _, allowed) in COMPONENTS.items():
            for orientation in ('h', 'v', 'h-flip', 'v-flip'):
                with self.subTest(ctype=ctype, orientation=orientation):
                    if orientation not in allowed:
                        # Scales, axes and upright apparatus must not be drawn backwards or on their side.
                        with self.assertRaisesRegex(ValueError, 'orientation'):
                            expand_scene({'width': 'auto', 'height': 'auto', 'fit': {'margin': 8}, 'elements': [
                                {'id': 'x', 'kind': 'component', 'type': ctype, 'object_id': 'x', 'at': [300, 300],
                                 'orientation': orientation}]})
                        continue
                    source = understanding([('x', ctype)])
                    value = {'width': 'auto', 'height': 'auto', 'fit': {'margin': 8}, 'structure': source,
                             'elements': [{'id': 'x', 'kind': 'component', 'type': ctype, 'object_id': 'x',
                                           'at': [300, 300], 'orientation': orientation,
                                           'params': examples.get(ctype, {})}]}
                    name = f'{ctype}-{orientation}'
                    self.draw(value, name)
                    check_black_white(self.root / f'{name}.png')
                    safe_svg(self.root / f'{name}.svg')

    def test_invalid_component_input_is_rejected_with_id(self):
        source = understanding([('x', 'lamp')])
        base = {'id': 'x', 'kind': 'component', 'type': 'lamp', 'object_id': 'x', 'at': [60, 60]}
        cases = [({'type': 'capacitor'}, '不在组件库'), ({'params': {'cells': 2}}, 'params 只能包含'),
                 ({'orientation': 'diagonal'}, 'orientation'), ({'size': 9}, 'size'), ({'colour': 'red'}, '不支持的字段')]
        for change, message in cases:
            value = {'width': 120, 'height': 120, 'structure': source, 'elements': [{**base, **change}]}
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, f'组件 x.*{message}|{message}'):
                expand_scene(value, understanding=source)
        tube = understanding([('t', 'test_tube')])
        value = {'width': 120, 'height': 160, 'structure': tube, 'elements': [
            {'id': 't', 'kind': 'component', 'type': 'test_tube', 'object_id': 't', 'at': [60, 80],
             'params': {'angle': 30, 'liquid': .5}}]}
        with self.assertRaisesRegex(ValueError, '液面应保持水平'):
            expand_scene(value, understanding=tube)

    def test_component_scene_through_figure_workflow(self):
        doc = document(self.root)
        value, source = circuit()
        figure = doc['figure_task']['figures'][0]
        figure.update(figure_type='circuit', understanding=source, drawing={'scene': value})
        ledger = generate(doc, self.root, self.root / 'images', mode='redraw')
        self.assertEqual(ledger['records'][0]['state'], 'awaiting_validation', ledger['records'][0].get('reason'))

    def test_preview_and_list_cli(self):
        value, _ = circuit()
        path = self.root / 'scene.json'
        path.write_text(json.dumps({'scene': value}, ensure_ascii=False), encoding='utf-8')

        def cli(*args):
            done = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'figure_components.py'), *args],
                                  capture_output=True, text=True, encoding='utf-8')
            return done.returncode, json.loads(done.stdout)
        code, first = cli('preview', str(path), '--output-dir', str(self.root / 'pv'))
        self.assertEqual(code, 0, first)
        code, second = cli('preview', str(path), '--output-dir', str(self.root / 'pv'))
        self.assertEqual(code, 0, second)
        self.assertNotEqual(first['png'], second['png'])
        self.assertTrue(Path(second['png']).name.startswith('preview-2'))
        code, listing = cli('list')
        self.assertEqual(code, 0)
        self.assertEqual(set(listing), set(COMPONENTS))
        self.assertEqual(listing['meter_dial']['orientations'], ['h'])
        value['elements'][2]['type'] = 'switch'
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        code, error = cli('preview', str(path), '--output-dir', str(self.root / 'pv'))
        self.assertEqual(code, 1)
        self.assertIn('组件 L1', error['error'])


if __name__ == '__main__':
    unittest.main()
