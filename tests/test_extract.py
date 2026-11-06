#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stdlib-only test suite for extract_text.py.

Generates a tiny PDF and a tiny .docx on the fly (no sample files, no
third-party packages), then exercises the CLI in the same way a user would.

Run:
    python -m unittest discover -s tests -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'scripts', 'extract_text.py')


# ---------------------------------------------------------------------------
# Fixtures: build minimal but valid-enough documents with the stdlib only
# ---------------------------------------------------------------------------

def _escape_pdf(text):
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _content_stream(lines):
    body = ['BT', '/F1 12 Tf', '72 720 Td']
    for line in lines:
        body.append('(%s) Tj' % _escape_pdf(line))
        body.append('0 -18 Td')
    body.append('ET')
    return ('\n'.join(body)).encode('latin1')


def make_pdf(path, pages_lines, footer=None):
    """Write a multi-page PDF with a simple Helvetica content stream."""
    pages = []
    for lines in pages_lines:
        content = list(lines)
        if footer:
            content.append(footer)
        pages.append(content)
    n = len(pages)
    font_obj = 3 + 2 * n
    objects = {}
    kids = ' '.join('%d 0 R' % (3 + 2 * i) for i in range(n))
    objects[1] = b'<< /Type /Catalog /Pages 2 0 R >>'
    objects[2] = ('<< /Type /Pages /Kids [%s] /Count %d >>' % (kids, n)).encode()
    for i, lines in enumerate(pages):
        page_obj = 3 + 2 * i
        content_obj = 4 + 2 * i
        objects[page_obj] = (
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
            '/Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> >> >>'
            % (content_obj, font_obj)).encode()
        stream = _content_stream(lines)
        objects[content_obj] = (
            b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream')
    objects[font_obj] = b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'

    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += b'%d 0 obj\n' % num + objects[num] + b'\nendobj\n'
    xref_at = len(out)
    size = max(objects) + 1
    out += b'xref\n0 %d\n' % size
    out += b'0000000000 65535 f \n'
    for num in range(1, size):
        out += b'%010d 00000 n \n' % offsets.get(num, 0)
    out += (b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'
            % (size, xref_at))
    with open(path, 'wb') as fh:
        fh.write(bytes(out))


DOCX_BODY = (
    '<w:body>'
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
    '<w:r><w:t>1. Introduction</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>This is body text about PHA and radiative cooling.</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
    '<w:r><w:t>2. Experimental Section</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>Materials: PHA (5 g) in 50 mL dichloromethane.</w:t></w:r></w:p>'
    '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Material</w:t></w:r></w:p></w:tc>'
    '<w:tc><w:p><w:r><w:t>Amount</w:t></w:r></w:p></w:tc></w:tr>'
    '<w:tr><w:tc><w:p><w:r><w:t>PHA</w:t></w:r></w:p></w:tc>'
    '<w:tc><w:p><w:r><w:t>5 g</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    '<w:p><w:r><w:t>中文测试：辐射制冷、孔隙率 95%。</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
    '<w:r><w:t>References</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>[1] Ref one.</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>[2] Ref two.</w:t></w:r></w:p>'
    '</w:body>'
)


def make_docx(path):
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/'
           'wordprocessingml/2006/main">' + DOCX_BODY + '</w:document>')
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', doc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cli(*args, cwd=None):
    proc = subprocess.run(
        [sys.executable, SCRIPT] + list(args),
        cwd=cwd or ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    return (proc.returncode,
            proc.stdout.decode('utf-8', 'replace'),
            proc.stderr.decode('utf-8', 'replace'))


def _make_workdir():
    """Portable scratch dir; EXTRACT_TEST_TMPDIR overrides the system temp dir."""
    base = os.environ.get('EXTRACT_TEST_TMPDIR') or tempfile.gettempdir()
    os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix='extract_test_', dir=base)


class BaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = _make_workdir()
        cls.pdf = os.path.join(cls.tmp, 'sample.pdf')
        cls.docx = os.path.join(cls.tmp, 'sample.docx')
        make_pdf(
            cls.pdf,
            pages_lines=[
                ['Solar reflectance reaches 95.11 percent.', 'Second body line.'],
                ['Middle page text about mechanism.'],
                ['More results.'],
                ['References', '[1] Ref one', '[2] Ref two'],
            ],
            footer='Downloaded from example.org for testing purposes only',
        )
        make_docx(cls.docx)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCliBasics(BaseCase):
    def test_help(self):
        code, out, _ = run_cli('--help')
        self.assertEqual(code, 0)
        self.assertIn('usage', out.lower())

    def test_version(self):
        code, out, _ = run_cli('--version')
        self.assertEqual(code, 0)
        self.assertIn('1.0.0', out)

    def test_missing_file(self):
        code, _, err = run_cli(os.path.join(self.tmp, 'nope.pdf'))
        self.assertEqual(code, 2)
        self.assertIn('not found', err.lower())

    def test_unsupported_doc(self):
        old = os.path.join(self.tmp, 'old.doc')
        with open(old, 'wb') as fh:
            fh.write(bytes.fromhex('d0cf11e0a1b11ae1') + b'junk' * 20)
        code, _, err = run_cli(old)
        self.assertEqual(code, 2)
        self.assertIn('not supported', err.lower())


