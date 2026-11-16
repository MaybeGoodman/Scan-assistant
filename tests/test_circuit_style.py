"""REQUIREMENTS 19.1 / 25.1: textbook circuit symbols and serif italic/upright label typography."""
from copy import deepcopy
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
from test_figures import document, reviews, scene  # noqa: E402
from test_components import circuit, understanding  # noqa: E402
import figure_drawing  # noqa: E402
from figure_drawing import FONT_DIR, auto_style, label_runs, layout_label, pick_font, render, safe_svg  # noqa: E402
from figure_components import CIRCUIT_STROKE, PIVOT_R, expand_scene  # noqa: E402
from figure_workflow import complete, generate, review_template  # noqa: E402


def part(elements, name):
    return next(e for e in elements if e['id'] == name)


class LabelTypographyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_bundled_serif_fonts_are_used_by_style(self):
        for style, name in (('italic', 'STIXTwoText-Italic.ttf'), ('upright', 'STIXTwoText-Regular.ttf')):
            font, fallback = pick_font(30, 'R', style=style)
            self.assertFalse(fallback)
            self.assertEqual(Path(font.path).name, name)
            self.assertEqual(Path(font.path).parent, FONT_DIR)
        self.assertTrue((FONT_DIR / 'OFL.txt').is_file())

    def test_automatic_convention_and_explicit_override(self):
        self.assertEqual(auto_style('R'), 'italic')
        self.assertEqual(auto_style('AB'), 'italic')
        self.assertEqual(auto_style('θ'), 'italic')
        for text in ('1', '5 N', '2cm', 'cm', 'sin', 'Ω', '+', '甲'):
            self.assertEqual(auto_style(text), 'upright', text)
        laid = layout_label({'id': 'l', 'kind': 'label', 'at': [10, 10], 'size': 14,
                             'runs': [{'text': 'R'}, {'text': '1', 'script': 'sub'}]})
        self.assertEqual([r['style'] for r in laid['runs']], ['italic', 'upright'])
        self.assertAlmostEqual(laid['runs'][1]['dy'], 14 * .25)
        laid = layout_label({'id': 'l', 'kind': 'label', 'at': [10, 10], 'text': 'N', 'style': 'upright'})
        self.assertEqual(laid['runs'][0]['style'], 'upright')
        laid = layout_label({'id': 'l', 'kind': 'label', 'at': [10, 10], 'style': 'upright',
                             'runs': [{'text': 'v', 'style': 'italic'}, {'text': 'm/s'}]})
        self.assertEqual([r['style'] for r in laid['runs']], ['italic', 'upright'])
        with self.assertRaisesRegex(ValueError, 'style'):
            layout_label({'id': 'l', 'kind': 'label', 'at': [10, 10], 'text': 'N', 'style': 'bold'})
        # Chemistry formulas stay upright; variables with subscripts stay italic.
        for runs in ([{'text': 'H'}, {'text': '2', 'script': 'sub'}, {'text': 'O'}],
                     [{'text': 'CO'}, {'text': '2', 'script': 'sub'}],
                     [{'text': 'NaCl'}], [{'text': 'Fe'}, {'text': '3+', 'script': 'sup'}]):
            laid = layout_label({'id': 'l', 'kind': 'label', 'at': [10, 10], 'runs': runs})
            self.assertEqual({r['style'] for r in laid['runs']}, {'upright'}, runs)
        for runs in ([{'text': 'v'}, {'text': '0', 'script': 'sub'}], [{'text': 'R'}, {'text': '1', 'script': 'sub'}],
                     [{'text': 'AB'}], [{'text': 'F'}, {'text': 'A', 'script': 'sub'}]):
            laid = layout_label({'id': 'l', 'kind': 'label', 'at': [10, 10], 'runs': runs})
            self.assertEqual(laid['runs'][0]['style'], 'italic', runs)

    def test_style_is_typography_not_label_content(self):
        s = scene()
        s['elements'][-1]['runs'] = [{'text': 'F', 'style': 'italic'}, {'text': '1', 'script': 'sub', 'style': 'upright'}]
        self.assertEqual(label_runs(s['elements'][-1]), label_runs(s['structure']['labels'][0]))
        result = render(s, self.root / 'a.svg', self.root / 'a.png', understanding=s['structure'])
        self.assertNotIn('font_fallback', result)
        svg = (self.root / 'a.svg').read_text(encoding='utf-8')
        self.assertIn('STIX Two Text', svg)
        self.assertIn('font-style="italic">F<', svg)
        self.assertIn('font-size="12.6">1<', svg)
        self.assertNotIn('font-style="italic">1<', svg)
        safe_svg(self.root / 'a.svg')

    def test_explicit_font_is_final_and_missing_font_still_fails(self):
        s = scene()
        bundled = FONT_DIR / 'STIXTwoText-Regular.ttf'
        result = render(s, self.root / 'b.svg', self.root / 'b.png', understanding=s['structure'], font_path=bundled)
        self.assertNotIn('font_fallback', result)
        with self.assertRaisesRegex(ValueError, 'font'):
            render(s, self.root / 'c.svg', self.root / 'c.png', understanding=s['structure'], font_path=self.root / 'no.ttf')

    def test_sans_fallback_is_flagged_and_caps_review_at_minor_issue(self):
        doc = document(self.root)
        with mock.patch.object(figure_drawing, 'SERIF_FONTS', {'italic': [], 'upright': []}):
            s = scene()
            result = render(s, self.root / 'd.svg', self.root / 'd.png', understanding=s['structure'])
            self.assertTrue(result['font_fallback'])
            ledger = generate(doc, self.root, self.root / 'images', mode='redraw')
        entry = ledger['records'][0]['attempts'][-1]
        self.assertTrue(entry['font_fallback'])
        row = review_template(ledger)['reviews'][0]
        self.assertTrue(row['font_fallback'])
        self.assertTrue(any('font_fallback' in note for note in row['notes']))
        _, rejected = complete(ledger, reviews(ledger, 'pass'), self.root)
        self.assertEqual(rejected['records'][0]['state'], 'failed')
        self.assertIn('font_fallback', rejected['records'][0]['reason'])
        result, done = complete(ledger, reviews(ledger, 'minor_issue'), self.root)
        self.assertEqual(done['status'], 'completed')
        image = next(b for b in result['blocks'] if b.get('type') == 'image')
        self.assertTrue(image['redraw']['font_fallback'])
        # Without fallback neither the attempt nor the finished block carries the marker.
        clean = generate(document(self.root), self.root, self.root / 'images2', mode='redraw')
        self.assertNotIn('font_fallback', clean['records'][0]['attempts'][-1])
        self.assertNotIn('font_fallback', review_template(clean)['reviews'][0])
        result, _ = complete(clean, reviews(clean, 'pass'), self.root)
        self.assertNotIn('font_fallback', next(b for b in result['blocks'] if b.get('type') == 'image')['redraw'])


