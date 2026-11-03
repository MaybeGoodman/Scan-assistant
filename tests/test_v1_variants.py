"""V1.0: similar-question ledger, per-candidate verification, bounded retry, isolated delivery."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
from docx_audit import audit  # noqa: E402
from subjects import MODULES  # noqa: E402
from variant_checks import run_check  # noqa: E402
import variants  # noqa: E402


def source_document(module='M05', review='confirmed', marker=False):
    stem = '19．已知函数f(x)=x²-2ax+3。' if not marker else '19．已知函数f(x)=x²-2ax+〔3〕。'
    return {'blocks': [
        {'type': 'text', 'id': 'stem', 'role': 'stem', 'text': stem},
        {'type': 'text', 'id': 's1', 'role': 'subquestion', 'text': '（1）若f(1)=0，求a的值；'},
        {'type': 'text', 'id': 's2', 'role': 'subquestion', 'text': '（2）在（1）的条件下，求f(x)在[0,3]上的最值；'},
        {'type': 'text', 'id': 'ans', 'role': 'answer', 'text': '【答案】（1）a=2；（2）最大值3，最小值-1。'}],
        'questions': [{'question_id': 'q19', 'number': '19', 'module': module, 'blocks': ['stem', 'ans'],
                       'subquestions': [{'subquestion_id': 'a', 'number': '(1)', 'blocks': ['s1']},
                                        {'subquestion_id': 'b', 'number': '(2)', 'blocks': ['s2'], 'depends_on': ['a']}],
                       'review_status': review}]}


def candidate(slot=1, constant=5, a=3, low=-4, high=5, **changes):
    value = {
        'question_id': 'q19', 'slot': slot,
        'variant': {'blocks': [
            {'type': 'text', 'id': 'stem', 'role': 'stem', 'text': f'设二次函数g(x)=x²-2ax+{constant}，a为实数。'},
            {'type': 'text', 'id': 's1', 'role': 'subquestion', 'text': '（1）已知g(1)=0，求a；'},
            {'type': 'text', 'id': 's2', 'role': 'subquestion', 'text': f'（2）当a取（1）中的值时，求g(x)在区间[0,{a + 1}]上的最大值与最小值。'}],
            'stem': ['stem'], 'subquestions': [{'number': '(1)', 'blocks': ['s1']},
                                               {'number': '(2)', 'blocks': ['s2'], 'depends_on': ['(1)']}]},
        'design': {'knowledge_points': ['二次函数'], 'method': '代入求参，配方求最值', 'question_type': '函数综合',
                   'difficulty': 'same', 'difficulty_evidence': '两小问、两步计算',
                   'difference_from_source': '常数项与区间改变', 'difference_from_siblings': f'常数项为{constant}'},
        'internal': {'answers': [{'item': '(1)', 'answer': f'a={a}'}, {'item': '(2)', 'answer': f'最大值{high}，最小值{low}'}],
                     'solution': f'1-2a+{constant}=0，a={a}；顶点x={a}，最小{low}，最大{high}。',
                     'checks': [{'kind': 'substitute', 'item': '(1)', 'equation': f'1-2*a+{constant} = 0', 'vars': {'a': str(a)}},
                                {'kind': 'arith', 'item': '(2)', 'expr': f'{a}**2-2*{a}*{a}+{constant}', 'expect': str(low)},
                                {'kind': 'semantic', 'item': '(1)', 'independent_answer': f'a={a}'},
                                {'kind': 'semantic', 'item': '(2)', 'independent_answer': f'最大值{high}，最小值{low}'}]},
        'review': {'checklist': {key: True for key in MODULES['M05']['checklist']}, 'notes': ['独立复核']}}
    for path, item in changes.items():
        target = value
        keys = path.split('__')
        for key in keys[:-1]:
            target = target[int(key)] if key.isdigit() else target[key]
        target[keys[-1]] = item
    return value


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path

    def init(self, document=None, **options):
        source = self.write('source.json', document or source_document())
        return variants.init(source, options.pop('run_id', 'g1'), ['q19'], **options)['ledger']

    def submit(self, ledger, data, name):
        return variants.submit(ledger, self.write(name, data))['submitted']

    def test_gate_refuses_unconfirmed_draft_or_unknown_module(self):
        with self.assertRaisesRegex(ValueError, '尚未确认'):
            self.init(source_document(review='needs_review'))
        with self.assertRaisesRegex(ValueError, '推断补写'):
            self.init(source_document(marker=True), run_id='g2')
        document = source_document()
        del document['questions'][0]['module']
        with self.assertRaisesRegex(ValueError, '未标注模块'):
            self.init(document, run_id='g3')

    def test_three_passing_variants_deliver_final_student_package(self):
        ledger = self.init()
        for slot, (constant, a, low, high) in enumerate([(5, 3, -4, 5), (7, 4, -9, 7), (9, 5, -16, 9)], 1):
            data = candidate(slot, constant, a, low, high)
            data['variant']['blocks'][0]['text'] = ['设二次函数g(x)=x²-2ax+5，a为实数。',
                                                    '已知抛物线y=x²-2ax+7经过点(1,0)。',
                                                    '函数h(x)=x²-2ax+9的图像与x轴交于点(1,0)。'][slot - 1]
            self.assertEqual(self.submit(ledger, data, f'c{slot}.json')['status'], 'passed')
        self.assertEqual(variants.status(ledger)['status'], 'ready_to_deliver')
        out = self.root / 'student'
        result = variants.deliver(ledger, 'both', out, word_confirmed=True)
        self.assertEqual(result['delivery'], 'final')
        self.assertEqual(sorted(p.name for p in out.iterdir()), ['student-chat.md', 'student.docx'])
        chat = (out / 'student-chat.md').read_text(encoding='utf-8')
        self.assertNotIn('最小值-4', chat)
        self.assertIn('同类题 3', chat)
        self.assertTrue(audit(out / 'student.docx', ['最大值5，最小值-4', '顶点x=3'])['ok'])
        key = Path(result['internal']) / 'answer-key.md'
        self.assertIn('最小值-4', key.read_text(encoding='utf-8'))
        self.assertFalse(key.is_relative_to(out))

    def test_structure_isolation_and_checklist_failures(self):
        ledger = self.init()
        cases = {
            'missing subquestion': candidate(variant__subquestions=[{'number': '(1)', 'blocks': ['s1']}]),
            'lost dependency': candidate(variant__subquestions=[{'number': '(1)', 'blocks': ['s1']},
                                                               {'number': '(2)', 'blocks': ['s2']}]),
            'answer in stem': candidate(variant__blocks__0__text='设g(x)=x²-2ax+5（答案a=3）。'),
            'answer role in variant': candidate(variant__blocks__2__role='answer'),
            'wrong difficulty': candidate(design__difficulty='harder'),
            'checklist false': candidate(review__checklist={**{k: True for k in MODULES['M05']['checklist']},
                                                            'boundary_cases': False}),
            'no deterministic check': candidate(internal__checks=[
                {'kind': 'semantic', 'item': '(1)', 'independent_answer': 'a=3'},
                {'kind': 'semantic', 'item': '(2)', 'independent_answer': '最大值5，最小值-4'}]),
            'subquestion not covered': candidate(internal__checks=[
                {'kind': 'arith', 'item': '(1)', 'expr': '1', 'expect': '1'},
                {'kind': 'semantic', 'item': '(1)', 'independent_answer': 'a=3'}]),
            'independent solve disagrees': candidate(internal__checks=[
                {'kind': 'arith', 'item': '(2)', 'expr': '9-18+5', 'expect': '-4'},
                {'kind': 'semantic', 'item': '(1)', 'independent_answer': 'a=2'},
                {'kind': 'semantic', 'item': '(2)', 'independent_answer': '最大值5，最小值-4'}]),
        }
        target = variants.target_of(variants.load(ledger)[1], 'q19')
        led = variants.load(ledger)[1]
        for name, data in cases.items():
            status, _, failures, _ = variants.verify(data, target, led, [])
            self.assertEqual(status, 'failed', name)
            self.assertTrue(failures, name)
        replica = candidate(variant__blocks=[
            {'type': 'text', 'id': 'stem', 'role': 'stem', 'text': '19．已知函数f(x)=x²-2ax+3。'},
            {'type': 'text', 'id': 's1', 'role': 'subquestion', 'text': '（1）若f(1)=0，求a的值；'},
            {'type': 'text', 'id': 's2', 'role': 'subquestion', 'text': '（2）在（1）的条件下，求f(x)在[0,3]上的最值；'}])
        status, _, failures, _ = variants.verify(replica, target, led, [])
        self.assertTrue(any('复刻' in f for f in failures))

    def test_retry_budget_partial_delivery_and_duplicate(self):
        ledger = self.init(max_attempts=2, count=3)
        good = candidate(1)
        self.assertEqual(self.submit(ledger, good, 'a.json')['status'], 'passed')
        duplicate = candidate(2)
        self.assertIn('近似重复', self.submit(ledger, duplicate, 'b.json')['failures'][0])
        second = candidate(2, 7, 4, -9, 7)
        second['variant']['blocks'][0]['text'] = '已知抛物线y=x²-2ax+7经过点(1,0)。'
        self.assertEqual(self.submit(ledger, second, 'c.json')['status'], 'passed')
        bad = candidate(3, 9, 5, -16, 9, internal__answers=[{'item': '(1)', 'answer': 'a=5'}, {'item': '(2)', 'answer': '错误'}])
        bad['variant']['blocks'][0]['text'] = '函数h(x)=x²-2ax+9的图像与x轴交于点(1,0)。'
        self.assertEqual(self.submit(ledger, bad, 'd.json')['status'], 'failed')
        self.assertEqual(self.submit(ledger, bad, 'e.json')['status'], 'failed')
        with self.assertRaisesRegex(ValueError, '用完重试次数'):
            self.submit(ledger, bad, 'f.json')
        with self.assertRaisesRegex(ValueError, '已通过'):
            self.submit(ledger, candidate(1), 'g.json')
        result = variants.deliver(ledger, 'chat', self.root / 'out')
        self.assertEqual(result['delivery'], 'partial')
        self.assertEqual(result['shortfalls'], ['第19题目标 3 道，验证通过 2 道，缺 1 道'])
        self.assertEqual(result['delivered']['q19'], ['q19-v1-a1', 'q19-v2-a2'])

    def test_tampered_candidate_and_changed_source_are_rejected(self):
        ledger = self.init(count=1)
        self.submit(ledger, candidate(1), 'a.json')
        stored = Path(ledger).parent / 'candidates' / 'q19-v1-a1.json'
        stored.write_text(stored.read_text(encoding='utf-8').replace('a=3', 'a=4'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '被修改'):
            variants.deliver(ledger, 'chat', self.root / 'out')
        (self.root / 'source.json').write_text('{"blocks": []}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '源题文件'):
            variants.status(ledger)

    def test_delivery_requires_word_confirmation_and_separate_folder(self):
        ledger = self.init(count=1)
        self.submit(ledger, candidate(1), 'a.json')
        with self.assertRaisesRegex(ValueError, 'word-confirmed'):
            variants.deliver(ledger, 'docx', self.root / 'out')
        with self.assertRaisesRegex(ValueError, '内部记录'):
            variants.deliver(ledger, 'chat', Path(ledger).parent / 'student')


class SubjectCheckTests(unittest.TestCase):
    def check(self, **check):
        return run_check({'item': '(1)', **check}, {'student_text': 'passagetext', 'answers': {'(1)': 'B'}})['ok']

    def test_eight_modules_have_checklists(self):
        self.assertEqual(sorted(MODULES), [f'M0{i}' for i in range(1, 9)])
        for code, info in MODULES.items():
            self.assertGreaterEqual(len(info['checklist']), 5, code)
            self.assertIn(code, variants.MODULE_KINDS)

    def test_injected_errors_by_subject(self):
        self.assertFalse(self.check(kind='balance', equation='KClO3 -> KCl + O2'))         # chemistry unbalanced
        self.assertFalse(self.check(kind='balance', equation='Fe^3+ + Cu = Fe^2+ + Cu^2+'))  # charge not conserved
        self.assertTrue(self.check(kind='balance', equation='MnO4^- + 5Fe^2+ + 8H^+ = Mn^2+ + 5Fe^3+ + 4H2O'))
        self.assertFalse(self.check(kind='units', expr='U*R', units={'U': 'V', 'R': 'Ohm'}, expect='A'))  # physics unit
        self.assertTrue(self.check(kind='units', expr='m*g*h', units={'m': 'kg', 'g': 'm/s^2', 'h': 'm'}, expect='J'))
        self.assertFalse(self.check(kind='roots', expr='x**2-5*x+6', var='x', claimed=['2']))  # maths missed root
        self.assertFalse(self.check(kind='substitute', equation='2*x+3 = 10', vars={'x': '4'}))
        self.assertFalse(self.check(kind='choice', options={'A': 'a', 'B': 'b'}, answer=['A', 'B']))  # English two keys
        self.assertFalse(self.check(kind='choice', options={'A': 'same', 'B': 'same'}, answer='A'))
        self.assertFalse(self.check(kind='evidence', quote='notinpassage'))
        self.assertFalse(self.check(kind='rubric', criteria=['a', 'b'], satisfied=True))
        self.assertIsNone(run_check({'kind': 'semantic', 'item': '(1)', 'uncertain': True, 'independent_answer': ''},
                                    {'student_text': '', 'answers': {}})['ok'])
        self.assertFalse(self.check(kind='arith', expr='__import__("os")', expect='1'))


if __name__ == '__main__':
    unittest.main()
