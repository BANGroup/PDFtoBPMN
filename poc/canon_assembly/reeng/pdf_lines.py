"""Строки эталона, которых нет ни в одном Word-файле документа (класс B: Word в Lotus расходится с утверждённым PDF) -> текст из PDF (A2, круг 2).

scan(sd, canon_text, canon_docx, srcs) -> verify_canon-miss строки с классом: 'B' (нет ни в одном Word), 'A' (в Word есть, в канон не встала),
'variant' (отличие только буквой ѐ/ѝ/ё), 'hf' (в колонтитуле/сноске Word). Вставляются только 'B'.
"""
import os, re, sys, glob, zipfile, json, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lxml import etree
import pagediff as P
import missing_pages as MP

W = P.W
VAR = str.maketrans({'ѐ': 'е', 'ѝ': 'и', 'Ѐ': 'е', 'Ѝ': 'и', 'ё': 'е', 'Ё': 'е'})


def nk(s): return P.key(unicodedata.normalize('NFC', s).translate(VAR))   # NFC: Word хранит «й» как «и»+U+0306, PDF — одним знаком


def word_text(files):
    """(текст всех XML-частей Word: тело, колонтитулы, сноски, надписи; текст только колонтитулов/сносок)."""
    body, hf = [], []
    for f in files:
        if not f.lower().endswith('.docx') or not os.path.exists(f): continue
        try: z = zipfile.ZipFile(f)
        except Exception: continue
        for n in z.namelist():
            if not (n.startswith('word/') and n.endswith('.xml')): continue
            try: r = etree.fromstring(z.read(n))
            except Exception: continue
            t = ''.join(x.text or '' for x in r.iter(W + 't'))
            (body if n == 'word/document.xml' else hf).append(t)
    return ' '.join(body + hf), ' '.join(hf)


def sources_of(sd):
    """Word-файлы документа (база, листы замены; .doc — из кэша doc2docx, без Word)."""
    import doc2docx
    out = []
    for f in sorted(glob.glob(sd + '/word/*') + glob.glob(sd + '/amendments/**/*', recursive=True)):
        if f.lower().endswith('.docx'): out.append(f)
        elif f.lower().endswith('.doc'):
            c = doc2docx.cached(f)
            if c and not os.path.exists(f + 'x'): out.append(c)
    return out


def _garbage_ocr(l):
    """Строка скана с битым распознаванием (латиница вместо кириллицы с «шумом»): II/Jr/crpa и т.п."""
    lat = len(re.findall(r'[A-Za-z]', l)); cyr = len(re.findall(r'[А-Яа-яЁё]', l))
    return lat >= 8 and cyr == 0 and bool(re.search(r'[^\w\s.,()\-«»:;/]|II|Jr|\b[a-z]{1,2}\b.*\b[a-z]{1,2}\b', l))


def classify(lines, sd):
    """lines [(метка, строка)] -> [{'label','text','cls'}]: B — нет ни в одном Word; A — есть (точно); variant — только после замены ѐ/ѝ/ё; hf — в колонтитуле/сноске."""
    allt, hft = word_text(sources_of(sd))
    raw_all, norm_all, norm_hf = P.key(allt), nk(allt), nk(hft)
    out = []
    for lab, l in lines:
        t = P.LIST_MARK.sub('', l); k = nk(t)
        if _garbage_ocr(l): c = 'garbage'
        elif k in norm_hf: c = 'hf'
        elif P.key(t) in raw_all: c = 'A'
        elif k in norm_all: c = 'variant'
        else: c = 'B'
        out.append({'label': lab, 'text': l, 'cls': c})
    return out


def scan(sd, canon_text, canon_docx, srcs=None):
    r, _ = MP.by_page(sd, canon_text, canon_docx, srcs or sources_of(sd))
    return r, classify(r['_miss_real'], sd)


if __name__ == '__main__':
    sd, ct, cd = sys.argv[1:4]
    r, o = scan(sd, ct, cd)
    print(json.dumps({'lines': r['lines'], 'missing': r['missing'], 'items': o}, ensure_ascii=False))


# ======================================================================= вставка строк PDF в канон (A2, круг 2)
import copy, bisect, difflib
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import pdf_frag as F
import pynum

XMLSP = '{http://www.w3.org/XML/1998/namespace}space'
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'


