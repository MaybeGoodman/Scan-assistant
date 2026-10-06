import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from docx import Document
from lxml import etree

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/image-print-extractor/skills/image-print-extractor/scripts'
sys.path.insert(0, str(SCRIPTS))
from formulas import FormulaError, M, W, to_omml
from export_docx import export_docx
from export_page import export

NS = {'m': M, 'w': W}


class FormulaTests(unittest.TestCase):
    def test_short_inline_quantity_keeps_value_and_unit_on_one_line(self):
        source = r'3.9\times10^7\,\mathrm{J/m^3}'
        xml = to_omml(source)
        self.assertTrue(xml.xpath('./m:box/m:boxPr/m:noBreak[@m:val="1"]', namespaces=NS))
        self.assertEqual(''.join(xml.xpath('.//m:t/text()', namespaces=NS)), '3.9×107\u2009J/m3')
        self.assertFalse(to_omml(source, display=True).xpath('./m:box', namespaces=NS))
        self.assertFalse(to_omml(r'\mathrm{'+'W'*40+'}').xpath('./m:box', namespaces=NS))
        self.assertFalse(to_omml(r'\frac{1}{2}\mathrm{m}').xpath('./m:box', namespaces=NS))

    def test_empty_base_degree_has_no_word_placeholder(self):
        for source in (r'20\,{}^{\circ}\mathrm{C}',
                       r'4.2\times10^3\,\mathrm{J/(kg\cdot{}^{\circ}C)}'):
            with self.subTest(source=source):
                xml = to_omml(source)
                self.assertIn('°', ''.join(xml.itertext()))
                self.assertFalse(xml.xpath('.//m:sSup[not(m:e//m:t)]', namespaces=NS))
                self.assertTrue(xml.xpath('.//m:r[m:t="°"]/m:rPr/m:sty[@m:val="p"]', namespaces=NS))

    def test_degree_fix_preserves_powers_and_other_prescripts(self):
        for source in (r'x^{\circ}', r'60^{\circ}', r'{}^{23}X', r'10^7'):
            with self.subTest(source=source):
                xml = to_omml(source)
                self.assertEqual(len(xml.xpath('.//m:sSup', namespaces=NS)), 1)

    def test_nested_fraction_root_and_scripts(self):
        xml = to_omml(r'\frac{x_i^2+1}{\sqrt[3]{1+\frac{a}{b}}}')
        self.assertEqual(len(xml.xpath('.//m:f', namespaces=NS)), 2)
        self.assertEqual(len(xml.xpath('.//m:sSubSup', namespaces=NS)), 1)
        self.assertEqual(xml.xpath('string(.//m:rad/m:deg//m:t)', namespaces=NS), '3')
        self.assertEqual(xml.xpath('string(.//m:rad/m:radPr/m:degHide/@m:val)', namespaces=NS), '0')

    def test_functions_units_and_chinese_are_upright(self):
        xml = to_omml(r'\sin x+\ln y+3\,\mathrm{kg}+\mathrm{d}+\text{当 }t=0')
        for text in ('sin', 'ln', 'kg', 'd', '当 '):
            self.assertTrue(xml.xpath('.//m:r[m:t=$text]/m:rPr/m:sty[@m:val="p"]', namespaces=NS, text=text))
        self.assertTrue(xml.xpath('.//m:r[m:t="x"]/m:rPr/m:sty[@m:val="i"]', namespaces=NS))

    def test_matrix_fences_and_cells(self):
        xml = to_omml(r'\begin{pmatrix}a&b\\c&d\end{pmatrix}')
        self.assertEqual(len(xml.xpath('.//m:m/m:mr', namespaces=NS)), 2)
        self.assertEqual(len(xml.xpath('.//m:m/m:mr/m:e', namespaces=NS)), 4)
        self.assertTrue(xml.xpath('.//m:dPr/m:begChr[@m:val="("]', namespaces=NS))
        self.assertTrue(xml.xpath('.//m:dPr/m:endChr[@m:val=")"]', namespaces=NS))

    def test_cases_alignment_and_single_fence(self):
        xml = to_omml(r'f(x)=\begin{cases}x^2&x>0\\0&x\leq0\end{cases}', display=True)
        self.assertEqual(len(xml.xpath('.//m:m/m:mr', namespaces=NS)), 2)
        self.assertEqual(xml.xpath('.//m:mcJc/@m:val', namespaces=NS), ['left', 'left'])
        self.assertTrue(xml.xpath('.//m:begChr[@m:val="{"]', namespaces=NS))
        self.assertTrue(xml.xpath('.//m:endChr[@m:val=""]', namespaces=NS))

    def test_aligned_equations_keep_columns(self):
        xml = to_omml(r'\begin{aligned}a&=b+c\\&=d\end{aligned}', display=True)
        self.assertEqual(xml.xpath('.//m:mcJc/@m:val', namespaces=NS), ['right', 'left'])
        rows = xml.xpath('.//m:m/m:mr', namespaces=NS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(''.join(rows[1][0].itertext()), '')
        self.assertEqual(''.join(rows[1][1].itertext()), '=d')

    def test_sum_integral_and_limit(self):
        xml = to_omml(r'\sum_{i=1}^{n}i+\int_0^1 x\,\mathrm{d}x+\lim_{x\to0}\frac{\sin x}{x}', display=True)
        self.assertEqual(xml.xpath('.//m:naryPr/m:chr/@m:val', namespaces=NS), ['∑', '∫'])
        self.assertEqual(len(xml.xpath('.//m:nary/m:sub', namespaces=NS)), 2)
        self.assertIn('lim', ''.join(xml.itertext()))

    def test_accents_bars_and_delimiters(self):
        xml = to_omml(r'\vec{v}+\overline{AB}+\left|\frac{x}{y}\right|')
        self.assertTrue(xml.xpath('.//m:acc/m:accPr/m:chr[@m:val="⃗"]', namespaces=NS))
        self.assertTrue(xml.xpath('.//m:bar/m:e', namespaces=NS))
        self.assertTrue(xml.xpath('.//m:d/m:e//m:f', namespaces=NS))

    def test_invalid_or_unsupported_input_fails_closed(self):
        for source in (r'\frac{1}{', r'\unknown{x}', r'\ce{H2O}', r'\input{secret}',
                       r'\begin{matrix}a\end{cases}', '$x$', 'x%comment', '', r'\frac{1}',
                       r'\begin{unsupported}x\end{unsupported}', r'\begin{array}{p}a\end{array}'):
            with self.subTest(source=source), self.assertRaises(FormulaError):
                to_omml(source)

    def test_local_uncertainty_does_not_destroy_known_structure(self):
        xml = to_omml(r'\frac{\text{XXX}}{y}')
        self.assertTrue(xml.xpath('.//m:f/m:num//m:t[text()="XXX"]', namespaces=NS))
        self.assertTrue(xml.xpath('.//m:f/m:den//m:t[text()="y"]', namespaces=NS))

    def test_function_spacing_and_limit_placement(self):
        xml = to_omml(r'\sin x+\lim_{x\to0}f(x)', display=True)
        self.assertTrue(xml.xpath('.//m:func/m:fName//m:t[text()="sin"]', namespaces=NS))
        self.assertTrue(xml.xpath('.//m:limLow/m:lim', namespaces=NS))
        inline = to_omml(r'\lim_{x\to0}f(x)')
        self.assertTrue(inline.xpath('.//m:sSub', namespaces=NS))
        explicit = to_omml(r'\lim\nolimits_{x\to0}f(x)', display=True)
        self.assertTrue(explicit.xpath('.//m:sSub', namespaces=NS))


class ExportFormulaTests(unittest.TestCase):
    def export_blocks(self, root, blocks):
        source = root / 'source.json'
        source.write_text(json.dumps({'blocks': blocks}, ensure_ascii=False), encoding='utf-8')
        target = export_docx(source, root / 'result.docx', word_confirmed=True)
        with ZipFile(target) as zipped:
            xml = etree.fromstring(zipped.read('word/document.xml'))
            self.assertFalse(any(name.startswith('word/media/') for name in zipped.namelist()))
        report = json.loads(target.with_suffix('.review.json').read_text(encoding='utf-8'))
        return xml, report

    def test_inline_display_chemistry_and_table_routing(self):
        chemistry = r'\mathrm{Fe^{3+}}+3\mathrm{OH^-}\rightarrow\mathrm{Fe(OH)_3}\downarrow'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            xml, report = self.export_blocks(root, [
                {'type': 'text', 'runs': [{'type': 'text', 'text': '变量'},
                    {'type': 'math', 'latex': 'x'}, {'type': 'text', 'text': '与离子'},
                    {'type': 'chemistry', 'latex': r'\mathrm{SO_4^{2-}}'}]},
                {'type': 'math', 'latex': r'x^2+\frac{1}{y}'},
                {'type': 'chemistry', 'latex': chemistry},
                {'type': 'table', 'rows': 1, 'cols': 1, 'cells': [{'row': 0, 'col': 0, 'runs': [
                    {'type': 'math', 'latex': 'a_1'}, {'type': 'text', 'text': '；'},
                    {'type': 'chemistry', 'latex': r'\mathrm{CuSO_4}\cdot 5\mathrm{H_2O}'}]}]}])
            self.assertEqual(len(xml.xpath('//m:oMath', namespaces=NS)), 3)
            self.assertEqual(len(xml.xpath('//m:oMathPara', namespaces=NS)), 1)
            self.assertEqual(len(xml.xpath('//w:tbl//m:oMath', namespaces=NS)), 1)
            self.assertIn(chemistry, xml.xpath('//w:t/text()', namespaces=NS))
            self.assertNotIn(r'\frac', ''.join(xml.xpath('//w:t/text()', namespaces=NS)))
            self.assertEqual(report['needs_review'], 0)
            self.assertEqual(len(report['expressions']), 6)
            # Saving again must preserve native math and literal chemistry.
            Document(root / 'result.docx').save(root / 'saved.docx')
            with ZipFile(root / 'saved.docx') as saved:
                saved_xml = etree.fromstring(saved.read('word/document.xml'))
            self.assertEqual(len(saved_xml.xpath('//m:oMath', namespaces=NS)), 3)
            self.assertIn(chemistry, saved_xml.xpath('//w:t/text()', namespaces=NS))

    def test_conditions_isotopes_states_and_unbalanced_source_are_literal(self):
        expressions = [r'\mathrm{H_2}+\mathrm{O_2}\rightarrow\mathrm{H_2O}',
            r'\mathrm{N_2}+3\mathrm{H_2}\overset{\text{催化剂}}{\underset{\text{高温、高压}}{\rightleftharpoons}}2\mathrm{NH_3}',
            r'{}^{14}_{6}\mathrm{C}', r'\mathrm{H_2(g)}', r'\mathrm{e^-}',
            r'\mathrm{[Fe(CN)_6]^{3-}}', r'\mathrm{H_2}\xrightarrow{\text{点燃}}\mathrm{XXX}\uparrow']
        with tempfile.TemporaryDirectory() as temp:
            xml, report = self.export_blocks(Path(temp), [{'type': 'chemistry', 'latex': s} for s in expressions])
            self.assertEqual(xml.xpath('//w:t/text()', namespaces=NS), expressions)
            self.assertFalse(xml.xpath('//m:oMath', namespaces=NS))
            self.assertEqual(report['needs_review'], 1)

    def test_errors_are_locatable_and_known_content_survives(self):
        with tempfile.TemporaryDirectory() as temp:
            xml, report = self.export_blocks(Path(temp), [
                {'type': 'text', 'source': {'page': 2, 'bbox': [10, 20, 90, 40]}, 'runs': [
                    {'type': 'text', 'text': '前文'}, {'type': 'math', 'latex': r'\bad{x}'},
                    {'type': 'text', 'text': '后文'}, {'type': 'math', 'latex': r'\frac{\text{XXX}}{y}'}]},
                {'type': 'chemistry', 'latex': r'\ce{H2O}', 'id': 'chem-2'},
                {'type': 'math', 'latex': 'x', 'status': 'unresolved', 'reason': 'Upper index unreadable'},
                {'type': 'math', 'latex': 'y^2', 'repairs': [{'detail': 'Restored visible superscript', 'evidence': 'page 3'}]}])
            self.assertEqual(xml.xpath('//w:t/text()', namespaces=NS)[:3], ['前文', 'XXX', '后文'])
            self.assertEqual(report['needs_review'], 5)
            self.assertEqual(report['expressions'][0]['source']['page'], 2)
            self.assertEqual(report['expressions'][0]['location'], 'blocks[0].runs[1]')
            self.assertIn('Unsupported', report['expressions'][0]['reason'])
            self.assertEqual(report['expressions'][2]['id'], 'chem-2')
            self.assertTrue(xml.xpath('//m:f/m:den//m:t[text()="y"]', namespaces=NS))
            self.assertNotIn(r'\bad', etree.tostring(xml, encoding='unicode'))

    def test_legacy_word_math_requires_classification(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, 'typed math or chemistry'):
                self.export_blocks(root, [{'type': 'text', 'text': '已知 $x^2$。'}])
            self.assertFalse((root / 'result.docx').exists())
            self.assertFalse((root / 'result.review.json').exists())

    def test_missing_converter_is_not_misrepresented_as_ocr_failure(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {'latex2mathml.converter': None}):
            root = Path(temp)
            with self.assertRaisesRegex(RuntimeError, 'Install latex2mathml'):
                self.export_blocks(root, [{'type': 'math', 'latex': 'x'}])
            self.assertFalse((root / 'result.docx').exists())

    def test_report_cannot_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'result.review.json').write_text('keep', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                self.export_blocks(root, [{'type': 'text', 'text': '正文'}])
            self.assertEqual((root / 'result.review.json').read_text(), 'keep')
            self.assertFalse((root / 'result.docx').exists())

    def test_html_supports_same_typed_content_and_escapes_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source.json'
            source.write_text(json.dumps({'blocks': [
                {'type': 'text', 'runs': [{'type': 'text', 'text': '<script>'},
                    {'type': 'math', 'latex': 'x<2'}, {'type': 'chemistry', 'latex': r'\mathrm{H_2O}'}]},
                {'type': 'math', 'latex': r'\frac{1}{2}'},
                {'type': 'chemistry', 'latex': r'\mathrm{Na^+}'},
                {'type': 'table', 'rows': 1, 'cols': 1, 'cells': [{'row': 0, 'col': 0,
                    'runs': [{'type': 'math', 'latex': 'a_1'}]}]}]}), encoding='utf-8')
            target = export(source, root / 'html')
            html = target.read_text(encoding='utf-8')
            self.assertIn('&lt;script&gt;', html)
            self.assertIn('$x&lt;2$', html)
            self.assertIn(r'\mathrm{H_2O}', html)
            self.assertIn(r'$$\frac{1}{2}$$', html)
            self.assertIn('$a_1$', html)


if __name__ == '__main__':
    unittest.main()
