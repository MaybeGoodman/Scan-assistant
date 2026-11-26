"""V1.1 P0 image redraw regression tests: two-level figure groups, hybrid routing,
physical apparatus, terminal/data-space/state checks, local repair, fact versioning,
dependency/handwriting fallback, tool-unavailable degradation, and mixed Word/images export."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from docx import Document
from PIL import Image, ImageDraw

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from figure_components import check_label_overlaps, expand_scene  # noqa: E402
from figure_drawing import (  # noqa: E402
    CHECKS, check_black_white, check_print_readability, render, safe_svg,
)
from figure_workflow import complete, generate, prepare_repair, review_template  # noqa: E402
from pipeline import repair_command, retry_command, review_command, run_command  # noqa: E402


def _make_png(path, color='white', line_offset=0, size=(360, 260)):
    im = Image.new('RGB', size, color)
    draw = ImageDraw.Draw(im)
    draw.rectangle((20 + line_offset, 20, size[0] - 20, size[1] - 20), outline='black', width=3)
    draw.line((40, 40 + line_offset, size[0] - 40, size[1] - 40), fill='black', width=3)
    im.save(path, format='PNG', dpi=(300, 300))
    return path


def _make_gen_png(path, size=(360, 260)):
    im = Image.new('RGB', size, 'white')
    draw = ImageDraw.Draw(im)
    draw.ellipse((60, 40, 300, 220), outline='black', width=4)
    draw.line((60, 130, 300, 130), fill='black', width=3)
    im.save(path, format='PNG', dpi=(300, 300))
    return path


def _fill_reviews(tpl, status='pass', overrides=None):
    overrides = overrides or {}
    out = deepcopy(tpl)
    for row in out['reviews']:
        key = f'{row["figure_id"]}:{row["subfigure_id"]}' if row.get('subfigure_id') else row['figure_id']
        st = overrides.get(key, status)
        row['status'] = st
        row['checks'] = {k: (st in {'pass', 'minor_issue'}) for k in CHECKS}
        row['notes'] = ['test review']
    return out


def _simple_scene(rect_x=80, label_text='甲'):
    struct = {
        'objects': [{'id': 'box', 'kind': 'body'}],
        'labels': [{'id': 'lbl', 'target': 'box', 'text': label_text}],
        'arrows': [],
        'connections': [],
    }
    sc = {
        'width': 240, 'height': 180, 'structure': struct,
        'elements': [
            {'id': 'box', 'kind': 'rect', 'object_id': 'box', 'at': [rect_x, 40], 'width': 80, 'height': 80},
            {'id': 'lbl', 'kind': 'label', 'object_id': 'box', 'label_id': 'lbl',
             'at': [120, 155], 'anchor': 'middle', 'size': 14, 'text': label_text},
        ],
    }
    return sc, deepcopy(struct)


def _r04_physical_circuit_scene():
    """R04: Physical battery (2 cells), two open knife switches, ammeter, voltmeter, lamp holder."""
    struct = {
        'objects': [
            {'id': 'B', 'kind': 'phys_battery', 'params': {'cells': 2, 'positive': 'a'}},
            {'id': 'S1', 'kind': 'phys_knife_switch', 'params': {'state': 'open'}},
            {'id': 'S2', 'kind': 'phys_knife_switch', 'params': {'state': 'open'}},
            {'id': 'A1', 'kind': 'phys_meter', 'params': {'kind': 'A'}},
            {'id': 'L1', 'kind': 'phys_lamp_holder'},
            {'id': 'V1', 'kind': 'phys_meter', 'params': {'kind': 'V'}},
        ],
        'labels': [],
        'arrows': [],
        'connections': [
            ['B', 'S1'], ['S1', 'A1'], ['A1', 'L1'], ['L1', 'S2'], ['S2', 'B'],
            ['V1', 'L1'], ['V1', 'L1'],
        ],
        'terminal_connections': [
            ['B.pos', 'S1.a'],
            ['S1.b', 'A1.pos1'],
            ['A1.-', 'L1.a'],
            ['L1.b', 'S2.a'],
            ['S2.b', 'B.neg'],
            ['V1.pos1', 'L1.a'],
            ['V1.-', 'L1.b'],
        ],
    }
    elements = [
        {'id': 'B', 'kind': 'component', 'type': 'phys_battery', 'object_id': 'B', 'at': [120, 60],
         'params': {'cells': 2, 'positive': 'a'}},
        {'id': 'S1', 'kind': 'component', 'type': 'phys_knife_switch', 'object_id': 'S1', 'at': [280, 60],
         'params': {'state': 'open'}},
        {'id': 'A1', 'kind': 'component', 'type': 'phys_meter', 'object_id': 'A1', 'at': [420, 120],
         'params': {'kind': 'A', 'terminals': ['-', 'pos1', 'pos2']}},
        {'id': 'L1', 'kind': 'component', 'type': 'phys_lamp_holder', 'object_id': 'L1', 'at': [280, 230]},
        {'id': 'S2', 'kind': 'component', 'type': 'phys_knife_switch', 'object_id': 'S2', 'at': [120, 230],
         'params': {'state': 'open'}},
        {'id': 'V1', 'kind': 'component', 'type': 'phys_meter', 'object_id': 'V1', 'at': [280, 340],
         'params': {'kind': 'V', 'terminals': ['-', 'pos1', 'pos2']}},
        # Wires routed cleanly around components without passing over unrelated terminals
        {'id': 'w1', 'kind': 'wire', 'from': 'B.pos', 'to': 'S1.a', 'route': 'manual', 'via': [[60, 20], [258, 20]]},
        {'id': 'w2', 'kind': 'wire', 'from': 'S1.b', 'to': 'A1.pos1', 'route': 'manual', 'via': [[340, 60], [340, 175], [420, 175]]},
        {'id': 'w3', 'kind': 'wire', 'from': 'A1.-', 'to': 'L1.a', 'route': 'manual', 'via': [[394, 190], [261, 190]]},
        {'id': 'w4', 'kind': 'wire', 'from': 'L1.b', 'to': 'S2.a', 'route': 'manual', 'via': [[299, 275], [98, 275]]},
        {'id': 'w5', 'kind': 'wire', 'from': 'S2.b', 'to': 'B.neg', 'route': 'manual', 'via': [[185, 230], [185, 60]]},
        # Co-termination on L1.a and L1.b for voltmeter parallel connection
        {'id': 'w6', 'kind': 'wire', 'from': 'V1.pos1', 'to': 'L1.a', 'route': 'manual', 'via': [[280, 395], [235, 395], [235, 244]]},
        {'id': 'w7', 'kind': 'wire', 'from': 'V1.-', 'to': 'L1.b', 'route': 'manual', 'via': [[254, 385], [335, 385], [335, 244]]},
    ]
    return {'width': 'auto', 'height': 'auto', 'fit': {'margin': 16}, 'structure': struct, 'elements': elements}, deepcopy(struct)


class RedrawV11Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        _make_png(self.root / 'src.png')
        _make_png(self.root / 'src2.png', line_offset=10)
        _make_gen_png(self.root / 'gen.png')

    def test_pre_generation_metadata_in_understanding(self):
        sc, u = _simple_scene()
        u.update(
            fact_version=1,
            stem_context='如图所示，比较甲、乙两物体。',
            evidence=[{'claim': '甲为矩形', 'source': 'original_visible'}],
            design_allowances={'clean_scan_noise': True},
            uncertainties={'critical': [], 'appearance': ['线宽微调']},
            verification_targets=['检查甲字标注'],
        )
        # scene['structure'] does not need to duplicate provenance metadata keys
        res = render(sc, self.root / 'meta.svg', self.root / 'meta.png', understanding=u)
        self.assertIn('png_sha256', res)
        check_black_white(self.root / 'meta.png')
        safe_svg(self.root / 'meta.svg')

    def test_terminal_level_positive_and_negative_cases_r04(self):
        sc, u = _r04_physical_circuit_scene()
        res = render(sc, self.root / 'r04.svg', self.root / 'r04.png', understanding=u)
        self.assertIn('png_sha256', res)
        check_black_white(self.root / 'r04.png')
        safe_svg(self.root / 'r04.svg')

        # Negative 1: wrong neighbor terminal (A1.pos2 instead of A1.pos1)
        bad_wrong_term = deepcopy(sc)
        bad_wrong_term['elements'][7]['to'] = 'A1.pos2'
        with self.assertRaisesRegex(ValueError, '端子级接线与原图理解不一致'):
            expand_scene(bad_wrong_term, understanding=u)

        # Negative 2: floating / virtual contact (虚接) - endpoint shifted off post
        bad_floating = deepcopy(sc)
        bad_floating['elements'][6] = {
            'id': 'w1', 'kind': 'wire', 'from': 'B.pos', 'to': [240, 60],
            'connection': ['B', 'S1'], 'route': 'manual', 'via': [[60, 20], [240, 20]],
        }
        with self.assertRaisesRegex(ValueError, '悬空/虚接'):
            expand_scene(bad_floating, understanding=u)

        # Negative 3: extra short-circuit bridge across open switch S1 (额外跨接)
        bad_bridge = deepcopy(sc)
        bad_bridge['elements'].append({
            'id': 'w_bad', 'kind': 'wire', 'from': 'S1.a', 'to': 'S1.b',
            'connection': ['S1', 'S1'], 'route': 'manual', 'via': [[280, 95]],
        })
        with self.assertRaisesRegex(ValueError, '端子级接线与原图理解不一致'):
            expand_scene(bad_bridge, understanding=u)

        # Negative 4: wire path passes right through an unrelated terminal (A1.pos1)
        bad_pass = deepcopy(sc)
        bad_pass['elements'][8] = {
            'id': 'w3', 'kind': 'wire', 'from': 'A1.-', 'to': 'L1.a',
            'route': 'manual', 'via': [[420, 142], [420, 190], [261, 190]],
        }
        with self.assertRaisesRegex(ValueError, '误触无关端子'):
            expand_scene(bad_pass, understanding=u)

    def test_clinical_thermometer_and_data_space_reading_checks_r05(self):
        struct = {
            'objects': [{'id': 'T', 'kind': 'clinical_thermometer', 'params': {'min': 35, 'max': 42, 'value': 37.8}}],
            'labels': [], 'arrows': [], 'connections': [],
            'data_space': {'readings': [{'component_id': 'T', 'value': 37.8, 'tolerance': 0.05}]},
        }
        sc = {
            'width': 'auto', 'height': 'auto', 'fit': {'margin': 14}, 'structure': struct,
            'elements': [{'id': 'T', 'kind': 'component', 'type': 'clinical_thermometer', 'object_id': 'T',
                          'at': [200, 60], 'params': {'min': 35, 'max': 42, 'major': 1, 'minor': 10, 'value': 37.8}}],
        }
        render(sc, self.root / 'r05.svg', self.root / 'r05.png', understanding=struct)
        check_black_white(self.root / 'r05.png')

        # Negative: reading mismatch (expected 38.5 vs rendered 37.8)
        bad_u = deepcopy(struct)
        bad_u['objects'][0]['params']['value'] = 37.8
        bad_u['data_space']['readings'][0]['value'] = 38.5
        bad_sc = deepcopy(sc)
        bad_sc['structure'] = bad_u
        with self.assertRaisesRegex(ValueError, '实际渲染液柱读数'):
            expand_scene(bad_sc, understanding=bad_u)

    def test_boiling_experiment_bubbles_and_coincident_plateau_r06(self):
        # Data curve plot with exact plateau overlap: I(0,92)->(6,98)->(10,98), II(0,90)->(8,98)->(10,98)
        struct = {
            'objects': [
                {'id': 'AX', 'kind': 'axes'},
                {'id': 'c1', 'kind': 'curve'},
                {'id': 'c2', 'kind': 'curve'},
                {'id': 'b_group', 'kind': 'bubbles'},
            ],
            'labels': [
                {'id': 'l_i', 'target': 'c1', 'text': 'I'},
                {'id': 'l_ii', 'target': 'c2', 'text': 'II'},
            ],
            'arrows': [], 'connections': [],
            'data_space': {
                'key_points': [
                    {'axes': 'AX', 'element_id': 'c1', 'point': [0, 92]},
                    {'axes': 'AX', 'element_id': 'c1', 'point': [6, 98]},
                    {'axes': 'AX', 'element_id': 'c2', 'point': [0, 90]},
                    {'axes': 'AX', 'element_id': 'c2', 'point': [8, 98]},
                ],
                'coincident_segments': [
                    {'axes': 'AX', 'elements': ['c1', 'c2'], 'points': [[8, 98], [10, 98]]},
                ],
            },
            'state_checks': [
                {'kind': 'monotonic_radius', 'elements': ['bub1', 'bub2', 'bub3'], 'direction': 'up', 'trend': 'increasing'},
            ],
        }
        sc = {
            'width': 'auto', 'height': 'auto', 'fit': {'margin': 16}, 'structure': struct,
            'elements': [
                {'id': 'AX', 'kind': 'component', 'type': 'axes', 'object_id': 'AX', 'at': [60, 180],
                 'params': {'length': [200, 140], 'x_range': [0, 10], 'y_range': [88, 100],
                            'x_major': 2, 'y_major': 2, 'x_label': 't/min', 'y_label': 'T/℃', 'grid': True}},
                {'id': 'c1', 'kind': 'data_curve', 'axes': 'AX', 'object_id': 'c1',
                 'points': [[0, 92], [6, 98], [10, 98]], 'markers': 'dot'},
                {'id': 'c2', 'kind': 'data_curve', 'axes': 'AX', 'object_id': 'c2',
                 'points': [[0, 90], [8, 98], [10, 98]], 'dash': [4, 2]},
                {'id': 'l_i', 'kind': 'label', 'object_id': 'c1', 'label_id': 'l_i', 'at': [110, 105], 'size': 11, 'text': 'I'},
                {'id': 'l_ii', 'kind': 'label', 'object_id': 'c2', 'label_id': 'l_ii', 'at': [155, 130], 'size': 11, 'text': 'II'},
                {'id': 'bub1', 'kind': 'circle', 'object_id': 'b_group', 'center': [310, 160], 'radius': 3},
                {'id': 'bub2', 'kind': 'circle', 'object_id': 'b_group', 'center': [310, 130], 'radius': 5},
                {'id': 'bub3', 'kind': 'circle', 'object_id': 'b_group', 'center': [310, 95], 'radius': 8},
            ],
        }
        render(sc, self.root / 'r06.svg', self.root / 'r06.png', understanding=struct)
        check_black_white(self.root / 'r06.png')

        # Negative 1: curve II misses (8, 98)
        bad_pt = deepcopy(sc)
        bad_pt['elements'][2]['points'] = [[0, 90], [8, 96], [10, 96]]
        with self.assertRaisesRegex(ValueError, '未经过关键数据点'):
            expand_scene(bad_pt, understanding=struct)

        # Negative 2: rising bubbles shrink instead of growing
        bad_bub = deepcopy(sc)
        bad_bub['elements'][7]['radius'] = 2
        with self.assertRaisesRegex(ValueError, '气泡大小趋势错误'):
            expand_scene(bad_bub, understanding=struct)

    def test_balloons_relative_position_gap_and_readability_r03_r08(self):
        # R03: rod on left of balloon with visible gap >= 6
        struct = {
            'objects': [{'id': 'rod_a', 'kind': 'rod'}, {'id': 'balloon', 'kind': 'balloon'}],
            'labels': [{'id': 'la', 'target': 'rod_a', 'text': 'a'}],
            'arrows': [], 'connections': [],
            'state_checks': [{'kind': 'relative_position', 'a': 'rod_a', 'b': 'balloon', 'relation': 'left_of', 'min_gap': 6}],
        }
        sc = {
            'width': 220, 'height': 180, 'structure': struct,
            'elements': [
                {'id': 'rod_a', 'kind': 'rect', 'object_id': 'rod_a', 'at': [30, 80], 'width': 40, 'height': 12},
                {'id': 'balloon', 'kind': 'circle', 'object_id': 'balloon', 'center': [120, 86], 'radius': 22},
                {'id': 'la', 'kind': 'label', 'object_id': 'rod_a', 'label_id': 'la', 'at': [50, 72], 'anchor': 'middle', 'size': 12, 'text': 'a'},
            ],
        }
        render(sc, self.root / 'r03.svg', self.root / 'r03.png', understanding=struct)
        rd = check_print_readability(sc, target_width_mm=80.0)
        self.assertTrue(rd['ok'], rd)

        # Negative: rod touches/overlaps balloon (gap < 6)
        bad = deepcopy(sc)
        bad['elements'][0]['at'] = [65, 80]
        with self.assertRaisesRegex(ValueError, '相对位置校验失败'):
            expand_scene(bad, understanding=struct)

        # Print readability catches overlapping labels (R08)
        overlap_sc = deepcopy(sc)
        overlap_sc['elements'].append({'id': 'l_dup', 'kind': 'label', 'object_id': 'balloon', 'at': [50, 72], 'anchor': 'middle', 'size': 12, 'text': 'T/℃'})
        self.assertTrue(check_label_overlaps(overlap_sc['elements']))
        rd_bad = check_print_readability(overlap_sc, target_width_mm=80.0)
        self.assertFalse(rd_bad['ok'])

    def test_rotary_rheostat_r10_and_resistor_iu_r09(self):
        # R10: rotary rheostat with A/B/C terminals and leader anchors knob/wiper/wire
        struct = {
            'objects': [{'id': 'VR', 'kind': 'phys_rotary_rheostat', 'params': {'angle': 250}}],
            'labels': [
                {'id': 'l_a', 'target': 'VR', 'text': 'A'},
                {'id': 'l_b', 'target': 'VR', 'text': 'B'},
                {'id': 'l_c', 'target': 'VR', 'text': 'C'},
            ],
            'arrows': [], 'connections': [],
        }
        sc = {
            'width': 'auto', 'height': 'auto', 'fit': {'margin': 16}, 'structure': struct,
            'elements': [
                {'id': 'VR', 'kind': 'component', 'type': 'phys_rotary_rheostat', 'object_id': 'VR',
                 'at': [120, 100], 'params': {'angle': 250}},
                {'id': 'l_a', 'kind': 'label', 'object_id': 'VR', 'label_id': 'l_a', 'at': [92, 162], 'anchor': 'middle', 'size': 12, 'text': 'A'},
                {'id': 'l_b', 'kind': 'label', 'object_id': 'VR', 'label_id': 'l_b', 'at': [120, 166], 'anchor': 'middle', 'size': 12, 'text': 'B'},
                {'id': 'l_c', 'kind': 'label', 'object_id': 'VR', 'label_id': 'l_c', 'at': [148, 162], 'anchor': 'middle', 'size': 12, 'text': 'C'},
            ],
        }
        render(sc, self.root / 'r10.svg', self.root / 'r10.png', understanding=struct)
        check_black_white(self.root / 'r10.png')
        safe_svg(self.root / 'r10.svg')

    def test_hybrid_figure_group_routing_composition_and_tech_guard(self):
        sc_a, u_a = _simple_scene(rect_x=60, label_text='甲')
        doc = {
            'blocks': [
                {'type': 'text', 'id': 'q1', 'text': '1．混合图组测试。'},
                {'type': 'image', 'figure_id': 'g1', 'path': 'src.png'},
            ],
            'figure_task': {
                'schema_version': 1, 'task_id': 'hybrid-1', 'page_count': 1, 'scan_complete': True,
                'figures': [{
                    'figure_id': 'g1', 'figure_group_id': 'grp-1', 'source_page': 1,
                    'source_bbox': [0, 0, 360, 260], 'source_path': 'src.png', 'parent_block_id': 'q1',
                    'figure_type': 'apparatus', 'relation': 'main',
                    'layout': {'mode': 'horizontal', 'gap': 24, 'padding': 16, 'caption_position': 'bottom'},
                    'subfigures': [
                        {'subfigure_id': 'tech', 'label': '图1', 'figure_type': 'coordinates',
                         'redrawable': True, 'critical_uncertainty': False,
                         'understanding': u_a, 'drawing': {'scene': sc_a}},
                        {'subfigure_id': 'scene_photo', 'label': '图2', 'figure_type': 'photo',
                         'allow_generative': True, 'redrawable': True, 'critical_uncertainty': False,
                         'understanding': {'objects': [{'id': 'scene', 'kind': 'illustration'}]},
                         'drawing': {'generated_png': 'gen.png'}},
                    ],
                }],
            },
        }
        # Technical subfigure cannot use generated_png
        bad_doc = deepcopy(doc)
        bad_doc['figure_task']['figures'][0]['subfigures'][0]['drawing'] = {'generated_png': 'gen.png'}
        bad_ledger = generate(bad_doc, self.root, self.root / 'bad_img', mode='redraw')
        self.assertEqual(bad_ledger['records'][0]['subfigures'][0]['state'], 'failed')
        self.assertIn('Technical diagrams require structured drawing', bad_ledger['records'][0]['subfigures'][0]['reason'])

        # Valid hybrid group: subfigure review -> composite PNG (no fake combined SVG, preserves subfigure_svgs) -> group review
        ledger = generate(doc, self.root, self.root / 'hyb_img', mode='redraw')
        self.assertEqual(ledger['records'][0]['state'], 'awaiting_validation')
        tpl1 = review_template(ledger)
        self.assertEqual(len(tpl1['reviews']), 2)
        res_mid, ledger_mid = complete(ledger, _fill_reviews(tpl1), self.root)
        self.assertIsNone(res_mid)
        self.assertEqual(ledger_mid['records'][0]['state'], 'awaiting_composite_validation')
        comp_entry = ledger_mid['records'][0]['composite_attempts'][-1]
        self.assertIsNone(comp_entry['svg_path'])  # hybrid group must not fake combined vector SVG
        self.assertIn('tech', comp_entry['subfigure_svgs'])  # structured subfigure SVG preserved

        tpl2 = review_template(ledger_mid)
        self.assertEqual(len(tpl2['reviews']), 1)
        self.assertEqual(tpl2['reviews'][0]['scope'], 'group')
        final_doc, done_ledger = complete(ledger_mid, _fill_reviews(tpl2), self.root)
        self.assertIsNotNone(final_doc)
        self.assertEqual(done_ledger['status'], 'completed')
        self.assertEqual(final_doc['blocks'][1]['redraw']['drawing_method'], 'hybrid')

    def test_local_repair_preserves_untouched_subfigures_and_fact_versioning(self):
        sc_a, u_a = _simple_scene(rect_x=50, label_text='甲')
        sc_b, u_b = _simple_scene(rect_x=80, label_text='乙')
        sc_b_new, _ = _simple_scene(rect_x=110, label_text='乙')
        doc = {
            'blocks': [
                {'type': 'text', 'id': 'q1', 'text': '1．三图组。'},
                {'type': 'image', 'figure_id': 'g1', 'path': 'src.png'},
            ],
            'figure_task': {
                'schema_version': 1, 'task_id': 'rep-1', 'page_count': 1, 'scan_complete': True,
                'figures': [{
                    'figure_id': 'g1', 'source_page': 1, 'source_bbox': [0, 0, 360, 260],
                    'source_path': 'src.png', 'parent_block_id': 'q1',
                    'figure_type': 'structure', 'relation': 'main',
                    'layout': {'mode': 'horizontal', 'gap': 20, 'padding': 16},
                    'subfigures': [
                        {'subfigure_id': 'jia', 'label': '甲', 'figure_type': 'structure',
                         'redrawable': True, 'critical_uncertainty': False,
                         'understanding': u_a, 'drawing': {'scene': sc_a}},
                        {'subfigure_id': 'yi', 'label': '乙', 'figure_type': 'structure',
                         'redrawable': True, 'critical_uncertainty': False,
                         'understanding': u_b, 'drawing': {'scene': sc_b}},
                    ],
                }],
            },
        }
        # Initial run to completion
        l1 = generate(doc, self.root, self.root / 'v1_img', mode='redraw')
        _, l1_mid = complete(l1, _fill_reviews(review_template(l1)), self.root)
        _, l1_done = complete(l1_mid, _fill_reviews(review_template(l1_mid)), self.root)
        self.assertEqual(l1_done['status'], 'completed')
        orig_jia_png = l1_done['records'][0]['subfigures'][0]['attempts'][-1]['png_path']

        # Local appearance repair: only target g1:yi
        l2 = prepare_repair(
            l1_done, self.root, self.root / 'v2_img',
            targets=['g1:yi'], updated_drawings={'g1:yi': {'scene': sc_b_new}},
        )
        self.assertEqual(l2['task_version'], 2)
        # Untouched jia was NOT regenerated (exact same PNG path & validated state)
        self.assertEqual(l2['records'][0]['subfigures'][0]['state'], 'validated')
        self.assertEqual(l2['records'][0]['subfigures'][0]['attempts'][-1]['png_path'], orig_jia_png)
        # Only yi is awaiting_validation with fresh attempt 1
        tpl_rep = review_template(l2)
        self.assertEqual([r['subfigure_id'] for r in tpl_rep['reviews']], ['yi'])
        _, l2_mid = complete(l2, _fill_reviews(tpl_rep), self.root)
        # verify_unchanged_regions ran during re-composition and recorded jia!
        comp = l2_mid['records'][0]['composite_attempts'][-1]
        self.assertEqual(comp['unchanged_regions_verified'], ['jia'])
        self.assertIsNotNone(comp['svg_path'])  # pure structured group still produces combined safe SVG!
        safe_svg(self.root / comp['svg_path'])
        final_v2, l2_done = complete(l2_mid, _fill_reviews(review_template(l2_mid)), self.root)
        self.assertEqual(l2_done['status'], 'completed')
        self.assertEqual(final_v2['figure_processing']['task_version'], 2)

        # Fact correction requires reason + evidence and increments fact_version
        with self.assertRaisesRegex(ValueError, 'reason、evidence'):
            prepare_repair(l2_done, self.root, self.root / 'v3_bad', targets=['g1:yi'],
                           fact_correction={'reason': '', 'evidence': 'x', 'updates': {'g1:yi': u_b}})
        sc_b_v3, u_b_v3 = _simple_scene(rect_x=90, label_text='丙')
        l3 = prepare_repair(
            l2_done, self.root, self.root / 'v3_img',
            targets=['g1:yi'], updated_drawings={'g1:yi': {'scene': sc_b_v3}},
            fact_correction={'reason': '原图乙标签实为丙', 'evidence': '放大原图右下角可见丙字', 'updates': {'g1:yi': u_b_v3}},
        )
        new_u = l3['document']['figure_task']['figures'][0]['subfigures'][1]['understanding']
        self.assertEqual(new_u['fact_version'], 2)
        self.assertEqual(len(new_u['fact_changes']), 1)

    def test_strong_dependency_vs_independent_fallback_and_handwriting_policy(self):
        sc_a, u_a = _simple_scene(label_text='甲')
        # 1. Strong dependency: one subfigure has critical_uncertainty -> entire group fails without consuming attempts
        strong_doc = {
            'blocks': [{'type': 'text', 'id': 'q1', 'text': '1．强依赖'}, {'type': 'image', 'figure_id': 'g1', 'path': 'src.png'}],
            'figure_task': {
                'schema_version': 1, 'task_id': 'dep-1', 'page_count': 1, 'scan_complete': True,
                'figures': [{
                    'figure_id': 'g1', 'source_page': 1, 'source_bbox': [0, 0, 360, 260],
                    'source_path': 'src.png', 'parent_block_id': 'q1', 'figure_type': 'circuit', 'relation': 'main',
                    'group_dependency': 'strong',
                    'subfigures': [
                        {'subfigure_id': 'a', 'label': '左', 'figure_type': 'circuit',
                         'redrawable': True, 'critical_uncertainty': False, 'understanding': u_a, 'drawing': {'scene': sc_a}},
                        {'subfigure_id': 'b', 'label': '右', 'figure_type': 'circuit',
                         'redrawable': True, 'critical_uncertainty': True, 'understanding': u_a, 'drawing': {'scene': sc_a}},
                    ],
                }],
            },
        }
        ls = generate(strong_doc, self.root, self.root / 'strong_img', mode='redraw')
        # Subfigure b failed directly without consuming attempts
        self.assertEqual(ls['records'][0]['subfigures'][1]['attempts'], [])
        self.assertEqual(ls['records'][0]['subfigures'][1]['state'], 'failed')
        res_s, done_s = complete(ls, _fill_reviews(review_template(ls)), self.root)
        self.assertEqual(done_s['records'][0]['state'], 'failed')
        self.assertEqual(res_s['blocks'][1]['type'], 'text')  # whole group fell back to placeholder

        # 2. Independent subfigures + handwriting disallowed on original fallback -> failed sub gets placeholder tile, passing sub kept!
        indep_doc = deepcopy(strong_doc)
        del indep_doc['figure_task']['figures'][0]['group_dependency']
        indep_doc['figure_task']['figures'][0]['subfigures'][1]['has_handwriting'] = True
        li = generate(indep_doc, self.root, self.root / 'indep_img', mode='redraw',
                      image_fallback='original', disallow_handwriting_fallback=True)
        _, li_mid = complete(li, _fill_reviews(review_template(li)), self.root)
        comp = li_mid['records'][0]['composite_attempts'][-1]
        self.assertEqual(comp['partial_fallbacks'][0]['mode'], 'placeholder')
        self.assertTrue(comp['partial_fallbacks'][0]['handwriting_blocked_original'])
        self.assertFalse(comp['contains_original_fallback'])
        res_i, done_i = complete(li_mid, _fill_reviews(review_template(li_mid)), self.root)
        self.assertEqual(done_i['status'], 'completed')
        self.assertEqual(res_i['blocks'][1]['type'], 'image')

    def test_tool_unavailable_degradation_and_standalone_images_and_mixed_word(self):
        sc_a, u_a = _simple_scene(label_text='图1')
        candidates = {
            'blocks': [
                {'type': 'text', 'id': 'q1', 'text': '1．第一题（结构化成功）',
                 'selection': {'category': 'MAIN_CONTENT', 'relation': 'main', 'certainty': 'high', 'reason': '题干'}},
                {'type': 'image', 'figure_id': 'f1', 'path': 'src.png',
                 'selection': {'category': 'MAIN_CONTENT', 'relation': 'main', 'certainty': 'high', 'reason': '插图'}},
                {'type': 'text', 'id': 'q2', 'text': '2．第二题（宿主无生图工具降级）',
                 'selection': {'category': 'MAIN_CONTENT', 'relation': 'main', 'certainty': 'high', 'reason': '题干'}},
                {'type': 'image', 'figure_id': 'f2', 'path': 'src2.png',
                 'selection': {'category': 'MAIN_CONTENT', 'relation': 'main', 'certainty': 'high', 'reason': '插图'}},
            ],
            'figure_task': {
                'schema_version': 1, 'task_id': 'mix-1', 'page_count': 1, 'scan_complete': True,
                'figures': [
                    {'figure_id': 'f1', 'source_page': 1, 'source_bbox': [0, 0, 360, 260],
                     'source_path': 'src.png', 'parent_block_id': 'q1', 'figure_type': 'structure', 'relation': 'main',
                     'redrawable': True, 'critical_uncertainty': False,
                     'understanding': u_a, 'drawing': {'scene': sc_a}},
                    {'figure_id': 'f2', 'source_page': 1, 'source_bbox': [0, 0, 360, 260],
                     'source_path': 'src2.png', 'parent_block_id': 'q2', 'figure_type': 'illustration', 'relation': 'main',
                     'placeholder_label': '第2题插图', 'redrawable': True, 'critical_uncertainty': False,
                     'understanding': {'objects': [{'id': 'scene', 'kind': 'illustration'}]},
                     'drawing': {'tool_unavailable': True}},
                ],
            },
        }
        cand_path = self.root / 'candidates.json'
        cand_path.write_text(json.dumps(candidates, ensure_ascii=False), encoding='utf-8')

        # 1. Mixed Word export via pipeline (f1 succeeds, f2 degrades cleanly to placeholder)
        docx_out = self.root / 'mixed.docx'
        st = run_command(cand_path, 'w1', source=self.root / 'src.png', image_mode='redraw',
                         fmt='docx', word_confirmed=True, output=docx_out)
        self.assertEqual(st['status'], 'awaiting_review')
        rev_path = self.root / st['files']['reviews']
        tpl = json.loads((self.root / st['files']['review_template']).read_text(encoding='utf-8'))
        rev_path.write_text(json.dumps(_fill_reviews(tpl), ensure_ascii=False), encoding='utf-8')
        done = review_command(Path(st['base']) / 'w1-work' / 'w1.state.json', rev_path)
        self.assertEqual(done['status'], 'completed')
        # Failed figure placeholder keeps V1.0/V1.1 draft gate until explicitly confirmed/finalized
        self.assertEqual(done['delivery'], 'draft')
        self.assertGreaterEqual(done['open_review_items'], 1)
        self.assertEqual(done['failed_figures'], ['f2'])
        doc_obj = Document(docx_out)
        self.assertEqual(len(doc_obj.inline_shapes), 1)
        texts = [p.text for p in doc_obj.paragraphs]
        self.assertTrue(any('第2题插图：无法可靠重绘' in t for t in texts))

        # 2. Standalone images delivery (--format images) without requiring Word confirmation
        img_out = self.root / 'standalone_imgs'
        st2 = run_command(cand_path, 'img1', source=self.root / 'src.png', image_mode='redraw',
                          fmt='images', output=img_out)
        rev2 = self.root / st2['files']['reviews']
        tpl2 = json.loads((self.root / st2['files']['review_template']).read_text(encoding='utf-8'))
        rev2.write_text(json.dumps(_fill_reviews(tpl2), ensure_ascii=False), encoding='utf-8')
        done2 = review_command(Path(st2['base']) / 'img1-work' / 'img1.state.json', rev2)
        self.assertEqual(done2['status'], 'completed')
        self.assertTrue((img_out / 'f1.png').is_file())
        self.assertTrue((img_out / 'f1.svg').is_file())
        manifest = json.loads((img_out / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['figures']), 2)

        # 3. Pipeline repair subcommand on completed run
        sc_a2, _ = _simple_scene(rect_x=110, label_text='甲')
        # Keep understanding label consistent ('图1') for appearance-only repair
        sc_a2, _ = _simple_scene(rect_x=110, label_text='图1')
        patch_file = self.root / 'f1_new.json'
        patch_file.write_text(json.dumps({'drawing': {'scene': sc_a2}}, ensure_ascii=False), encoding='utf-8')
        st_rep = repair_command(Path(done2['base']) / 'img1-work' / 'img1.state.json', 'img2',
                                targets=['f1'], drawings={'f1': str(patch_file)}, output=self.root / 'repaired_imgs')
        self.assertEqual(st_rep['status'], 'awaiting_review')
        self.assertEqual(st_rep['task_version'], 2)
        self.assertEqual(st_rep['parent_run_id'], 'img1')


if __name__ == '__main__':
    unittest.main()