def _skip(t):
    """w:t внутри надписи/fallback в поток не входит (как pynum.para_text)."""
    a = t.getparent()
    while a is not None:
        if a.tag in (W + 'txbxContent', MC + 'Fallback', W + 'del'): return True
        a = a.getparent()
    return False


def ptext_runs(p):
    """[(w:t, text)] абзаца в порядке документа."""
    return [(t, t.text or '') for t in p.iter(W + 't') if not _skip(t)]


class Canon:
    """Поток key-текста абзацев канона (по порядку документа) и позиции -> (абзац, смещение символа)."""
    def __init__(self, d):
        self.d = d
        self.paras = [p for kind, p in pynum.walk_paras(d.element.body) if kind == 'p']
        self.texts = [''.join(x for _, x in ptext_runs(p)) for p in self.paras]
        self.keys = [P.key(t) for t in self.texts]
        self.offs, o = [], 0
        for k in self.keys: self.offs.append(o); o += len(k)
        self.S = ''.join(self.keys)

    def occ(self, k, lo=0, hi=None, cap=60):
        out, p = [], self.S.find(k, lo, hi if hi is not None else len(self.S))
        while p != -1 and len(out) < cap:
            out.append(p); p = self.S.find(k, p + 1, hi if hi is not None else len(self.S))
        return out

    def where(self, pos, end=False):
        """Позиция в потоке -> (индекс абзаца, смещение символа в тексте абзаца). end=True: позиция — конец строки (при границе абзацев берётся конец предыдущего)."""
        i = bisect.bisect_right(self.offs, pos - 1 if end else pos) - 1
        i = max(i, 0); kin = pos - self.offs[i]
        t = self.texts[i]; n = 0
        if kin <= 0: return i, 0
        for ci, c in enumerate(t):
            if P.key(c): n += 1
            if n == kin: return i, ci + 1
        return i, len(t)


def _run_split(p, off):
    """Граница символа off в тексте абзаца: возвращает (run, 'after') — новый элемент вставлять после run; разрезает w:t при необходимости. None, если нельзя."""
    pos = 0; last = None
    for t, x in ptext_runs(p):
        r = t.getparent()
        if r.tag != W + 'r': continue
        if pos + len(x) < off: pos += len(x); last = r; continue
        if off - pos <= 0:
            return (last, 'after') if last is not None else (r, 'before')
        if off - pos >= len(x): return r, 'after'
        # режем w:t, если он единственный текстовый у прогона
        if len(r.findall(W + 't')) != 1: return None
        k = off - pos
        r2 = copy.deepcopy(r)
        t.text = x[:k]; t.set(XMLSP, 'preserve')
        t2 = r2.find(W + 't'); t2.text = x[k:]; t2.set(XMLSP, 'preserve')
        r.addnext(r2)
        return r, 'after'
    return (last, 'after') if last is not None else None


def _new_run(like, text):
    r = OxmlElement('w:r')
    rpr = like.find(W + 'rPr') if like is not None else None
    if rpr is not None: r.append(copy.deepcopy(rpr))
    t = OxmlElement('w:t'); t.text = text; t.set(XMLSP, 'preserve'); r.append(t)
    return r


def _bookmark(el_first, el_last, bid, name):
    s = OxmlElement('w:bookmarkStart'); s.set(qn('w:id'), str(bid)); s.set(qn('w:name'), name)
    e = OxmlElement('w:bookmarkEnd'); e.set(qn('w:id'), str(bid))
    el_first.addprevious(s); el_last.addnext(e)


def inline_insert(p, off, text, bid, name):
    """Вставка текста PDF в абзац p на символьное смещение off (прогон копирует rPr соседнего)."""
    full = ''.join(x for _, x in ptext_runs(p))
    pre = ' ' if (off > 0 and off <= len(full) and not full[off - 1].isspace() and not text[:1].isspace()) else ''
    post = ' ' if (off < len(full) and not full[off].isspace() and full[off] not in ',.;:)»' ) else ''
    sp = _run_split(p, off)
    if sp is None: return False
    r0, mode = sp
    like = r0
    nr = _new_run(like, pre + text + post)
    if mode == 'after': r0.addnext(nr)
    else: r0.addprevious(nr)
    _bookmark(nr, nr, bid, name)
    return True


