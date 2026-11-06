"""Reproducible synthetic benchmark; runtime extractor remains stdlib-only.

Run: python tests/benchmark_tokens.py --tokenizer estimate
Optional exact counter: install tiktoken separately, then use --tokenizer o200k_base.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from test_extract import make_docx, make_pdf

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '407cb39c98dd295641e1aef47c1b36bb9a382c85'


def run(script, path, flags):
    result = subprocess.run([sys.executable, str(script), str(path), *flags],
                            capture_output=True, timeout=10)
    return result.returncode, result.stdout.decode('utf-8'), result.stderr.decode('utf-8')


def canonical(text):
    lines = []
    for line in text.split('\n'):
        if line.strip():
            line = re.sub(r'^===== PAGE ([0-9]+) =====$', r'[p\1]', line)
            lines.append(line.rstrip(' \t\r'))
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default=BASELINE)
    parser.add_argument('--tokenizer', default='estimate',
                        choices=['estimate', 'o200k_base', 'cl100k_base'])
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('extract', ROOT / 'scripts/extract_text.py')
    extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extractor)
    if args.tokenizer == 'estimate':
        count = extractor.estimate_tokens
    else:
        import tiktoken  # optional developer dependency, never needed by extractor
        encoder = tiktoken.get_encoding(args.tokenizer)
        count = lambda text: len(encoder.encode(text, disallowed_special=()))

    def old_file(name):
        return subprocess.check_output(['git', 'show', args.baseline_ref + ':' + name],
                                       cwd=str(ROOT)).decode('utf-8')

    old_skill = old_file('SKILL.md')
    new_skill = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
    metrics = []
    checks = 0
    with tempfile.TemporaryDirectory(prefix='extract_benchmark_',
                                     dir=os.environ.get('EXTRACT_TEST_TMPDIR')) as tmp:
        work = Path(tmp)
        old_script = work / 'baseline.py'
        old_script.write_text(old_file('scripts/extract_text.py'), encoding='utf-8')
        pdf, docx, text = work / 'sample.pdf', work / 'sample.docx', work / 'sample.txt'
        make_pdf(str(pdf), [
            ['%d. Experimental Section' % page,
             'PAN: 5 g; solvent: 50 mL; temperature: 60 C; time: 2 h.',
             'Results: solar reflectance 95.11 percent.',
             'Repeated control line with real content.'] for page in range(1, 13)
        ], footer='Synthetic document footer for testing only')
        make_docx(str(docx))
        text.write_text('Methods\n\n  PAN: 5 g; DMF: 50 mL\n\nResults: 95.11%; 60 °C; 2 h.\n',
                        encoding='utf-8')
        scenarios = [
            ('pdf_full', pdf, []), ('pdf_outline', pdf, ['--outline']),
            ('pdf_search', pdf, ['--grep', 'PAN', '-A', '1']),
            ('pdf_pages', pdf, ['--pages', '2-4']),
            ('pdf_compact', pdf, ['--compact']),
            ('pdf_references', pdf, ['--drop-refs']),
            ('pdf_no_markers', pdf, ['--no-page-marker']),
            ('docx_full', docx, []), ('docx_outline', docx, ['--outline']),
            ('docx_search', docx, ['--grep', 'PHA', '-A', '1']),
            ('docx_plain', docx, ['--plain']),
            ('docx_references', docx, ['--drop-refs']),
            ('text_full', text, []), ('text_search', text, ['--grep', 'PAN']),
        ]
        for name, path, flags in scenarios:
            old = run(old_script, path, flags)
            new = run(ROOT / 'scripts/extract_text.py', path, flags)
            assert old == new, 'legacy output changed: ' + name
            checks += 1
            lean = run(ROOT / 'scripts/extract_text.py', path, [*flags, '--lean'])
            assert old[0] == lean[0], 'exit code changed: ' + name
            assert canonical(old[1]) == canonical(lean[1]), 'content changed: ' + name
            old_total = count(old[1]) + count(old[2])
            new_total = count(lean[1]) + count(lean[2])
            metrics.append(dict(scenario=name, stdout_before=count(old[1]),
                                stdout_after=count(lean[1]),
                                combined_before=old_total, combined_after=new_total,
                                saved_percent=round(100 * (1 - new_total / old_total), 2)))
        # Also verify capped legacy output remains byte-for-byte identical.
        for path in (pdf, docx, text):
            flags = ['--max-chars', '40']
            assert run(old_script, path, flags) == run(ROOT / 'scripts/extract_text.py', path, flags)
            checks += 1

    before, after = count(old_skill), count(new_skill)
    print(json.dumps(dict(baseline_ref=args.baseline_ref, tokenizer=args.tokenizer,
                          fixtures='synthetic only; no real research documents',
                          legacy_cases_identical=checks,
                          lean_content_cases_identical=len(metrics),
                          skill=dict(before=before, after=after,
                                     saved_percent=round(100 * (1 - after / before), 2)),
                          scenarios=metrics), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
