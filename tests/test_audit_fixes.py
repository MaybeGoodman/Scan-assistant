"""Regression tests for logic, deduplication, and edge-case fixes across scripts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

import chemistry_word  # noqa: E402
import confirmation  # noqa: E402
import docx_audit  # noqa: E402
import export_docx  # noqa: E402
import figure_components  # noqa: E402
import figure_drawing  # noqa: E402
import figure_workflow  # noqa: E402
import formulas  # noqa: E402
import pipeline  # noqa: E402
import questions  # noqa: E402
import select_content  # noqa: E402
import variant_checks  # noqa: E402
import variants  # noqa: E402
from test_figures import document as figure_document, scene as figure_scene  # noqa: E402
from test_v1_variants import candidate as variant_candidate, source_document as variant_source  # noqa: E402


def _make_png(path, size=(240, 180)):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', size, 'white').save(path)
    return path


class ConfirmationAndSelectionTests(unittest.TestCase):
    def test_negated_preserve_and_option_d_labels(self):
        for reply in ('不要保留原图', '不用原图', '不需要保留原图', '不保留原图'):
            parsed = confirmation.parse(reply, ask=('image',))
            self.assertNotEqual(parsed['image_mode'], 'preserve', reply)
        parsed = confirmation.parse('重新绘制，不要保留原图', ask=('image',))
        self.assertEqual(parsed['image_mode'], 'redraw')
        self.assertEqual(parsed['image_fallback'], 'placeholder')
        parsed = confirmation.parse('重绘，失败时不要保留原图', ask=('image',))
        self.assertEqual(parsed['image_mode'], 'redraw')
        self.assertEqual(parsed['image_fallback'], 'placeholder')
        parsed = confirmation.parse('重新绘制，失败或照片时保留原图', ask=('image',))
        self.assertEqual(parsed['image_mode'], 'redraw')
        self.assertEqual(parsed['image_fallback'], 'original')
        parsed = confirmation.parse('失败或照片时保留原图', ask=('image',))
        self.assertEqual(parsed['image_mode'], 'redraw')
        self.assertEqual(parsed['image_fallback'], 'original')
        self.assertEqual(confirmation.reply_mode('重新绘制'), 'redraw')
        self.assertEqual(figure_workflow.reply_mode('保留原图'), 'preserve')

    def test_generate_invitation_negated_polite_reply(self):
        for reply in ('好的，不需要了', '嗯，不用了', '好，算了', '不用了，谢谢', '好的，暂时不用'):
            parsed = confirmation.parse(reply, ask=('generate',))
            self.assertEqual(parsed['generate'], False, reply)
        for reply in ('好', '好的', '要', '需要，来3道'):
            parsed = confirmation.parse(reply, ask=('generate',))
            self.assertEqual(parsed['generate'], True, reply)

    def test_container_ad_with_unannotated_children_is_removed(self):
        ad_sel = {'category': 'ADVERTISEMENT', 'certainty': 'high', 'relation': 'unrelated', 'reason': '宣传广告'}
        ad_runs = {
            'type': 'text',
            'selection': ad_sel,
            'runs': [{'type': 'text', 'text': '扫码关注领取资料'}],
        }
        ad_table = {
            'type': 'table', 'rows': 1, 'cols': 1,
            'selection': ad_sel,
            'cells': [{'row': 0, 'col': 0, 'text': '微信扫码'}],
        }
        main_block = {
            'type': 'text', 'text': '1. 计算题',
            'selection': {'category': 'MAIN_CONTENT', 'certainty': 'high', 'relation': 'main', 'reason': '正文'},
        }
        result, _ = select_content.select_document({'blocks': [main_block, ad_runs, ad_table]})
        self.assertEqual([b['text'] for b in result['blocks']], ['1. 计算题'])

    def test_container_with_explicit_main_child_is_still_protected(self):
        mixed_table = {
            'type': 'table', 'rows': 1, 'cols': 2,
            'selection': {'category': 'ADVERTISEMENT', 'certainty': 'high', 'relation': 'unrelated', 'reason': '广告'},
            'cells': [
                {'row': 0, 'col': 0, 'text': '广告'},
                {'row': 0, 'col': 1, 'runs': [
                    {'type': 'text', 'text': '关键数据',
                     'selection': {'category': 'MAIN_CONTENT', 'certainty': 'high', 'relation': 'main', 'reason': '正文'}}
                ]},
            ],
        }
        result, _ = select_content.select_document({'blocks': [mixed_table]})
        self.assertEqual(len(result['blocks']), 1)

    def test_block_with_all_runs_filtered_is_dropped(self):
        doc = {'blocks': [
            {'type': 'text', 'text': '题干'},
            {'type': 'text', 'runs': [
                {'type': 'text', 'text': '广告',
                 'selection': {'category': 'ADVERTISEMENT', 'certainty': 'high', 'relation': 'unrelated', 'reason': '广告'}}
            ]},
        ]}
        result, _ = select_content.select_document(doc)
        self.assertEqual(len(result['blocks']), 1)
        self.assertEqual(result['blocks'][0]['text'], '题干')


class PipelineAndFigureRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_student_mode_finalize_reaches_final_and_merges_resolutions(self):
        source_img = _make_png(self.root / 'page.png')
        cand_file = self.root / 'cand.json'
        cand_file.write_text(json.dumps({
            'blocks': [
                {'type': 'text', 'id': 'b1', 'role': 'stem', 'text': '1. 已知 〔x=2〕 且 XXX'},
                {'type': 'text', 'id': 'b2', 'role': 'answer', 'text': '【答案】2'},
            ]
        }, ensure_ascii=False), encoding='utf-8')
        state = pipeline.run_command(
            cand_file, 'stu1', source=source_img, fmt='docx', word_confirmed=True,
            output=self.root / 'draft.docx', output_mode='student',
        )
        self.assertEqual(state['delivery'], 'draft')
        report = json.loads((self.root / state['files']['export_report']).read_text(encoding='utf-8'))
        keys = [item['key'] for item in report['review_items']]
        self.assertEqual(len(keys), 2)

        res1 = self.root / 'r1.json'
        res1.write_text(json.dumps({'resolutions': [
            {'key': keys[0], 'resolution': 'confirmed', 'by': 'user', 'note': '已核对第一项'}
        ]}, ensure_ascii=False), encoding='utf-8')
        state_path = self.root / 'stu1-work' / 'stu1.state.json'
        state1 = pipeline.finalize_command(state_path, res1, self.root / 'mid.docx')
        self.assertEqual(state1['delivery'], 'draft')
        self.assertEqual(state1['open_review_items'], 1)

        res2 = self.root / 'r2.json'
        res2.write_text(json.dumps({'resolutions': [
            {'key': keys[1], 'resolution': 'accepted', 'by': 'user', 'note': '已核对第二项'}
        ]}, ensure_ascii=False), encoding='utf-8')
        state2 = pipeline.finalize_command(state_path, res2, self.root / 'final.docx')
        self.assertEqual(state2['delivery'], 'final')
        self.assertEqual(state2['open_review_items'], 0)

    def test_attempt1_render_error_allows_retry_and_recovers(self):
        doc = figure_document(self.root)
        # Push force line beyond canvas width=400 so attempt 1 fails with clipping error
        doc['figure_task']['figures'][0]['drawing']['scene']['elements'][1]['points'][1][0] = 450
        cand_file = self.root / 'cand.json'
        cand_file.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        state = pipeline.run_command(
            cand_file, 'retry1', source=self.root / 'source.png', image_mode='redraw',
            fmt='html', output=self.root / 'out',
        )
        self.assertEqual(state['status'], 'needs_retry')
        self.assertEqual(state['needs_retry'], ['f1'])
        self.assertTrue(state.get('render_errors'))

        # A failed retry with an invalid drawing file cleans up attempt-2 source so a subsequent retry can succeed.
        state_path = self.root / 'retry1-work' / 'retry1.state.json'
        bad_patch = self.root / 'bad_patch.json'
        bad_patch.write_text(json.dumps({'not_drawing': {}}), encoding='utf-8')
        with self.assertRaises(ValueError):
            pipeline.retry_command(state_path, drawings={'f1': str(bad_patch)})
        self.assertFalse((self.root / 'retry1.figure-source.a2.json').exists())

        good_patch = self.root / 'good_patch.json'
        good_patch.write_text(json.dumps({'drawing': {'scene': figure_scene()}}, ensure_ascii=False), encoding='utf-8')
        state2 = pipeline.retry_command(state_path, drawings={'f1': str(good_patch)})
        self.assertEqual(state2['status'], 'awaiting_review')

    def test_attempt2_render_error_becomes_permanent_failure(self):
        doc = figure_document(self.root)
        doc['figure_task']['figures'][0]['drawing']['scene']['elements'][1]['points'][1][0] = 450
        ledger1 = figure_workflow.generate(doc, self.root, self.root / 'imgs', mode='redraw')
        self.assertEqual(ledger1['records'][0]['state'], 'needs_retry')
        self.assertEqual(ledger1['records'][0]['attempts'][-1]['validation_status'], 'render_error')
        _, done1 = figure_workflow.complete(ledger1, {'reviews': []}, self.root)
        self.assertEqual(done1['status'], 'needs_retry')
        self.assertEqual(done1['needs_retry'], ['f1'])

        # Attempt 2 also clips -> permanent failed
        ledger2 = figure_workflow.generate(doc, self.root, self.root / 'imgs', mode='redraw', previous=ledger1)
        self.assertEqual(ledger2['records'][0]['state'], 'failed')
        self.assertTrue(ledger2['records'][0]['failed'])

    def test_resume_discovers_variants_ledgers(self):
        src = self.root / 'reviewed.json'
        src.write_text(json.dumps(variant_source(), ensure_ascii=False), encoding='utf-8')
        variants.init(src, 'gen1', ['q19'], count=1)
        found = pipeline.resume(self.root)
        self.assertEqual(len(found['variants']), 1)
        self.assertTrue(found['variants'][0]['ledger'].endswith('gen1.gen.json'))
        self.assertEqual(found['variants'][0]['status'], 'awaiting_candidates')


class DrawingChemistryFormulaAndChecksTests(unittest.TestCase):
    def test_looks_chemical_distinguishes_math_and_chemistry(self):
        for chem in (
            [{'text': 'H'}, {'text': '2', 'script': 'sub'}, {'text': 'O'}],
            [{'text': 'H'}, {'text': '2', 'script': 'sub'}, {'text': 'SO'}, {'text': '4', 'script': 'sub'}],
            [{'text': 'CO'}, {'text': '2', 'script': 'sub'}],
            [{'text': 'NaCl'}],
            [{'text': 'Fe'}, {'text': '3+', 'script': 'sup'}],
            [{'text': 'Ca(OH)'}, {'text': '2', 'script': 'sub'}],
        ):
            self.assertTrue(figure_drawing.looks_chemical(chem), chem)
        for math_runs in (
            [{'text': 'v'}, {'text': '0', 'script': 'sub'}, {'text': 't'}],
            [{'text': 'R'}, {'text': '1', 'script': 'sub'}, {'text': '+'}, {'text': 'R'}, {'text': '2', 'script': 'sub'}],
            [{'text': 'x'}, {'text': '2', 'script': 'sup'}, {'text': '+y'}],
            [{'text': 'F'}, {'text': '1', 'script': 'sub'}, {'text': '='}, {'text': 'F'}, {'text': '2', 'script': 'sub'}],
            [{'text': 'AB'}, {'text': '1', 'script': 'sub'}],
        ):
            self.assertFalse(figure_drawing.looks_chemical(math_runs), math_runs)

    def test_circuit_wire_to_bare_coordinate_keeps_circuit_stroke(self):
        source = {
            'objects': [{'id': 'R1', 'kind': 'resistor'}, {'id': 'P', 'kind': 'node'}],
            'connections': [['R1', 'P']],
        }
        scene = {
            'width': 300, 'height': 200, 'structure': source,
            'elements': [
                {'id': 'R1', 'kind': 'component', 'type': 'resistor', 'object_id': 'R1', 'at': [100, 100]},
                {'id': 'P', 'kind': 'circle', 'object_id': 'P', 'center': [200, 100], 'radius': 2, 'fill': 'black'},
                {'id': 'w1', 'kind': 'wire', 'from': 'R1.b', 'to': [200, 100], 'connection': ['R1', 'P']},
            ],
        }
        expanded = figure_components.expand_scene(scene, understanding=source)
        wire = next(e for e in expanded['elements'] if e['id'] == 'w1')
        self.assertEqual(wire['stroke_width'], figure_components.CIRCUIT_STROKE)

    def test_chemistry_parser_whitespace_and_omml_operator_spacing(self):
        nodes = chemistry_word.parse(r'{}^{23}_{11} \mathrm {Na} + \mathrm{H_2O} \xrightarrow [\Delta] { \text{条件} } \mathrm{NaOH}')
        self.assertTrue(nodes)
        omml = chemistry_word.to_omml(chemistry_word.parse(r'{}^{23}_{11} \mathrm {Na} + \mathrm{H_2O}'))
        text = ''.join(omml.itertext())
        self.assertIn(' + ', text)
        self.assertIn('Na', text)
        self.assertIn('23', text)

    def test_multicolumn_aligned_converts_to_omml(self):
        for latex in (
            r'\begin{aligned} a &= b & c \\ d &= e & f \end{aligned}',
            r'\begin{aligned} x &= 1 & y &= 2 \\ x &= 3 & y &= 4 \end{aligned}',
        ):
            omml = formulas.to_omml(latex, display=True)
            cols = omml.xpath('.//m:mc', namespaces={'m': formulas.M})
            self.assertGreaterEqual(len(cols), 3)

    def test_variant_checks_units_brackets_and_compact_equations(self):
        # Parenthesized units and negative exponents
        r1 = variant_checks.run_check(
            {'kind': 'units', 'item': '(1)', 'units': {'Q': 'J', 'm': 'kg', 'dT': 'K'},
             'expr': 'Q/(m*dT)', 'expect': 'J/(kg*K)'},
            {},
        )
        self.assertTrue(r1['ok'], r1)
        r2 = variant_checks.run_check(
            {'kind': 'units', 'item': '(1)', 'units': {'d': 'm', 't': 's'},
             'expr': 'd*t**(-2)', 'expect': 'm/s^2'},
            {},
        )
        self.assertTrue(r2['ok'], r2)
        r3 = variant_checks.run_check(
            {'kind': 'units', 'item': '(1)', 'units': {'v': 'm/s'},
             'expr': 'v^2', 'expect': '(m/s)^2'},
            {},
        )
        self.assertTrue(r3['ok'], r3)
        # Unmatched parenthesis returns clean CheckError (ok=False), not uncaught IndexError
        r4 = variant_checks.run_check({'kind': 'balance', 'item': '(1)', 'equation': 'H2O) = H2O'}, {})
        self.assertIs(r4['ok'], False)
        # Compact equations and braced ion charges
        r5 = variant_checks.run_check({'kind': 'balance', 'item': '(1)', 'equation': '2H2+O2=2H2O'}, {})
        self.assertTrue(r5['ok'], r5)
        r6 = variant_checks.run_check({'kind': 'balance', 'item': '(1)', 'equation': 'Fe^{3+}+3OH^-=Fe(OH)3↓'}, {})
        self.assertTrue(r6['ok'], r6)


class QuestionsVariantsAndAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_questions_validations_and_answer_label_precision(self):
        # Duplicate block reference in one question is rejected
        with self.assertRaises(ValueError):
            questions.validate_questions({
                'blocks': [{'type': 'text', 'id': 'b1', 'text': '题干'}],
                'questions': [{'question_id': 'q1', 'blocks': ['b1', 'b1']}],
            })
        # Empty material_id is rejected
        with self.assertRaises(ValueError):
            questions.validate_questions({
                'blocks': [{'type': 'text', 'id': 'b1', 'text': '材料'}],
                'materials': [{'material_id': '', 'blocks': ['b1']}],
            })
        # 补写说明 with runs does not false-flag inference
        items = questions.review_items({
            'blocks': [{'type': 'text', 'runs': [
                {'type': 'text', 'text': '补写说明：'},
                {'type': 'text', 'text': '将〔a〕恢复为原字'},
            ]}]
        })
        self.assertEqual([i for i in items if i['kind'] == 'inference'], [])
        # "答题时..." is not flagged as possible_answer
        items2 = questions.review_items({'blocks': [{'type': 'text', 'text': '答题时请注意单位换算'}]}, mode='student')
        self.assertEqual([i for i in items2 if i['kind'] == 'possible_answer'], [])

    def test_docx_audit_catches_bracketed_answer_label_and_leaves_no_temp_files(self):
        doc_path = self.root / 'doc.json'
        doc_data = {'blocks': [{'type': 'text', 'text': '【答案】B'}]}
        doc_path.write_text(json.dumps(doc_data, ensure_ascii=False), encoding='utf-8')
        out_docx = self.root / 'out.docx'
        export_docx.export_docx(doc_path, out_docx, word_confirmed=True, output_mode='original')
        audited = docx_audit.audit(out_docx, student=True)
        self.assertFalse(audited['ok'])
        self.assertTrue(any('疑似答案标签' in p for p in audited['problems']))

        before = set(self.root.iterdir())
        check = docx_audit.consistency(out_docx, doc_data, source=doc_path)
        self.assertTrue(check['ok'], check)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_variants_leak_checks_and_deliver_cleanup(self):
        src = self.root / 'reviewed.json'
        src.write_text(json.dumps(variant_source(), ensure_ascii=False), encoding='utf-8')
        ledger = variants.init(src, 'vfix', ['q19'], count=1)['ledger']

        # Split answer fragment in own stem is rejected in verify()
        leaked_cand = variant_candidate(slot=1, constant=5, a=3, low=-4, high=5)
        leaked_cand['variant']['blocks'][0]['text'] += '（已知最大值5）'
        c_bad = self.root / 'c_bad.json'
        c_bad.write_text(json.dumps(leaked_cand, ensure_ascii=False), encoding='utf-8')
        res = variants.submit(ledger, c_bad)
        self.assertEqual(res['submitted']['status'], 'failed')
        self.assertTrue(any('答案出现在学生题面中' in f for f in res['submitted']['failures']))
        # Failed candidate does not freeze assets
        self.assertFalse((self.root / 'vfix-gen' / 'assets' / res['submitted']['candidate_id']).exists())

        # Valid candidate passes and delivers cleanly in docx-only mode without chat artifacts
        good_cand = variant_candidate(slot=1, constant=7, a=4, low=-9, high=7)
        c_good = self.root / 'c_good.json'
        c_good.write_text(json.dumps(good_cand, ensure_ascii=False), encoding='utf-8')
        res_good = variants.submit(ledger, c_good)
        self.assertEqual(res_good['submitted']['status'], 'passed')

        out_dir = self.root / 'docx-only'
        delivered = variants.deliver(ledger, 'docx', out_dir, word_confirmed=True)
        self.assertEqual(delivered['delivery'], 'final')
        self.assertEqual(set(delivered['files']), {'docx'})
        self.assertFalse((out_dir / 'student-chat.md').exists())
        self.assertFalse((out_dir / 'figures').exists())

    def test_variants_deliver_does_not_self_exempt_and_rolls_back_on_error(self):
        src = self.root / 'reviewed.json'
        src.write_text(json.dumps(variant_source(), ensure_ascii=False), encoding='utf-8')
        ledger_path = Path(variants.init(src, 'vroll', ['q19'], count=1)['ledger'])
        good_cand = variant_candidate(slot=1, constant=7, a=4, low=-9, high=7)
        c_good = self.root / 'c_good.json'
        c_good.write_text(json.dumps(good_cand, ensure_ascii=False), encoding='utf-8')
        variants.submit(ledger_path, c_good)

        # Simulate a leaked answer that somehow survived into stored candidate + matching hash
        ledger_data = json.loads(ledger_path.read_text(encoding='utf-8'))
        stored = ledger_path.parent / ledger_data['candidates'][0]['file']
        cand_data = json.loads(stored.read_text(encoding='utf-8'))
        cand_data['variant']['blocks'][0]['text'] += '（参考最大值7）'
        stored.write_text(json.dumps(cand_data, ensure_ascii=False), encoding='utf-8')
        ledger_data['candidates'][0]['sha256'] = variants.sha256(stored)
        ledger_path.write_text(json.dumps(ledger_data, ensure_ascii=False), encoding='utf-8')

        out_dir = self.root / 'rollback-out'
        with self.assertRaisesRegex(ValueError, '含内部答案'):
            variants.deliver(ledger_path, 'chat', out_dir)
        # Rolled back cleanly: student.json and output_dir removed
        self.assertFalse((self.root / 'vroll.student.json').exists())
        self.assertFalse(out_dir.exists())


if __name__ == '__main__':
    unittest.main()
