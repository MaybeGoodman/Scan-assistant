"""V1.0: question index, student projection, native chemistry in Word, draft/final gate, finalize."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
from lxml import etree  # noqa: E402
from chemistry_word import ChemistryRenderError, is_simple, parse, plain_text, rich_segments  # noqa: E402
from confirmation import parse as parse_reply  # noqa: E402
from docx_audit import audit, consistency  # noqa: E402
from export_docx import export_docx  # noqa: E402
from export_page import export_result  # noqa: E402
from questions import (QuestionError, delivery_status, forbidden_strings, project, question_blocks,  # noqa: E402
                       review_items, validate_questions)

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}


def exam(**question):
    """One comprehensive question with a printed answer, analysis and an inline answer run."""
    blocks = [
        {'type': 'text', 'id': 't', 'role': 'title', 'text': '高一数学练习'},
        {'type': 'text', 'id': 'stem', 'role': 'stem', 'runs': [
            {'type': 'text', 'text': '18．已知'}, {'type': 'math', 'latex': 'f(x)=x^2-2ax+3'}, {'type': 'text', 'text': '。'}]},
        {'type': 'text', 'id': 's1', 'role': 'subquestion', 'text': '（1）若f(1)=0，求a；'},
        {'type': 'text', 'id': 's2', 'role': 'subquestion', 'runs': [
            {'type': 'text', 'text': '（2）求最小值。'}, {'type': 'text', 'role': 'filled_answer', 'text': '最小值为负一'}]},
        {'type': 'text', 'id': 'ans', 'role': 'answer', 'text': '【答案】（1）a=2；（2）最小值-1。'},
        {'type': 'text', 'id': 'ana', 'role': 'analysis', 'text': '【解析】配方得顶点为(2,-1)。'},
        {'type': 'table', 'id': 'tab', 'rows': 1, 'cols': 2, 'cells': [
            {'row': 0, 'col': 0, 'text': '小问'}, {'row': 0, 'col': 1, 'role': 'answer', 'text': '答案格内容'}]},
    ]
    entry = {'question_id': 'q18', 'number': '18', 'module': 'M05', 'blocks': ['stem', 'ans', 'ana'],
             'subquestions': [{'subquestion_id': 'q18-1', 'number': '(1)', 'blocks': ['s1']},
                              {'subquestion_id': 'q18-2', 'number': '(2)', 'blocks': ['s2'], 'depends_on': ['q18-1']}],
             'review_status': 'confirmed', **question}
    return {'blocks': blocks, 'questions': [entry]}


class QuestionIndexTests(unittest.TestCase):
    def test_valid_index_and_ordered_bundle(self):
        document = exam()
        self.assertEqual(validate_questions(document), [])
        self.assertEqual([b['id'] for b in question_blocks(document, 'q18')], ['stem', 'ans', 'ana', 's1', 's2'])

    def test_rejects_out_of_order_shared_and_forward_dependencies(self):
        bad = exam(blocks=['ans', 'stem'])
        with self.assertRaisesRegex(QuestionError, '顺序'):
            validate_questions(bad)
        bad = exam()
        bad['questions'].append({'question_id': 'q19', 'blocks': ['stem']})
        with self.assertRaisesRegex(QuestionError, '同时属于'):
            validate_questions(bad)
        bad = exam()
        bad['questions'][0]['subquestions'][0]['depends_on'] = ['q18-2']
        with self.assertRaisesRegex(QuestionError, '排在它前面'):
            validate_questions(bad)
        bad = exam()
        bad['blocks'][0]['role'] = 'hint'
        with self.assertRaisesRegex(QuestionError, '未知的内容角色'):
            validate_questions(bad)

    def test_legacy_document_without_index_is_unchanged(self):
        legacy = {'blocks': [{'type': 'text', 'text': '答案：B'}]}
        self.assertEqual(project(legacy, 'original')[0], legacy)
        self.assertEqual(delivery_status(review_items(legacy))[0], 'final')


class StudentProjectionTests(unittest.TestCase):
    def test_student_view_removes_answer_roles_and_keeps_question(self):
        student, removed = project(exam(), 'student')
        ids = [b.get('id') for b in student['blocks']]
        self.assertNotIn('ans', ids)
        self.assertNotIn('ana', ids)
        self.assertEqual(student['blocks'][3]['runs'], [{'type': 'text', 'text': '（2）求最小值。'}])
        self.assertEqual(student['blocks'][4]['cells'][1], {'row': 0, 'col': 1, 'text': ''})
        self.assertEqual(student['questions'][0]['blocks'], ['stem'])
        self.assertEqual({r['role'] for r in removed}, {'answer', 'analysis', 'filled_answer'})

    def test_original_view_keeps_printed_answers(self):
        original, removed = project(exam(), 'original')
        self.assertEqual(removed, [])
        self.assertEqual(len(original['blocks']), 7)

    def test_unannotated_answer_label_is_flagged_not_deleted(self):
        document = {'blocks': [{'type': 'text', 'text': '【答案】B'}]}
        student, _ = project(document, 'student')
        self.assertEqual(student['blocks'][0]['text'], '【答案】B')
        items = review_items(student, mode='student')
        self.assertEqual([i['kind'] for i in items], ['possible_answer'])

    def test_fragment_level_forbidden_strings(self):
        values = forbidden_strings([{'text': '【答案】（1）8\\,\\mathrm{m/s}；（2）72\\,\\mathrm{m}。'}])
        self.assertIn('8m/s', values)
        self.assertIn('72m', values)


class ChemistryWordTests(unittest.TestCase):
    def test_simple_formula_uses_rich_text_sub_superscripts(self):
        segments = rich_segments(parse(r'\mathrm{SO_4^{2-}}'))
        self.assertEqual(segments, [('SO', None), ('4', 'subscript'), ('2−', 'superscript')])
        self.assertTrue(is_simple(parse(r'\mathrm{CuSO_4}\cdot 5\mathrm{H_2O}')))
        self.assertEqual(plain_text(r'\mathrm{Fe(OH)_3}\downarrow'), 'Fe(OH)3↓')

    def test_conditions_prescripts_and_oxidation_states_use_omml(self):
        for source in (r'2\mathrm{KClO_3}\xrightarrow[\Delta]{\mathrm{MnO_2}}2\mathrm{KCl}+3\mathrm{O_2}\uparrow',
                       r'{}^{23}_{11}\mathrm{Na}', r'\overset{+2}{\mathrm{Fe}}\mathrm{O}'):
            self.assertFalse(is_simple(parse(source)), source)

    def test_unsupported_construct_raises_for_review(self):
        with self.assertRaises(ChemistryRenderError):
            parse(r'\mathrm{H_2O}\mathop{=}\limits^{\Delta}')

    def export(self, root, blocks, **options):
        source = root / 'in.json'
        source.write_text(json.dumps({'blocks': blocks}, ensure_ascii=False), encoding='utf-8')
        target = export_docx(source, root / 'out.docx', word_confirmed=True, **options)
        with ZipFile(target) as package:
            xml = etree.fromstring(package.read('word/document.xml'))
        return xml, json.loads(target.with_suffix('.review.json').read_text(encoding='utf-8'))

    def test_native_word_chemistry_in_body_options_and_tables(self):
        equation = r'2\mathrm{KClO_3}\xrightarrow[\Delta]{\mathrm{MnO_2}}2\mathrm{KCl}+3\mathrm{O_2}\uparrow'
        with tempfile.TemporaryDirectory() as temp:
            xml, report = self.export(Path(temp), [
                {'type': 'text', 'runs': [{'type': 'text', 'text': 'A．'}, {'type': 'chemistry', 'latex': r'\mathrm{Ca^{2+}}'}]},
                {'type': 'chemistry', 'latex': equation},
                {'type': 'table', 'rows': 1, 'cols': 1, 'cells': [{'row': 0, 'col': 0, 'runs': [
                    {'type': 'chemistry', 'latex': r'\mathrm{NH_4^+}'}]}]}])
            texts = xml.xpath('//w:t/text()', namespaces=NS)
            self.assertNotIn('\\mathrm', ''.join(texts))
            self.assertTrue(xml.xpath('//w:vertAlign[@w:val="superscript"]', namespaces=NS))
            self.assertTrue(xml.xpath('//w:tbl//w:vertAlign[@w:val="subscript"]', namespaces=NS))
            self.assertEqual(len(xml.xpath('//m:oMathPara//m:limLow', namespaces=NS)), 1)
            self.assertEqual([r['rendering'] for r in report['expressions']], ['rich_text', 'omml', 'rich_text'])
            self.assertEqual(report['chemistry_format'], 'native')
            self.assertEqual(report['delivery'], 'final')

    def test_render_failure_keeps_source_and_makes_draft(self):
        bad = r'\mathrm{H_2O}\mathop{=}\limits^{\Delta}'
        with tempfile.TemporaryDirectory() as temp:
            xml, report = self.export(Path(temp), [{'type': 'chemistry', 'latex': bad}])
            self.assertIn(bad, xml.xpath('//w:t/text()', namespaces=NS))
            self.assertEqual(report['expressions'][0]['status'], 'needs_review')
            self.assertEqual(report['delivery'], 'draft')

    def test_source_compatibility_path_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            xml, report = self.export(Path(temp), [{'type': 'chemistry', 'latex': r'\mathrm{SO_4^{2-}}'}],
                                      chemistry_format='source')
            self.assertIn(r'\mathrm{SO_4^{2-}}', xml.xpath('//w:t/text()', namespaces=NS))
            self.assertEqual(report['expressions'][0]['status'], 'preserved')


class DeliveryGateTests(unittest.TestCase):
    def test_inference_and_unreadable_markers_make_a_marked_draft(self):
        document = exam()
        document['blocks'][2]['text'] = '（1）若f(〔1〕)=0，求a；'
        document['blocks'].append({'type': 'text', 'text': '补写说明：第18题（1）中〔1〕依据残留笔画推断。'})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'in.json'
            source.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            target = export_docx(source, root / 'draft.docx', word_confirmed=True)
            report = json.loads(target.with_suffix('.review.json').read_text(encoding='utf-8'))
            self.assertEqual(report['delivery'], 'draft')
            self.assertEqual([i['kind'] for i in report['review_items']], ['inference'])
            with ZipFile(target) as package:
                header = package.read('word/header1.xml').decode('utf-8')
            self.assertIn('待复核草稿', header)
            page = export_result(source, root / 'html')
            self.assertEqual(page['delivery'], 'draft')
            self.assertTrue((root / 'html/result.md').read_text(encoding='utf-8').startswith('【待复核草稿】'))
            # A matching resolution makes the same content final; a stale key would not match.
            document['review_resolutions'] = [{'key': report['review_items'][0]['key'], 'resolution': 'confirmed',
                                               'by': 'host', 'note': '回看原图确认'}]
            self.assertEqual(delivery_status(review_items(document))[0], 'final')
            document['blocks'][2]['text'] = '（1）若f(〔7〕)=0，求a；'
            self.assertEqual(delivery_status(review_items(document))[0], 'draft')

    def test_unconfirmed_or_incomplete_question_blocks_final(self):
        kinds = {i['kind'] for i in review_items(exam(review_status='needs_review'))}
        self.assertIn('question', kinds)
        kinds = {i['kind'] for i in review_items(exam(completeness={'complete': False, 'missing': ['(3)']}))}
        self.assertIn('incomplete', kinds)

    def test_student_word_has_no_answers_and_matches_chat(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'in.json'
            source.write_text(json.dumps(exam(), ensure_ascii=False), encoding='utf-8')
            target = export_docx(source, root / 'student.docx', word_confirmed=True, output_mode='student')
            result = audit(target, ['a=2', '最小值-1', '顶点为(2,-1)', '答案格内容', '最小值为负一'])
            self.assertTrue(result['ok'], result['problems'])
            report = json.loads(target.with_suffix('.review.json').read_text(encoding='utf-8'))
            self.assertNotIn('a=2', json.dumps(report, ensure_ascii=False))
            student, _ = project(exam(), 'student')
            self.assertTrue(consistency(target, student)['ok'])
            original = export_docx(source, root / 'original.docx', word_confirmed=True)
            self.assertFalse(audit(original, ['顶点为(2,-1)'])['ok'])

    def test_answer_quoted_in_another_block_is_a_leak(self):
        document = exam()
        document['blocks'].append({'type': 'text', 'role': 'other', 'text': '说明：参考答案为最小值-1。'})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'in.json'
            source.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '泄漏检查'):
                export_docx(source, root / 'student.docx', word_confirmed=True, output_mode='student')
            self.assertFalse((root / 'student.docx').exists())

    def test_given_data_matching_an_answer_is_not_a_leak(self):
        document = exam()
        document['blocks'][1]['runs'][1]['latex'] = 'R_1=10\\,\\Omega'
        document['blocks'][4]['text'] = '【答案】（1）10\\,\\Omega；（2）另一值。'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'in.json'
            source.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            export_docx(source, root / 'student.docx', word_confirmed=True, output_mode='student')

    def test_audit_flags_alt_text_comments_and_hidden_parts(self):
        from docx import Document
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'x.docx'
            document = Document()
            document.add_paragraph('题干')
            run = document.add_paragraph().add_run('隐藏')
            run.font.hidden = True
            document.core_properties.subject = '答案是 42'
            document.save(path)
            problems = audit(path, ['答案是42'])['problems']
            self.assertTrue(any('隐藏' in p for p in problems))
            self.assertTrue(any('答案是' in p for p in problems))


class PipelineFinalizeTests(unittest.TestCase):
    def run_cli(self, *args):
        result = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'pipeline.py'), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8')
        return result.returncode, json.loads(result.stdout)

    def test_draft_then_finalize_with_current_keys_only(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            Image.new('RGB', (40, 40), 'white').save(root / 'page.png')
            document = exam()
            document['blocks'][2]['text'] = '（1）若f(〔1〕)=0，求a；'
            (root / 'c.json').write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            code, state = self.run_cli('run', root / 'c.json', '--source', root / 'page.png', '--run-id', 'r1',
                                       '--format', 'docx', '--word-confirmed', '--output', root / 'out.docx',
                                       '--output-mode', 'original')
            self.assertEqual((code, state['status'], state['delivery']), (0, 'completed', 'draft'))
            stale = root / 'stale.json'
            stale.write_text(json.dumps({'resolutions': [{'key': 'inference:blocks[2]:000000000000',
                                                          'resolution': 'confirmed', 'by': 'host', 'note': ''}]}),
                             encoding='utf-8')
            code, result = self.run_cli('finalize', '--state', state['state'], '--resolutions', stale,
                                        '--output', root / 'final.docx')
            self.assertEqual(code, 1)
            self.assertIn('过期', result['error'])
            report = json.loads((root / 'r1-work/r1.word.review.json').read_text(encoding='utf-8'))
            good = root / 'good.json'
            good.write_text(json.dumps({'resolutions': [{'key': i['key'], 'resolution': 'confirmed', 'by': 'user',
                                                         'note': '已核对原图'} for i in report['review_items']]}),
                            encoding='utf-8')
            code, state = self.run_cli('finalize', '--state', state['state'], '--resolutions', good,
                                       '--output', root / 'final.docx')
            self.assertEqual((code, state['delivery']), (0, 'final'))
            self.assertTrue((root / 'final.docx').exists() and (root / 'out.docx').exists())


class GenerateConfirmationTests(unittest.TestCase):
    def test_generate_invitation_answers(self):
        self.assertTrue(parse_reply('生成同类题', ['generate'])['generate'])
        self.assertIs(parse_reply('不用了', ['generate'])['generate'], False)
        self.assertIs(parse_reply('1B', ['generate'])['generate'], False)
        self.assertEqual(parse_reply('随便', ['generate'])['ambiguous'], ['generate'])
        self.assertNotIn('generate', parse_reply('1A 2C', ['word', 'image']))


if __name__ == '__main__':
    unittest.main()
