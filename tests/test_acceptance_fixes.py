"""1.0.1: regressions for the independent acceptance findings F01–F07 (2026-11-03).

Each class keeps the acceptance report's original failing input and expected result,
plus the adjacent normal flow that must keep working.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
from lxml import etree  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from docx_audit import consistency  # noqa: E402
from export_docx import export_docx  # noqa: E402
import pdf_batches  # noqa: E402
from questions import QuestionError, validate_questions  # noqa: E402
from test_v1_variants import candidate as baseline_candidate  # noqa: E402
from variant_checks import run_check  # noqa: E402
import variants  # noqa: E402

M = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def acceptance_source():
    """The acceptance probe's source question q20 (two dependent subquestions)."""
    return {'blocks': [{'type': 'text', 'id': 'stem', 'role': 'stem', 'text': '20．已知二次函数 f(x)=x²-4x+4。'},
                       {'type': 'text', 'id': 's1', 'role': 'subquestion', 'text': '（1）求函数的零点；'},
                       {'type': 'text', 'id': 's2', 'role': 'subquestion', 'text': '（2）求函数在[0,3]上的最小值。'}],
            'questions': [{'question_id': 'q20', 'number': '20', 'module': 'M05', 'blocks': ['stem'],
                           'subquestions': [{'subquestion_id': 's1', 'number': '(1)', 'blocks': ['s1']},
                                            {'subquestion_id': 's2', 'number': '(2)', 'blocks': ['s2'],
                                             'depends_on': ['s1']}],
                           'review_status': 'confirmed'}]}


def candidate(slot=1, **kw):
    value = baseline_candidate(slot, **kw)
    value['question_id'] = 'q20'
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def word_text(path):
    with ZipFile(path) as package:
        root = etree.fromstring(package.read('word/document.xml'))
    return ''.join(root.xpath('//w:t/text() | //m:t/text()', namespaces={**W, **M}))


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path

    def init(self, document=None, run_id='g', count=1, max_attempts=2):
        source = self.write('source.json', document or acceptance_source())
        return variants.init(source, run_id, ['q20'], count=count, max_attempts=max_attempts)['ledger']

    def submit(self, ledger, data, name='c.json'):
        return variants.submit(ledger, self.write(name, data))['submitted']

    def deliver(self, ledger, name='student'):
        return variants.deliver(ledger, 'both', self.root / name, word_confirmed=True)


class F01AliasedSubquestions(Base):
    def test_acceptance_input_second_subquestion_reusing_first_block_is_rejected(self):
        ledger = self.init()
        data = candidate()
        data['variant']['blocks'] = [b for b in data['variant']['blocks'] if b['id'] != 's2']
        data['variant']['subquestions'][1]['blocks'] = ['s1']
        result = self.submit(ledger, data)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('重复引用' in f for f in result['failures']), result['failures'])
        self.assertEqual(variants.status(ledger)['questions'][0]['passed'], 0)
        with self.assertRaisesRegex(ValueError, '仍有可重试'):
            self.deliver(ledger)
        self.assertFalse((self.root / 'student').exists())

    def test_subquestion_reusing_stem_block_is_rejected(self):
        ledger = self.init()
        data = candidate()
        data['variant']['subquestions'][1]['blocks'] = ['stem']
        result = self.submit(ledger, data)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('块 stem' in f for f in result['failures']), result['failures'])

    def test_subquestion_with_only_a_figure_has_no_answerable_text(self):
        figure = self.root / 'fig.png'
        Image.new('RGB', (300, 120), 'white').save(figure)
        ledger = self.init()
        data = candidate()
        data['variant']['blocks'][2] = {'type': 'image', 'id': 's2', 'role': 'figure', 'path': 'fig.png', 'alt': ''}
        result = self.submit(ledger, data)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('没有可作答的文字题面' in f for f in result['failures']), result['failures'])

    def test_source_index_cannot_share_a_block_inside_one_question(self):
        document = acceptance_source()
        document['questions'][0]['subquestions'][1]['blocks'] = ['s1']
        with self.assertRaisesRegex(QuestionError, '共用块'):
            validate_questions(document)

    def test_complete_candidate_still_delivers_both_subquestions(self):
        ledger = self.init()
        self.assertEqual(self.submit(ledger, candidate())['status'], 'passed')
        result = self.deliver(ledger)
        self.assertEqual(result['delivery'], 'final')
        chat = Path(result['files']['chat']).read_text(encoding='utf-8')
        body = word_text(result['files']['docx'])
        for text in ('（1）已知g(1)=0', '（2）当a取（1）中的值时'):
            self.assertIn(text, chat)
            self.assertIn(text, body)


