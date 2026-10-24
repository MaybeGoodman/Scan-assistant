"""Combined pre-start confirmation parsing (0.6.0)."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
from confirmation import parse  # noqa: E402

BOTH = ['word', 'image']


class CombinedReplyTests(unittest.TestCase):
    def check(self, response, ask, word, image, ambiguous=()):
        result = parse(response, ask)
        self.assertEqual((result['word'], result['image_mode'], result['ambiguous']), (word, image, list(ambiguous)), response)

    def test_numbered_answers(self):
        self.check('1A 2A', BOTH, True, 'redraw')
        self.check('1b，2c', BOTH, False, 'preserve')
        self.check('１Ａ、２Ｂ', BOTH, True, 'ignore')
        self.check('1-A；2.C', BOTH, True, 'preserve')
        self.check('1：b 2：a', BOTH, False, 'redraw')

    def test_keyword_answers(self):
        self.check('Word，重绘', BOTH, True, 'redraw')
        self.check('不要word，图片也不要', BOTH, False, 'ignore')
        self.check('直接输出提取内容，保留原图', BOTH, False, 'preserve')
        self.check('好的，生成 Word，图片也重新画出来', BOTH, True, 'redraw')
        self.check('docx，只要文字', BOTH, True, 'ignore')

    def test_option_labels_from_choice_tools(self):
        self.check('生成 Word（.docx）', ['word'], True, None)
        self.check('直接输出提取内容', ['word'], False, None)
        self.check('重新绘制插图', ['image'], None, 'redraw')
        self.check('不要图片', ['image'], None, 'ignore')
        self.check('保留原图', ['image'], None, 'preserve')

    def test_generic_reply_to_two_questions_is_ambiguous(self):
        for reply in ('好的', '是', '可以', '嗯嗯'):
            self.check(reply, BOTH, None, None, BOTH)
        self.check('是，图不要', BOTH, None, 'ignore', ['word'])

    def test_conflicts_are_ambiguous(self):
        self.check('1A 1B 2A', BOTH, None, 'redraw', ['word'])
        self.check('Word，不要word', BOTH, None, None, BOTH)
        self.check('2E 1A', BOTH, True, None, ['image'])  # 0.7.0: D is a valid option, E is not
        self.check('随便', BOTH, None, None, BOTH)

    def test_single_question_reuses_existing_rules(self):
        self.check('是', ['image'], None, 'redraw')
        self.check('不用了', ['image'], None, 'ignore')
        self.check('不用重绘，原图保留', ['image'], None, 'preserve')
        self.check('可以', ['word'], True, None)
        self.check('不要', ['word'], False, None)
        self.check('A', ['image'], None, 'redraw')
        self.check('b', ['word'], False, None)
        self.check('都行', ['image'], None, None, ['image'])

    def test_unasked_items_raise(self):
        with self.assertRaises(ValueError):
            parse('2A', ['word'])
        with self.assertRaises(ValueError):
            parse('Word', ['image'])
        with self.assertRaises(ValueError):
            parse('1A', ['pdf'])

    def test_cli_exit_codes(self):
        def run(response, ask='word,image'):
            done = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'confirmation.py'), 'parse',
                                   '--ask', ask, '--response', response], capture_output=True, text=True, encoding='utf-8')
            return done.returncode, json.loads(done.stdout)
        self.assertEqual(run('1A 2C'), (0, {'word': True, 'image_mode': 'preserve', 'image_fallback': None,
                                            'ambiguous': []}))
        self.assertEqual(run('好的')[0], 2)
        self.assertEqual(run('2A', 'word')[0], 1)


class FallbackReplyTests(unittest.TestCase):
    """0.7.0 option D: redraw, keeping the original crop for failed figures and photos."""

    def fallback(self, response, ask=BOTH):
        result = parse(response, ask)
        return result['word'], result['image_mode'], result['image_fallback'], result['ambiguous']

    def test_option_d_and_explicit_wording(self):
        self.assertEqual(self.fallback('1A 2D'), (True, 'redraw', 'original', []))
        self.assertEqual(self.fallback('Word，重绘，失败保留原图'), (True, 'redraw', 'original', []))
        self.assertEqual(self.fallback('重新绘制，失败或照片时保留原图', ['image']), (None, 'redraw', 'original', []))
        self.assertEqual(self.fallback('D', ['image']), (None, 'redraw', 'original', []))

    def test_existing_letters_keep_their_meaning(self):
        self.assertEqual(self.fallback('1A 2A'), (True, 'redraw', 'placeholder', []))
        self.assertEqual(self.fallback('1B 2B'), (False, 'ignore', None, []))
        self.assertEqual(self.fallback('保留原图', ['image']), (None, 'preserve', None, []))
        self.assertEqual(self.fallback('重新绘制插图（失败处留占位）', ['image']), (None, 'redraw', 'placeholder', []))

    def test_generic_reply_is_still_ambiguous(self):
        self.assertEqual(self.fallback('好的'), (None, None, None, BOTH))


if __name__ == '__main__':
    unittest.main()
