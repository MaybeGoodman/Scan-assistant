import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

scripts = Path(__file__).resolve().parents[1] / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
def load(name):
    spec = importlib.util.spec_from_file_location(name, scripts / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
exporter, cropper = load('export_page'), load('crop_png')


class ExportTests(unittest.TestCase):
    def test_merged_and_blank_cells(self):
        table = {'rows':2,'cols':2,'cells':[
            {'row':0,'col':0,'colspan':2,'text':'表头'},
            {'row':1,'col':0,'text':''},{'row':1,'col':1,'text':'$x^2$'}]}
        html = exporter.table_html(table)
        self.assertIn('colspan="2"', html)
        self.assertIn('colspan="1"></td>', html)
        self.assertEqual(html.count('<td '), 3)

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):
            exporter.table_html({'rows':1,'cols':1,'cells':[
                {'row':0,'col':0,'text':'a'},{'row':0,'col':0,'text':'b'}]})

    def test_missing_cell_rejected(self):
        with self.assertRaises(ValueError):
            exporter.table_html({'rows':1,'cols':1,'cells':[]})

    def test_order_escape_and_png(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            Image.new('RGB',(10,10),'white').save(base/'figure.png')
            blocks = [{'type':'text','text':'前文 <script>alert(1)</script> $x<2$'},
                      {'type':'image','path':'figure.png'},
                      {'type':'table','rows':1,'cols':1,'cells':[{'row':0,'col':0,'text':''}]},
                      {'type':'text','text':'后文'}]
            source = base/'page.json'
            source.write_text(json.dumps({'blocks':blocks}),encoding='utf-8')
            result = exporter.export(source,base/'out')
            html = result.read_text(encoding='utf-8')
            self.assertNotIn('<script>',html)
            self.assertIn('&lt;script&gt;',html)
            self.assertLess(html.index('前文'),html.index('<img'))
            self.assertLess(html.index('<img'),html.index('<table'))
            self.assertLess(html.index('<table'),html.index('后文'))
            self.assertEqual((base/'out/figures/figure-02.png').read_bytes(),(base/'figure.png').read_bytes())
            self.assertIn('[表格](result.html#table-3)',(base/'out/result.md').read_text(encoding='utf-8'))
            with self.assertRaises(FileExistsError):
                exporter.export(source,base/'out')

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            exporter.image_source(Path('.'),'../secret.png')

    def test_bad_png_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base/'bad.png').write_text('not a PNG')
            with self.assertRaises(ValueError):
                exporter.image_source(base,'bad.png')

    def test_crop_pixels_and_bounds(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            image = Image.new('RGB',(10,10),'white')
            image.putpixel((2,3),(10,20,30))
            image.save(base/'source.png')
            cropper.crop(base/'source.png',base/'crop.png',(2,3,5,7))
            with Image.open(base/'crop.png') as crop:
                self.assertEqual(crop.size,(3,4))
                self.assertEqual(crop.getpixel((0,0)),(10,20,30))
            with self.assertRaises(ValueError):
                cropper.crop(base/'source.png',base/'bad.png',(-1,0,3,3))
            with self.assertRaises(FileExistsError):
                cropper.crop(base/'source.png',base/'crop.png',(0,0,3,3))

if __name__ == '__main__':
    unittest.main()