class F02FrozenFigures(Base):
    def figure_candidate(self, review=True, name='diagram.png'):
        figure = self.root / name
        image = Image.new('RGB', (700, 300), 'white')
        ImageDraw.Draw(image).line((20, 100, 650, 100), fill='black', width=4)
        image.save(figure)
        data = candidate()
        data['variant']['blocks'].append({'type': 'image', 'id': 'fig', 'role': 'figure', 'path': name, 'alt': ''})
        if review:
            data['review']['figures'] = [{
                'id': 'fig', 'sha256': sha(figure), 'reviewed_by': 'host_vision', 'status': 'pass',
                'checks': {key: True for key in variants.FIGURE_CHECKS}, 'notes': ['看图核对：线段与题面一致']}]
        return figure, data

    def tamper(self, figure):
        image = Image.open(figure)
        ImageDraw.Draw(image).text((15, 15), 'ANSWER: a=3', (0, 0, 0))
        image.save(figure)

    def test_acceptance_input_figure_without_visual_review_is_not_passed(self):
        ledger = self.init()
        _, data = self.figure_candidate(review=False)
        result = self.submit(ledger, data)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('视觉复核' in f for f in result['failures']))

    def test_reviewed_figure_changed_after_verification_blocks_delivery(self):
        ledger = self.init()
        figure, data = self.figure_candidate()
        self.assertEqual(self.submit(ledger, data)['status'], 'passed')
        self.tamper(figure)  # Candidate JSON untouched; only the referenced PNG changes.
        with self.assertRaisesRegex(ValueError, '验证后被修改'):
            self.deliver(ledger)
        self.assertFalse((self.root / 'student').exists())
        self.assertFalse((self.root / 'g.student.json').exists())

    def test_frozen_copy_changed_blocks_delivery(self):
        ledger = self.init()
        _, data = self.figure_candidate()
        self.submit(ledger, data)
        frozen = next((Path(ledger).parent / 'assets').rglob('fig.png'))
        self.tamper(frozen)
        with self.assertRaisesRegex(ValueError, '冻结副本'):
            self.deliver(ledger)

    def test_review_bound_to_a_different_file_is_rejected(self):
        ledger = self.init()
        figure, data = self.figure_candidate()
        image = Image.open(figure)  # Edited between the visual review and submission (still pure B/W).
        ImageDraw.Draw(image).line((20, 200, 650, 200), fill='black', width=4)
        image.save(figure)
        result = self.submit(ledger, data)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('sha256' in f for f in result['failures']), result['failures'])

    def test_incomplete_review_checks_are_rejected(self):
        ledger = self.init()
        _, data = self.figure_candidate()
        data['review']['figures'][0]['checks']['no_answer_content'] = False
        self.assertEqual(self.submit(ledger, data)['status'], 'failed')

    def test_verified_figure_bytes_reach_chat_and_word_unchanged(self):
        ledger = self.init()
        figure, data = self.figure_candidate()
        verified = figure.read_bytes()
        self.submit(ledger, data)
        result = self.deliver(ledger)
        self.assertEqual(result['delivery'], 'final')
        with ZipFile(result['files']['docx']) as package:
            media = [package.read(n) for n in package.namelist() if n.startswith('word/media/')]
        self.assertEqual(media, [verified])
        chat_figures = list((self.root / 'student' / 'figures').glob('*.png'))
        self.assertEqual([p.read_bytes() for p in chat_figures], [verified])

    def test_old_ledger_entry_without_frozen_assets_is_refused(self):
        ledger = self.init()
        _, data = self.figure_candidate()
        self.submit(ledger, data)
        state = json.loads(Path(ledger).read_text(encoding='utf-8'))
        state['candidates'][0]['assets'] = []  # As written by 1.0.0, which never froze figures.
        Path(ledger).write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '没有在提交时冻结'):
            self.deliver(ledger)


