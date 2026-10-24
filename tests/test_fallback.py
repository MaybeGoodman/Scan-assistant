"""0.7.0: original-image fallback for failed redraws and photos, placeholder labels."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from docx import Document

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
from test_figures import document, reviews  # noqa: E402
from figure_drawing import sha256  # noqa: E402
from figure_workflow import complete, generate  # noqa: E402
from export_page import export  # noqa: E402
from export_docx import export_docx  # noqa: E402
import pipeline  # noqa: E402


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return Path(path)


def texts(result):
    return [b.get('text') for b in result['blocks'] if b['type'] == 'text' and 'text' in b]


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def three(self):
        """f1 redrawable, f2 critical uncertainty (fails), f3 a main photo."""
        doc = document(self.root, 3)
        figures = doc['figure_task']['figures']
        figures[1]['critical_uncertainty'] = True
        figures[2].update(figure_type='photo')
        return doc

    def run_flow(self, doc, fallback=None):
        ledger = generate(doc, self.root, self.root / 'images', mode='redraw', image_fallback=fallback)
        return complete(ledger, reviews(ledger), self.root)

    def test_default_keeps_placeholder_and_no_longer_drops_photos(self):
        result, ledger = self.run_flow(self.three())
        self.assertEqual([r['state'] for r in ledger['records']], ['validated', 'failed', 'skipped_photo'])
        self.assertIn('[第2张插图：无法可靠重绘]', texts(result))
        self.assertIn('[第3张插图（照片）：未重绘]', texts(result))
        processing = result['figure_processing']
        self.assertEqual(processing['image_fallback'], 'placeholder')
        self.assertEqual(processing['failed_figures'], ['f2'])
        self.assertEqual(processing['skipped_photos'], ['f3'])
        self.assertEqual(processing['fallback_figures'], [])

    def test_original_fallback_keeps_source_crop_for_failures_and_photos(self):
        result, _ = self.run_flow(self.three(), 'original')
        images = [b for b in result['blocks'] if b['type'] == 'image']
        self.assertEqual(len(images), 3)
        self.assertIn('redraw', images[0])
        digest = sha256(self.root / 'source.png')
        self.assertEqual(images[1]['fallback'], {'reason': 'failed', 'source_sha256': digest})
        self.assertEqual(images[2]['fallback'], {'reason': 'photo', 'source_sha256': digest})
        self.assertEqual(images[1]['path'], 'source.png')
        self.assertFalse(any('无法可靠重绘' in (t or '') or '未重绘' in (t or '') for t in texts(result)))
        self.assertEqual(result['figure_processing']['fallback_figures'], ['f2', 'f3'])
        write(self.root / 'final.json', result)
        export(self.root / 'final.json', self.root / 'html')
        html = (self.root / 'html/result.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('<img'), 3)
        self.assertNotIn('fallback', html)
        word = Document(export_docx(self.root / 'final.json', self.root / 'out.docx', word_confirmed=True))
        self.assertEqual(len(word.inline_shapes), 3)

    def test_changed_original_falls_back_to_placeholder_with_reason(self):
        doc = self.three()
        ledger = generate(doc, self.root, self.root / 'images', mode='redraw', image_fallback='original')
        ledger['records'][1]['source_sha256'] = '0' * 64  # simulate the crop changing after generation
        result, _ = complete(ledger, reviews(ledger), self.root)
        self.assertIn('[第2张插图：无法可靠重绘]', texts(result))
        self.assertIn('f2', result['figure_processing']['fallback_errors'])
        self.assertEqual(result['figure_processing']['fallback_figures'], ['f3'])

    def test_exporters_reject_changed_or_malformed_fallback(self):
        result, _ = self.run_flow(self.three(), 'original')
        tampered = deepcopy(result)
        next(b for b in tampered['blocks'] if 'fallback' in b)['fallback']['source_sha256'] = 'a' * 64
        write(self.root / 'bad.json', tampered)
        with self.assertRaisesRegex(ValueError, '哈希不一致'):
            export(self.root / 'bad.json', self.root / 'bad-html')
        malformed = deepcopy(result)
        next(b for b in malformed['blocks'] if 'fallback' in b)['fallback']['reason'] = 'other'
        write(self.root / 'bad2.json', malformed)
        with self.assertRaisesRegex(ValueError, 'fallback'):
            export_docx(self.root / 'bad2.json', self.root / 'bad.docx', word_confirmed=True)

    def test_fallback_only_for_redraw_and_fixed_across_retry(self):
        doc = document(self.root)
        for mode in ('ignore', 'preserve'):
            with self.assertRaisesRegex(ValueError, 'redraw'):
                generate(doc, self.root, self.root / 'images', mode=mode, image_fallback='original')
        with self.assertRaises(ValueError):
            generate(doc, self.root, self.root / 'images', mode='redraw', image_fallback='keep')
        ledger = generate(doc, self.root, self.root / 'images', mode='redraw')
        _, reviewed = complete(ledger, reviews(ledger, 'major_issue', checks={'labels': False, **{
            k: True for k in reviews(ledger)['reviews'][0]['checks'] if k != 'labels'}}), self.root)
        self.assertEqual(reviewed['status'], 'needs_retry')
        with self.assertRaisesRegex(ValueError, 'image_fallback'):
            generate(doc, self.root, self.root / 'images', mode='redraw', previous=reviewed, image_fallback='original')

    def test_placeholder_label_and_visible_ordinal(self):
        doc = document(self.root, 3)
        figures = doc['figure_task']['figures']
        figures[0].update(figure_type='watermark', relation='unrelated')  # ignored, invisible
        figures[1]['critical_uncertainty'] = True
        figures[2].update(critical_uncertainty=True, placeholder_label='第27题丙图')
        result, _ = self.run_flow(doc)
        self.assertIn('[第1张插图：无法可靠重绘]', texts(result))  # was 第2张 in 0.6.0
        self.assertIn('[第27题丙图：无法可靠重绘]', texts(result))

    def test_invalid_placeholder_label_is_rejected(self):
        for bad in ('', '图[1]', 'a\nb', 'x' * 21, 3):
            doc = document(self.root)
            doc['figure_task']['figures'][0]['placeholder_label'] = bad
            with self.assertRaisesRegex(ValueError, 'placeholder_label'):
                generate(doc, self.root, self.root / 'images', mode='redraw')

    def test_simple_schematic_photo_is_still_redrawn(self):
        doc = document(self.root)
        doc['figure_task']['figures'][0].update(figure_type='photo', simple_schematic=True)
        ledger = generate(doc, self.root, self.root / 'images', mode='redraw', image_fallback='original')
        self.assertEqual(ledger['records'][0]['state'], 'awaiting_validation')

    def test_unrelated_photo_is_still_ignored(self):
        doc = document(self.root, 2)
        doc['figure_task']['figures'][1].update(figure_type='photo', relation='unrelated')
        result, ledger = self.run_flow(doc, 'original')
        self.assertEqual(ledger['records'][1]['state'], 'ignored')
        self.assertEqual(sum(b['type'] == 'image' for b in result['blocks']), 1)

    def test_pipeline_passes_fallback_choice(self):
        source = write(self.root / 'candidates.json', self.three())
        with self.assertRaisesRegex(ValueError, 'redraw'):
            pipeline.run_command(source, 'r0', source=self.root / 'source.png', image_mode='ignore',
                                 image_fallback='original', fmt='html', output=self.root / 'out0')
        state = pipeline.run_command(source, 'r1', source=self.root / 'source.png', image_mode='redraw',
                                     image_fallback='original', fmt='html', output=self.root / 'out')
        self.assertEqual(state['status'], 'awaiting_review')
        template = json.loads((self.root / state['files']['review_template']).read_text(encoding='utf-8'))
        self.assertEqual([row['figure_id'] for row in template['reviews']], ['f1'])
        for row in template['reviews']:
            row.update(status='pass', notes=['已对照'], checks={k: True for k in row['checks']})
        write(self.root / state['files']['reviews'], template)
        state = pipeline.review_command(self.root / 'r1-work/r1.state.json', self.root / state['files']['reviews'])
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['fallback_figures'], ['f2', 'f3'])
        self.assertEqual(state['skipped_photos'], ['f3'])
        self.assertEqual((self.root / 'out/result.html').read_text(encoding='utf-8').count('<img'), 3)


if __name__ == '__main__':
    unittest.main()
