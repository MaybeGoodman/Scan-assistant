"""0.7.0: enforced batching for long PDFs, per-figure files, drawing-only retry and resume."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from docx import Document
from PIL import Image

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
from test_figures import document  # noqa: E402
from test_pdf_batches import make_pdf  # noqa: E402
from test_pipeline import fill, read, write  # noqa: E402
from prepare_pdf import prepare  # noqa: E402
from pdf_batches import commit, init, merge  # noqa: E402
import pipeline  # noqa: E402


def tree_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob('*')) if p.is_file()}


class EnforcedBatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def batched(self, pages=7):
        pdf = self.root / 'exam.pdf'
        make_pdf(pdf, pages)
        prepare(pdf, self.root / 'pages', 72)
        state = init(self.root / 'pages/pages.json', self.root / 'progress.json', batch_size=5)
        for entry in state['batches']:
            blocks = [{'type': 'text', 'id': f'p{p}-1', 'text': f'第{p}页正文'} for p in entry['pages']]
            path = write(self.root / f'batch-{entry["batch"]:02d}.json',
                         {'batch': entry['batch'], 'pages': entry['pages'], 'blocks': blocks})
            commit(self.root / 'progress.json', entry['batch'], path)
        merge(self.root / 'progress.json', self.root / 'candidates.json')
        return pdf, self.root / 'candidates.json'

    def run_text(self, candidates, source, run_id='r1', **kwargs):
        return pipeline.run_command(candidates, run_id, source=source, fmt='html',
                                    output=self.root / f'out-{run_id}', **kwargs)

    def test_long_pdf_without_batches_is_refused_before_any_output(self):
        pdf = self.root / 'exam.pdf'
        make_pdf(pdf, 7)
        candidates = write(self.root / 'candidates.json', {'blocks': [{'type': 'text', 'text': '正文'}]})
        with self.assertRaisesRegex(ValueError, '共 7 页.*pdf_batches'):
            self.run_text(candidates, pdf)
        self.assertFalse((self.root / 'r1-work').exists())

    def test_batched_long_pdf_passes_and_provenance_stays_internal(self):
        pdf, candidates = self.batched()
        self.assertEqual(read(candidates)['provenance']['selected_pages'], list(range(1, 8)))
        state = self.run_text(candidates, pdf)
        self.assertEqual(state['status'], 'completed')
        saved = read(self.root / 'r1-work/r1.state.json')['inputs']
        self.assertEqual((saved['progress'], saved['selected_pages']), ('progress.json', list(range(1, 8))))
        html = (self.root / 'out-r1/result.html').read_text(encoding='utf-8')
        self.assertIn('第7页正文', html)
        for leak in ('pdf_batches', 'progress', 'provenance'):
            self.assertNotIn(leak, html)
        word = pipeline.run_command(candidates, 'r2', source=pdf, fmt='docx', word_confirmed=True,
                                    output=self.root / 'out.docx')
        self.assertEqual(word['status'], 'completed')
        text = '\n'.join(p.text for p in Document(self.root / 'out.docx').paragraphs)
        self.assertNotIn('pdf_batches', text)

    def test_tampered_progress_source_or_unfinished_batches_are_refused(self):
        pdf, candidates = self.batched()
        progress = self.root / 'progress.json'
        original = progress.read_text(encoding='utf-8')
        progress.write_text(original + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '进度文件'):
            self.run_text(candidates, pdf, 'a')
        progress.write_text(original, encoding='utf-8')
        other = self.root / 'other.pdf'
        make_pdf(other, 8)
        with self.assertRaisesRegex(ValueError, '哈希不一致'):
            self.run_text(candidates, other, 'b')
        ledger = json.loads(original)
        ledger['batches'][-1]['status'] = 'pending'
        write(progress, ledger)
        data = read(candidates)
        data['provenance']['progress_sha256'] = hashlib.sha256(progress.read_bytes()).hexdigest()
        write(candidates, data)
        with self.assertRaisesRegex(ValueError, '未完成批次'):
            self.run_text(candidates, pdf, 'c')

    def test_short_pdf_and_images_do_not_need_batches(self):
        pdf = self.root / 'short.pdf'
        make_pdf(pdf, 5)
        candidates = write(self.root / 'candidates.json', {'blocks': [{'type': 'text', 'text': '正文'}]})
        self.assertEqual(self.run_text(candidates, pdf, 'a')['status'], 'completed')
        image = self.root / 'photo.jpg'
        Image.new('RGB', (40, 30), 'white').save(image)
        self.assertEqual(self.run_text(candidates, image, 'b')['status'], 'completed')

    def test_missing_unsupported_or_mismatched_source_is_refused(self):
        _, candidates = self.batched()
        image = self.root / 'scan.png'
        Image.new('RGB', (40, 30), 'white').save(image)
        with self.assertRaisesRegex(ValueError, '图片'):
            self.run_text(candidates, image, 'a')
        with self.assertRaisesRegex(ValueError, '--source'):
            self.run_text(candidates, None, 'b')
        (self.root / 'notes.txt').write_text('x', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'PDF 或图片'):
            self.run_text(candidates, self.root / 'notes.txt', 'c')

    def test_cli_requires_source(self):
        candidates = write(self.root / 'candidates.json', {'blocks': [{'type': 'text', 'text': '正文'}]})
        done = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'pipeline.py'), 'run', str(candidates),
                               '--run-id', 'r1', '--format', 'html', '--output', str(self.root / 'out')],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 2)
        self.assertIn('--source', done.stderr)


class FigureFileAndRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scan = self.root / 'scan.png'
        Image.new('RGB', (40, 30), 'white').save(self.scan)

    def split(self):
        """Move each figure's understanding/drawing into its own file, as a host would while working."""
        inline = document(self.root)
        doc = deepcopy(inline)
        (self.root / 'figures').mkdir()
        for figure in doc['figure_task']['figures']:
            data = {k: figure.pop(k) for k in ('understanding', 'redrawable', 'critical_uncertainty', 'drawing')}
            write(self.root / 'figures' / f'{figure["figure_id"]}.json', data)
            figure['figure_file'] = f'figures/{figure["figure_id"]}.json'
        return inline, doc

    def start(self, doc, run_id='r1'):
        return pipeline.run_command(write(self.root / 'candidates.json', doc), run_id, source=self.scan,
                                    image_mode='redraw', fmt='html', output=self.root / f'out-{run_id}')

    def test_figure_file_is_inlined_like_the_0_6_0_structure(self):
        inline, doc = self.split()
        state = self.start(doc)
        self.assertEqual(state['status'], 'awaiting_review')
        source = read(self.root / 'r1.figure-source.json')
        self.assertEqual(source['figure_task']['figures'], inline['figure_task']['figures'])
        recorded = read(self.root / 'r1-work/r1.state.json')['files']['figure_files']
        self.assertEqual(recorded['f1']['path'], 'figures/f1.json')
        state = pipeline.review_command(self.root / 'r1-work/r1.state.json', fill(state))
        self.assertEqual(state['status'], 'completed')

    def test_figure_file_conflicts_and_escapes_are_refused(self):
        _, doc = self.split()
        doc['figure_task']['figures'][0]['redrawable'] = True
        with self.assertRaisesRegex(ValueError, '同时出现'):
            self.start(doc, 'a')
        doc['figure_task']['figures'][0].pop('redrawable')
        doc['figure_task']['figures'][0]['figure_file'] = '../outside.json'
        with self.assertRaises(ValueError):
            self.start(doc, 'b')
        write(self.root / 'figures/bad.json', {'drawing': {}, 'figure_type': 'photo'})
        doc['figure_task']['figures'][0]['figure_file'] = 'figures/bad.json'
        with self.assertRaisesRegex(ValueError, 'figure_file 只能包含'):
            self.start(doc, 'c')

    def needs_retry(self):
        state = self.start(document(self.root))
        state_path = self.root / 'r1-work/r1.state.json'
        state = pipeline.review_command(state_path, fill(state, 'major_issue', labels=False))
        self.assertEqual(state['needs_retry'], ['f1'])
        self.assertIn('--drawing', state['next_action'])
        return state_path, state

    def test_drawing_only_retry_changes_nothing_else(self):
        state_path, state = self.needs_retry()
        before = read(self.root / state['files']['figure_source'])
        drawing = deepcopy(before['figure_task']['figures'][0]['drawing'])
        drawing['scene']['elements'][0]['width'] = 90
        path = write(self.root / 'f1.a2.json', {'drawing': drawing})
        state = pipeline.retry_command(state_path, drawings={'f1': path})
        self.assertEqual((state['status'], state['attempt']), ('awaiting_review', 2))
        after = read(self.root / 'r1.figure-source.a2.json')
        self.assertEqual(after['figure_task']['figures'][0]['drawing'], drawing)
        after['figure_task']['figures'][0]['drawing'] = before['figure_task']['figures'][0]['drawing']
        self.assertEqual(after, before)
        self.assertEqual(pipeline.review_command(state_path, fill(state))['status'], 'completed')

    def test_drawing_retry_rejects_wrong_figures_or_content(self):
        state_path, state = self.needs_retry()
        drawing = read(self.root / state['files']['figure_source'])['figure_task']['figures'][0]['drawing']
        good = write(self.root / 'good.json', {'drawing': drawing})
        cases = [({'f9': good}, '不在 needs_retry'),
                 ({'f1': write(self.root / 'extra.json', {'drawing': drawing, 'understanding': {}})}, '只能包含'),
                 ({'f1': self.root.parent / 'elsewhere.json'}, '目录内')]
        for drawings, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                pipeline.retry_command(state_path, drawings=drawings)
            self.assertEqual(read(state_path)['status'], 'needs_retry')
        with self.assertRaisesRegex(ValueError, '二选一'):
            pipeline.retry_command(state_path, good, {'f1': good})
        with self.assertRaisesRegex(ValueError, '二选一'):
            pipeline.retry_command(state_path)
        with self.assertRaisesRegex(ValueError, '格式'):
            pipeline.parse_drawings(['f1'])

    def test_cli_drawing_retry(self):
        state_path, state = self.needs_retry()
        drawing = read(self.root / state['files']['figure_source'])['figure_task']['figures'][0]['drawing']
        path = write(self.root / 'f1.fix.json', {'drawing': drawing})
        done = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'pipeline.py'), 'retry', '--state',
                               str(state_path), '--drawing', f'f1={path}'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout)['status'], 'awaiting_review')