class F03SharedMaterialGate(Base):
    def with_material(self, blocks):
        document = acceptance_source()
        document['materials'] = [{'material_id': 'passage', 'blocks': blocks}]
        document['questions'][0]['materials'] = ['passage']
        return document

    def test_acceptance_input_missing_passage_blocks_init(self):
        with self.assertRaisesRegex(ValueError, '共享材料 passage 引用的块 MISSING_PASSAGE'):
            self.init(self.with_material(['MISSING_PASSAGE']))
        self.assertFalse((self.root / 'g-gen').exists())

    def test_material_without_blocks_blocks_init(self):
        with self.assertRaisesRegex(ValueError, '没有任何题面块'):
            self.init(self.with_material([]))

    def test_missing_subquestion_block_is_located(self):
        document = acceptance_source()
        document['questions'][0]['subquestions'][1]['blocks'] = ['s2', 's3']
        with self.assertRaisesRegex(ValueError, '小问 s2 引用的块 s3'):
            self.init(document)

    def test_present_passage_still_allows_generation(self):
        document = self.with_material(['passage-1'])
        document['blocks'].insert(0, {'type': 'text', 'id': 'passage-1', 'role': 'material', 'text': '阅读材料：……'})
        status = variants.status(self.init(document))
        self.assertEqual(status['status'], 'awaiting_candidates')


class F04CandidateReviewItems(Base):
    def assert_not_counted(self, data):
        ledger = self.init()
        result = self.submit(ledger, data)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('待复核' in f for f in result['failures']), result['failures'])
        self.assertEqual(variants.status(ledger)['questions'][0]['passed'], 0)
        return ledger

    def test_acceptance_input_inference_bracket(self):
        data = candidate()
        data['variant']['blocks'][0]['text'] = '设二次函数g(x)=x²-2ax+〔5〕，a为实数。'
        self.assert_not_counted(data)

    def test_unreadable_marker_unresolved_expression_and_unclear_role(self):
        for change in ('XXX', 'unresolved', 'uncertain'):
            with self.subTest(change):
                self.temp.cleanup()
                self.temp = tempfile.TemporaryDirectory()
                self.root = Path(self.temp.name)
                data = candidate()
                block = data['variant']['blocks'][0]
                if change == 'XXX':
                    block['text'] = '设二次函数g(x)=x²-2ax+XXX，a为实数。'
                elif change == 'unresolved':
                    block.pop('text')
                    block['runs'] = [{'type': 'text', 'text': '设'},
                                     {'type': 'math', 'latex': 'g(x)', 'status': 'unresolved', 'reason': '看不清'}]
                else:
                    block['role'] = 'uncertain'
                self.assert_not_counted(data)

    def test_retry_with_corrected_text_passes_and_delivers_final(self):
        data = candidate()
        data['variant']['blocks'][0]['text'] = '设二次函数g(x)=x²-2ax+〔5〕，a为实数。'
        ledger = self.assert_not_counted(data)
        self.assertEqual(self.submit(ledger, candidate(), 'c2.json')['status'], 'passed')
        result = self.deliver(ledger)
        self.assertEqual(result['delivery'], 'final')
        self.assertIn('全部达到目标数量', result['next_action'])


