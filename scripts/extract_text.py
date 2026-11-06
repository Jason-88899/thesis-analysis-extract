#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-dependency document text extractor: PDF + Word (.docx), built to save tokens.

Prints to stdout (the chat) instead of writing files, and offers low-token
reading modes so an agent can study a paper without dumping the whole document
into the context window:

    --outline     structure map only (section headings + page numbers)
    --grep        keyword search with context (locate Experimental Section etc.)
    --compact     drop repeated headers/footers/watermarks, page numbers, fix
                  hyphenated line breaks, collapse blank lines
    --drop-refs   cut the reference list (pure noise for content extraction)
    --pages       PDF page selection
    --max-chars   hard cap on printed characters

Only the Python standard library is used: PDF is parsed by hand (objects,
ObjStm, FlateDecode, page tree, font ToUnicode CMaps); Word is read by
unzipping the OOXML package and walking word/document.xml.

Supported: .pdf, .docx/.docm/.dotx, .txt/.md/.csv/.json/.yaml
Not supported: .doc (Word 97-2003 binary) -> convert to .docx first.

Exit codes: 0 = printed, 2 = missing/unsupported/parse error, 3 = almost no text.
"""

import argparse
import os
import re
import sys
import zipfile
import zlib
from collections import Counter
from xml.etree import ElementTree as ET

MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024


def limited_decompress(data):
    decoder = zlib.decompressobj()
    out = decoder.decompress(data, MAX_EXPANDED_BYTES + 1)
    if len(out) > MAX_EXPANDED_BYTES or decoder.unconsumed_tail:
        raise ValueError('PDF stream exceeds the 32 MiB decompression limit')
    return out

# ============================================================================
# Part 1 — PDF engine
# ============================================================================

OBJ_RE = re.compile(rb'(?<![0-9])(\d+)\s+(\d+)\s+obj\b')

GLYPH_MAP = {
    b'zero.tf': '0', b'one.tf': '1', b'two.tf': '2', b'three.tf': '3',
    b'four.tf': '4', b'five.tf': '5', b'six.tf': '6', b'seven.tf': '7',
    b'eight.tf': '8', b'nine.tf': '9',
    b'period': '.', b'comma': ',', b'hyphen': '-', b'slash': '/',
    b'percent': '%', b'parenleft': '(', b'parenright': ')', b'colon': ':',
    b'semicolon': ';', b'equal': '=', b'plus': '+', b'minus': '-',
    b'multiply': 'x', b'degree': '\u00b0', b'fi': 'fi', b'fl': 'fl',
    b'uniFB00': 'ff', b'uniFB03': 'ffi', b'uniFB04': 'ffl', b'endash': '-',
    b'emdash': '--', b'quoteright': "'", b'quoteleft': "'",
    b'quotedblleft': '"', b'quotedblright': '"', b'mu': '\u03bc',
    b'asterisk': '*', b'space': ' ',
}

LIGATURES = {
    '\ufb00': 'ff', '\ufb01': 'fi', '\ufb02': 'fl', '\ufb03': 'ffi',
    '\ufb04': 'ffl', '\ufb05': 'st', '\ufb06': 'st',
}


class PdfFile:
    def __init__(self, path):
        if os.path.getsize(path) > MAX_INPUT_BYTES:
            raise ValueError('input exceeds the 64 MiB limit')
        with open(path, 'rb') as fh:
            self.raw = fh.read()
        if re.search(rb'/Encrypt\b', self.raw):
            raise ValueError('encrypted PDF is not supported; decrypt it first')
        self.objects = {}
        self.stream_cache = {}
        self.cmap_cache = {}
        self._scan_objects()
        self._expand_object_streams()

    def _scan_objects(self):
        for m in OBJ_RE.finditer(self.raw):
            num = int(m.group(1))
            start = m.end()
            end = self.raw.find(b'endobj', start)
            if end < 0:
                continue
            self.objects[num] = self.raw[start:end]

    def _expand_object_streams(self):
        for num in list(self.objects):
            if b'/ObjStm' in self.dict(num):
                self._load_objstm(num)

    def _load_objstm(self, num):
        d = self.dict(num)
        dm = re.search(rb'/N\s+(\d+)', d)
        dfm = re.search(rb'/First\s+(\d+)', d)
        if not dm or not dfm:
            return
        first = int(dfm.group(1))
        data = self.stream(num)
        if not data:
            return
        header = data[:first].split()
        pairs = []
        for i in range(0, (len(header) // 2) * 2, 2):
            try:
                pairs.append((int(header[i]), int(header[i + 1])))
            except ValueError:
                pass
        for idx, (obj_num, off) in enumerate(pairs):
            start = first + off
            end = first + pairs[idx + 1][1] if idx + 1 < len(pairs) else len(data)
            self.objects[obj_num] = data[start:end]

    def dict(self, num):
        body = self.objects.get(num, b'')
        i = body.find(b'stream')
        return body if i < 0 else body[:i]

    def ref(self, d, key):
        m = re.search(re.escape(key.encode()) + rb'\s*(\d+)\s+\d+\s+R', d)
        return int(m.group(1)) if m else None

    def stream(self, num):
        if num in self.stream_cache:
            return self.stream_cache[num]
        body = self.objects.get(num)
        if body is None:
            self.stream_cache[num] = None
            return None
        i = body.find(b'stream')
        if i < 0:
            self.stream_cache[num] = None
            return None
        d = body[:i]
        j = i + 6
        if body[j:j + 2] == b'\r\n':
            j += 2
        elif body[j:j + 1] in (b'\n', b'\r'):
            j += 1
        data = body[j:]
        k = data.rfind(b'endstream')
        if k >= 0:
            data = data[:k]
        while data.endswith(b'\n') or data.endswith(b'\r'):
            data = data[:-1]
        fm = re.search(rb'/Filter\s*(\[[^\]]*\]|/\w+)', d)
        filt = fm.group(1) if fm else b''
        out = data
        if b'FlateDecode' in filt:
            try:
                out = limited_decompress(data)
            except zlib.error:
                try:
                    out = limited_decompress(data)
                except zlib.error:
                    out = None
        self.stream_cache[num] = out
        return out

    def font_cmap(self, font_obj):
        if font_obj in self.cmap_cache:
            return self.cmap_cache[font_obj]
        d = self.dict(font_obj)
        cmap = {}
        tu = self.ref(d, '/ToUnicode')
        if tu is not None:
            cmap = self._parse_cmap(self.stream(tu))
        if not cmap:
            cmap = self._encoding_diff(d)
        self.cmap_cache[font_obj] = cmap
        return cmap

    def _encoding_diff(self, d):
        enc = self.ref(d, '/Encoding')
        if enc is None:
            return {}
        ed = self.dict(enc)
        dm = re.search(rb'/Differences\s*\[(.*?)\]', ed, re.S)
        if not dm:
            return {}
        out = {}
        code = 0
        for tok in re.finditer(rb'(\d+)|/(\w+)', dm.group(1)):
            if tok.group(1):
                code = int(tok.group(1))
            else:
                name = tok.group(2)
                if name in GLYPH_MAP:
                    out[code] = GLYPH_MAP[name]
                elif len(name) == 1:
                    out[code] = name.decode()
                elif re.fullmatch(rb'uni[0-9A-Fa-f]{4}', name):
                    out[code] = chr(int(name[3:], 16))
                code += 1
        return out

    @staticmethod
    def _hex_to_str(hex_bytes):
        try:
            b = bytes.fromhex(hex_bytes.decode())
        except ValueError:
            return ''
        try:
            return b.decode('utf-16-be')
        except UnicodeDecodeError:
            return b.decode('latin1', 'ignore')

    def _parse_cmap(self, data):
        if not data:
            return {}
        cmap = {}
        for blk in re.finditer(rb'beginbfchar(.*?)endbfchar', data, re.S):
            for m in re.finditer(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blk.group(1)):
                cmap[int(m.group(1), 16)] = self._hex_to_str(m.group(2))
        for blk in re.finditer(rb'beginbfrange(.*?)endbfrange', data, re.S):
            body = blk.group(1)
            for m in re.finditer(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', body):
                a, b, c = (int(m.group(i), 16) for i in (1, 2, 3))
                if b - a > 65535:
                    raise ValueError('PDF CMap range exceeds the supported limit')
                for off in range(b - a + 1):
                    cmap[a + off] = chr(c + off)
            for m in re.finditer(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]', body, re.S):
                a = int(m.group(1), 16)
                for off, val in enumerate(re.findall(rb'<([0-9A-Fa-f]+)>', m.group(3))):
                    cmap[a + off] = self._hex_to_str(val)
        return cmap

    def pages(self):
        cat = None
        for num in self.objects:
            if re.search(rb'/Type\s*/Catalog', self.dict(num)):
                cat = num
                break
        found = []
        if cat is not None:
            self._walk(self.ref(self.dict(cat), '/Pages'), found, 0)
        if not found:
            for num in sorted(self.objects):
                if re.search(rb'/Type\s*/Page\b', self.dict(num)):
                    found.append(num)
        return found

    def _walk(self, num, out, depth):
        if num is None or depth > 30:
            return
        d = self.dict(num)
        if re.search(rb'/Type\s*/Pages', d):
            kids = re.search(rb'/Kids\s*\[(.*?)\]', d, re.S)
            if kids:
                for m in re.finditer(rb'(\d+)\s+\d+\s+R', kids.group(1)):
                    self._walk(int(m.group(1)), out, depth + 1)
        elif re.search(rb'/Type\s*/Page\b', d):
            out.append(num)

    def page_fonts(self, page_dict):
        fonts = {}
        m = re.search(rb'/Font\s*<<(.*?)>>', page_dict, re.S)
        if m:
            for x in re.finditer(rb'/(\w+)\s+(\d+)\s+\d+\s+R', m.group(1)):
                fonts[x.group(1).decode()] = self.font_cmap(int(x.group(2)))
        return fonts

    def collect_refs(self, page_dict, key):
        m = re.search(re.escape(key.encode()) + rb'\s*(\[[^\]]*\]|\d+\s+\d+\s+R)', page_dict)
        if not m:
            return []
        return [int(x) for x in re.findall(rb'(\d+)\s+\d+\s+R', m.group(1))]


ESCAPE_MAP = {110: '\n', 114: '\r', 116: '\t', 98: '\b', 102: '\f'}


def unescape_pdf(bs):
    out = bytearray()
    i, n = 0, len(bs)
    while i < n:
        c = bs[i]
        if c == 0x5C and i + 1 < n:
            nxt = bs[i + 1]
            i += 2
            if nxt in ESCAPE_MAP:
                out.extend(ESCAPE_MAP[nxt].encode('latin1'))
            elif 48 <= nxt <= 55:
                oct_s = bytes([nxt])
                while len(oct_s) < 3 and i < n and 48 <= bs[i] <= 55:
                    oct_s += bytes([bs[i]])
                    i += 1
                out.append(int(oct_s, 8))
            elif nxt == 10:
                pass
            else:
                out.append(nxt)
        else:
            out.append(c)
            i += 1
    return bytes(out)


def tokens(data):
    i, n = 0, len(data)
    delim = b' \t\r\n\f\x00'
    stops = b' \t\r\n\f/[]<>(){}'
    while i < n:
        c = data[i:i + 1]
        if c in delim:
            i += 1
            continue
        if c == b'(':
            depth, j, buf = 1, i + 1, []
            while j < n and depth > 0:
                ch = data[j:j + 1]
                if ch == b'\\':
                    buf.append(data[j:j + 2])
                    j += 2
                    continue
                if ch == b'(':
                    depth += 1
                elif ch == b')':
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                buf.append(ch)
                j += 1
            yield ('str', b''.join(buf))
            i = j
            continue
        if c == b'<':
            if data[i:i + 2] == b'<<':
                yield ('op', b'<<')
                i += 2
                continue
            j = data.find(b'>', i)
            if j < 0:
                break
            hx = re.sub(rb'\s', b'', data[i + 1:j])
            try:
                bs = bytes.fromhex(hx.decode() + ('0' if len(hx) % 2 else ''))
            except ValueError:
                bs = b''
            yield ('str', bs)
            i = j + 1
            continue
        if c == b'/':
            j = i + 1
            while j < n and data[j:j + 1] not in stops:
                j += 1
            yield ('name', data[i + 1:j])
            i = j
            continue
        if c == b'%':
            # PDF comments extend to the next line; never interpret their text.
            while i < n and data[i:i + 1] not in (b'\r', b'\n'):
                i += 1
            continue
        if c in b'[]{}>)':
            yield ('op', c)
            i += 1
            continue
        j = i
        while j < n and data[j:j + 1] not in stops:
            j += 1
        tok = data[i:j]
        i = j
        try:
            float(tok)
            yield ('num', tok)
        except ValueError:
            yield ('op', tok)


class PageExtractor:
    """Walks one content stream and rebuilds text with rough line breaks."""

    def __init__(self, fonts):
        self.out = []
        self.stack = []
        self.fonts = fonts
        self.font = None
        self.last_y = None

    def decode(self, bs):
        bs = unescape_pdf(bs)
        cmap = self.fonts.get(self.font) or {}
        chars = []
        for b in bs:
            if cmap:
                chars.append(cmap.get(b, ''))
            elif 32 <= b < 127:
                chars.append(chr(b))
            elif b >= 160:
                chars.append(bytes([b]).decode('latin1'))
        text = ''.join(chars)
        for k, v in LIGATURES.items():
            text = text.replace(k, v)
        return text

    def run(self, data):
        for kind, val in tokens(data):
            if kind != 'op':
                self.stack.append((kind, val))
                continue
            op = val
            if op == b'Tf':
                names = [v for k, v in self.stack if k == 'name']
                if names:
                    self.font = names[-1].decode('latin1')
                self.stack = []
            elif op == b'Tj':
                ss = [v for k, v in self.stack if k == 'str']
                if ss:
                    self.out.append(self.decode(ss[-1]))
                self.stack = []
            elif op == b'TJ':
                for k, v in self.stack:
                    if k == 'str':
                        self.out.append(self.decode(v))
                    elif k == 'num':
                        try:
                            if float(v) < -140:
                                self.out.append(' ')
                        except ValueError:
                            pass
                self.stack = []
            elif op in (b'Td', b'TD'):
                nums = [float(v) for k, v in self.stack if k == 'num']
                if len(nums) >= 2:
                    if abs(nums[1]) > 1.2:
                        self.out.append('\n')
                    elif nums[0] > 1.5:
                        self.out.append(' ')
                self.stack = []
            elif op == b'Tm':
                nums = [float(v) for k, v in self.stack if k == 'num']
                if len(nums) >= 6:
                    y = nums[5]
                    if self.last_y is None or abs(y - self.last_y) > 1.2:
                        self.out.append('\n')
                    self.last_y = y
                self.stack = []
            elif op in (b'T*', b'BT', b'ET'):
                self.out.append('\n')
                self.stack = []

    def text(self):
        t = ''.join(self.out).replace('\u00ad', '')
        t = re.sub(r'[ \t]+', ' ', t)
        t = re.sub(r' *\n *', '\n', t)
        t = re.sub(r'\n{2,}', '\n', t)
        return t.strip()


def parse_page_filter(spec):
    if spec is None:
        return set()
    keep = set()
    for part in spec.split(','):
        part = part.strip()
        if not re.fullmatch(r'[0-9]+(?:-[0-9]+)?', part):
            raise ValueError('--pages must use positive pages, e.g. 1-3,5')
        ends = part.split('-')
        a, b = int(ends[0]), int(ends[-1])
        if a < 1 or b < a or b > 100000:
            raise ValueError('--pages requires 1 <= start <= end <= 100000')
        keep.update(range(a, b + 1))
    return keep


def extract_pdf_pages(path, keep=None):
    """Return ([(page_no, text), ...], total_pages)."""
    pdf = PdfFile(path)
    all_pages = pdf.pages()
    out = []
    for idx, page_num in enumerate(all_pages, 1):
        if keep and idx not in keep:
            continue
        d = pdf.dict(page_num)
        ex = PageExtractor(pdf.page_fonts(d))
        for ref in pdf.collect_refs(d, '/Contents'):
            data = pdf.stream(ref)
            if data:
                ex.run(data)
        out.append((idx, ex.text()))
    return out, len(all_pages)


# ============================================================================
# Part 2 — Word (.docx) engine
# ============================================================================

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
W_P = W + 'p'
W_TBL = W + 'tbl'
W_TR = W + 'tr'
W_TC = W + 'tc'
W_T = W + 't'
W_TAB = W + 'tab'
W_BR = W + 'br'
W_CR = W + 'cr'
W_PPR = W + 'pPr'
W_PSTYLE = W + 'pStyle'
W_OUTLINE = W + 'outlineLvl'
W_VAL = W + 'val'
W_DEL = W + 'del'
W_DELTEXT = W + 'delText'
W_INSTR = W + 'instrText'
W_SDT = W + 'sdt'
W_SDT_CONTENT = W + 'sdtContent'
W_BODY = W + 'body'

HEADING_RE = re.compile(r'(?i)^heading\s*([1-9])$')


def _paragraph_text(p):
    parts = []

    def rec(el):
        for ch in el:
            tag = ch.tag
            if tag == W_T:
                parts.append(ch.text or '')
            elif tag == W_TAB:
                parts.append('\t')
            elif tag in (W_BR, W_CR):
                parts.append('\n')
            elif tag in (W_DEL, W_DELTEXT, W_INSTR):
                continue
            else:
                rec(ch)

    rec(p)
    return ''.join(parts)


def _heading_level(p):
    ppr = p.find(W_PPR)
    level = 0
    if ppr is not None:
        st = ppr.find(W_PSTYLE)
        if st is not None:
            val = st.get(W_VAL) or ''
            m = HEADING_RE.match(val)
            if m:
                level = int(m.group(1))
            elif val in ('Title', 'title'):
                level = 1
        ol = ppr.find(W_OUTLINE)
        if ol is not None and level == 0:
            try:
                level = int(ol.get(W_VAL)) + 1
            except (TypeError, ValueError):
                pass
    return level


def _table_text(tbl):
    rows = []
    for tr in tbl.findall(W_TR):
        cells = []
        for tc in tr.findall(W_TC):
            chunks = []
            for ch in tc:
                if ch.tag == W_P:
                    chunks.append(_paragraph_text(ch))
                elif ch.tag == W_TBL:
                    chunks.append(_table_text(ch))
            cells.append(' '.join(x.strip() for x in chunks if x.strip()))
        rows.append(' | '.join(cells))
    return '\n'.join(rows)


def _iter_blocks(container, out):
    for ch in container:
        if ch.tag == W_P:
            out.append(('p', ch))
        elif ch.tag == W_TBL:
            out.append(('tbl', ch))
        elif ch.tag in (W_SDT, W_SDT_CONTENT):
            _iter_blocks(ch, out)
        elif ch.tag.endswith('}customXml'):
            _iter_blocks(ch, out)


def extract_docx(path, plain=False):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if 'word/document.xml' not in names:
            raise ValueError('not a Word document (missing word/document.xml)')
        info = z.getinfo('word/document.xml')
        if info.file_size > MAX_EXPANDED_BYTES:
            raise ValueError('Word document.xml exceeds the 32 MiB limit')
        xml = z.read(info)
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', xml, re.I):
        raise ValueError('DTD and entity declarations are not supported')
    root = ET.fromstring(xml)
    body = root.find(W_BODY)
    if body is None:
        raise ValueError('not a Word document (missing w:body)')
    blocks = []
    _iter_blocks(body, blocks)

    lines = []
    headings = []
    n_tables = 0
    for kind, el in blocks:
        if kind == 'p':
            txt = _paragraph_text(el).strip()
            lvl = _heading_level(el)
            if lvl:
                headings.append((lvl, txt))
                if lines and lines[-1] != '':
                    lines.append('')
                lines.append(('' if plain else '#' * min(lvl, 6) + ' ') + txt)
                lines.append('')
            else:
                lines.append(txt)
        else:
            n_tables += 1
            if lines and lines[-1] != '':
                lines.append('')
            lines.append(_table_text(el))
            lines.append('')

    text = '\n'.join(lines)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip(), {
        'tables': n_tables,
        'paragraphs': sum(1 for k, _ in blocks if k == 'p'),
        'headings': headings,
    }


# ============================================================================
# Part 3 — token-saving utilities
# ============================================================================

def estimate_tokens(text):
    """Rough token estimate: CJK chars ~1 token, other chars ~4 per token."""
    if not text:
        return 0
    cjk = 0
    for ch in text:
        o = ord(ch)
        if (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF
                or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF):
            cjk += 1
    return int(round(cjk + (len(text) - cjk) / 4.0))


def lean_text(text, pdf_markers=False):
    """Trim output overhead, preserving body lines, order and indentation.

    This never removes repeated content, references, numbers or units.
    PDF page metadata is shortened only when page markers are enabled.
    """
    lines = []
    for line in text.split('\n'):
        if not line.strip():
            continue
        if pdf_markers:
            match = re.fullmatch(r'===== PAGE ([0-9]+) =====', line)
            if match:
                line = '[p%s]' % match.group(1)
        lines.append(line.rstrip(' \t\r'))
    return '\n'.join(lines)


PAGE_NO_RE = re.compile(r'^\s*(?:page\s*)?\d{1,4}\s*$', re.I)


def compact_page_texts(texts):
    """Drop repeated lines (headers/footers/watermarks), page numbers, fix hyphen breaks."""
    n = len(texts)
    freq = Counter()
    for t in texts:
        seen = set()
        for line in t.split('\n'):
            s = line.strip()
            if len(s) >= 15 and s not in seen:
                seen.add(s)
                freq[s] += 1
    thresh = max(3, int(n * 0.5))
    repeated = {s for s, c in freq.items() if c >= thresh}

    out = []
    for t in texts:
        kept = []
        for line in t.split('\n'):
            s = line.strip()
            if s in repeated or PAGE_NO_RE.match(s):
                continue
            kept.append(line)
        t2 = '\n'.join(kept)
        t2 = re.sub(r'-\n(?=[a-z])', '', t2)      # re-join hyphenated line breaks
        t2 = re.sub(r'\n{3,}', '\n\n', t2)
        out.append(t2.strip())
    return out


def compact_text(text):
    text = re.sub(r'-\n(?=[a-z])', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


REF_RE = re.compile(
    r'^\s*#*\s*(references|bibliography|references and notes|reference|参考文献)\s*$', re.I)
REF_ENTRY_RE = re.compile(r'^\s*\[\d{1,3}\]\s+\S')


def strip_references(text):
    """Cut the reference list: by heading first, else by a run of [n] entries."""
    lines = text.split('\n')
    n = len(lines)
    for i, line in enumerate(lines):
        if i > n * 0.4 and REF_RE.match(line.strip()):
            return '\n'.join(lines[:i]).rstrip()

    # numeric style without an extractable heading: find the first "[1]" in the
    # second half, then require a few more [n] entries nearby (continuation
    # lines between entries are allowed).
    for i in range(int(n * 0.5), n):
        if re.match(r'^\s*\[1\]\s+\S', lines[i].strip()):
            window = lines[i:i + 80]
            count = sum(1 for line in window if REF_ENTRY_RE.match(line.strip()))
            if count >= 3:
                return '\n'.join(lines[:i]).rstrip()
            break
    return text


# -- PDF outline heuristic ---------------------------------------------------

OUTLINE_DROP = re.compile(
    r'^\s*(figure|fig\.|table|scheme|supplementary|movie|research article|'
    r'original article|communication|review)\b', re.I)
OUTLINE_KNOWN = re.compile(
    r'^(abstract|introduction|experimental(\s+section)?|materials and methods|'
    r'methods|results(\s+and\s+discussion)?|discussion|conclusions?|references|'
    r'acknowledg(e)?ments?|keywords|supporting information|appendix|'
    r'author contributions)\s*:?\s*$',
    re.I)
OUTLINE_NUM = re.compile(r'^(\d+(?:\.\d+){0,3})\.?\s+[A-Z]')
OUTLINE_ALLCAPS = re.compile(r'^[A-Z][A-Z0-9 ,\-/&():]{5,70}$')
HEADING_STOPWORDS = {
    'of', 'and', 'in', 'on', 'for', 'the', 'to', 'with', 'by', 'from', 'as',
    'within', 'at', 'a', 'an', 'or', 'vs', 'versus', 'into', 'over', 'via',
    'under', 'between', 'through', 'toward', 'towards', 'using', 'based'}


def _looks_like_pdf_heading(s):
    """Heuristic heading test tuned for journal PDFs (avoids body sentences)."""
    if not s or len(s) > 95 or OUTLINE_DROP.match(s):
        return False
    m = OUTLINE_NUM.match(s)
    if m:
        first = m.group(1).split('.')[0]
        try:
            fnum = int(first)
        except ValueError:
            fnum = 999
        if fnum > 99:                     # years, values, page numbers
            return False
        rest = re.sub(r'^[\s.)\]]+', '', s[m.end(1):]).strip()
        words = [w for w in re.split(r'\s+', rest) if w]
        if not words:
            return False
        caps = sum(1 for w in words if w[:1].isupper())
        # reject data-bearing lines such as "0.75 KPP at 7.8, 8.2, and 9.7"
        if rest.count(',') >= 2:
            return False
        if sum(1 for w in words if re.match(r'^[\d.]+$', w)) > 1:
            return False
        # Title-case check: every lowercase word must be a connector word
        bad = [w for w in words
               if w[:1].islower() and w.strip('.,;:()[]-–').lower() not in HEADING_STOPWORDS]
        if not bad:
            return True
        return False
    if OUTLINE_KNOWN.match(s) and len(s) <= 70:
        return True
    if OUTLINE_ALLCAPS.match(s) and len(s.split()) <= 9:
        return True
    return False


def pdf_outline(pages):
    items = []
    seen = set()
    for n, t in pages:
        for raw in t.split('\n'):
            s = raw.strip()
            if not _looks_like_pdf_heading(s):
                continue
            key = (n, s)
            if key in seen:
                continue
            seen.add(key)
            items.append((n, s))
    return items


# -- grep --------------------------------------------------------------------

def grep_text(text, pattern, before=0, after=4, ignore_case=True, max_matches=20):
    rx = re.compile(pattern, re.I if ignore_case else 0)
    lines = text.split('\n')
    markers = [(i, line) for i, line in enumerate(lines)
               if line.startswith('===== PAGE ')]
    hits = [i for i, line in enumerate(lines) if rx.search(line)]
    blocks = []
    used = 0
    for i in hits:
        if used >= max_matches:
            break
        a = max(0, i - before)
        b = min(len(lines), i + after + 1)
        if blocks and a <= blocks[-1][1]:
            blocks[-1] = (blocks[-1][0], max(blocks[-1][1], b))
        else:
            blocks.append((a, b))
        used += 1
    out = []
    for idx, (a, b) in enumerate(blocks):
        if idx:
            out.append('\n--')
        # keep the page marker so matches stay citable ("page N")
        marker = None
        for mi, ml in markers:
            if mi <= a:
                marker = (mi, ml)
            else:
                break
        if marker and not (a <= marker[0] < b):
            out.append(marker[1])
        out.extend(lines[a:b])
    return '\n'.join(out), len(hits), len(blocks)


# ============================================================================
# Part 4 — dispatcher
# ============================================================================

PDF_MAGIC = b'%PDF'
ZIP_MAGIC = b'PK\x03\x04'
OLE_MAGIC = b'\xd0\xcf\x11\xe0'

DOC_EXTS = {'.doc'}
DOCX_EXTS = {'.docx', '.docm', '.dotx', '.dotm'}
TEXT_EXTS = {'.txt', '.md', '.markdown', '.csv', '.tsv', '.log', '.json', '.yaml', '.yml'}

DOC_HELP = (
    'ERROR: .doc (Word 97-2003 binary format) is not supported by this '
    'stdlib-only extractor.\n'
    '  Fix: open it in Word and "Save As" .docx, then run this script again.\n'
    '  Windows + Word installed? See references/troubleshooting.md for a '
    'Word COM one-liner that converts .doc -> .docx/.txt.')


def sniff(path):
    try:
        with open(path, 'rb') as fh:
            head = fh.read(8)
    except OSError:
        return None
    if head.startswith(PDF_MAGIC):
        return 'pdf'
    if head.startswith(ZIP_MAGIC):
        return 'docx'
    if head.startswith(OLE_MAGIC):
        return 'ole'
    return None


def detect_kind(path):
    ext = os.path.splitext(path)[1].lower()
    kind = sniff(path)
    if ext == '.pdf':
        return 'pdf'
    if ext in DOCX_EXTS:
        return 'doc' if kind == 'ole' else 'docx'
    if ext in DOC_EXTS:
        return 'docx' if kind == 'docx' else 'doc'
    if ext in TEXT_EXTS:
        return 'text'
    if kind == 'pdf':
        return 'pdf'
    if kind == 'docx':
        return 'docx'
    if kind == 'ole':
        return 'doc'
    return None


def _emit_text(text):
    stream = getattr(sys.stdout, 'buffer', None)
    if stream is not None:
        stream.write(text.encode('utf-8', 'replace'))
        stream.flush()
    else:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except UnicodeEncodeError:
            sys.stdout.write(text.encode('ascii', 'replace').decode('ascii'))
            sys.stdout.flush()


def _read_text_file(path):
    with open(path, 'rb') as fh:
        raw = fh.read()
    for enc in ('utf-8-sig', 'utf-8', 'gb18030', 'latin1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def _render_pages(pages, marker=True, compact=False, drop_refs=False):
    texts = [t for _, t in pages]
    if compact:
        texts = compact_page_texts(texts)
    parts = []
    for (n, _), t in zip(pages, texts):
        if marker:
            parts.append('\n===== PAGE %d =====\n' % n)
        parts.append(t)
        parts.append('\n')
    text = ''.join(parts)
    if drop_refs:
        text = strip_references(text)
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Zero-dependency text extractor for PDF and Word (.docx), '
                    'with token-saving outline / grep / compact modes.')
    ap.add_argument('path', help='input file (.pdf / .docx / .txt ...)')
    ap.add_argument('--pages', help='PDF only: page selection, e.g. "1-3,5"')
    ap.add_argument('--no-page-marker', action='store_true',
                    help='PDF only: omit "===== PAGE n =====" markers')
    ap.add_argument('--plain', action='store_true',
                    help='Word only: do not prefix headings with "#"')
    ap.add_argument('--outline', action='store_true',
                    help='print only the structure map (headings + page numbers)')
    ap.add_argument('--grep', metavar='PATTERN',
                    help='print matching lines with context instead of the whole text')
    ap.add_argument('-A', '--after', type=int, default=4,
                    help='grep: context lines after a match (default 4)')
    ap.add_argument('-B', '--before', type=int, default=0,
                    help='grep: context lines before a match (default 0)')
    ap.add_argument('-c', '--case-sensitive', action='store_true',
                    help='grep: match case (default is case-insensitive)')
    ap.add_argument('-m', '--max-matches', type=int, default=20,
                    help='grep: maximum matched blocks (default 20)')
    ap.add_argument('--compact', action='store_true',
                    help='drop repeated headers/footers/watermarks and page numbers, '
                         'join hyphenated line breaks, collapse blank lines')
    ap.add_argument('--lean', action='store_true',
                    help='remove blank lines and routine summaries; shorten PDF '
                         'page markers to [pN]; keep body text and warnings')
    ap.add_argument('--drop-refs', action='store_true',
                    help='cut the reference list')
    ap.add_argument('--max-chars', type=int, default=0,
                    help='hard cap on printed characters (0 = no cap)')
    ap.add_argument('--stats', action='store_true',
                    help='print per-page character/token stats to stderr')
    ap.add_argument('--version', action='version',
                    version='thesis-analysis-extract 1.1.0')
    args = ap.parse_args(argv)

    def report(*values):
        if not args.lean:
            print(*values, file=sys.stderr)

    if min(args.before, args.after, args.max_chars) < 0 or args.max_matches < 1:
        ap.error('context and character limits must be nonnegative; matches must be positive')
    if args.grep:
        try:
            re.compile(args.grep)
        except re.error as exc:
            print('ERROR: bad --grep pattern: %s' % exc, file=sys.stderr)
            return 2

    if args.outline and args.grep:
        print('NOTE: both --outline and --grep given; --grep takes precedence.',
              file=sys.stderr)

    path = args.path
    if not os.path.isfile(path):
        print('ERROR: input not found: %s' % path, file=sys.stderr)
        return 2

    kind = detect_kind(path)
    if kind is None:
        print('ERROR: unsupported file type: %s' % path, file=sys.stderr)
        return 2
    if kind == 'doc':
        print(DOC_HELP, file=sys.stderr)
        return 2
    if kind != 'pdf' and args.outline and not args.grep and kind != 'docx':
        print('ERROR: --outline supports PDF and Word only', file=sys.stderr)
        return 2

    raw_chars = None
    try:
        if os.path.getsize(path) > MAX_INPUT_BYTES:
            raise ValueError('input exceeds the 64 MiB limit')
        if kind == 'pdf':
            keep = parse_page_filter(args.pages)
            pages, total = extract_pdf_pages(path, keep)
            raw_chars = sum(len(t) for _, t in pages)
            if not pages:
                print('ERROR: no pages found', file=sys.stderr)
                return 2

            if args.outline and not args.grep:
                items = pdf_outline(pages)
                text = '\n'.join('p%-3d %s' % (n, s) for n, s in items)
                report('\n--- outline: %d headings | %d pages total ---'
                       % (len(items), total))
            else:
                text = _render_pages(pages, marker=not args.no_page_marker,
                                     compact=args.compact, drop_refs=args.drop_refs)
                if args.grep:
                    text, n_hits, n_blocks = grep_text(
                        text, args.grep, before=args.before, after=args.after,
                        ignore_case=not args.case_sensitive, max_matches=args.max_matches)
                    report('\n--- grep: %d hits in %d blocks (of %d pages) ---'
                           % (n_hits, n_blocks, len(pages)))
                else:
                    report('\n--- pages: %d/%d | chars: %d | ~%d tokens ---'
                           % (len(pages), total, len(text), estimate_tokens(text)))
                if args.stats:
                    per = []
                    for n, t in pages:
                        per.append('  page %-3d chars %-6d ~%-5d tokens%s'
                                   % (n, len(t), estimate_tokens(t),
                                      '  <-- likely image-only' if len(t) < 80 else ''))
                    print('\n'.join(per), file=sys.stderr)
        elif kind == 'docx':
            if args.pages:
                print('NOTE: --pages applies to PDF only; ignored for Word.', file=sys.stderr)
            text, meta = extract_docx(path, plain=args.plain)
            raw_chars = len(text)
            if args.compact:
                text = compact_text(text)
            if args.drop_refs:
                text = strip_references(text)
            if args.outline and not args.grep:
                text = '\n'.join('#' * min(l, 6) + ' ' + t for l, t in meta['headings'])
                report('\n--- outline: %d headings ---' % len(meta['headings']))
            elif args.grep:
                text, n_hits, n_blocks = grep_text(
                    text, args.grep, before=args.before, after=args.after,
                    ignore_case=not args.case_sensitive, max_matches=args.max_matches)
                report('\n--- grep: %d hits in %d blocks ---' % (n_hits, n_blocks))
            else:
                report('\n--- word: %d paragraphs, %d tables | chars: %d | ~%d tokens ---'
                       % (meta['paragraphs'], meta['tables'], len(text),
                          estimate_tokens(text)))
        else:
            text = _read_text_file(path)
            raw_chars = len(text)
            if args.compact:
                text = compact_text(text)
            if args.drop_refs:
                text = strip_references(text)
            if args.grep:
                text, n_hits, n_blocks = grep_text(
                    text, args.grep, before=args.before, after=args.after,
                    ignore_case=not args.case_sensitive, max_matches=args.max_matches)
                report('\n--- grep: %d hits in %d blocks ---' % (n_hits, n_blocks))
            else:
                report('\n--- text: chars: %d | ~%d tokens ---'
                       % (len(text), estimate_tokens(text)))
    except zipfile.BadZipFile:
        print('ERROR: file is not a valid .docx (encrypted or corrupted). '
              'Word-encrypted documents are not supported; decrypt first.', file=sys.stderr)
        return 2
    except re.error as exc:
        print('ERROR: bad --grep pattern: %s' % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - surface a usable message
        print('ERROR: failed to parse %s: %s' % (path, exc), file=sys.stderr)
        return 2

    if args.lean:
        text = lean_text(text, pdf_markers=(kind == 'pdf'
                                          and (not args.outline or bool(args.grep))
                                          and not args.no_page_marker))

    if args.max_chars and len(text) > args.max_chars:
        cut = args.max_chars
        text = text[:cut]
        print('\n--- truncated to %d chars (~%d tokens) ---' % (cut, estimate_tokens(text)),
              file=sys.stderr)

    _emit_text(text)

    if kind in ('pdf', 'docx') and (raw_chars or 0) < 50:
        print('WARNING: almost no text found. For PDFs this usually means a '
              'scanned/image-only file (use OCR); for Word, check for '
              'unusual structures (text boxes, altChunk).', file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BrokenPipeError:
        os._exit(0)