def new_paragraph(like_p, text, where_el, after, bid, name, numpr=None):
    """Новый абзац (pPr копия like_p без нумерации/раздела, rPr первого прогона) после/перед where_el."""
    p = OxmlElement('w:p')
    ppr = like_p.find(W + 'pPr')
    if ppr is not None:
        ppr = copy.deepcopy(ppr)
        for tag in ('numPr', 'sectPr'):
            for e in ppr.findall(W + tag): ppr.remove(e)
        p.append(ppr)
    like_run = next((r for r in like_p.iter(W + 'r') if r.find(W + 't') is not None), None)
    r = _new_run(like_run, text); p.append(r)
    if numpr is not None:
        pp = p.find(W + 'pPr')
        if pp is None: pp = OxmlElement('w:pPr'); p.insert(0, pp)
        pp.append(numpr)
    (where_el.addnext if after else where_el.addprevious)(p)
    _bookmark(r, r, bid, name)
    return p


def _lk(line):
    m = F.marker(line, False)
    t = m[2] if m else line
    return P.key(P.LIST_MARK.sub('', t))


def delete_chars(p, off0, off1):
    """Удалить символы [off0, off1) текста абзаца (только целые прогоны после разрезания). -> (ok, прогон-образец rPr)."""
    if off1 <= off0: return True, None
    if _run_split(p, off1) is None or _run_split(p, off0) is None: return False, None
    pos = 0; like = None; rm = []
    for t, x in ptext_runs(p):
        r = t.getparent(); n = len(x)
        if r.tag != W + 'r' or len(r.findall(W + 't')) != 1: pos += n; continue
        if pos >= off0 and pos + n <= off1: rm.append(r)
        pos += n
    for r in rm:
        if like is None: like = r
        r.getparent().remove(r)
    return True, like


def _liveify(p, lists):
    """Абзац с набранным номером «7.2.5 Текст» (после правки verify сочтёт его замороженным) -> живая нумерация; набранный номер из текста убирается."""
    txt = ''.join(x for _, x in ptext_runs(p))
    m = re.match(r'\s*(\d{1,3}(?:\.\d{1,3}){1,7})\.?\s+', txt)
    ppr = p.find(W + 'pPr')
    if not m: return False
    if ppr is not None and ppr.find(W + 'numPr') is not None and ppr.find(W + 'numPr/' + W + 'numId').get(qn('w:val')) != '0':
        # абзац уже в списке (нумерация соседа): набранный номер в тексте дублировал бы живой («6.3 6.3 Текст», КД-РД-Б5.009-01) — убираем его, номер выровняет numfix
        return delete_chars(p, 0, m.end())[0]
    ok, _ = delete_chars(p, 0, m.end())
    if not ok: return False
    ppr = p.find(W + 'pPr')
    if ppr is None: ppr = OxmlElement('w:pPr'); p.insert(0, ppr)
    for e in ppr.findall(W + 'numPr'): ppr.remove(e)
    np_ = OxmlElement('w:numPr')
    e = OxmlElement('w:ilvl'); e.set(qn('w:val'), str(m.group(1).count('.'))); np_.append(e)
    e = OxmlElement('w:numId'); e.set(qn('w:val'), str(lists.get('dec', 'ru'))); np_.append(e)
    pos = 0
    for i, ch in enumerate(ppr):
        if etree.QName(ch).localname in ('pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl'): pos = i + 1
    ppr.insert(pos, np_)
    return True


def _decimal_num(d, parts):
    """Новый десятичный список со стартами parts (подпись схемы, которой нет среди уровней документа). -> numId."""
    numroot = d.part.numbering_part.element
    ids = [int(a.get(qn('w:abstractNumId'))) for a in numroot.findall(W + 'abstractNum') if (a.get(qn('w:abstractNumId')) or '').isdigit()]
    nids = [int(n.get(qn('w:numId'))) for n in numroot.findall(W + 'num') if (n.get(qn('w:numId')) or '').isdigit()]
    aid, nid = str(max(ids + [0]) + 1), str(max(nids + [0]) + 1)
    cl = OxmlElement('w:abstractNum'); cl.set(qn('w:abstractNumId'), aid)
    mt = OxmlElement('w:multiLevelType'); mt.set(qn('w:val'), 'multilevel'); cl.append(mt)
    for i, stv in enumerate(parts):
        lvl = OxmlElement('w:lvl'); lvl.set(qn('w:ilvl'), str(i))
        for tag, val in (('w:start', str(stv)), ('w:numFmt', 'decimal'), ('w:suff', 'space'), ('w:lvlText', '.'.join('%%%d' % (j + 1) for j in range(i + 1)))):   # порядок по схеме
            e = OxmlElement(tag); e.set(qn('w:val'), val); lvl.append(e)
        cl.append(lvl)
    last = numroot.findall(W + 'abstractNum')
    (last[-1].addnext(cl) if last else numroot.insert(0, cl))
    num = OxmlElement('w:num'); num.set(qn('w:numId'), nid)
    ae = OxmlElement('w:abstractNumId'); ae.set(qn('w:val'), aid); num.append(ae)
    numroot.append(num)
    return nid