class F05FormulaConsistency(Base):
    def export(self, document):
        self.count = getattr(self, 'count', 0) + 1
        source = self.write(f'source{self.count}.json', document)
        target = self.root / f'correct{self.count}.docx'
        export_docx(source, target, word_confirmed=True)
        return source, target

    def mutate(self, target, change):
        with ZipFile(target) as package:
            parts = {n: package.read(n) for n in package.namelist()}
        root = etree.fromstring(parts['word/document.xml'])
        change(root)
        parts['word/document.xml'] = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
        wrong = target.with_name(target.stem + '-wrong.docx')
        with ZipFile(wrong, 'w', ZIP_DEFLATED) as package:
            for name, value in parts.items():
                package.writestr(name, value)
        return wrong

    def assert_detected(self, document, change):
        source, target = self.export(document)
        self.assertTrue(consistency(target, document, source=source)['ok'])
        wrong = self.mutate(target, change)
        result = consistency(wrong, document, source=source)
        self.assertFalse(result['ok'], 'mutation not detected')
        return result

    @staticmethod
    def math_doc(latex):
        return {'blocks': [{'type': 'text', 'role': 'stem', 'runs': [
            {'type': 'text', 'text': '计算：'}, {'type': 'math', 'latex': latex}, {'type': 'text', 'text': '。'}]}]}

    @staticmethod
    def set_text(xpath, ns, value, index=0):
        def change(root):
            node = root.xpath(xpath, namespaces=ns)[index]
            node.text = value
        return change

    def test_acceptance_input_denominator_2_to_7(self):
        result = self.assert_detected(self.math_doc(r'\frac{1}{2}+\sqrt{9}'),
                                      self.set_text('//m:f/m:den//m:t', M, '7'))
        self.assertIn('第 1 段', result['problems'][0])

    def test_numerator_exponent_and_radicand(self):
        cases = [(r'\frac{1}{2}', '//m:f/m:num//m:t', '5'), (r'x^{2}', '//m:sSup/m:sup//m:t', '3'),
                 (r'\sqrt{9}', '//m:rad/m:e//m:t', '8')]
        for latex, xpath, value in cases:
            with self.subTest(latex):
                self.assert_detected(self.math_doc(latex), self.set_text(xpath, M, value))

    def test_chemistry_charge_and_reaction_condition(self):
        charge = {'blocks': [{'type': 'text', 'runs': [{'type': 'text', 'text': '离子：'},
                                                       {'type': 'chemistry', 'latex': r'\mathrm{SO_4^{2-}}'}]}]}

        def flip_superscript(root):
            run = root.xpath('//w:r[w:rPr/w:vertAlign[@w:val="superscript"]]', namespaces=W)[0]
            run.xpath('w:t', namespaces=W)[0].text = '3−'
        self.assert_detected(charge, flip_superscript)

        def baseline_charge(root):
            align = root.xpath('//w:vertAlign[@w:val="superscript"]', namespaces=W)[0]
            align.getparent().remove(align)  # Same characters, charge no longer raised.
        self.assert_detected(charge, baseline_charge)
        condition = {'blocks': [{'type': 'text', 'runs': [{'type': 'chemistry', 'latex':
                     r'2\mathrm{KClO_3}\xrightarrow[\Delta]{\mathrm{MnO_2}}2\mathrm{KCl}+3\mathrm{O_2}\uparrow'}]}]}
        self.assert_detected(condition, self.set_text('//m:limUpp/m:lim//m:t', M, 'Fe'))

    def test_table_cell_math_and_paragraph_order(self):
        table = {'blocks': [{'type': 'text', 'text': '第一段'}, {'type': 'text', 'text': '第二段'},
                            {'type': 'table', 'rows': 1, 'cols': 1,
                             'cells': [{'row': 0, 'col': 0, 'runs': [{'type': 'math', 'latex': r'\frac{a}{b}'}]}]}]}
        self.assert_detected(table, self.set_text('//w:tbl//m:den//m:t', {**W, **M}, 'c'))

        def swap(root):
            first, second = root.xpath('//w:body/w:p', namespaces=W)[:2]
            first.addprevious(second)
        self.assert_detected(table, swap)

    def test_replaced_picture_is_detected(self):
        figure = self.root / 'fig.png'
        Image.new('RGB', (200, 80), 'white').save(figure)
        document = {'blocks': [{'type': 'text', 'text': '如图'}, {'type': 'image', 'id': 'f', 'path': 'fig.png', 'alt': ''}]}
        source, target = self.export(document)
        self.assertTrue(consistency(target, document, source=source)['ok'])
        other = self.root / 'other.png'
        image = Image.new('RGB', (200, 80), 'white')
        ImageDraw.Draw(image).text((5, 5), 'a=3', (0, 0, 0))
        image.save(other)
        with ZipFile(target) as package:
            parts = {n: package.read(n) for n in package.namelist()}
        media = next(n for n in parts if n.startswith('word/media/'))
        parts[media] = other.read_bytes()
        wrong = self.root / 'wrong.docx'
        with ZipFile(wrong, 'w', ZIP_DEFLATED) as package:
            for name, value in parts.items():
                package.writestr(name, value)
        self.assertFalse(consistency(wrong, document, source=source)['ok'])

    def test_without_source_pictures_are_compared_by_count(self):
        document = self.math_doc(r'\frac{1}{2}')
        _, target = self.export(document)
        self.assertTrue(consistency(target, document)['ok'])