class ResumeTests(unittest.TestCase):
    def test_resume_lists_runs_and_batches_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scan = root / 'scan.png'
            Image.new('RGB', (40, 30), 'white').save(scan)
            text = write(root / 'text.json', {'blocks': [{'type': 'text', 'text': '正文'}]})
            pipeline.run_command(text, 'done', source=scan, fmt='html', output=root / 'out-done')
            pipeline.run_command(write(root / 'candidates.json', document(root)), 'wait', source=scan,
                                 image_mode='redraw', fmt='html', output=root / 'out-wait')
            sub = root / 'long'
            sub.mkdir()
            make_pdf(sub / 'exam.pdf', 7)
            prepare(sub / 'exam.pdf', sub / 'pages', 72)
            init(sub / 'pages/pages.json', sub / 'progress.json', batch_size=5)
            commit(sub / 'progress.json', 1, write(sub / 'batch-01.json', {
                'batch': 1, 'pages': [1, 2, 3, 4, 5], 'blocks': [{'type': 'text', 'text': '第1批'}]}))
            before = tree_hashes(root)
            result = pipeline.resume(root)
            self.assertEqual(tree_hashes(root), before)
            self.assertEqual([(r['run_id'], r['status']) for r in result['runs']],
                             [('wait', 'awaiting_review'), ('done', 'completed')])
            self.assertIn('pipeline.py review', result['runs'][0]['next_action'])
            batch = result['batches'][0]
            self.assertEqual((batch['done_pages'], batch['total_pages'], batch['complete']), (5, 7, False))
            self.assertEqual(batch['next_batch'], {'batch': 2, 'pages': [6, 7]})
            done = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'pipeline.py'), 'resume', str(root)],
                                  capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads(done.stdout)['batches'][0]['next_batch']['batch'], 2)
            self.assertEqual(tree_hashes(root), before)


if __name__ == '__main__':
    unittest.main()