def append_orphan_numbers(d, ref_pdf, canon_text, limit=40):
    """Короткая нумерованная строка эталона, которой нет в выгрузке канона (подпись схемы: «7.3 Планирования»).
    В конец тела, живым номером (набранный номер стал бы frozen). Строки оглавления с точками не берутся.
    Вызывающий откатывает файл, если проверка не стала лучше."""
    rows = [l.split('\t') for l in open(canon_text, encoding='utf-8', errors='replace').read().split('\n')]
    paras = [(r[2].strip(), r[3]) for r in rows if len(r) >= 4]
    import verify_canon
    body = verify_canon.body_paras(paras)   # строка только в оглавлении для проверки — всё ещё неверный номер
    ck = P.key(' '.join(n + ' ' + t for n, t in body))
    items, seen = [], set()
    for p in P.canon_pages(ref_pdf):
        for l in p['lines']:
            t = l.strip(); k = P.key(t)
            if not k or k in seen or k in ck or re.search(r'[.…]{3,}\s*\d{0,3}\s*$', t): continue
            m = re.match(r'(\d+(?:\.\d+)+)\.?\s+(\S.*)', t)
            if not m or not 12 <= len(k) <= 160: continue
            seen.add(k); items.append((m.group(1), m.group(2).strip()))
            if len(items) >= limit: break
        if len(items) >= limit: break
    if not items: return 0
    body = d.element.body
    sect = body.find(W + 'sectPr')
    for num, rest in items:
        parts = [int(x) for x in num.split('.')]
        p = OxmlElement('w:p'); r = OxmlElement('w:r'); tt = OxmlElement('w:t'); tt.text = rest
        r.append(tt); p.append(r)
        (sect.addprevious(p) if sect is not None else body.append(p))
        try: nid = _decimal_num(d, parts)
        except Exception: continue
        ppr = OxmlElement('w:pPr'); np_ = OxmlElement('w:numPr')
        il = OxmlElement('w:ilvl'); il.set(qn('w:val'), str(len(parts) - 1)); np_.append(il)
        nv = OxmlElement('w:numId'); nv.set(qn('w:val'), nid); np_.append(nv)
        ppr.append(np_); p.insert(0, ppr)
    return len(items)


def build_lines(pdf_path):
    """Глобальный список строк эталона (как verify: после usable-фильтров) с геометрией: [{'t','x0','y0','x1','y1','blk','idx','label','pn'}]."""
    import fitz, collections
    pdf = fitz.open(pdf_path); pages = P.canon_pages(pdf_path)
    head = {k for k, c in collections.Counter(P.key(l) for p in pages for l in p['lines']).items() if c > 0.3 * len(pages)}
    GL = []
    for pi, pg in enumerate(pages):
        ls0 = F.page_lines(pdf[pi])
        for i in F.usable_idx([l['t'] for l in ls0], head):
            l = dict(ls0[i]); l['idx'] = len(GL); l['label'] = pg['label']; l['pn'] = pg['n']; GL.append(l)
    return GL