class CircuitSymbolTests(unittest.TestCase):
    def expand(self, ctype, params=None, orientation='h', extra=()):
        source = understanding([('X', {'kind': ctype, **({'params': params} if params else {})})] + list(extra))
        elements = [{'id': 'X', 'kind': 'component', 'type': ctype, 'object_id': 'X', 'at': [100, 100],
                     'orientation': orientation, **({'params': params} if params else {})}]
        return expand_scene({'width': 300, 'height': 300, 'structure': source, 'elements': elements},
                            understanding=source)['elements']

    def test_battery_cells_alternate_short_thick_and_long_thin_without_links(self):
        parts = self.expand('battery', {'cells': 2, 'positive': 'b'})
        names = {e['id'].split('/')[1] for e in parts}
        self.assertEqual(names, {'long1', 'short1', 'long2', 'short2', 'lead_a', 'lead_b'})
        long1, short1 = part(parts, 'X/long1'), part(parts, 'X/short1')
        self.assertEqual(long1['stroke_width'], CIRCUIT_STROKE)
        self.assertEqual(short1['stroke_width'], 3 * CIRCUIT_STROKE)
        self.assertAlmostEqual(abs(long1['points'][0][1] - long1['points'][1][1]), 21)
        self.assertAlmostEqual(abs(short1['points'][0][1] - short1['points'][1][1]), 11)
        xs = sorted(part(parts, f'X/{n}')['points'][0][0] for n in ('short1', 'long1', 'short2', 'long2'))
        self.assertEqual([round(b - a, 4) for a, b in zip(xs, xs[1:])], [6, 6, 6])
        # positive='b': the long (positive) line of each cell is on the b side.
        self.assertGreater(long1['points'][0][0], short1['points'][0][0])

    def test_rheostat_slider_arrowhead_touches_body(self):
        parts = self.expand('rheostat', {'slider': 0.25})
        body, head, line = part(parts, 'X/body'), part(parts, 'X/slider_head'), part(parts, 'X/slider')
        self.assertEqual((body['width'], body['height']), (48, 12))
        tip = min(head['points'], key=lambda p: -p[1])
        self.assertAlmostEqual(tip[1], body['at'][1])          # tip on the top edge of the body
        self.assertAlmostEqual(tip[0], body['at'][0] + 48 * .25)
        self.assertEqual(head['fill'], 'black')
        self.assertNotIn('arrow', line)                        # a symbol polygon, not a source arrow
        self.assertAlmostEqual(line['points'][0][1], body['at'][1] - 24)  # one lamp diameter above

    def test_switch_has_hollow_pivot_and_blade_from_its_edge(self):
        parts = self.expand('switch', {'state': 'open'})
        pivot, blade = part(parts, 'X/pivot'), part(parts, 'X/blade')
        self.assertEqual(pivot['fill'], 'white')
        self.assertEqual(pivot['radius'], PIVOT_R)
        self.assertFalse(any(e['id'].endswith('contact_b') for e in parts))
        (x0, y0), (x1, y1) = blade['points']
        self.assertAlmostEqual(math.hypot(x0 - pivot['center'][0], y0 - pivot['center'][1]), PIVOT_R, places=3)
        angle = math.degrees(math.atan2(y0 - y1, x1 - x0))
        self.assertTrue(25 <= angle <= 35, angle)
        self.assertLess(x1, 116)                                # never past the right lead end
        closed = part(self.expand('switch', {'state': 'closed'}), 'X/blade')
        self.assertAlmostEqual(closed['points'][0][1], closed['points'][1][1])
        self.assertAlmostEqual(closed['points'][1][0], 116)
        down = part(self.expand('switch', {'state': 'open', 'blade_side': 'down'}), 'X/blade')
        self.assertGreater(down['points'][1][1], down['points'][0][1])
        spdt = self.expand('switch_spdt', {'to': 'c'})
        self.assertEqual(part(spdt, 'X/pivot')['fill'], 'white')
        self.assertGreater(part(spdt, 'X/blade')['points'][1][1], 100)

    def test_meters_are_larger_than_lamps_with_upright_serif_letters(self):
        lamp = part(self.expand('lamp'), 'X/circle')
        for ctype in ('ammeter', 'voltmeter', 'motor'):
            parts = self.expand(ctype)
            circle, letter = part(parts, 'X/circle'), part(parts, 'X/letter')
            self.assertAlmostEqual(circle['radius'] / lamp['radius'], 1.29, places=2)
            self.assertEqual(letter['style'], 'upright')
            self.assertTrue(.4 <= letter['size'] * .66 / (2 * circle['radius']) <= .5)
            self.assertEqual(circle['stroke_width'], CIRCUIT_STROKE)
        x1 = part(self.expand('lamp'), 'X/x1')
        self.assertAlmostEqual(math.dist(*x1['points']), 2 * lamp['radius'], places=3)

    def test_circuit_wires_and_junctions_share_the_symbol_stroke(self):
        value, source = circuit()
        elements = expand_scene(value, understanding=source)['elements']
        self.assertEqual({e['stroke_width'] for e in elements if 'connection' in e}, {CIRCUIT_STROKE})
        self.assertEqual(part(elements, 'j1')['radius'], 2 * CIRCUIT_STROKE)
        self.assertEqual({e['stroke_width'] for e in elements if e['id'].startswith(('L1/', 'S/', 'B/long'))},
                         {CIRCUIT_STROKE})
        explicit = deepcopy(value)
        part(explicit['elements'], 'w1')['stroke_width'] = 2
        self.assertEqual(part(expand_scene(explicit, understanding=source)['elements'], 'w1')['stroke_width'], 2)
        # Apparatus connections keep the general 1.5 width.
        lab = understanding([('T', 'test_tube'), ('K', 'beaker')], connections=[('T', 'K')])
        tubes = expand_scene({'width': 400, 'height': 400, 'structure': lab, 'elements': [
            {'id': 'T', 'kind': 'component', 'type': 'test_tube', 'object_id': 'T', 'at': [100, 200]},
            {'id': 'K', 'kind': 'component', 'type': 'beaker', 'object_id': 'K', 'at': [250, 200]},
            {'id': 'w', 'kind': 'wire', 'from': 'T.top', 'to': 'K.top'}]}, understanding=lab)['elements']
        self.assertEqual(part(tubes, 'w')['stroke_width'], 1.5)

    def test_reference_circuit_renders_and_validates(self):
        value, source = circuit()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = render(value, root / 'c.svg', root / 'c.png', understanding=source)
            self.assertNotIn('font_fallback', result)
            self.assertIn('font-style="italic">L<', (root / 'c.svg').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
