"""Прототип: собрать канон из базового Word + листов замены и сверить с PDF-эталоном.

python3 assemble.py <папка документа> [--dump out.txt]
"""
import sys, re, glob, os, difflib, collections
import docx, fitz
from docx.oxml.ns import qn

W = qn('w:t'); BR = qn('w:br'); P = qn('w:p'); TBL = qn('w:tbl'); TYPE = qn('w:type')


def norm(s):
    s = s.lower().replace('ё', 'е')
    s = re.sub(r'[^0-9a-zа-я]+', ' ', s)
    return ' '.join(s.split())


def para_text(p):
    return ''.join(t.text or '' for t in p.iter(W))


def docx_pages(path):
    """Абзацы тела документа (включая ячейки таблиц) с разбиением на страницы по явным разрывам."""
    body = docx.Document(path).element.body
    pages, cur = [], []
    for el in body.iterchildren():
        paras = [el] if el.tag == P else list(el.iter(P)) if el.tag == TBL else []
        for p in paras:
            brk = any(b.get(TYPE) == 'page' for b in p.iter(BR)) or p.find('.//' + qn('w:sectPr')) is not None
            t = para_text(p).strip()
            if t:
                cur.append(t)
            if brk and el.tag == P and cur:
                pages.append(cur); cur = []
    if cur:
        pages.append(cur)
    return pages


def classify(fn):
    n = fn.lower()
    if re.search(r'лист\w*\s+изм', n): return 'changelog'
    if re.search(r'приказ|о внесении|служебн', n): return 'order'
    return 'sheets'


def page_key(fn):
    m = re.search(r'(\d+)', re.sub(r'^\d{6}_', '', os.path.basename(fn)))
    return int(m.group(1)) if m else 0


def best_match(unit, doc, lo=0, thr=0.82):
    """Индекс абзаца в doc, лучше всего совпадающего с unit."""
    u = norm(unit)
    if len(u) < 12: return None
    best, bi = thr, None
    for i in range(lo, len(doc)):
        d = norm(doc[i])
        if abs(len(d) - len(u)) > max(len(u), len(d)) * 0.5: continue
        r = difflib.SequenceMatcher(None, u, d, autojunk=False).quick_ratio()
        if r > best:
            r = difflib.SequenceMatcher(None, u, d, autojunk=False).ratio()
            if r > best: best, bi = r, i
    return bi


