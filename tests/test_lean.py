"""Check that lean output preserves extracted content and actionable warnings."""
import importlib.util
import os
import re

from test_extract import BaseCase, SCRIPT, make_pdf, run_cli

spec = importlib.util.spec_from_file_location('extract_lean', SCRIPT)
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)


def content(text):
    text = re.sub(r'(?m)^===== PAGE ([0-9]+) =====$', r'[p\1]', text)
    return re.sub(r'\s+', '', text)


class TestLean(BaseCase):
    def test_same_content_across_modes(self):
        for path, flags in (
            (self.pdf, []), (self.pdf, ['--pages', '1-2']),
            (self.pdf, ['--grep', 'Middle|results', '-A', '0']),
            (self.pdf, ['--outline']),
            (self.pdf, ['--compact', '--drop-refs']),
            (self.pdf, ['--no-page-marker']),
            (self.pdf, ['--outline', '--grep', 'Middle']),
            (self.docx, []), (self.docx, ['--outline']),
            (self.docx, ['--grep', 'PHA']), (self.docx, ['--plain']),
            (self.docx, ['--compact', '--drop-refs']),
        ):
            with self.subTest(path=path, flags=flags):
                code, normal, _ = run_cli(path, *flags)
                lean_code, lean, _ = run_cli(path, *flags, '--lean')
                self.assertEqual(code, lean_code)
                self.assertEqual(content(normal), content(lean))

    def test_short_pages_and_no_routine_summary(self):
        code, out, err = run_cli(self.pdf, '--lean')
        self.assertEqual(code, 0)
        self.assertIn('[p1]', out)
        self.assertIn('[p4]', out)
        self.assertIn('95.11', out)
        self.assertIn('[1] Ref one', out)
        self.assertEqual(err, '')
        self.assertNotIn('\n\n', out)

    def test_empty_search_stays_empty(self):
        code, out, err = run_cli(self.pdf, '--grep', 'never-matches-xyz', '--lean')
        self.assertEqual((code, out, err), (0, '', ''))

    def test_requested_stats_kept(self):
        _, _, err = run_cli(self.pdf, '--lean', '--stats')
        self.assertIn('page 1', err)
        self.assertNotIn('--- pages:', err)

    def test_errors_and_low_text_warning_kept(self):
        for flags in (['--grep', '[unclosed'], ['--pages', '0']):
            code, _, err = run_cli(self.pdf, '--lean', *flags)
            self.assertEqual(code, 2)
            self.assertIn('ERROR:', err)
        short = os.path.join(self.tmp, 'short.pdf')
        make_pdf(short, [['Short text.']])
        code, out, err = run_cli(short, '--lean')
        self.assertEqual(code, 3)
        self.assertIn('Short text.', out)
        self.assertIn('WARNING:', err)

    def test_character_limit_and_warning_kept(self):
        _, out, err = run_cli(self.pdf, '--lean', '--max-chars', '40')
        self.assertLessEqual(len(out), 40)
        self.assertIn('truncated', err)

    def test_text_whitespace_indentation_and_values(self):
        path = os.path.join(self.tmp, 'sample.txt')
        original = 'Methods\n\n  PAN: 5 g; DMF: 50 mL\n\n    60 °C; 2 h; -5.2 W m⁻²\n'
        with open(path, 'w', encoding='utf-8') as stream:
            stream.write(original)
        _, out, err = run_cli(path, '--lean')
        self.assertEqual(content(original), content(out))
        self.assertIn('\n    60 °C', out)
        self.assertEqual(err, '')

    def test_no_marker_mode_does_not_rewrite_document_text(self):
        self.assertEqual(extract.lean_text('===== PAGE 7 =====\n', False),
                         '===== PAGE 7 =====')

