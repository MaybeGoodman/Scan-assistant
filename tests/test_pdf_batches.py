"""Page ranges, region rendering and batch progress ledger for long PDFs (0.6.0)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image
from reportlab.pdfgen import canvas

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
from prepare_pdf import parse_pages, prepare  # noqa: E402
from render_pdf_region import render_region  # noqa: E402
from pdf_batches import commit, init, merge, status  # noqa: E402
from figure_workflow import plan  # noqa: E402
from select_content import select_file  # noqa: E402
from export_page import export  # noqa: E402


def make_pdf(path, pages):
    pdf = canvas.Canvas(str(path))
    for number in range(1, pages + 1):
        pdf.drawString(70, 700, f'PAGE {number}')
        pdf.showPage()
    pdf.save()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return Path(path)


class PageRangeTests(unittest.TestCase):
    def test_parse_pages_sorts_and_deduplicates(self):
        self.assertEqual(parse_pages('3-5,8,4', 10), [3, 4, 5, 8])
        self.assertEqual(parse_pages(' 2 , 2-3 ', 3), [2, 3])

    def test_parse_pages_rejects_invalid(self):
        for spec in ('0', '5-3', '11', 'a', '', '1,,2', '1-2-3', '-2'):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                parse_pages(spec, 10)

    def test_selected_pages_keep_original_numbers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_pdf(root / 'source.pdf', 10)
            result = prepare(root / 'source.pdf', root / 'pages', 72, pages=[2, 4])
            self.assertEqual(sorted(p.name for p in (root / 'pages').glob('*.png')),
                             ['page-0002.png', 'page-0004.png'])
            self.assertEqual(result['selected_pages'], [2, 4])
            self.assertEqual(result['source_page_count'], 10)
            self.assertEqual(result['page_count'], 2)
            self.assertIn('PAGE 4', result['pages'][1]['text_candidate'])
            with Image.open(root / 'pages/page-0002.png') as image:
                self.assertEqual(image.size, (result['pages'][0]['width'], result['pages'][0]['height']))
            self.assertEqual(len(result['source_sha256']), 64)

    def test_default_all_pages_at_200_dpi(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_pdf(root / 'source.pdf', 2)
            result = prepare(root / 'source.pdf', root / 'pages')
            self.assertEqual(result['dpi'], 200)
            self.assertEqual([p['page'] for p in result['pages']], [1, 2])
            self.assertEqual(result['selected_pages'], [1, 2])

    def test_dpi_bounds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_pdf(root / 'source.pdf', 1)
            for dpi in (71, 401):
                with self.subTest(dpi=dpi), self.assertRaises(ValueError):
                    prepare(root / 'source.pdf', root / f'pages-{dpi}', dpi)
            self.assertEqual(prepare(root / 'source.pdf', root / 'ok', 400)['dpi'], 400)

    def test_cli_pages_argument(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_pdf(root / 'source.pdf', 3)
            done = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'prepare_pdf.py'), str(root / 'source.pdf'),
                                   '--output-dir', str(root / 'pages'), '--dpi', '72', '--pages', '3'],
                                  capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(done.returncode, 0, done.stderr)
            manifest = json.loads((root / 'pages/pages.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['selected_pages'], [3])
            bad = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'prepare_pdf.py'), str(root / 'source.pdf'),
                                  '--output-dir', str(root / 'bad'), '--pages', '4'],
                                 capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('超出总页数 3', bad.stderr)


class RegionTests(unittest.TestCase):
    def test_region_doubles_resolution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_pdf(root / 'source.pdf', 2)
            target = render_region(root / 'source.pdf', 2, (100, 200, 300, 260), 200, 400, root / 'zoom.png')
            with Image.open(target) as image:
                self.assertLessEqual(abs(image.width - 400), 1)
                self.assertLessEqual(abs(image.height - 120), 1)
            with self.assertRaises(FileExistsError):
                render_region(root / 'source.pdf', 2, (100, 200, 300, 260), 200, 400, root / 'zoom.png')

    def test_region_rejects_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_pdf(root / 'source.pdf', 1)
            cases = [dict(page=2, box=(0, 0, 10, 10), base=200, dpi=400),
                     dict(page=1, box=(10, 10, 10, 20), base=200, dpi=400),
                     dict(page=1, box=(0, 0, 10, 10), base=400, dpi=200),
                     dict(page=1, box=(0, 0, 10, 10), base=200, dpi=700),
                     dict(page=1, box=(0, 0, 99999, 10), base=200, dpi=400)]
            for index, case in enumerate(cases):
                with self.subTest(case=case), self.assertRaises(ValueError):
                    render_region(root / 'source.pdf', case['page'], case['box'], case['base'], case['dpi'],
                                  root / f'z{index}.png')


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_pdf(self.root / 'source.pdf', 6)
        prepare(self.root / 'source.pdf', self.root / 'pdf-pages', 72)
        self.progress = self.root / 'progress.json'
        init(self.root / 'pdf-pages/pages.json', self.progress, batch_size=5)

    def tearDown(self):
        self.temp.cleanup()

    def batch(self, number, pages, blocks, figures=None, name=None):
        value = {'batch': number, 'pages': pages, 'blocks': blocks}
        if figures is not None:
            value['figures'] = figures
        return write(self.root / (name or f'batch-{number:02d}.json'), value)

    def snapshot(self):
        return self.progress.read_text(encoding='utf-8')

    def test_init_splits_batches(self):
        state = json.loads(self.snapshot())
        self.assertEqual([b['pages'] for b in state['batches']], [[1, 2, 3, 4, 5], [6]])
        self.assertEqual(state['pages_manifest'], 'pdf-pages/pages.json')
        self.assertEqual(status(self.progress)['next_batch'], {'batch': 1, 'pages': [1, 2, 3, 4, 5]})
        with self.assertRaises(FileExistsError):
            init(self.root / 'pdf-pages/pages.json', self.progress)
        with self.assertRaises(ValueError):
            init(self.root / 'pdf-pages/pages.json', self.root / 'p2.json', batch_size=21)

    def test_commit_rejections_leave_progress_unchanged(self):
        before = self.snapshot()
        wrong_pages = self.batch(1, [1, 2], [{'type': 'text', 'text': 'x'}], name='wrong.json')
        bad_figure = self.batch(2, [6], [{'type': 'text', 'id': 'p6-1', 'text': 'x'},
                                         {'type': 'image', 'figure_id': 'f1', 'path': 'f1.png'}],
                                [{'figure_id': 'f1', 'source_page': 1}], name='badfig.json')
        unmatched = self.batch(2, [6], [{'type': 'text', 'text': 'x'},
                                        {'type': 'image', 'figure_id': 'f1', 'path': 'f1.png'}], name='unmatched.json')
        late_join = self.batch(2, [6], [{'type': 'text', 'text': 'a'}, {'type': 'text', 'text': 'b', 'join_previous': True}],
                               name='late.json')
        first_join = self.batch(1, [1, 2, 3, 4, 5], [{'type': 'text', 'text': 'a', 'join_previous': True}], name='first.json')
        for number, path in ((1, wrong_pages), (2, bad_figure), (2, unmatched), (2, late_join), (1, first_join), (9, wrong_pages)):
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                commit(self.progress, number, path)
            self.assertEqual(self.snapshot(), before)
        good = self.batch(1, [1, 2, 3, 4, 5], [{'type': 'text', 'text': 'x'}])
        commit(self.progress, 1, good)
        after = self.snapshot()
        with self.assertRaises(ValueError):
            commit(self.progress, 1, good)
        self.assertEqual(self.snapshot(), after)
        self.assertFalse((self.root / 'progress.json.tmp').exists())

    def test_commit_rejects_file_outside_progress_directory(self):
        with tempfile.TemporaryDirectory() as other:
            outside = write(Path(other) / 'b.json', {'batch': 1, 'pages': [1, 2, 3, 4, 5], 'blocks': [{'type': 'text', 'text': 'x'}]})
            with self.assertRaises(ValueError):
                commit(self.progress, 1, outside)

    def test_merge_requires_all_batches(self):
        commit(self.progress, 1, self.batch(1, [1, 2, 3, 4, 5], [{'type': 'text', 'text': 'x'}]))
        with self.assertRaises(ValueError):
            merge(self.progress, self.root / 'candidates.json')
        self.assertFalse((self.root / 'candidates.json').exists())
        self.assertEqual(status(self.progress)['next_batch'], {'batch': 2, 'pages': [6]})

    def test_merge_detects_modified_batch_file(self):
        first = self.batch(1, [1, 2, 3, 4, 5], [{'type': 'text', 'text': 'x'}])
        commit(self.progress, 1, first)
        commit(self.progress, 2, self.batch(2, [6], [{'type': 'text', 'text': 'y'}]))
        write(first, {'batch': 1, 'pages': [1, 2, 3, 4, 5], 'blocks': [{'type': 'text', 'text': 'changed'}]})
        with self.assertRaisesRegex(ValueError, '被修改'):
            merge(self.progress, self.root / 'candidates.json')

    def test_join_previous_concatenates_runs(self):
        commit(self.progress, 1, self.batch(1, [1, 2, 3, 4, 5], [
            {'type': 'text', 'id': 'p5-1', 'text': '已知电阻 ', 'layout': {'keep_with_next': True}}]))
        commit(self.progress, 2, self.batch(2, [6], [
            {'type': 'text', 'join_previous': True, 'runs': [{'type': 'math', 'latex': 'R_0'}, {'type': 'text', 'text': ' 不变。'}]},
            {'type': 'text', 'id': 'p6-1', 'text': '下一题'}]))
        result = merge(self.progress, self.root / 'candidates.json')
        first = result['blocks'][0]
        self.assertEqual(first['id'], 'p5-1')
        self.assertEqual(first['layout'], {'keep_with_next': True})
        self.assertNotIn('text', first)
        self.assertEqual(first['runs'], [{'type': 'text', 'text': '已知电阻 '}, {'type': 'math', 'latex': 'R_0'},
                                         {'type': 'text', 'text': ' 不变。'}])
        self.assertNotIn('join_previous', json.dumps(result))
        self.assertEqual(len(result['blocks']), 2)
        self.assertNotIn('figure_task', result)

    def test_join_previous_requires_text_blocks(self):
        commit(self.progress, 1, self.batch(1, [1, 2, 3, 4, 5], [
            {'type': 'table', 'rows': 1, 'cols': 1, 'cells': [{'row': 0, 'col': 0, 'text': 'a'}]}]))
        commit(self.progress, 2, self.batch(2, [6], [{'type': 'text', 'text': 'b', 'join_previous': True}]))
        with self.assertRaisesRegex(ValueError, 'join_previous'):
            merge(self.progress, self.root / 'candidates.json')

    def test_join_previous_selection_conflict(self):
        commit(self.progress, 1, self.batch(1, [1, 2, 3, 4, 5], [
            {'type': 'text', 'text': 'a', 'selection': {'category': 'MAIN_CONTENT', 'relation': 'main', 'certainty': 'high', 'reason': 'x'}}]))
        commit(self.progress, 2, self.batch(2, [6], [
            {'type': 'text', 'text': 'b', 'join_previous': True,
             'selection': {'category': 'UNKNOWN', 'relation': 'unknown', 'certainty': 'uncertain', 'reason': 'y'}}]))
        with self.assertRaisesRegex(ValueError, 'selection'):
            merge(self.progress, self.root / 'candidates.json')

    def test_duplicate_ids_rejected(self):
        commit(self.progress, 1, self.batch(1, [1, 2, 3, 4, 5], [{'type': 'text', 'id': 'q1', 'text': 'a'}]))
        commit(self.progress, 2, self.batch(2, [6], [{'type': 'text', 'id': 'q1', 'text': 'b'}]))
        with self.assertRaisesRegex(ValueError, 'q1'):
            merge(self.progress, self.root / 'candidates.json')

    def test_merged_figures_pass_figure_workflow(self):
        def figure(fid, page, parent):
            return {'figure_id': fid, 'source_page': page, 'source_bbox': [0, 0, 10, 10], 'source_path': f'{fid}.png',
                    'parent_block_id': parent, 'figure_type': 'circuit', 'relation': 'main'}
        commit(self.progress, 1, self.batch(1, [1, 2, 3, 4, 5], [
            {'type': 'text', 'id': 'p2-1', 'text': '1．如图。'}, {'type': 'image', 'figure_id': 'f1', 'path': 'f1.png'}],
            [figure('f1', 2, 'p2-1')]))
        commit(self.progress, 2, self.batch(2, [6], [
            {'type': 'text', 'id': 'p6-1', 'text': '2．如图。'}, {'type': 'image', 'figure_id': 'f2', 'path': 'f2.png'}],
            [figure('f2', 6, 'p6-1')]))
        result = merge(self.progress, self.root / 'candidates.json')
        task = result['figure_task']
        self.assertEqual((task['page_count'], task['scan_complete']), (6, True))
        self.assertEqual([f['figure_id'] for f in task['figures']], ['f1', 'f2'])
        decision = plan(result)
        self.assertEqual(decision['status'], 'awaiting_confirmation')
        self.assertEqual(decision['figure_ids'], ['f1', 'f2'])

    def test_merge_output_must_be_beside_progress(self):
        commit(self.progress, 1, self.batch(1, [1, 2, 3, 4, 5], [{'type': 'text', 'text': 'a'}]))
        commit(self.progress, 2, self.batch(2, [6], [{'type': 'text', 'text': 'b'}]))
        with self.assertRaises(ValueError):
            merge(self.progress, self.root / 'sub/candidates.json')

    def test_merged_candidates_export_end_to_end(self):
        ad = {'category': 'ADVERTISEMENT', 'relation': 'unrelated', 'certainty': 'high', 'reason': '页脚推广'}
        commit(self.progress, 1, self.batch(1, [1, 2, 3, 4, 5], [
            {'type': 'text', 'id': 'p1-1', 'text': '第一页正文'}, {'type': 'text', 'text': '扫码领资料', 'selection': ad}]))
        commit(self.progress, 2, self.batch(2, [6], [{'type': 'text', 'id': 'p6-1', 'text': '第六页正文'}]))
        merge(self.progress, self.root / 'candidates.json')
        select_file(self.root / 'candidates.json', self.root / 'reviewed.json', self.root / 'work/selection.json')
        html = export(self.root / 'reviewed.json', self.root / 'out').read_text(encoding='utf-8')
        self.assertIn('第一页正文', html)
        self.assertIn('第六页正文', html)
        self.assertNotIn('扫码领资料', html)

    def test_cli_status_and_errors(self):
        done = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'pdf_batches.py'), 'status', str(self.progress)],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)['next_batch']['batch'], 1)
        bad = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPTS / 'pdf_batches.py'), 'merge', str(self.progress),
                              '--output', str(self.root / 'c.json')], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(bad.returncode, 1)
        self.assertIn('未完成批次', json.loads(bad.stdout)['error'])


if __name__ == '__main__':
    unittest.main()
