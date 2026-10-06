"""Сверка только основного текста: от раздела «1 Цель…» до первого приложения; приложения — отдельно.
Колонтитулы, штампы изменений и автонумерация пунктов исключаются.

python3 body.py <папка документа> [--guard]
"""
import sys, re, glob, os, collections, difflib
sys.path.insert(0, os.path.dirname(__file__))
import assemble as A
from assemble import docx_pages, classify, norm, shingles
import fitz

K = 4
NUM = re.compile(r'^\s*((\d+\.)*\d+\.?|[а-яa-z]\)|\d+\))\s+')
START = re.compile(r'^1\.?\s+(цель|общие положения|назначение|область применения)', re.I)
APPX = re.compile(r'^(приложение|annex)\s*(№\s*)?1\b\.?', re.I)


def strip_num(t):
    return NUM.sub('', t.strip().lstrip('-–•·').strip())


def pdf_lines(path):
    d = fitz.open(path)
    pages = [d[i].get_text() for i in range(d.page_count)]
    cnt = collections.Counter()
    for pg in pages:
        for l in set(norm(x) for x in pg.splitlines()):
            if l: cnt[l] += 1
    rep = {l for l, c in cnt.items() if c > max(3, 0.3 * len(pages))}
    lines = []
    for pg in pages:
        raw = pg.splitlines()
        # шапка страницы: всё до строки «Стр… из …» включительно, если она в первых 12 строках
        cut = next((i for i, l in enumerate(raw[:14]) if re.search(r'Стр\.?.{0,12}\d+\s*\w?\s*из', l, re.I)), -1)
        for l in raw[cut + 1:]:
            n = norm(l)
            if not n or n in rep: continue
            if re.fullmatch(r'(изменение|revision|№|\d+|\s)+', n): continue  # штамп «Изменение № K»
            lines.append(l.strip())
    return lines


def split_core(lines):
    """Содержательный текст: от заголовка «Общие положения» (раздел после служебных 1–4) до приложений."""
    body, appx = split_body(lines)
    k = next((i for i, l in enumerate(body) if re.match(r'общие положения', strip_num(l).lower())
              and not re.search(r'[^\d\s.]\d{1,3}$', l.strip())), None)
    return (body[:k], body[k:], appx) if k is not None else ([], body, appx)


def split_body(lines):
    """(основной текст, приложения). Начало — заголовок раздела 1 (с номером или без — автонумерация Word),
    за которым идёт содержательный текст, а не строка оглавления. Конец — первый заголовок «Приложение 1» после него."""
    def is_start(k):
        t = strip_num(lines[k]).lower()
        if not re.match(r'(цель|общие положения|назначение и область|область применения)', t): return False
        if re.search(r'(\.{4,}|…|\s\d+|[^\d\s.]\d{1,3})$', lines[k].strip()): return False   # строка оглавления
        nxt = ' '.join(lines[k + 1:k + 4])
        return len(nxt.split()) > 12 and not re.search(r'(\.{4,}|[^\d\s.]\d{1,3}\s)', lines[k + 1] + ' ')
    s = next((k for k in range(len(lines)) if is_start(k)), 0)
    e = next((k for k in range(s + 1, len(lines)) if APPX.match(strip_num(lines[k])) and len(lines[k].split()) < 25
              and not re.search(r'(\.{4,}|…)', lines[k])), len(lines))
    return lines[s:e], lines[e:]


def words(lines):
    return norm(' '.join(strip_num(l) for l in lines)).split()


def measure(name, wl, pl):
    ws, ps = shingles(wl, K), shingles(pl, K)
    rec = len(ws & ps) / max(len(ps), 1)
    extra = 1 - len(ws & ps) / max(len(ws), 1)
    return rec, extra


def assemble_doc(ddir, guard):
    base = max([f for f in glob.glob(ddir + '/word/*.docx') if classify(f) == 'sheets'], key=os.path.getsize)
    doc = [t for pg in docx_pages(base) for t in pg]
    base_doc = list(doc)
    log = []
    for adir in sorted(glob.glob(ddir + '/amendments/*'), key=lambda p: float(re.search(r'изм([\d.]+)', p).group(1))):
        for s in sorted([f for f in glob.glob(adir + '/*.docx') if classify(f) == 'sheets'], key=A.page_key):
            for pg in docx_pages(s):
                doc = apply(doc, pg, log, guard)
    return base_doc, doc, log


def apply(doc, page, log, guard):
    if guard:
        return A.apply_page(doc, page, log)
    # без защиты — как в первой версии
    idx = [(j, A.best_match(t, doc)) for j, t in enumerate(page)]
    hits = [(j, i) for j, i in idx if i is not None]
    if not hits: return doc
    offs = sorted(i - j for j, i in hits); med = offs[len(offs) // 2]
    good = [(j, i) for j, i in hits if abs((i - j) - med) <= max(15, len(page))]
    (j0, i0), (j1, i1) = good[0], good[-1]
    start, end = max(i0 - j0, 0), min(i1 + (len(page) - 1 - j1), len(doc) - 1)
    return doc[:start] + page + doc[end + 1:]


def show_diff(wl, pl, n=10):
    sm = difflib.SequenceMatcher(None, wl, pl, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != 'equal']
    ops.sort(key=lambda o: -max(o[2] - o[1], o[4] - o[3]))
    for tag, a0, a1, b0, b1 in ops[:n]:
        print(f'    [{tag}] Word({a1-a0}): «{" ".join(wl[a0:a1])[:140]}»')
        print(f'    {"":>{len(tag)+2}} PDF({b1-b0}):  «{" ".join(pl[b0:b1])[:140]}»')


def main(ddir, guard=False, diff=False):
    canon = [f for f in glob.glob(ddir + '/files/*.pdf') if re.search('[Ээ]талон', f)][0]
    ps, pb, pa = split_core(pdf_lines(canon))
    base_doc, doc, log = assemble_doc(ddir, guard)
    print(f'{os.path.basename(ddir)}: эталон — служебные {len(words(ps))} слов, содержательный {len(words(pb))} слов (с «{pb[0][:30]}»), приложения {len(words(pa))} слов')
    for name, d in (('база', base_doc), ('собранный', doc)):
        ws, wb, wa = split_core(d)
        r0, x0 = measure(name, words(ws), words(ps))
        r1, x1 = measure(name, words(wb), words(pb))
        r2, x2 = measure(name, words(wa), words(pa))
        print(f'  {name:9}: СОДЕРЖАТЕЛЬНЫЙ {r1:.1%} (лишнего {x1:.1%}) | служебные 1–4 {r0:.1%} (лишнего {x0:.1%}) | приложения {r2:.1%} (лишнего {x2:.1%})')
    if diff:
        _, wb, _ = split_core(doc)
        print('  Крупнейшие расхождения основного текста (собранный vs эталон):')
        show_diff(words(wb), words(pb))


if __name__ == '__main__':
    main(sys.argv[1], '--guard' in sys.argv, '--diff' in sys.argv)