def chain_back(cn, GL, c, g0, g1, ADJ=40):
    """От доверенной строки c назад: строки, лежащие в каноне вплотную (зазор ≤ ADJ + 1.6 × длина пропущенных строк) к курсору. -> (loc {idx: (start,end)}, cursor_after_group, P_end|None, prev_idx|None)."""
    cursor = cn.occ(_lk(GL[c]['t']))[0]
    loc = {}; skipped = 0; P_end = None; prev = None; E = cursor; Eset = False
    x = c - 1
    while x >= max(g0 - 14, 0):
        k = _lk(GL[x]['t'])
        hit = None
        if len(k) >= 12:
            lim = ADJ + 1.6 * skipped
            lo = max(0, cursor - len(k) - int(lim))
            for q in cn.occ(k, lo, cursor, cap=40)[::-1]:
                if q + len(k) <= cursor and cursor - (q + len(k)) <= lim: hit = q; break
        if hit is not None and not (g0 <= x <= g1 and False):
            loc[x] = (hit, hit + len(k)); cursor = hit; skipped = 0
            if x < g0: P_end = hit + len(k); prev = x; break
        else:
            skipped += len(k)
        if x == g1 + 1 or x == g1: pass
        x -= 1
    return loc, prev, P_end


def insert_b_lines(d, ref_pdf, items):
    """items [{'label','text','cls':'B'}] -> (число вставленных строк, отчёт). Строки вставляются в место, найденное по соседним строкам эталона
    (цепочка строк, лежащих в каноне вплотную); различающийся текст Word на этом месте (ratio ≥ 0.5) заменяется текстом PDF. d правится на месте."""
    cn = Canon(d)
    GL = build_lines(ref_pdf)
    lists = F.Lists(d)
    byp = {}
    for g in GL: byp.setdefault((g['label'], g['t'].strip()), []).append(g['idx'])
    bset = {}; rep = []; n_ins = 0; touched = []
    ids = [int(x.get(qn('w:id'))) for x in d.element.iter(W + 'bookmarkStart') if (x.get(qn('w:id')) or '').isdigit()]
    bid0 = max(ids + [9000]); bid = bid0
    for it in items:
        idxs = byp.get((it['label'], it['text'].strip()))
        if not idxs:   # verify режет строку эталона иначе, чем геометрия PDF: тот же ключ и та же метка
            idxs = [g['idx'] for g in GL if g['label'] == it['label'] and _lk(g['t']) == _lk(it['text'])]
        if not idxs: rep.append({**it, 'status': 'не вставлено', 'reason': 'строка не найдена в списке строк эталона'}); continue
        bset[idxs[0]] = it
    bl = sorted(bset)
    trusted = lambda j: len(_lk(GL[j]['t'])) >= 12 and len(cn.occ(_lk(GL[j]['t']), cap=2)) == 1
    groups, cur = [], []
    for j in bl:
        if cur and (j - cur[-1] > 12 or GL[j]['label'] != GL[cur[-1]]['label']): groups.append(cur); cur = []
        cur.append(j)
    if cur: groups.append(cur)
    work = []

    def forward_anchor(g):
        """Резерв: строки после группы (до 3) подряд единым вхождением в канон -> вставка перед ними."""
        nx = [x for x in range(g[-1] + 1, min(g[-1] + 6, len(GL))) if x not in bset]
        for n in (3, 2, 1):
            seq = nx[:n]
            if len(seq) < n: continue
            k = ''.join(_lk(GL[x]['t']) for x in seq)
            if len(k) < 14: continue
            oc = cn.occ(k, cap=3)
            if len(oc) == 1: return oc[0], seq[0]
        return None

    def fwd_work(g, info, why):
        fa = forward_anchor(g)
        if not fa: return None
        pos, nx = fa
        pi_, off_ = cn.where(pos, end=False)
        pre_txt = cn.texts[pi_][:off_]; pre_k = P.key(pre_txt)
        ctxt = ''.join(_lk(GL[x]['t']) for x in g)
        w = {'g': g, 'info': dict(info, via='следующие строки'), 'P': pos, 'E': pos, 'gap': 0, 'ratio': 1.0, 'content': list(g), 'prev': None, 'c': nx}
        if pre_k and len(pre_k) <= 1.6 * len(ctxt) + 20:
            ratio = difflib.SequenceMatcher(None, pre_k, ctxt, autojunk=False).ratio()
            if ratio >= 0.5: w.update({'P': pos - len(pre_k), 'gap': len(pre_k), 'ratio': round(ratio, 2), 'force': True, 'loc': (pi_, 0, pi_, off_)})
        return w
    for g in groups:
        info = {'label': GL[g[0]]['label'], 'lines': [GL[x]['t'] for x in g]}
        res = None; why = ''
        c = next((x for x in range(g[-1] + 1, min(g[-1] + 60, len(GL))) if trusted(x)), None)
        if c is None: why = 'нет однозначной строки-якоря после группы'
        else:
            loc, prev, P_end = chain_back(cn, GL, c, g[0], g[-1])
            if P_end is None: why = 'нет строки-якоря перед группой, лежащей в каноне вплотную'
            else:
                after = [x for x in loc if x > g[-1]]
                E = min([loc[x][0] for x in after] + [cn.occ(_lk(GL[c]['t']))[0]])
                content = [x for x in range(prev + 1, c) if x not in loc and not (after and x > min(after))]
                gap = E - P_end
                gtxt = cn.S[P_end:E]; ctxt = ''.join(_lk(GL[x]['t']) for x in content)
                ratio = difflib.SequenceMatcher(None, gtxt, ctxt, autojunk=False).ratio() if gap > 8 else 1.0
                if not any(x in bset for x in content): why = 'B-строка оказалась найденной в цепочке'
                elif gap < 0: why = 'порядок строк нарушен'
                elif gap > 8 and ratio < 0.5: why = f'в Word между якорями иной текст ({gap} знаков, сходство {ratio:.2f})'
                else:
                    pi_, _o = cn.where(P_end, end=True); pk_, _o2 = cn.where(E)
                    mids = cn.paras[pi_ + 1:pk_]
                    if gap > 8 and pk_ != pi_ and (len(mids) > 3 or any(m.getparent() is not cn.paras[pi_].getparent() for m in mids)): why = 'замена затрагивает абзацы разных контейнеров/более 3'
                    else: res = {'g': g, 'info': info, 'P': P_end, 'E': E, 'gap': gap, 'ratio': round(ratio, 2), 'content': content, 'prev': prev, 'c': c}
        if res is None: res = fwd_work(g, info, why)
        if res is None: rep.append({**info, 'status': 'не вставлено', 'reason': why}); continue
        work.append(res)
    for w in sorted(work, key=lambda w: -w['P']):
        info = w['info']; content = w['content']
        if w.get('loc'): pi, off0, pk, off1 = w['loc']
        else: pi, off0 = cn.where(w['P'], end=True); pk, off1 = cn.where(w['E'], end=False)
        if (pk, off1) < (pi, off0): pk, off1 = pi, off0
        if pk != pi and off0 < len(cn.texts[pi]) and False: pass
        pre = w['prev']; nxt = w['c']
        window = ([GL[pre]] if pre is not None else []) + [GL[x] for x in content] + [GL[nxt]]
        paras = F.build_paras(F.merge_visual([dict(x) for x in window]))
        cset = set(content)
        out_paras = [q for q in paras if any(i in cset for i in q['idxs'])]
        if not out_paras: rep.append({**info, 'status': 'не вставлено', 'reason': 'нет абзацев после склейки'}); continue
        # удаление различающегося текста Word
        p0, pK = cn.paras[pi], cn.paras[pk]
        if w['gap'] > 8 or w.get('force'):
            if pi == pk: ok, _ = delete_chars(p0, off0, off1)
            else:
                mids = cn.paras[pi + 1:pk]
                if len(mids) > 3 or any(m.getparent() is not p0.getparent() for m in mids): rep.append({**info, 'status': 'не вставлено', 'reason': 'замена затрагивает абзацы разных контейнеров/более 3'}); continue
                ok, _ = delete_chars(p0, off0, len(cn.texts[pi]))
                ok2, _ = delete_chars(pK, 0, off1)
                for m in mids: m.getparent().remove(m)
                ok = ok and ok2
            if not ok: rep.append({**info, 'status': 'не вставлено', 'reason': 'граница прогона: нельзя разрезать (замена)'}); continue
        done = []; cur_p, cur_off = p0, off0; first = True
        for q in out_paras:
            txt = ' '.join(GL[i]['t'].strip() for i in q['idxs'] if i in cset)
            joins_prev = pre is not None and pre in q['idxs']; joins_next = nxt in q['idxs']
            bid += 1; nm = f"PDF_src_p{GL[content[0]]['pn']}_{bid - bid0}"
            if q['kind'] and not joins_prev and not joins_next:
                rep.append({**info, 'status': 'не вставлено', 'reason': 'новый нумерованный абзац (%s): не поддержано' % q['kind'], 'text': txt[:80]}); continue
            if joins_prev or (not joins_next):
                if joins_prev or first and cur_off is not None and pi == pk and cur_off < len(''.join(x for _, x in ptext_runs(cur_p))):
                    ok = inline_insert(cur_p, cur_off, txt, bid, nm); mode = 'в абзац'
                else:
                    np_ = new_paragraph(cur_p, txt, cur_p, True, bid, nm); cur_p = np_; cur_off = None; ok = True; mode = 'новый абзац'
            else:
                tgt = pK if pk != pi else cur_p
                o_ = 0 if pk != pi else cur_off
                if o_ is None: np_ = new_paragraph(cur_p, txt, cur_p, True, bid, nm); cur_p = np_; ok = True; mode = 'новый абзац'
                else: ok = inline_insert(tgt, o_, txt, bid, nm); mode = 'в начало абзаца'
            first = False
            if ok:
                n_ins += len([x for x in q['idxs'] if x in cset]); touched.append(cur_p if mode != 'в начало абзаца' else pK)
                done.append({'mode': mode, 'text': txt[:120], 'bookmark': nm, 'заменено_знаков': w['gap'] if (w['gap'] > 8 or w.get('force')) else 0, 'canon_before': cn.texts[pi][-50:]})
            else: rep.append({**info, 'status': 'не вставлено', 'reason': 'граница прогона: нельзя разрезать', 'text': txt[:80]})
        if done: rep.append({**info, 'status': 'вставлено', 'gap_chars': w['gap'], 'ratio': w['ratio'], 'inserted': done})
    for p in {id(x): x for x in touched}.values(): _liveify(p, lists)
    return n_ins, rep


