"""Номера автонумерации Word: [(номер|None, текст)] для абзацев тела (в т.ч. в ячейках таблиц).

python3 docx_numbering.py <file.docx> [--check-pdf <эталон.pdf>]
"""
import sys, re
import docx
from docx.oxml.ns import qn

P, TBL, T = qn('w:p'), qn('w:tbl'), qn('w:t')
VAL = qn('w:val')
RU = 'абвгдежзийклмнопрстуфхцчшщъыьэюя'


def _val(el, tag):
    c = el.find(qn(tag)) if el is not None else None
    return c.get(VAL) if c is not None else None


def _fmt(n, f):
    if f in ('decimal', 'decimalZero'):
        return ('0%d' % n if f == 'decimalZero' and n < 10 else str(n))
    if f in ('lowerLetter', 'upperLetter'):
        s = ''
        m = n
        while m > 0:
            m, r = divmod(m - 1, 26)
            s = chr(97 + r) + s
        return s.upper() if f == 'upperLetter' else s
    if f in ('lowerRoman', 'upperRoman'):
        s = ''
        m = n
        for v, r in ((1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'), (100, 'c'), (90, 'xc'), (50, 'l'),
                     (40, 'xl'), (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i')):
            while m >= v:
                s += r; m -= v
        return s.upper() if f == 'upperRoman' else s
    if f in ('russianLower', 'russianUpper'):
        s = RU[(n - 1) % len(RU)] * ((n - 1) // len(RU) + 1)
        return s.upper() if f == 'russianUpper' else s
    return str(n)


class Numbering:
    def __init__(self, d):
        self.styles = {}
        for s in d.styles.element.findall(qn('w:style')):
            self.styles[s.get(qn('w:styleId'))] = s
        root = d.part.numbering_part.element if d.part.package and _has_numbering(d) else None
        self.abs, self.num = {}, {}
        if root is not None:
            for a in root.findall(qn('w:abstractNum')):
                self.abs[a.get(qn('w:abstractNumId'))] = {l.get(qn('w:ilvl')): l for l in a.findall(qn('w:lvl'))}
            for n in root.findall(qn('w:num')):
                nid = n.get(qn('w:numId'))
                ov = {o.get(qn('w:ilvl')): o for o in n.findall(qn('w:lvlOverride'))}
                self.num[nid] = (_val(n, 'w:abstractNumId'), ov)
        self.cnt = {}    # abstractNumId -> {ilvl:int -> count}
        self.seen = set()  # (numId, ilvl) с применённым startOverride

    def style_numpr(self, sid):
        """(numId, ilvl) из стиля и цепочки basedOn."""
        num = lvl = None
        seen = set()
        while sid and sid in self.styles and sid not in seen:
            seen.add(sid)
            st = self.styles[sid]
            np_ = st.find(qn('w:pPr') + '/' + qn('w:numPr'))
            if np_ is not None:
                if num is None: num = _val(np_, 'w:numId')
                if lvl is None: lvl = _val(np_, 'w:ilvl')
            sid = _val(st, 'w:basedOn')
        return num, lvl

    def lvl_def(self, nid, il):
        a, ov = self.num[nid]
        o = ov.get(str(il))
        if o is not None and o.find(qn('w:lvl')) is not None:
            return o.find(qn('w:lvl'))
        return self.abs.get(a, {}).get(str(il))

    def start_of(self, nid, il):
        o = self.num[nid][1].get(str(il))
        if o is not None and _val(o, 'w:startOverride') is not None:
            return int(_val(o, 'w:startOverride'))
        ld = self.lvl_def(nid, il)
        s = _val(ld, 'w:start') if ld is not None else None
        return int(s) if s is not None else 1

    def number(self, p):
        ppr = p.find(qn('w:pPr'))
        nid = il = None
        if ppr is not None:
            np_ = ppr.find(qn('w:numPr'))
            if np_ is not None:
                nid, il = _val(np_, 'w:numId'), _val(np_, 'w:ilvl')
            sn, sl = self.style_numpr(_val(ppr, 'w:pStyle'))
        else:
            sn, sl = self.style_numpr(None)
        nid = nid if nid is not None else sn
        il = int(il if il is not None else (sl or 0))
        if nid in (None, '0') or nid not in self.num:
            return None
        a = self.num[nid][0]
        ld = self.lvl_def(nid, il)
        if ld is None:
            return None
        c = self.cnt.setdefault(a, {})
        key = (nid, il)
        ov = self.num[nid][1].get(str(il))
        if key not in self.seen and ov is not None and _val(ov, 'w:startOverride') is not None:
            c[il] = self.start_of(nid, il)
        elif il in c:
            c[il] += 1
        else:
            c[il] = self.start_of(nid, il)
        self.seen.add(key)
        for m in list(c):                       # сброс нижних уровней
            if m > il:
                r = _val(self.lvl_def(nid, m), 'w:lvlRestart')
                if r is None or (r != '0' and il <= int(r) - 1):
                    del c[m]
        if _val(ld, 'w:numFmt') in ('bullet', 'none'):
            return None
        legal = ld.find(qn('w:isLgl')) is not None

        def sub(m):
            k = int(m.group(1)) - 1
            f = _val(self.lvl_def(nid, k), 'w:numFmt') if self.lvl_def(nid, k) is not None else 'decimal'
            return _fmt(c.get(k, self.start_of(nid, k)), 'decimal' if legal else f)
        return re.sub(r'%(\d)', sub, _val(ld, 'w:lvlText') or '')


def _has_numbering(d):
    try:
        d.part.numbering_part
        return True
    except Exception:
        return False


def numbered_paragraphs(path):
    d = docx.Document(path)
    nb = Numbering(d)
    out = []
    for el in d.element.body.iterchildren():
        paras = [el] if el.tag == P else list(el.iter(P)) if el.tag == TBL else []
        for p in paras:
            num = nb.number(p)   # счётчики двигает и пустой абзац
            t = ''.join(x.text or '' for x in p.iter(T)).strip()
            if t:
                out.append((num, t))
    return out


def norm(s):
    return ' '.join(re.sub(r'[^0-9a-zа-я]+', ' ', s.lower().replace('ё', 'е')).split())


def check_pdf(items, pdf):
    import fitz
    text = ' ' + norm(' '.join(pg.get_text() for pg in fitz.open(pdf))) + ' '
    groups = {'цифры с точками': [0, 0], 'прочие (1), а) и т.п.)': [0, 0]}
    bad = []
    for num, t in items:
        if not num:
            continue
        g = groups['цифры с точками' if re.fullmatch(r'\d+(\.\d+)*\.?', num) else 'прочие (1), а) и т.п.)']
        g[0] += 1
        if ' ' + norm(num) + ' ' + ' '.join(norm(t).split()[:4]) in text:
            g[1] += 1
        else:
            bad.append((num, t[:60]))
    for k, (tot, ok) in groups.items():
        print(f'{k}: нумерованных {tot}, подтверждено {ok}, доля {ok / max(tot, 1):.1%}')
    for n, t in bad[:15]:
        print('  НЕТ:', n, '|', t)


if __name__ == '__main__':
    items = numbered_paragraphs(sys.argv[1])
    if '--check-pdf' in sys.argv:
        check_pdf(items, sys.argv[sys.argv.index('--check-pdf') + 1])
    else:
        for n, t in items:
            print(n or '-', '|', t[:80])