def apply_page(doc, page, log):
    """Заменить в doc фрагмент, которому соответствует страница замены.
    Якоря: первый и последний абзац страницы, найденные в doc."""
    idx = [(j, best_match(t, doc)) for j, t in enumerate(page)]
    hits = [(j, i) for j, i in idx if i is not None]
    if not hits:
        log.append(('НЕ НАЙДЕНО МЕСТО', page[0][:80])); return doc
    # монотонная цепочка якорей: берём медиану, отсекаем выбросы
    offs = sorted(i - j for j, i in hits)
    med = offs[len(offs) // 2]
    good = [(j, i) for j, i in hits if abs((i - j) - med) <= max(15, len(page))]
    (j0, i0), (j1, i1) = good[0], good[-1]
    start = i0 - j0
    end = i1 + (len(page) - 1 - j1)
    start = max(start, 0); end = min(end, len(doc) - 1)
    span = end - start + 1
    if len(good) < 0.5 * len(page) or span > 2 * len(page) + 3 or span < 0.5 * len(page) - 3:
        log.append(('GAP: ненадёжная привязка', f'якорей {len(good)}/{len(page)}, диапазон {span}', page[0][:60]))
        return doc
    log.append(('замена', f'абз. {start}-{end} ({end-start+1}) → {len(page)} абз.; якорей {len(good)}/{len(page)}', page[0][:60]))
    return doc[:start] + page + doc[end + 1:]


def pdf_text(path, skip_title=True):
    d = fitz.open(path)
    pages = [d[i].get_text() for i in range(d.page_count)]
    # колонтитулы: строки, повторяющиеся на >30% страниц
    cnt = collections.Counter()
    for pg in pages:
        for l in set(norm(x) for x in pg.splitlines()):
            if l: cnt[l] += 1
    rep = {l for l, c in cnt.items() if c > max(3, 0.3 * len(pages))}
    out = []
    for k, pg in enumerate(pages):
        if skip_title and k == 0: continue
        for l in pg.splitlines():
            n = norm(l)
            if n and n not in rep and not re.fullmatch(r'(стр \d+\w? из \d+|\d+\w?)', n):
                out.append(n)
    return ' '.join(out).split(), d.page_count


HDR = re.compile(r'(дата введения изменения|effective date|основание|reason|приказ от|стр|page|из|of|изменение|revision)$')


def pdf_pages(path):
    d = fitz.open(path)
    pages = [d[i].get_text() for i in range(d.page_count)]
    cnt = collections.Counter()
    for pg in pages:
        for l in set(norm(x) for x in pg.splitlines()):
            if l: cnt[l] += 1
    rep = {l for l, c in cnt.items() if c > max(3, 0.3 * len(pages))}
    out = []
    for pg in pages:
        lines = [norm(l) for l in pg.splitlines()]
        lines = [l for l in lines if l and l not in rep]
        # колонтитул изменения: «дата введения изменения … стр N из M»
        txt = ' '.join(lines)
        txt = re.sub(r'дата введения изменения.*?(стр|page)( page)? \d+\w?( из of| из)? \d+', ' ', txt)
        txt = re.sub(r'дата введения изменения.{0,120}?п \d+ \d+', ' ', txt)
        out.append(txt.split())
    return out


def shingles(words, k=5):
    return {' '.join(words[i:i + k]) for i in range(len(words) - k + 1)}


def page_report(name, words, pdfp):
    have = shingles(words)
    rows = []
    for n, pw in enumerate(pdfp, 1):
        sh = shingles(pw)
        if len(sh) < 5: rows.append((n, None, len(pw))); continue
        rows.append((n, len(sh & have) / len(sh), len(pw)))
    scored = [r for r in rows if r[1] is not None]
    tot = sum(len(shingles(pdfp[n-1])) for n, _, _ in scored)
    hit = sum(r * len(shingles(pdfp[n-1])) for n, r, _ in scored)
    b = collections.Counter('≥95%' if r >= .95 else '80-95%' if r >= .8 else '50-80%' if r >= .5 else '<50%' for _, r, _ in scored)
    allpdf = set().union(*[shingles(p) for p in pdfp])
    extra = 1 - len(have & allpdf) / max(len(have), 1)
    print(f'  {name}: покрытие эталона {hit/tot:.1%}; страниц {dict(sorted(b.items()))}; без текста {len(rows)-len(scored)}; лишнего в Word {extra:.1%}')
    return rows


def compare(words_a, words_b):
    sm = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)
    match = sum(b.size for b in sm.get_matching_blocks())
    ops = [o for o in sm.get_opcodes() if o[0] != 'equal']
    return match / max(len(words_b), 1), match / max(len(words_a), 1), ops


def main(ddir, dump=None):
    base = [f for f in glob.glob(ddir + '/word/*.docx') if classify(f) == 'sheets']
    base = max(base, key=os.path.getsize)
    canon = [f for f in glob.glob(ddir + '/files/*.pdf') if re.search('[Ээ]талон', f)][0]
    doc = [t for pg in docx_pages(base) for t in pg]
    base_words = norm(' '.join(doc)).split()
    print(f'База: {os.path.basename(base)} — {len(doc)} абз.')
    log = []
    for adir in sorted(glob.glob(ddir + '/amendments/*'), key=lambda p: float(re.search(r'изм([\d.]+)', p).group(1))):
        sheets = sorted([f for f in glob.glob(adir + '/*.docx') if classify(f) == 'sheets'], key=page_key)
        print(f'  {os.path.basename(adir)}: листов-файлов {len(sheets)}', [os.path.basename(s)[:40] for s in sheets])
        if not sheets:
            log.append(('НЕТ WORD ЛИСТОВ', os.path.basename(adir))); continue
        for s in sheets:
            for pg in docx_pages(s):
                doc = apply_page(doc, pg, log)
    for l in log:
        print('    ', *l)
    asm_words = norm(' '.join(doc)).split()
    pdf_words, npages = pdf_text(canon)
    print(f'Эталон: {os.path.basename(canon)} — {npages} стр., {len(pdf_words)} слов')
    pdfp = pdf_pages(canon)
    page_report('БАЗА без изменений', base_words, pdfp)
    rows = page_report('СОБРАННЫЙ канон', asm_words, pdfp)
    bad = [r for r in rows if r[1] is not None and r[1] < .8]
    print('  Страницы эталона < 80%:', ', '.join(f'{n}:{r:.0%}' for n, r, _ in bad))
    for n, r, _ in bad[:6]:
        print(f'   стр.{n} ({r:.0%}): «{" ".join(pdfp[n-1][:40])}»')
    print('  Страницы без текста:', [n for n, r, _ in rows if r is None])
    if dump:
        open(dump, 'w').write('\n'.join(doc))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[3] if len(sys.argv) > 3 else None)
