import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from docx import Document
from PIL import Image
from reportlab.pdfgen import canvas

scripts = Path(__file__).resolve().parents[1] / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(scripts))
from export_docx import export_docx
from prepare_pdf import prepare


class PdfWordTests(unittest.TestCase):
    def test_confirmation_required(self):
        with self.assertRaisesRegex(ValueError, 'Confirm Word'):
            export_docx('unused.json', 'unused.docx')

    def test_editable_content_merges_and_embedded_png(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            Image.new('RGB', (300, 100), 'white').save(root / 'figure.png')
            source = root / 'reviewed.json'
            blocks = [
                {'type':'text', 'text':'跨页续句已接回，公式 $x^2+1$ 保留。'},
                {'type':'table', 'rows':3, 'cols':3, 'cells':[
                    {'row':0, 'col':0, 'rowspan':2, 'colspan':2, 'text':'合并表头'},
                    {'row':0, 'col':2, 'text':'数值'},
                    {'row':1, 'col':2, 'text':''},
                    {'row':2, 'col':0, 'text':'A'},
                    {'row':2, 'col':1, 'text':'XXX'},
                    {'row':2, 'col':2, 'text':'$a>0$'}]},
                {'type':'image', 'path':'figure.png', 'alt':'印刷插图'},
                {'type':'text', 'text':'与正文相关的来源说明保留。'}]
            source.write_text(json.dumps({'blocks':blocks}), encoding='utf-8')
            target = export_docx(source, root / 'result.docx', word_confirmed=True)
            doc = Document(target)
            self.assertEqual(doc.paragraphs[0].text, blocks[0]['text'])
            self.assertEqual(doc.paragraphs[-1].text, blocks[-1]['text'])
            table = doc.tables[0]
            self.assertEqual(table.cell(0, 0).text, '合并表头')
            self.assertEqual(table.cell(1, 1).text, '合并表头')
            self.assertEqual(table.cell(1, 2).text, '')
            self.assertEqual(len(doc.inline_shapes), 1)
            tags = [el.tag.rsplit('}',1)[-1] for el in doc.element.body]
            self.assertEqual(tags, ['p','tbl','p','p','sectPr'])
            with ZipFile(target) as z:
                self.assertTrue(any(name.startswith('word/media/') for name in z.namelist()))
                xml = z.read('word/document.xml').decode('utf-8')
                self.assertIn('w:gridSpan', xml)
                self.assertIn('w:vMerge', xml)
            with self.assertRaises(FileExistsError):
                export_docx(source, target, word_confirmed=True)

    def test_invalid_table_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'bad.json'
            source.write_text(json.dumps({'blocks':[{'type':'table','rows':1,'cols':1,'cells':[]}]}))
            with self.assertRaises(ValueError):
                export_docx(source, root / 'bad.docx', word_confirmed=True)
            self.assertFalse((root / 'bad.docx').exists())

    def test_pdf_all_pages_and_unfiltered_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = canvas.Canvas(str(root / 'source.pdf'))
            pdf.drawString(70,700,'PRINTED CONTENT')
            pdf.drawString(70,600,'DOWNLOAD WATERMARK')
            pdf.showPage()
            pdf.showPage()  # Blank/textless page still needs visual review.
            pdf.save()
            result = prepare(root / 'source.pdf', root / 'pages', 72)
            self.assertEqual(result['page_count'], 2)
            self.assertEqual([p['page'] for p in result['pages']], [1, 2])
            self.assertIn('PRINTED CONTENT', result['pages'][0]['text_candidate'])
            self.assertIn('DOWNLOAD WATERMARK', result['pages'][0]['text_candidate'])
            self.assertEqual(result['pages'][1]['text_candidate'], '')
            for page in result['pages']:
                with Image.open(root / 'pages' / page['image']) as image:
                    self.assertEqual(image.format, 'PNG')
            with self.assertRaises(FileExistsError):
                prepare(root / 'source.pdf', root / 'pages')

if __name__ == '__main__':
    unittest.main()
