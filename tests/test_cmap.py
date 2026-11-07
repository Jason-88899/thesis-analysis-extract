"""Synthetic CMap regressions; no user documents required."""
import importlib.util
import unittest
from test_extract import SCRIPT

spec = importlib.util.spec_from_file_location('extract_cmap', SCRIPT)
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)

class TestCMap(unittest.TestCase):
    def parse(self, entry):
        parser = extract.PdfFile.__new__(extract.PdfFile)
        return parser._parse_cmap(b'1 beginbfrange\n' + entry + b'\nendbfrange')

    def test_surrogate_range(self):
        self.assertEqual(self.parse(b'<41> <43> <D835DC50>'),
                         {65: '\U0001d450', 66: '\U0001d451', 67: '\U0001d452'})

    def test_multiple_characters(self):
        self.assertEqual(self.parse(b'<41> <42> <00660069>'), {65: 'fi', 66: 'fj'})

    def test_prefix_and_surrogate(self):
        self.assertEqual(self.parse(b'<41> <42> <0061D835DC50>'),
                         {65: 'a\U0001d450', 66: 'a\U0001d451'})

    def test_bmp_range(self):
        self.assertEqual(self.parse(b'<41> <43> <4E00>'),
                         {65: '\u4e00', 66: '\u4e01', 67: '\u4e02'})

    def test_invalid_destinations(self):
        for dest in (b'D800', b'DC00', b'123', b'12', b'D800D800'):
            with self.subTest(dest=dest):
                self.assertEqual(self.parse(b'<41> <41> <' + dest + b'>'), {})

    def test_reversed_range(self):
        self.assertEqual(self.parse(b'<43> <41> <0041>'), {})

    def test_no_final_byte_wrap(self):
        self.assertEqual(self.parse(b'<41> <42> <00FF>'), {65: '\u00ff'})

    def test_resource_bound(self):
        with self.assertRaises(ValueError):
            self.parse(b'<0> <10000> <0041>')