class TestPdf(BaseCase):
    def test_invalid_pages(self):
        for spec in ('0', '3-1', '-1', '1,,2', '1-100001', ''):
            with self.subTest(spec=spec):
                code, out, _ = run_cli(self.pdf, '--pages', spec)
                self.assertEqual(code, 2)
                self.assertEqual(out, '')

    def test_negative_limits(self):
        for flag in ('--max-chars', '-A', '-B', '-m'):
            code, _, _ = run_cli(self.pdf, flag, '-1')
            self.assertEqual(code, 2)

    def test_pdf_delimiters_and_comments(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('extract', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = list(module.tokens(b'<< /ActualText (ok) >> { } % (private) Tj\n'))
        self.assertIn(('str', b'ok'), result)
        self.assertNotIn(('str', b'private'), result)

    def test_encrypted_pdf_rejected(self):
        encrypted = os.path.join(self.tmp, 'encrypted.pdf')
        with open(self.pdf, 'rb') as source, open(encrypted, 'wb') as target:
            target.write(source.read() + b'\ntrailer << /Encrypt 99 0 R >>')
        code, out, err = run_cli(encrypted)
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('encrypted PDF', err)

    def test_decompression_limit(self):
        import importlib.util
        import zlib
        spec = importlib.util.spec_from_file_location('extract', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.MAX_EXPANDED_BYTES = 128
        with self.assertRaises(ValueError):
            module.limited_decompress(zlib.compress(b'x' * 129))

    def test_full_text(self):
        code, out, err = run_cli(self.pdf)
        self.assertEqual(code, 0, err)
        self.assertIn('95.11', out)
        self.assertIn('===== PAGE 1 =====', out)
        self.assertIn('===== PAGE 4 =====', out)

    def test_page_selection(self):
        code, out, _ = run_cli(self.pdf, '--pages', '2')
        self.assertEqual(code, 0)
        self.assertIn('Middle page', out)
        self.assertNotIn('95.11', out)

    def test_grep_adds_page_marker(self):
        code, out, _ = run_cli(self.pdf, '--grep', 'Middle', '-A', '1')
        self.assertEqual(code, 0)
        self.assertIn('===== PAGE 2 =====', out)
        self.assertIn('Middle page', out)

    def test_case_sensitive_flag(self):
        _, out, _ = run_cli(self.pdf, '--grep', 'middle')
        self.assertIn('Middle page', out)          # default: insensitive
        _, out2, _ = run_cli(self.pdf, '--grep', 'middle', '-c')
        self.assertNotIn('Middle page', out2)      # -c: sensitive

    def test_compact_drops_repeated_footer(self):
        _, out, _ = run_cli(self.pdf, '--compact')
        self.assertNotIn('Downloaded from example.org', out)
        self.assertIn('95.11', out)

    def test_drop_refs(self):
        _, out, _ = run_cli(self.pdf, '--drop-refs')
        self.assertNotIn('[1] Ref one', out)
        self.assertIn('95.11', out)

    def test_max_chars(self):
        _, out, _ = run_cli(self.pdf, '--max-chars', '40')
        self.assertLessEqual(len(out.strip()), 40)

    def test_outline_mode(self):
        code, out, err = run_cli(self.pdf, '--outline')
        self.assertEqual(code, 0, err)
        self.assertIn('References', out)


class TestDocx(BaseCase):
    def test_entity_declaration_rejected(self):
        hostile = os.path.join(self.tmp, 'entity.docx')
        with zipfile.ZipFile(hostile, 'w') as target:
            target.writestr('word/document.xml', '<!DOCTYPE x [<!ENTITY e "hello">]><x/>')
        code, out, err = run_cli(hostile)
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('entity declarations', err)

    def test_full_text(self):
        code, out, err = run_cli(self.docx)
        self.assertEqual(code, 0, err)
        self.assertIn('1. Introduction', out)
        self.assertIn('This is body text', out)
        self.assertIn('Material | Amount', out)
        self.assertIn('中文测试：辐射制冷', out)

    def test_headings_marked(self):
        _, out, _ = run_cli(self.docx)
        self.assertIn('# 1. Introduction', out)
        self.assertIn('## 2. Experimental Section', out)

    def test_plain_mode(self):
        _, out, _ = run_cli(self.docx, '--plain')
        self.assertNotIn('# 1. Introduction', out)
        self.assertIn('1. Introduction', out)

    def test_outline(self):
        _, out, _ = run_cli(self.docx, '--outline')
        self.assertIn('# 1. Introduction', out)
        self.assertIn('# References', out)

    def test_grep(self):
        _, out, _ = run_cli(self.docx, '--grep', 'Experimental')
        self.assertIn('2. Experimental Section', out)
        self.assertIn('Materials: PHA', out)

    def test_drop_refs(self):
        _, out, _ = run_cli(self.docx, '--drop-refs')
        self.assertNotIn('[1] Ref one', out)
        self.assertIn('1. Introduction', out)

    def test_compact_collapses_blanks(self):
        _, out, _ = run_cli(self.docx, '--compact')
        self.assertNotIn('\n\n\n', out)

    def test_bad_regex(self):
        code, _, err = run_cli(self.docx, '--grep', '[unclosed')
        self.assertEqual(code, 2)
        self.assertIn('bad --grep pattern', err.lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)