def merged_cells(lines_cls, cn):
    """Строка PDF, склеенная из соседних ячеек таблицы: все её куски (разрез по 2+ пробелам и номерам-маркерам «1.») найдены в каноне -> 'merged'."""
    for it in lines_cls:
        if it['cls'] != 'B': continue
        parts = [x for x in re.split(r'\s{2,}|(?<=\s)\d\.\s', it['text']) if len(P.key(x)) >= 6]
        if len(parts) >= 2 and all(P.key(x) in cn.S for x in parts): it['cls'] = 'merged'
    return lines_cls


def patch_canon(sd, od, ref_pdf, srcs=None, work=None):
    """Строки класса B из PDF -> канон: od/canon.docx правится, пересчитываются canon_text.txt и verify.json.
    -> {'inserted': N, 'items': [...], 'report': [...], 'verify': v}. Исходный канон сохраняется как canon_before_pdflines.docx."""
    import shutil, py_numfix
    cd, ct = os.path.join(od, 'canon.docx'), os.path.join(od, 'canon_text.txt')
    srcs = srcs or sources_of(sd)
    r, items = scan(sd, ct, cd, srcs)
    d = docx.Document(cd)
    cn = Canon(d)
    merged_cells(items, cn)
    res = {'inserted': 0, 'items': items, 'report': [], 'missing_before': r['missing']}
    todo = [i for i in items if i['cls'] == 'B' and i['label'] is not None]
    def dump_json(): json.dump({k: res.get(k) for k in ('inserted', 'items', 'report', 'missing_before', 'verify', 'ooxml_problems')}, open(os.path.join(od, 'pdf_lines.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if not todo: dump_json(); return res
    n, rep = insert_b_lines(d, ref_pdf, todo)
    res['inserted'] = n; res['report'] = rep
    if not n: dump_json(); return res
    shutil.copy(cd, os.path.join(od, 'canon_before_pdflines.docx'))
    py_numfix.run(d, ref_pdf)
    d.save(cd)
    import ooxml_check
    res['ooxml_problems'] = ooxml_check.check(cd)
    pynum.dump(cd, ct)
    import verify_canon
    v = verify_canon.verify(sd, ct, cd, srcs)
    json.dump(v, open(os.path.join(od, 'verify.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    res['verify'] = {k: v[k] for k in ('lines', 'missing', 'numbered', 'numbered_bad', 'duplicates', 'frozen_numbers', 'live_numbering', 'coverage')}
    json.dump({k: res[k] for k in ('inserted', 'items', 'report', 'missing_before', 'verify', 'ooxml_problems')}, open(os.path.join(od, 'pdf_lines.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return res
