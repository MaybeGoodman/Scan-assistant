"""1.2.0 AxMath-compatible chemical equation paste output tests (T1-T9 + edge cases)."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from docx import Document
from lxml import etree
from PIL import Image

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))

from chemistry_word import BLANK_TEXT, is_simple, parse, plain_text, rich_segments, to_omml  # noqa: E402
from content_blocks import merge_equation, plain_source  # noqa: E402
from docx_audit import M, NS, audit, body_signature, consistency  # noqa: E402
from export_docx import export_docx  # noqa: E402
from export_page import export_result  # noqa: E402
from latex_validation import validate_latex  # noqa: E402
import pipeline  # noqa: E402
from subjects import MODULES  # noqa: E402
import variants  # noqa: E402


T1_BLOCK = {
    'type': 'text',
    'runs': [
        {'type': 'text', 'text': '______'},
        {'type': 'chemistry', 'latex': r'\mathrm{Cr_2O_7^{2-}}'},
        {'type': 'text', 'text': ' + ______'},
        {'type': 'chemistry', 'latex': r'\mathrm{H^+}'},
        {'type': 'text', 'text': ' = ______'},
        {'type': 'chemistry', 'latex': r'\mathrm{Cl_2}\uparrow'},
    ],
}
T1_EXPR = r'\underline{\qquad}\,\mathrm{Cr_2O_7^{2-}}+\underline{\qquad}\,\mathrm{H^+}=\underline{\qquad}\,\mathrm{Cl_2}\uparrow'
T1_EXPECTED_MD = '```latex\n' + T1_EXPR + '\n```'
T1_LEGACY_MD = (
    r'\_\_\_\_\_\_`\mathrm{Cr_2O_7^{2-}}` + \_\_\_\_\_\_`\mathrm{H^+}`'
    r' = \_\_\_\_\_\_`\mathrm{Cl_2}\uparrow`'
)
T2_BLOCK = {'type': 'text', 'runs': [{'type': 'chemistry', 'latex': T1_EXPR}]}


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


def _chem_source_doc():
    return {
        'blocks': [
            {'type': 'text', 'id': 'stem', 'role': 'stem', 'text': '12．配平下列离子方程式：'},
            {'type': 'text', 'id': 'eq', 'role': 'stem', 'runs': [{'type': 'chemistry', 'latex': T1_EXPR}]},
            {'type': 'text', 'id': 'ans', 'role': 'answer', 'text': '【答案】系数为 1、14、3。'},
        ],
        'questions': [{
            'question_id': 'q12', 'number': '12', 'module': 'M07',
            'blocks': ['stem', 'eq', 'ans'], 'subquestions': [],
            'review_status': 'confirmed',
        }],
    }


def _chem_candidate(slot, stem_text, eq_block, answer, equation_check, diff_siblings):
    return {
        'question_id': 'q12',
        'slot': slot,
        'variant': {
            'blocks': [
                {'type': 'text', 'id': 'stem', 'role': 'stem', 'text': stem_text},
                eq_block,
            ],
            'stem': ['stem', eq_block['id']],
            'materials': [],
            'subquestions': [],
        },
        'design': {
            'knowledge_points': ['氧化还原反应配平'],
            'method': '化合价升降法与电荷守恒',
            'question_type': '填空配平题',
            'difficulty': 'same',
            'difficulty_evidence': '单道酸性介质氧化还原离子方程式配平',
            'difference_from_source': '更换氧化剂与还原剂体系',
            'difference_from_siblings': diff_siblings,
        },
        'internal': {
            'answers': [{'item': 'all', 'answer': answer}],
            'solution': f'配平后系数依次为 {answer}，经元素与电荷守恒检验无误。',
            'checks': [
                {'kind': 'balance', 'item': 'all', 'equation': equation_check},
                {'kind': 'semantic', 'item': 'all', 'independent_answer': answer, 'method': '化合价升降法独立配平'},
            ],
        },
        'review': {
            'checklist': {k: True for k in MODULES['M07']['checklist']},
            'notes': ['已核对元素守恒与电荷守恒'],
        },
    }


class AxMathPasteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_t1_split_runs_equation_merged(self):
        self.assertEqual(merge_equation(T1_BLOCK), T1_EXPECTED_MD)
        self.assertEqual(plain_source(T1_BLOCK, validate_chemistry=True, markdown=True), T1_EXPECTED_MD)
        src = _write_json(self.root / 't1.json', {'blocks': [T1_BLOCK]})
        res = export_result(src, self.root / 't1-out')
        self.assertEqual(res['delivery'], 'final')
        self.assertEqual(res['markdown'].read_text(encoding='utf-8'), T1_EXPECTED_MD + '\n')
        # HTML output stays unchanged (no fenced code block).
        html = res['output'].read_text(encoding='utf-8')
        self.assertNotIn('```latex', html)
        self.assertIn(r'______\mathrm{Cr_2O_7^{2-}} + ______\mathrm{H^+} = ______\mathrm{Cl_2}\uparrow', html)

    def test_t2_blank_inside_chemistry_run(self):
        self.assertEqual(validate_latex(r'\underline{\qquad}\,\mathrm{H^+}', chemistry=True),
                         r'\underline{\qquad}\,\mathrm{H^+}')
        self.assertEqual(validate_latex(T1_EXPR, chemistry=True), T1_EXPR)
        self.assertEqual(plain_source(T2_BLOCK, validate_chemistry=True, markdown=True), T1_EXPECTED_MD)
        src = _write_json(self.root / 't2.json', {'blocks': [T2_BLOCK]})
        res = export_result(src, self.root / 't2-out')
        self.assertEqual(res['delivery'], 'final')
        self.assertEqual(res['markdown'].read_text(encoding='utf-8'), T1_EXPECTED_MD + '\n')

    def test_t3_chinese_mixed_paragraph_not_merged(self):
        block = {
            'type': 'text',
            'runs': [
                {'type': 'text', 'text': '1 g '},
                {'type': 'chemistry', 'latex': r'\mathrm{N_2}'},
                {'type': 'text', 'text': ' 中含有 n 个分子'},
            ],
        }
        self.assertIsNone(merge_equation(block))
        expected = r'1 g `\mathrm{N_2}` 中含有 n 个分子'
        self.assertEqual(plain_source(block, validate_chemistry=True, markdown=True), expected)
        src = _write_json(self.root / 't3.json', {'blocks': [block]})
        res = export_result(src, self.root / 't3-out')
        self.assertEqual(res['markdown'].read_text(encoding='utf-8'), expected + '\n')

    def test_t4_legacy_markdown_switch(self):
        self.assertEqual(
            plain_source(T1_BLOCK, validate_chemistry=True, markdown=True, paste_target='markdown'),
            T1_LEGACY_MD,
        )
        src = _write_json(self.root / 't4.json', {'blocks': [T1_BLOCK]})
        res = export_result(src, self.root / 't4-out', paste_target='markdown')
        self.assertEqual(res['markdown'].read_text(encoding='utf-8'), T1_LEGACY_MD + '\n')

    def test_t5_escaped_blank_option(self):
        expected_expr = r'\_\_\_\_\_\_\mathrm{Cr_2O_7^{2-}}+\_\_\_\_\_\_\mathrm{H^+}=\_\_\_\_\_\_\mathrm{Cl_2}\uparrow'
        expected_md = '```latex\n' + expected_expr + '\n```'
        self.assertEqual(merge_equation(T1_BLOCK, blank='escaped'), expected_md)
        src = _write_json(self.root / 't5.json', {'blocks': [T1_BLOCK]})
        res = export_result(src, self.root / 't5-out', blank_latex='escaped')
        md = res['markdown'].read_text(encoding='utf-8')
        self.assertEqual(md, expected_md + '\n')
        self.assertNotIn(r'\underline', md)
        self.assertEqual(md.count(r'\_\_\_\_\_\_'), 3)

    def test_t6_merge_validation_failure_falls_back_and_marks_draft(self):
        # 1) Direct merge_equation / plain_source fallback when a chemistry run uses an unsupported command.
        bad_chem = {
            'type': 'text',
            'runs': [
                {'type': 'text', 'text': '______'},
                {'type': 'chemistry', 'latex': r'\ce{H2O}'},
            ],
        }
        failures = []
        self.assertIsNone(merge_equation(bad_chem, failures=failures))
        self.assertEqual(len(failures), 1)
        self.assertIn('Unsupported LaTeX command', failures[0]['detail'])
        self.assertEqual(plain_source(bad_chem, markdown=True), r'\_\_\_\_\_\_`\ce{H2O}`')

        # 2) Full export_result: runs valid individually for HTML, but merged equation fails validate_latex.
        mixed_invalid = {
            'type': 'text',
            'runs': [
                {'type': 'text', 'text': '______'},
                {'type': 'chemistry', 'latex': r'\mathrm{H^+}'},
                {'type': 'text', 'text': ' + '},
                {'type': 'math', 'latex': r'\alpha'},
            ],
        }
        src = _write_json(self.root / 't6.json', {'blocks': [mixed_invalid]})
        res = export_result(src, self.root / 't6-out')
        self.assertEqual(res['delivery'], 'draft')
        kinds = [item['kind'] for item in res['review_items']]
        self.assertIn('paste_merge_failed', kinds)
        md = res['markdown'].read_text(encoding='utf-8')
        self.assertTrue(md.startswith('【待复核草稿】'))
        self.assertNotIn('```latex', md)
        self.assertIn(r'\_\_\_\_\_\_`\mathrm{H^+}` + $\alpha$', md)

    def test_t7_word_native_underline_and_audit(self):
        # Rich-text path for T2 expression.
        self.assertTrue(is_simple(parse(T1_EXPR)))
        self.assertEqual(plain_text(T1_EXPR).count('____'), 3)

        src = _write_json(self.root / 't7.json', {'blocks': [T2_BLOCK]})
        out_docx = self.root / 't7.docx'
        export_docx(src, out_docx, word_confirmed=True, chemistry_format='native')

        doc = Document(out_docx)
        ul_blanks = [r for r in doc.paragraphs[0].runs if r.font.underline and r.text == BLANK_TEXT]
        self.assertEqual(len(ul_blanks), 3)
        self.assertTrue(consistency(out_docx, json.loads(src.read_text(encoding='utf-8')), source=src)['ok'])

        # Signature distinguishes "with blanks" vs "without blanks".
        no_blank_expr = r'\mathrm{Cr_2O_7^{2-}}+\mathrm{H^+}=\mathrm{Cl_2}\uparrow'
        src_no = _write_json(self.root / 't7-no.json',
                             {'blocks': [{'type': 'text', 'runs': [{'type': 'chemistry', 'latex': no_blank_expr}]}]})
        out_no = self.root / 't7-no.docx'
        export_docx(src_no, out_no, word_confirmed=True, chemistry_format='native')
        sig_with, _ = body_signature(out_docx)
        sig_without, _ = body_signature(out_no)
        self.assertNotEqual(sig_with, sig_without)
        self.assertFalse(consistency(out_docx, json.loads(src_no.read_text(encoding='utf-8')), source=src_no)['ok'])

        # Blank variants: \quad, \ , and empty group all normalize to BLANK_TEXT and ____.
        for blank_cmd in (r'\underline{\quad}\,\mathrm{H^+}', r'\underline{\ }\,\mathrm{H^+}', r'\underline{}\,\mathrm{H^+}'):
            self.assertEqual(rich_segments(parse(blank_cmd))[0], (BLANK_TEXT, 'underline'))
            self.assertTrue(plain_text(blank_cmd).startswith('____'))

        # Non-blank underline keeps its original content with underline.
        ul_text = r'\underline{\mathrm{A}}+\mathrm{B}'
        self.assertEqual(plain_text(ul_text), 'A+B')
        self.assertEqual(rich_segments(parse(ul_text))[0], ('A', 'underline'))

        # OMML path (\underline combined with \xrightarrow) uses m:bar with pos="bot".
        omml_expr = r'\underline{\qquad}\,\mathrm{KClO_3}\xrightarrow[\Delta]{\mathrm{MnO_2}}\underline{\qquad}\,\mathrm{KCl}'
        self.assertFalse(is_simple(parse(omml_expr)))
        self.assertEqual(plain_text(omml_expr).count('____'), 2)
        omml_tree = to_omml(parse(omml_expr))
        bars = omml_tree.xpath('.//m:bar', namespaces=NS)
        self.assertEqual(len(bars), 2)
        for bar in bars:
            pos = bar.find('m:barPr/m:pos', NS)
            self.assertIsNotNone(pos)
            self.assertEqual(pos.get('{%s}val' % M), 'bot')
            self.assertEqual(''.join(bar.xpath('.//m:t/text()', namespaces=NS)), BLANK_TEXT)
        src_omml = _write_json(self.root / 't7-omml.json', {'blocks': [{'type': 'chemistry', 'latex': omml_expr}]})
        out_omml = self.root / 't7-omml.docx'
        export_docx(src_omml, out_omml, word_confirmed=True, chemistry_format='native')
        self.assertTrue(consistency(out_omml, json.loads(src_omml.read_text(encoding='utf-8')), source=src_omml)['ok'])

    def test_t8_variant_submit_blocks_adjacent_text_blanks(self):
        source = _write_json(self.root / 'src.json', _chem_source_doc())
        ledger = variants.init(source, 'g8', ['q12'], count=1)['ledger']

        bad_block = {'id': 'eq', 'role': 'stem', **T1_BLOCK}
        bad_cand = _chem_candidate(
            1, '配平酸性条件下重铬酸根与氯离子的反应：', bad_block,
            '1、6、14、2、3、7', 'Cr2O7^{2-} + 6Cl^- + 14H^+ = 2Cr^{3+} + 3Cl2↑ + 7H2O', '重铬酸根与氯离子',
        )
        res_bad = variants.submit(ledger, _write_json(self.root / 'bad.json', bad_cand))['submitted']
        self.assertEqual(res_bad['status'], 'failed')
        self.assertTrue(any('请写进表达式' in msg for msg in res_bad['failures']), res_bad['failures'])

        # Pure Chinese sentence with ______ is NOT rejected.
        good_eq = (
            r'\underline{\qquad}\,\mathrm{MnO_4^-}+\underline{\qquad}\,\mathrm{Cl^-}'
            r'+\underline{\qquad}\,\mathrm{H^+}=\underline{\qquad}\,\mathrm{Mn^{2+}}'
            r'+\underline{\qquad}\,\mathrm{Cl_2}\uparrow+\underline{\qquad}\,\mathrm{H_2O}'
        )
        good_cand = _chem_candidate(
            1, '在酸性条件下，完成下列离子方程式的配平（还原剂为______）：',
            {'type': 'text', 'id': 'eq', 'role': 'stem', 'runs': [{'type': 'chemistry', 'latex': good_eq}]},
            '2、10、16、2、5、8',
            '2MnO4^- + 10Cl^- + 16H^+ = 2Mn^{2+} + 5Cl2↑ + 8H2O',
            '高锰酸根与氯离子',
        )
        res_good = variants.submit(ledger, _write_json(self.root / 'good.json', good_cand))['submitted']
        self.assertEqual(res_good['status'], 'passed', res_good['failures'])

    def test_t9_similar_questions_end_to_end(self):
        source = _write_json(self.root / 'src.json', _chem_source_doc())
        ledger = variants.init(source, 'g9', ['q12'], count=3)['ledger']

        specs = [
            (
                1,
                '在酸性溶液中配平高锰酸根离子与氯离子的氧化还原反应：',
                (r'\underline{\qquad}\,\mathrm{MnO_4^-}+\underline{\qquad}\,\mathrm{Cl^-}'
                 r'+\underline{\qquad}\,\mathrm{H^+}=\underline{\qquad}\,\mathrm{Mn^{2+}}'
                 r'+\underline{\qquad}\,\mathrm{Cl_2}\uparrow+\underline{\qquad}\,\mathrm{H_2O}'),
                '2、10、16、2、5、8',
                '2MnO4^- + 10Cl^- + 16H^+ = 2Mn^{2+} + 5Cl2↑ + 8H2O',
                'MnO4-/Cl- 体系',
            ),
            (
                2,
                '配平重铬酸根离子在硫酸溶液中氧化亚铁离子的离子方程式：',
                (r'\underline{\qquad}\,\mathrm{Cr_2O_7^{2-}}+\underline{\qquad}\,\mathrm{Fe^{2+}}'
                 r'+\underline{\qquad}\,\mathrm{H^+}=\underline{\qquad}\,\mathrm{Cr^{3+}}'
                 r'+\underline{\qquad}\,\mathrm{Fe^{3+}}+\underline{\qquad}\,\mathrm{H_2O}'),
                '1、6、14、2、6、7',
                'Cr2O7^{2-} + 6Fe^{2+} + 14H^+ = 2Cr^{3+} + 6Fe^{3+} + 7H2O',
                'Cr2O7^{2-}/Fe^{2+} 体系',
            ),
            (
                3,
                '写出并配平金属铜与稀硝酸反应的离子方程式系数：',
                (r'\underline{\qquad}\,\mathrm{Cu}+\underline{\qquad}\,\mathrm{NO_3^-}'
                 r'+\underline{\qquad}\,\mathrm{H^+}=\underline{\qquad}\,\mathrm{Cu^{2+}}'
                 r'+\underline{\qquad}\,\mathrm{NO}\uparrow+\underline{\qquad}\,\mathrm{H_2O}'),
                '3、2、8、3、2、4',
                '3Cu + 2NO3^- + 8H^+ = 3Cu^{2+} + 2NO↑ + 4H2O',
                'Cu/NO3- 体系',
            ),
        ]
        for slot, stem, expr, answer, balance_eq, diff in specs:
            cand = _chem_candidate(
                slot, stem,
                {'type': 'text', 'id': 'eq', 'role': 'stem', 'runs': [{'type': 'chemistry', 'latex': expr}]},
                answer, balance_eq, diff,
            )
            submitted = variants.submit(ledger, _write_json(self.root / f'c{slot}.json', cand))['submitted']
            self.assertEqual(submitted['status'], 'passed', submitted['failures'])

        out = self.root / 'student-out'
        result = variants.deliver(ledger, 'both', out, word_confirmed=True)
        self.assertEqual(result['delivery'], 'final')
        chat = (out / 'student-chat.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```latex\n([^\n]+)\n```', chat)
        self.assertEqual(len(blocks), 3)
        for block_expr in blocks:
            validate_latex(block_expr, chemistry=True)
            self.assertIn(r'\underline{\qquad}\,', block_expr)
        for _, _, _, answer, _, _ in specs:
            self.assertNotIn(answer, chat)

        student_doc_path = self.root / 'g9.student.json'
        self.assertTrue(audit(out / 'student.docx', ['2、10、16、2、5、8', '1、6、14、2、6、7', '3、2、8、3、2、4'])['ok'])
        self.assertTrue(consistency(out / 'student.docx', json.loads(student_doc_path.read_text(encoding='utf-8')),
                                    source=student_doc_path)['ok'])

    def test_pipeline_persists_paste_options_across_finalize_and_cli(self):
        scan = self.root / 'scan.png'
        Image.new('RGB', (40, 30), 'white').save(scan)
        cands = _write_json(self.root / 'candidates.json', {
            'blocks': [
                {'type': 'text', 'text': '配平〔下列〕方程式：'},
                T1_BLOCK,
            ],
        })
        state = pipeline.run_command(
            cands, 'p1', source=scan, fmt='html', output=self.root / 'draft-out',
            paste_target='axmath', blank_latex='escaped',
        )
        self.assertEqual(state['delivery'], 'draft')
        self.assertEqual(state['options']['paste_target'], 'axmath')
        self.assertEqual(state['options']['blank_latex'], 'escaped')
        draft_md = (self.root / 'draft-out/result.md').read_text(encoding='utf-8')
        self.assertIn(r'\_\_\_\_\_\_\mathrm{Cr_2O_7^{2-}}', draft_md)

        report = json.loads((self.root / state['files']['export_report']).read_text(encoding='utf-8'))
        resolutions = _write_json(self.root / 'res.json', {
            'resolutions': [{'key': item['key'], 'resolution': 'confirmed', 'by': 'host', 'note': '已核对'}
                            for item in report['review_items']],
        })
        state_file = self.root / 'p1-work/p1.state.json'
        final_state = pipeline.finalize_command(state_file, resolutions, self.root / 'final-out')
        self.assertEqual(final_state['delivery'], 'final')
        final_md = (self.root / 'final-out/result.md').read_text(encoding='utf-8')
        self.assertIn(r'\_\_\_\_\_\_\mathrm{Cr_2O_7^{2-}}', final_md)
        self.assertNotIn(r'\underline', final_md)

        # CLI flags on export_page.py
        cli_src = _write_json(self.root / 'cli.json', {'blocks': [T1_BLOCK]})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / 'export_page.py'), str(cli_src),
             '--output-dir', str(self.root / 'cli-out'),
             '--paste-target', 'axmath', '--blank-latex', 'escaped'],
            check=True, capture_output=True, text=True,
        )
        self.assertIn('result.html', proc.stdout)
        self.assertIn(r'\_\_\_\_\_\_', (self.root / 'cli-out/result.md').read_text(encoding='utf-8'))

    def test_fullwidth_operators_and_arrows_in_merge_equation(self):
        block = {
            'type': 'text',
            'runs': [
                {'type': 'text', 'text': '＿＿（'},
                {'type': 'chemistry', 'latex': r'\mathrm{H_2}'},
                {'type': 'text', 'text': '）＋ '},
                {'type': 'chemistry', 'latex': r'\mathrm{O_2}'},
                {'type': 'text', 'text': ' → '},
                {'type': 'chemistry', 'latex': r'\mathrm{H_2O}'},
                {'type': 'text', 'text': ' ↓'},
            ],
        }
        expected = '```latex\n' + r'\underline{\qquad}\,(\mathrm{H_2})+\mathrm{O_2}\rightarrow\mathrm{H_2O}\downarrow' + '\n```'
        self.assertEqual(merge_equation(block), expected)


if __name__ == '__main__':
    unittest.main()