class F06RootCompleteness(unittest.TestCase):
    def roots(self, expr, claimed, interval=('-1', '1')):
        return run_check({'kind': 'roots', 'item': 'all', 'expr': expr, 'var': 'x', 'claimed': claimed,
                          'interval': list(interval)}, {})

    def test_acceptance_input_off_grid_double_root(self):
        result = self.roots('(x-0.123456789)**2', [])
        self.assertIs(result['ok'], False)
        self.assertIn('遗漏', result['detail'])

    def test_listed_double_root_and_boundary_roots(self):
        self.assertIs(self.roots('(x-0.123456789)**2', ['0.123456789'])['ok'], True)
        self.assertIs(self.roots('(x-1)*(x+1)', ['1'])['ok'], False)  # Boundary root -1 missing.
        self.assertIs(self.roots('(x-1)*(x+1)', ['-1', '1'])['ok'], True)
        self.assertIs(self.roots('x**3', ['0'])['ok'], True)
        self.assertIs(self.roots('(x-3)*(x-0.5)', ['0.5'])['ok'], True)  # 3 lies outside the interval.

    def test_irrational_roots_listed_numerically(self):
        self.assertIs(self.roots('x**2-5', ['sqrt(5)', '-sqrt(5)'], ('-10', '10'))['ok'], True)
        self.assertIs(self.roots('x**2-5', ['sqrt(5)'], ('-10', '10'))['ok'], False)

    def test_non_polynomial_cannot_claim_completeness(self):
        for expr in ('1/(x-0.5)', 'sin(x)', 'sqrt(x+2)-1'):
            with self.subTest(expr):
                self.assertIsNone(self.roots(expr, [])['ok'])
        self.assertIs(self.roots('sin(x)', ['1'])['ok'], False)  # A wrong claimed root still fails.

    def test_uncertain_roots_check_keeps_candidate_out_of_passed(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        source = root / 'source.json'
        source.write_text(json.dumps(acceptance_source(), ensure_ascii=False), encoding='utf-8')
        ledger = variants.init(source, 'g', ['q20'], count=1)['ledger']
        data = candidate()
        data['internal']['checks'].append({'kind': 'roots', 'item': '(1)', 'expr': '1/(a-2)', 'var': 'a',
                                           'claimed': [], 'interval': ['-5', '5']})
        (root / 'c.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(variants.submit(ledger, root / 'c.json')['submitted']['status'], 'needs_review')


class F07CrossBatchIndex(Base):
    question = {'question_id': 'q跨页', 'number': '18', 'module': 'M05', 'blocks': ['stem'],
                'subquestions': [{'subquestion_id': 's1', 'number': '(1)', 'blocks': ['s1']},
                                 {'subquestion_id': 's2', 'number': '(2)', 'blocks': ['s2'], 'depends_on': ['s1']}],
                'review_status': 'confirmed'}

    def progress(self, batches):
        manifest = self.write('pages.json', {'source_sha256': '0' * 64, 'source_page_count': len(batches),
                                             'selected_pages': list(range(1, len(batches) + 1)),
                                             'pages': [{'page': i} for i in range(1, len(batches) + 1)]})
        progress = self.root / 'progress.json'
        pdf_batches.init(manifest, progress, batch_size=1)
        for number, data in enumerate(batches, 1):
            pdf_batches.commit(progress, number, self.write(f'b{number}.json', {'batch': number, 'pages': [number], **data}))
        return progress

    def acceptance_batches(self, second_question=None):
        return [{'blocks': [{'type': 'text', 'id': 'stem', 'text': '跨页综合题'},
                            {'type': 'text', 'id': 's1', 'text': '（1）求参；'}], 'questions': [self.question]},
                {'blocks': [{'type': 'text', 'id': 's2', 'text': '（2）在前问条件下求最值。'}],
                 'questions': [second_question or self.question]}]

    def test_acceptance_input_question_index_survives_merge_with_spans(self):
        merged = pdf_batches.merge(self.progress(self.acceptance_batches()), self.root / 'merged.json')
        self.assertEqual(len(merged['questions']), 1)
        question = merged['questions'][0]
        self.assertEqual(question['question_id'], 'q跨页')
        self.assertEqual([s['subquestion_id'] for s in question['subquestions']], ['s1', 's2'])
        self.assertEqual(question['source_spans'], [{'batch': 1, 'pages': [1], 'blocks': ['stem', 's1']},
                                                    {'batch': 2, 'pages': [2], 'blocks': ['s2']}])
        self.assertNotIn('index_check', merged)

    def test_conflicting_declarations_are_located(self):
        changed = deepcopy(self.question)
        changed['subquestions'][1]['depends_on'] = []
        with self.assertRaisesRegex(ValueError, 'q跨页 在第 1 批与第 2 批'):
            pdf_batches.merge(self.progress(self.acceptance_batches(changed)), self.root / 'merged.json')

    def test_question_declared_once_is_kept(self):
        batches = self.acceptance_batches()
        del batches[1]['questions']
        merged = pdf_batches.merge(self.progress(batches), self.root / 'merged.json')
        self.assertEqual(merged['questions'][0]['question_id'], 'q跨页')

    def test_cut_question_is_flagged_and_cannot_generate(self):
        batches = self.acceptance_batches()
        batches[1]['blocks'] = [{'type': 'text', 'id': 'other', 'text': '19．下一题'}]
        merged = pdf_batches.merge(self.progress(batches), self.root / 'merged.json')
        self.assertEqual(merged['index_check']['missing_blocks'][0]['block'], 's2')
        with self.assertRaisesRegex(ValueError, '小问 s2 引用的块 s2'):
            variants.init(self.root / 'merged.json', 'g', ['q跨页'])

    def test_merged_reading_group_goes_straight_into_generation(self):
        question = {'question_id': 'q21', 'number': '21', 'module': 'M08', 'blocks': ['q21'],
                    'materials': ['passageA'], 'review_status': 'confirmed'}
        material = {'material_id': 'passageA', 'blocks': ['p1', 'p2']}
        batches = [{'blocks': [{'type': 'text', 'id': 'p1', 'role': 'material', 'text': 'Para 1 ...'}],
                    'materials': [material]},
                   {'blocks': [{'type': 'text', 'id': 'p2', 'role': 'material', 'text': 'Para 2 ...'},
                               {'type': 'text', 'id': 'q21', 'role': 'stem', 'text': '21. What is the passage about?'}],
                    'materials': [material], 'questions': [question]}]
        merged = pdf_batches.merge(self.progress(batches), self.root / 'merged.json')
        self.assertEqual(merged['materials'], [material])
        state = variants.init(self.root / 'merged.json', 'g', ['q21'])
        self.assertEqual(state['status'], 'awaiting_candidates')

    def test_batch_index_must_be_well_formed(self):
        manifest = self.write('pages.json', {'source_sha256': '0' * 64, 'source_page_count': 1,
                                             'selected_pages': [1], 'pages': [{'page': 1}]})
        progress = self.root / 'progress.json'
        pdf_batches.init(manifest, progress, batch_size=1)
        bad = self.write('b1.json', {'batch': 1, 'pages': [1], 'blocks': [{'type': 'text', 'text': 'x'}],
                                     'questions': [{'number': '1'}]})
        with self.assertRaisesRegex(ValueError, 'question_id'):
            pdf_batches.commit(progress, 1, bad)


if __name__ == '__main__':
    unittest.main()
