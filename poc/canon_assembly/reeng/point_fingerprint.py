#!/usr/bin/env python3
"""Сверка канона (Word) с эталоном (PDF) по отпечаткам пунктов 6+ («бит идентичности»), TASK-021 шаг 6.

  python3 point_fingerprint.py DOC [DOC ...]   # конкретные документы
  python3 point_fingerprint.py --all           # весь объём (282 документа: без РПП, РОТО, ИОТ-)
Результат: data/canon_reeng/full2/points/<doc>.json, summary.csv, README.md (при --all или --readme).
Только чтение корпуса; ИИ и Word не нужны.
"""
import csv, glob, hashlib, json, os, re, sys, difflib, collections
import fitz

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
FULL = os.path.join(ROOT, 'data/canon_reeng', os.environ.get('FP_RUN', 'full2'))  # прогон: FP_RUN=full3
PTS = os.environ.get('FP_OUT') or os.path.join(FULL, 'points')   # FP_OUT — другой каталог результатов (проверки без перезаписи)
STEP1 = os.environ.get('FP_STEP1', os.path.join(ROOT, 'data/canon_reeng/step1/out'))  # FP_STEP1=- — не подмешивать step1
REF_RE = re.compile(r'[Ээ]т[а-я]{0,2}(?:ал|ла)он', re.I)
NUM_RE = re.compile(r'^(\d{1,3}(?:\.\d{1,3})*)\.?(?:\s+|$)(.*)$')
APP_RE = re.compile(r'^[^\w(«"]{0,3}\s*(?-i:(?=[ПA]))(?:приложение|appendix|annex)\s+([0-9]{1,2}|[А-ЯA-Z])(?!\w)\s*(?:([.\-–—:])(?=\s|$))?\s*(.*)$', re.I)
TOC_LINE = re.compile(r'[.…·_]{3,}\s*\d+\w?\s*$')   # строка оглавления: точки-заполнители и номер страницы в конце
TCELL = '\u2063'   # метка строки-ячейки таблицы Word (в приложения по таким строкам не переходим)
CAPTION = re.compile(r'(Рисунок|Рис\.|Figure|Fig\.)\s*[0-9А-Я]', re.I)   # подпись под рисунком — часть схемы, не текст пункта
WIDE_GAP = float(os.environ.get('FP_WIDE_GAP', 4.0))
SHP = '\u2064'     # метка строки текста схемы/рисунка (надпись Word; строка PDF внутри векторной схемы): в нумерации не участвует, из «ядра» пункта вырезается
TOP, BOT = 0.125, 0.92   # зона колонтитулов (доля высоты страницы)
STAMP = re.compile(r'(Дата введения|Основание|Изменение\s*(/\s*Revision)?\s*№|Revision\s*№)', re.I)
STAMP_BARE = re.compile(r'(Изменение|Revision)(\s*/\s*(Изменение|Revision))?\s*$')   # колонтитул «Изменение» без номера (только в зоне колонтитулов, регистр как в штампе)
PAGENO = re.compile(r'Стр\.?\s*/?\s*(page)?\s*\d|^\s*(page|стр\.?)\s*\d+\s*(of|из)\s*\d+\s*$', re.I)


def norm(s):
    return re.sub(r'[^0-9a-zа-я]', '', s.lower().replace('ё', 'е'))


def sha(s):
    return hashlib.sha1(s.encode('utf-8')).hexdigest()


def garbage(line):  # как pagediff.garbage
    if re.search(r'\w@\w[\w.-]*\.\w+', line): return False
    lat = len(re.findall(r'[A-Za-z]', line)); cyr = len(re.findall(r'[А-Яа-яЁё]', line))
    return lat > 8 and cyr == 0 and re.search(r'[@{}_]|[a-z][A-Z][a-z]', line) is not None


def lang(s):
    lat = len(re.findall(r'[A-Za-z]', s)); cyr = len(re.findall(r'[А-Яа-яЁё]', s))
    return 'en' if lat >= 8 and lat / max(lat + cyr, 1) > 0.5 else 'ru'   # язык по доле латиницы


# ---------------------------------------------------------------- источники строк
def _rows(ws, H):
    rows = []
    for w in sorted(ws, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        yc = (w[1] + w[3]) / 2
        if rows and abs(rows[-1][0] - yc) <= max(2.5, 0.35 * (w[3] - w[1])):
            rows[-1][1].append(w)
        else:
            rows.append([yc, [w]])
    out = []
    for yc, r in rows:
        r.sort(key=lambda w: w[0])
        t = ' '.join(w[4] for w in r).strip()
        out.append((SHP + t.replace(SHP, '') if SHP in t else t, yc / H))   # строка со словом из схемы — вся строка из схемы
    return out


def fig_rects(p):
    """Области векторных схем страницы: связные группы рисунков (рамки, линии, стрелки), где есть >=2 стрелки (закрашенные многоугольники из отрезков/кривых).
    Таблицы стрелок не содержат. Повёрнутые страницы не разбираем."""
    if p.rotation: return []
    try: dr = p.get_drawings()
    except Exception: return []
    if not 2 <= len(dr) <= 1500: return []
    W, H = p.rect.width, p.rect.height
    nd = []   # (rect, стрелка?)
    for x in dr:
        r = x['rect']; k = ''.join(i[0] for i in x['items'])
        if r.width > 0.9 * W or r.y1 < 0.1 * H or r.y0 > 0.94 * H: continue   # линии на всю ширину и колонтитулы
        nd.append((fitz.Rect(r) + (-4, -4, 4, 4), x.get('fill') is not None and 're' not in k.replace('relll', 'l') and (k.count('l') >= 3 or 'c' in k)))
    if sum(1 for _, ar in nd if ar) < 2: return []   # без стрелок схемы нет (быстрый выход: таблицы на сотни прямоугольников)
    par = list(range(len(nd)))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    for i in range(len(nd)):
        for j in range(i + 1, len(nd)):
            if nd[i][0].intersects(nd[j][0]): par[f(i)] = f(j)
    comp = collections.defaultdict(list)
    for i in range(len(nd)): comp[f(i)].append(i)
    out = []
    for g in comp.values():
        if sum(1 for i in g if nd[i][1]) >= 2:
            r = fitz.Rect(nd[g[0]][0])
            for i in g: r |= nd[i][0]
            out.append(r)
    return out


def _wl(w):
    c = len(re.findall(r'[А-Яа-яЁё]', w[4])); l = len(re.findall(r'[A-Za-z]', w[4]))
    return 'c' if c > l else 'l' if l > c else None


def split_columns(units, W, H):
    """Двуязычная вёрстка в две колонки по блокам fitz (get_text('dict')): колонка — по x-середине блока относительно середины
    (страницы; если колонки сдвинуты полями — середины текстовой области). units: [(x0,y0,x1,y1,text,block_id)].
    Возвращает (русская, английская) или None."""
    if len(units) < 6: return None
    blk = collections.defaultdict(list)
    for u in units: blk[u[5]].append(u)
    boxes = [(min(u[0] for u in g), max(u[2] for u in g), min(u[1] for u in g), g) for g in blk.values()]
    body = [bx for bx in boxes if 0.2 * H <= bx[2] <= BOT * H] or boxes
    cx = (min(bx[0] for bx in body) + max(bx[1] for bx in body)) / 2

    def share(g, k):
        t = ' '.join(u[4] for u in g)
        c = len(re.findall(r'[А-Яа-яЁё]', t)); l = len(re.findall(r'[A-Za-z]', t))
        return (c / max(c + l, 1) if k == 'c' else l / max(c + l, 1)), c + l
    for mid in (W / 2, cx):
        L, R, wide = [], [], []
        ok = True
        for x0, x1, y0, g in boxes:
            if x0 < mid - 0.05 * W and x1 > mid + 0.05 * W:   # блок через середину: в верхней зоне (шапка) не мешает, в теле — не двухколоночная страница
                if 0.2 * H < y0 < BOT * H: ok = False; break
                wide += g; continue   # заголовки через всю ширину («7 УПРАВЛЕНИЕ / MANAGEMENT») — в русский поток
            (L if (x0 + x1) / 2 < mid else R).extend(g)
        if not ok: continue
        for a, b in ((L, R), (R, L)):
            sa, na = share(a, 'c'); sb, nb = share(b, 'l')
            if sa >= 0.75 and sb >= 0.75 and na >= 80 and nb >= 80: return a + wide, b
    return None


def split_columns_bands(units, W, H):
    """Запасной разбор страниц с рисунками/широкими блоками (первый разбор по середине страницы не прошёл): колонки — по полосам
    текстовых блоков. Граница — наибольший разрыв между x-серединами блоков (кластеры), а не середина страницы; блоки через границу
    с малым текстом (рисунок, символы, заголовок; <=25 % букв страницы) уходят в русский поток, иначе страница не двухколоночная.
    Язык: русская сторона — ≥75 % кириллицы и английская ≥75 % латиницы (как раньше) либо английская ≥90 % латиницы, русская ≥35 %
    (в русской колонке встречаются латинские расшифровки), при зеркальных по высоте блоках (≥60 % блоков слева имеют пару справа).
    Возвращает (русская, английская) или None."""
    blk = collections.defaultdict(list)
    for u in units: blk[u[5]].append(u)
    nl = lambda g: len(re.findall(r'[A-Za-zА-Яа-яЁё]', ' '.join(u[4] for u in g)))
    boxes = [(min(u[0] for u in g), max(u[2] for u in g), min(u[1] for u in g), g) for g in blk.values()]
    body = [bx for bx in boxes if 0.2 * H <= bx[2] <= BOT * H and nl(bx[3]) >= 8]
    if len(body) < 4: return None
    xm = sorted((bx[0] + bx[1]) / 2 for bx in body)
    gaps = [(xm[i + 1] - xm[i], (xm[i] + xm[i + 1]) / 2) for i in range(len(xm) - 1) if 0.25 * W <= (xm[i] + xm[i + 1]) / 2 <= 0.75 * W]
    if not gaps: return None
    gap, d = max(gaps)
    if gap < 0.08 * W: return None
    L, R, wide = [], [], []
    for x0, x1, y0, g in boxes:
        if x0 < d - 0.05 * W and x1 > d + 0.05 * W: wide.append((y0, g)); continue
        (L if (x0 + x1) / 2 < d else R).append((y0, g))
    if sum(nl(g) for _, g in wide) > 0.25 * sum(nl(g) for _, g in L + R + wide): return None
    if sum(1 for y, g in L + R if nl(g) >= 8) < 4: return None
    flat = lambda S: [u for _, g in S for u in g]
    def share(S, k):
        t = ' '.join(u[4] for u in flat(S))
        c = len(re.findall(r'[А-Яа-яЁё]', t)); l = len(re.findall(r'[A-Za-z]', t))
        return (c / max(c + l, 1) if k == 'c' else l / max(c + l, 1)), c + l
    ys = lambda S: [y for y, g in S if nl(g) >= 8]
    for a, b in ((L, R), (R, L)):
        (sa, na), (sb, nb) = share(a, 'c'), share(b, 'l')
        if na < 80 or nb < 80: continue
        ya, yb = ys(a), ys(b)
        mirror = sum(1 for y in ya if any(abs(y - z) <= 4 for z in yb)) / max(min(len(ya), len(yb)), 1)
        if (sa >= 0.75 and sb >= 0.75) or (sb >= 0.9 and sa >= 0.35 and mirror >= 0.6):
            return flat(a) + flat(wide), flat(b)
    return None


def _wide_rows(ws, x):
    """Слова строк, идущих через щель x (заголовки на всю ширину): слово пересекает x либо между соседними словами строки через x нет зазора колонок (>= WIDE_GAP пт)."""
    rows = []
    for w in sorted(ws, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        yc = (w[1] + w[3]) / 2
        if rows and abs(rows[-1][0] - yc) <= max(2.5, 0.35 * (w[3] - w[1])): rows[-1][1].append(w)
        else: rows.append([yc, [w]])
    wide = []
    for _, r in rows:
        r.sort(key=lambda w: w[0])
        if any(w[0] < x < w[2] for w in r): wide += r; continue
        pairs = [(p, q) for p, q in zip(r, r[1:]) if p[2] <= x <= q[0]]
        if pairs and pairs[0][1][0] - pairs[0][0][2] < WIDE_GAP: wide += r
    return {id(w) for w in wide}


def _words_strict(ws, W):
    """Прежний строгий разбор: единственный x с наименьшим числом пересечённых слов (<=3), ближайший к середине страницы."""
    best = None
    for x in range(int(0.38 * W), int(0.62 * W), 2):
        st = sum(1 for w in ws if w[0] < x < w[2])
        if best is None or st < best[0] or (st == best[0] and abs(x - W / 2) < abs(best[1] - W / 2)): best = (st, x)
    st, x = best
    if st > 3: return None
    L = [w for w in ws if (w[0] + w[2]) / 2 < x]; R = [w for w in ws if (w[0] + w[2]) / 2 >= x]

    def share(g, k):
        kn = [_wl(w) for w in g if _wl(w)]
        return (kn.count(k) / len(kn), len(kn)) if kn else (0, 0)
    for a, b in ((L, R), (R, L)):
        sa, na = share(a, 'c'); sb, nb = share(b, 'l')
        if sa >= 0.75 and sb >= 0.75 and na >= 20 and nb >= 20: return a, b
    return None


def split_columns_words(ws, W, relax=False):
    """Запасной вариант (как раньше): щель без слов по словам страницы. Кандидаты — x, через которые идёт не больше 3 слов (или 3 % слов:
    заголовки на всю ширину); выбирается тот, где языки разделены лучше всего (раньше — просто ближайший к середине страницы).
    relax (3 % слов вместо 3 слов) — только для документов, где колонки уже найдены на других страницах (иначе двуязычные таблицы приложений
    ложно делились бы на «русский/английский» потоки, а в Word они идут одной таблицей). Строки на всю ширину (заголовок «РУССКИЙ / ENGLISH») целиком уходят в русский поток, как у блочного разбора."""
    if len(ws) < 60: return None
    if not relax: return _words_strict(ws, W)
    lim = max(3, 0.03 * len(ws))
    best = None

    def share(g, k):
        kn = [_wl(w) for w in g if _wl(w)]
        return (kn.count(k) / len(kn), len(kn)) if kn else (0, 0)
    for x in range(int(0.38 * W), int(0.62 * W), 2):
        if sum(1 for w in ws if w[0] < x < w[2]) > lim: continue
        wd = _wide_rows(ws, x)
        L = [w for w in ws if id(w) not in wd and (w[0] + w[2]) / 2 < x]; R = [w for w in ws if id(w) not in wd and (w[0] + w[2]) / 2 >= x]
        Wd = [w for w in ws if id(w) in wd]
        for a, b in ((L + Wd, R), (R + Wd, L)):
            sa, na = share(a, 'c'); sb, nb = share(b, 'l')
            if sa >= 0.75 and sb >= 0.75 and na >= 20 and nb >= 20:
                sc = (min(sa, sb), -abs(x - W / 2))
                if best is None or sc > best[0]: best = (sc, a, b)
    return (best[1], best[2]) if best else None


def pdf_lines(path):
    """Строки эталона без колонтитулов/штампов/мусора.
    Возвращает (lines, lines_en, flags, line_pages, bad_pages): lines_en — английская колонка двуязычных страниц."""
    d = fitz.open(path)
    pages = []     # на страницу: (строки основной колонки, строки английской колонки)
    flags = set()
    later = []   # страницы, где строгий разбор по словам не нашёл колонок (см. relax)
    for p in d:
        H = p.rect.height
        us, dirs = [], []
        for bi, b in enumerate(p.get_text('dict')['blocks']):
            if b.get('type') != 0: continue
            for ln in b['lines']:
                t = ''.join(sp_['text'] for sp_ in ln['spans']).strip()
                if t: us.append((ln['bbox'], t, bi)); dirs.append(tuple(round(v) for v in ln['dir']))
        UW, UH = p.mediabox.width, p.mediabox.height   # размеры в системе координат текста (до поворота страницы)
        dr = collections.Counter(dirs).most_common(1)[0][0] if dirs else (1, 0)
        if dr == (0, -1): tf = lambda b: (UH - b[3], b[0], UH - b[1], b[2]); W, H2 = UH, UW   # строки идут снизу вверх
        elif dr == (0, 1): tf = lambda b: (b[1], UW - b[2], b[3], UW - b[0]); W, H2 = UH, UW
        else: tf = lambda b: tuple(b); W, H2 = UW, UH
        us = [(*tf(b), t, bi) for b, t, bi in us]
        fr = fig_rects(p) if dr == (1, 0) else []
        if fr: us = [(x0, y0, x1, y1, SHP + t if any(r.contains(fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)) for r in fr) else t, bi) for x0, y0, x1, y1, t, bi in us]
        sp = split_columns(us, W, H2) or split_columns_bands(us, W, H2)
        if sp is None and dr == (1, 0):   # блоки не дали колонок — запасной разбор по щели между словами (только неповёрнутые страницы)
            ws = p.get_text('words'); sw = split_columns_words(ws, p.rect.width)
            later.append((len(pages), p, H2))
            if sw: pages.append((_rows(sw[0], H2), _rows(sw[1], H2))); continue
        pages.append((_rows(sp[0], H2), _rows(sp[1], H2)) if sp else (_rows(us, H2), []))
    if later and sum(1 for _, le in pages if le) >= max(3, 0.1 * len(pages)):   # двуязычный документ: страницы разбираются по словам мягче (и те, что строгий разбор уже поделил — x подбирается по языкам)
        for i, p, H2 in later:
            sw = split_columns_words(p.get_text('words'), p.rect.width, relax=True)
            if sw: pages[i] = (_rows(sw[0], H2), _rows(sw[1], H2))
    n = len(pages)
    allp = [ls + le for ls, le in pages]
    cnt = collections.Counter()
    for ls in allp:
        for k in {norm(re.sub(r'\d+', '', t)) for t, _ in ls if norm(t)}:
            cnt[k] += 1
    wc = collections.Counter()   # слова верхней/нижней зоны, встречающиеся на >30 % страниц (словарь колонтитулов)
    for ls in allp:
        for w in {norm(w) for t, rel in ls if rel < TOP or rel > BOT for w in re.split(r'[\s\-]+', re.sub(r'\d+', ' ', t))}:
            if w: wc[w] += 1
    vocab = {w for w, c in wc.items() if c > 0.3 * n} if n >= 4 else set()

    def clean(ls):
        pg = []; nb = 0
        for t, rel in ls:
            if not t: continue
            if garbage(t): nb += 1; continue
            if PAGENO.search(t) or STAMP.match(t.strip()): continue
            if (rel < TOP or rel > BOT) and STAMP_BARE.match(t.strip()): continue
            k = norm(re.sub(r'\d+', '', t))
            if k and n >= 4 and (rel < TOP or rel > BOT):   # колонтитул: строка повторяется или целиком из слов колонтитула
                ws = [norm(w) for w in re.split(r'[\s\-]+', re.sub(r'\d+', ' ', t)) if norm(w)]
                if cnt[k] > 0.3 * n or (ws and all(w in vocab for w in ws) and not re.match(r'(\d+(\.\d+)*\.?\s|Приложение)', t.strip())): continue
            pg.append(t)
        return pg, nb

    def join(items):   # склейка переносов: «слово-» + «продолжение» (строчная буква)
        res, pgs = [], []
        for t, pn in items:
            if res and re.search(r'[А-Яа-яA-Za-z]-$', res[-1]) and re.match(r'[а-яa-z]', t): res[-1] = res[-1][:-1] + t
            else: res.append(t); pgs.append(pn)
        return res, pgs

    out, out_en, bad = [], [], []
    for pn, (lm, le) in enumerate(pages):
        pg, nb = clean(lm); pe, nb2 = clean(le)
        if (nb or nb2) and nb + nb2 >= len(pg) + len(pe): bad.append(pn + 1)
        out += [(t, pn + 1) for t in pg]; out_en += [(t, pn + 1) for t in pe]
    res, pgs = join(out); res_en, _ = join(out_en)
    if any(le for _, le in pages): flags.add('двуязычная вёрстка в две колонки: %d стр.' % sum(1 for _, le in pages if le))
    return res, res_en, flags, pgs, bad


def word_lines(path):
    """canon_text.txt: idx, kind, ListString, text, pos. Номер автонумерации приклеивается к тексту."""
    rows = []
    for ln in open(path, encoding='utf-8', errors='replace').read().split('\n'):
        f = ln.split('\t')
        if len(f) < 5: continue
        try: pos = int(f[-1])
        except ValueError: pos = -1
        rows.append((f[1], f[2].strip(), re.sub(r'[\x00-\x08\x0b-\x1f]', '', '\t'.join(f[3:-1])).strip(), pos))   # служебные знаки (chr(1) — объект) не текст
    main = [r for r in rows if r[0] != 'S']
    shapes = sorted([r for r in rows if r[0] == 'S'], key=lambda r: r[3])
    seq = []
    si = 0
    for r in main:   # надписи вставляются по якорю после абзаца с ближайшим меньшим pos
        while si < len(shapes) and shapes[si][3] < r[3]:
            seq.append(shapes[si]); si += 1
        seq.append(r)
    seq.extend(shapes[si:])
    # штамп страницы, попавший в тело Word (таблица колонтитула: «Дата введения изменения», «Основание:___», «Стр. N из M»): вся подряд идущая таблица — не текст
    drop = set()
    i = 0
    while i < len(seq):
        if seq[i][0] != 'T': i += 1; continue
        j = i
        while j < len(seq) and seq[j][0] == 'T': j += 1
        run = [r[2] for r in seq[i:j]]
        if j - i <= 14 and any(re.search(r'Дата введения изменения|Основание\s*:\s*_|Стр\.?\s*\d+\w?\s*(из|/)\s*\d+', x) for x in run): drop.update(range(i, j))
        i = j
    out = []
    for n, (kind, ls, tx, pos) in enumerate(seq):
        if n in drop: continue
        s = (ls + ' ' + tx).strip() if ls and re.search(r'[0-9A-Za-zА-Яа-я]', ls) else tx
        s = re.sub(r'^[\uf000-\uf8ff•·▪‒–—\-]+\s*(?=\d+(?:\.\d+)+\s)', '', s)   # маркер-пуля перед набранным номером
        if s: out.append((TCELL + s) if kind == 'T' else (SHP + s) if kind == 'S' else s)
    return out


# ---------------------------------------------------------------- сегментация
def headlike(rest):
    rest = rest.strip()
    return 2 <= len(rest) <= 320 and not re.search(r'[;,:]$', rest) and (rest[:1].isupper() or rest[:1].isdigit())


def upper_head(rest):
    """Заголовок раздела прописными, перенесённый на вторую строку (первая кончается запятой/двоеточием): «10 УЧАСТИЕ В РАБОТЕ КОМИССИИ, ПРОВОДИМОМУ ПО …,»."""
    let = re.findall(r'[A-Za-zА-Яа-яЁё]', rest)
    return len(let) >= 8 and sum(c.isupper() for c in let) >= 0.9 * len(let) and len(rest) <= 320


def toc_key(rest):
    return norm(re.sub(r'([.…·]{2,}|\s)\s*\d+\w?\s*$', '', rest))


def find_start(lines):
    """Индекс заголовка раздела 6: не строка оглавления и не строка списка («6 Директорат…» в перечне рассылки).
    Предпочтение — кандидату, чьё название есть ещё и в оглавлении (двойник с точками-заполнителями или в заголовке ниже/выше)."""
    allc = []
    for i, l in enumerate(lines):
        m = NUM_RE.match(l.strip())
        if m and m.group(1) == '6' and m.group(2).strip() and len(m.group(2)) <= 320 and not m.group(2).strip()[0].islower():
            allc.append((i, toc_key(m.group(2)), bool(re.search(r'[.…·_]{3,}', l))))
    cands = [(i, k) for i, k, leader in allc if not leader and headlike(lines[i].strip()[1:].strip()) and len(lines[i]) <= 330]
    tiers = [[], [], [], [], []]
    for j, (i, k) in enumerate(cands):
        let = re.findall(r'[A-Za-zА-Яа-яЁё]', lines[i])
        up = let and sum(c.isupper() for c in let) >= 0.8 * len(let)
        has61 = any(re.match(r'6\.1\b', x.strip()) for x in lines[i + 1:i + 13])
        has7 = any(re.match(r'7\s+\S', x.strip()) for x in lines[i + 1:])
        if not (has61 or (up and has7)): continue
        n7 = next((q for q in range(i + 1, min(i + 60, len(lines))) if re.match(r'7\s+\S', lines[q].strip())), min(i + 60, len(lines)))
        body = max([len(x) for x in lines[i + 1:n7]] or [0]) >= 100    # в оглавлении строки короткие, в тексте есть абзацы
        twin = any(k2 == k and i2 != i for i2, k2, _ in allc)
        later_dup = bool(k) and any(k == k2 for _, k2 in cands[j + 1:])
        tiers[0 if twin and not later_dup else 1 if twin and body else 2 if body else 3 if twin else 4].append(i)
    r = next((t[0] for t in tiers if t), None)
    if r is None:   # заголовка раздела 6 нет (дефект документа): старт по первому пункту «6.1» (иначе «7.1»), не из оглавления
        for n in (6, 7):
            r = next((i for i, l in enumerate(lines) if re.match(r'%d\.1\s+\S' % n, l.strip()) and len(l) >= 40 and not re.search(r'[.…·_]{3,}', l)), None)
            if r is not None: break
    return r


def segment(lines, start=None, allow_dup=False, lenient=False):
    """Список пунктов [{num, lang, lines}] с раздела 6. num: '6.1', '7.2.5@en', 'прил.3'. start — индекс начала (иначе ищется)."""
    tc = [l.startswith(TCELL) for l in lines]
    sh = [l.startswith(SHP) for l in lines]
    lines = [l.lstrip(TCELL + SHP) for l in lines]
    st = find_start([('' if x else l) for l, x in zip(lines, sh)]) if start is None else start
    if st is None: return None, 'нет раздела 6', None
    pts = []
    seen = {}      # кортеж -> {lang: key}
    last_k = {}    # родитель -> последний компонент
    cur = None
    m0 = NUM_RE.match(lines[st].strip()) if st is not None else None
    top = (int(m0.group(1).split('.')[0]) - 1) if m0 else 5   # так заголовок раздела 6 тоже становится пунктом '6'
    in_app = False
    cap_prev = False
    junk = []
    apps_seen = set()

    def new(num, tup, ln, text):
        nonlocal cur
        lg = lang(text)
        key = num
        if tup is not None:
            s = seen.setdefault(tup, {})
            if lg in s or (s and False):   # повтор номера на том же языке
                if s and lg not in s: pass
                key = num + '#' + str(len(s) + 1)
            elif s:
                key = num + '@' + lg
            s[lg] = key
        cur = {'num': key, 'tup': tup, 'lang_first': lg, 'lines': [text]}
        pts.append(cur)

    for i in range(st, len(lines)):
        l = lines[i].strip()
        if not l or TOC_LINE.search(l): continue   # оглавление — не пункт (заголовок тела с тем же номером остаётся пунктом)
        l = re.sub(r'^[-–—•·▪]\s+(?=\d+(?:\.\d+)+\s+\S)', '', l) if not tc[i] else l   # маркер-тире перед набранным номером («- 21.3.2 Основной …»)
        cap = CAPTION.match(l) and len(l) <= 200 and not tc[i] and not in_app
        # подпись переносится на вторую строку («Рисунок 1 Схема … оперативной смены ОПДО каналов и средств» / «связи»): короткая строчная строка следом — тоже подпись
        cont = cap_prev and len(l) <= 100 and l[:1].islower() and not NUM_RE.match(l)
        cap_prev = bool(cap)
        if sh[i] or cap or cont:   # текст схемы/рисунка: в нумерации не участвует, лежит в пункте под меткой (ядро пункта его не берёт)
            if cur is not None: cur['lines'].append(SHP + l)
            continue
        ma = None if tc[i] or re.search(r'[.…·_]{4,}', l) else APP_RE.match(l)
        if ma and len(l) <= 160 and ma.group(1) not in apps_seen and not (ma.group(3) and ma.group(3)[:1].islower()) \
                and (ma.group(2) or not ma.group(3) or ma.group(3).startswith('(')) and not re.search(r'[,;]$', l):   # «Приложение 3 Приказ о …» без точки — строка таблицы
            apps_seen.add(ma.group(1)); in_app = True
            new('прил.' + ma.group(1), None, i, l); continue
        if in_app:
            cur['lines'].append(l); continue
        m = NUM_RE.match(l); jl = ''
        if not m:
            m2 = re.match(r'^[^\W\d_](?=\d{1,3}(?:\.\d{1,3})*\s+\S)', l)   # лишний знак, приклеенный к номеру («Щ9 ПРИЕМ…»)
            if m2:
                m = NUM_RE.match(l[1:]); jl = l[:30]
        ok = False
        if m:
            tup = tuple(int(x) for x in m.group(1).split('.'))
            rest = m.group(2)
            if len(tup) == 1:
                ok = tup[0] in (top + 1, top + 2) and rest.strip() != '' and (headlike(rest) or upper_head(rest))
                if ok:   # заголовок раздела: слова заглавными либо следом (≤8 строк) идёт «N.1» (строки таблиц «10 …» — не заголовки)
                    let = re.findall(r'[A-Za-zА-Яа-яЁё]', rest)
                    up = let and sum(c.isupper() for c in let) >= 0.8 * len(let)
                    ok = bool(up) or any(re.match(r'%d\.1\b' % tup[0], x.strip()) for x in lines[i + 1:i + 9])
                if ok: top = tup[0]
                elif tup[0] == top and cur and cur['tup'] == tup: ok = False
            else:
                par = tup[:-1]
                k = tup[-1]
                same_sec = tup[0] == top or (tup[0] == top + 1 and len(tup) == 2 and k == 1 and (top + 1,) not in seen) or (lenient and top <= tup[0] <= top + 6)
                if same_sec and (par in seen or par == (top,) or (par == (top + 1,) and k == 1) or (len(tup) >= 3 and par[:-1] in seen) or lenient) and rest.strip():   # lenient: английский поток без заголовков-родителей
                    prev = last_k.get(par, 0)
                    ok = (prev <= k <= prev + (3 if par in seen else 8)) if prev else k <= (3 if par in seen else 12)   # нет заголовка родителя — допускаем больший скачок
                    if ok and k == prev and tup in seen and lang(rest) in seen[tup]:
                        ok = 'rep' if allow_dup and len(tup) >= 3 else False   # Word: повтор номера (первый набран текстом, второй — автонумерация) → «N#2"
                    if ok and (tup[0] == top + 1 or (lenient and tup[0] > top)): top = tup[0]
            if not ok and tup in seen and rest.strip() and lang(rest) not in seen[tup] and len(rest.strip()) > 8:
                ok = 'dup'   # тот же номер на другом языке (блоком ниже/рядом) — порядок не проверяем
            if ok == 'rep':
                new('.'.join(map(str, tup)), tup, i, rest); continue
            if ok == 'dup':
                new('.'.join(map(str, tup)), tup, i, rest); continue
            if ok:
                if jl: junk.append(jl)
                if len(tup) > 1: last_k[tup[:-1]] = max(last_k.get(tup[:-1], 0), tup[-1])
                else: last_k.setdefault(tup, 0)
                new('.'.join(map(str, tup)), tup, i, rest if rest.strip() else l)
                continue
        if cur is None: continue
        cur['lines'].append(l)
    for p in pts:
        p['lines'] = [x for x in p['lines'] if x.strip()]
    return pts, ('лишний знак перед номером: ' + '; '.join(junk[:3])) if junk else '', st


TAIL_HEAD = re.compile(r'(?:^|(?<=[а-яё.,;:)\d]))\s*\d{1,2}(?:\.\d{1,2})*\.?\s*(?=[А-ЯЁ][А-ЯЁ0-9\s,()\-/«»".]{11,}$)')


def cut_tail(p):
    """Граница пункта: к концу пункта прилип заголовок следующего раздела прописными («… ответственность. 10 УЧАСТИЕ В РАБОТЕ КОМИССИИ …») — вырезаем.
    Строка заголовка целиком или хвост последней строки; пункт, заголовок которого сам прописной (первая строка), не трогаем."""
    ls = p['lines']
    def head(x):
        m = NUM_RE.match(x.strip())
        if not m or not m.group(2).strip(): return False
        let = re.findall(r'[A-Za-zА-Яа-яЁё]', m.group(2))
        return len(let) >= 8 and sum(c.isupper() for c in let) >= 0.9 * len(let)
    for j in range(len(ls) - 1, 0, -1):
        if ls[j].startswith(SHP): continue
        if head(ls[j]) and all(not x.startswith(SHP) and (len(x) < 150 or head(x)) for x in ls[j + 1:]) and len(ls) - j <= 4:
            p['lines'] = ls[:j]; return
        if j < len(ls) - 1 and not ls[j + 1].isupper(): break
    last = ls[-1] if ls else ''
    if ls and not last.startswith(SHP):
        m = TAIL_HEAD.search(last)
        if m and m.start() > (0 if len(ls) > 1 else 30):   # у однострочного пункта слева должен остаться текст (иначе это его собственный заголовок)
            ls[-1] = last[:m.start()].rstrip()
            if not ls[-1]: ls.pop()


# ---------------------------------------------------------------- отпечатки
INVIS = re.compile('[\u00ad\u200b-\u200f\u2060-\u2064\ufeff]')   # мягкий перенос, нулевая ширина, невидимые операторы
YESNO = {'да', 'нет'}


def vocab_of(lines):
    """Словарь слов документа (Word): нормализованные слова и их части по знакам."""
    v = set()
    for l in lines:
        for w in INVIS.sub('', l.lstrip(TCELL + SHP)).split():
            v.add(norm(w))
            v.update(norm(x) for x in re.split(r'[^\w]+', w) if x)
    v.discard('')
    return v


def heal(text, vocab):
    """Нормализованные слова текста, где разорванные слова склеены: на стыке соседних слов повтор 1–2 букв («перев возки», «изъ ъятие»,
    «кд-д дп-б1.002»), если склейка без повтора есть в словаре документа, а склейка с повтором и оба слова по отдельности — нет."""
    t = [x for x in (norm(w) for w in INVIS.sub('', text).split()) if x]
    if not vocab: return t
    out = []
    for w in t:
        while out:
            a = out[-1]; hit = None
            if a not in vocab and w not in vocab:
                for k in (2, 1):
                    if len(a) > k and len(w) > k and a[-k:] == w[:k] and (a + w[k:]) in vocab and (a + w) not in vocab: hit = a + w[k:]; break
            if not hit: break
            out.pop(); w = hit
        out.append(w)
    return out


def scheme_junk(ls):
    """Строки-остатки схем в конце/перед схемой, не помеченные SHP: латинская легенда («Data-in Process step»), «Да/Нет» развилок,
    одиночное слово перед блоком схемы."""
    ls = list(ls)
    k = len(ls)
    while k > 1 and lang(ls[k - 1]) == 'en' and '@' not in ls[k - 1]: k -= 1
    if 1 <= k < len(ls) and sum(len(x.split()) for x in ls[k:]) >= 3 and any(lang(x) == 'ru' for x in ls[:k]): ls = ls[:k]
    while len(ls) > 1 and ls[-1].split() and all(norm(w) in YESNO or not norm(w) for w in ls[-1].split()): ls.pop()
    return ls


def fingerprint(p, vocab=None):
    """fp — по всему тексту пункта; fp_core — «ядро»: без строк схем/рисунков (метка SHP: надписи Word, текст векторных схем PDF), без хвостовых
    номеров без текста, без прилипшего в конец заголовка следующего раздела, без латинской легенды и «Да/Нет» схем; невидимые символы удалены,
    разорванные слова склеены по словарю документа (heal). Совпадение по ядру только добавляет совпадения (fp не меняется)."""
    def one(lines):
        first = lines[0] if lines else ''
        # без номера в начале: у пункта номер — первая «лексема» первой строки
        first = NUM_RE.sub(lambda m: m.group(2), first, count=1) if p['tup'] is not None else APP_RE.sub(lambda m: m.group(3) or '', first, count=1)
        return ' '.join([first] + lines[1:])
    body = one([x.lstrip(SHP) for x in p['lines']])
    flat = norm(body)
    ls = p['lines']
    def tidy(lines):
        c = {'lines': [x for x in lines if not x.startswith(SHP)]}
        while len(c['lines']) > 1 and re.match(r'^\d{1,3}(?:\.\d{1,3})*\.?$', c['lines'][-1].strip()) and re.search(r'[.;:!?)»"]\s*$', c['lines'][-2]): c['lines'].pop()   # хвостовой номер без текста (пустой пронумерованный абзац Word)
        cut_tail(c)
        return c['lines']
    core0 = norm(one(tidy(ls)))   # прежнее ядро (без чистки схем и склейки слов): совпадение по нему сохраняется
    keep = []   # слово-остаток прямо перед блоком схемы («… регистрации.» / «рубежом» / схема)
    for i, x in enumerate(ls):
        if (not x.startswith(SHP) and i > 0 and i + 1 < len(ls) and ls[i + 1].startswith(SHP) and len(x.split()) <= 2 and x[:1].islower()
                and re.search(r'[.;:!?)»"]\s*$', ls[i - 1])): continue
        keep.append(x)
    cl = {'lines': tidy(keep)}
    cl['lines'] = scheme_junk(cl['lines'])
    ctext = one(cl['lines'])
    core = ''.join(heal(ctext, vocab))
    # fp_set: отсортированный набор знаков — не зависит ни от порядка строк/ячеек таблицы, ни от переносов внутри слов
    return {'fp': sha(flat), 'fp_set': sha(''.join(sorted(flat))), 'fp_core': sha(core), 'fp_core0': sha(core0), 'core_len': len(core), 'core0_len': len(core0), 'chars': len(flat), 'text': re.sub(r'\s+', ' ', body).strip(),
            'core_text': re.sub(r'\s+', ' ', ctext).strip()}


def wdiff(a, b, lim=300):
    """Пословный diff: (что в PDF, что в Word)."""
    ta = a.split(); tb = b.split()
    ka = [norm(w) for w in ta]; kb = [norm(w) for w in tb]
    sm = difflib.SequenceMatcher(None, ka, kb, autojunk=False)
    pa, pb = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal': continue
        x = ' '.join(ta[i1:i2]); y = ' '.join(tb[j1:j2])
        if x: pa.append(x)
        if y: pb.append(y)
    if len(pa) + len(pb) > 10:   # порядок слов разный (таблицы, схемы): показываем слова, которых нет с другой стороны (с кратностью)
        ca = collections.Counter(ka); cb = collections.Counter(kb)
        oa = ca - cb; ob = cb - ca
        pa, pb = [], []
        for w, k in zip(ta, ka):
            if oa.get(k, 0) > 0: pa.append(w); oa[k] -= 1
        for w, k in zip(tb, kb):
            if ob.get(k, 0) > 0: pb.append(w); ob[k] -= 1
        return ('[слова только в PDF] ' + ' '.join(pa))[:lim], ('[слова только в Word] ' + ' '.join(pb))[:lim]
    cut = lambda L: (' | '.join(L))[:lim]
    return cut(pa), cut(pb)


def compare(pp, wp):
    P = {p['num']: p for p in pp}; W = {p['num']: p for p in wp}
    res = []
    only_p = [n for n in P if n not in W]; only_w = [n for n in W if n not in P]
    merged = set()   # N#2 в Word, поглощённые пунктом N
    for n in P:
        if n not in W: continue
        a, b = P[n]['fp'], W[n]['fp']
        r = {'num': n, 'pdf': a['fp'], 'word': b['fp'], 'pdf_chars': a['chars'], 'word_chars': b['chars'], 'head': a['text'][:100]}
        if a['fp'] == b['fp']: r['status'] = 'совпадает'
        # ядро засчитывается только непустое (≥ 20 знаков): пункт-схема после очистки пуст, два пустых ядра — ложное совпадение (08.10)
        elif (a['fp_core'] == b['fp_core'] and min(a.get('core_len', 99), b.get('core_len', 99)) >= 20) or \
             (a['fp_core0'] == b['fp_core0'] and min(a.get('core0_len', 99), b.get('core0_len', 99)) >= 20):
            r['status'] = 'совпадает'; r['note'] = 'по ядру: без текста схем/рисунков, хвостовых номеров, прилипшего заголовка следующего раздела, невидимых символов; разорванные слова склеены'
        elif a['fp_set'] == b['fp_set']:
            r['status'] = 'совпадает (порядок иной)'
            if n.startswith('прил.'): r['note'] = 'схема/таблица — сверка по набору знаков (fp_set)'
        elif n + '#2' in only_w and a['fp'] == sha(norm(b['text']) + norm(W[n + '#2']['fp']['text'])):
            # номер набран в Word дважды (N и N#2), в PDF один пункт N: сумма текстов совпала — дефект нумерации сборки
            r['status'] = 'номер сбит'; r['word_num'] = n + '#2'; r['note'] = 'в Word номер N дважды; объединённый текст совпадает с пунктом PDF'
            merged.add(n + '#2')
        else:
            r['status'] = 'текст отличается'
            r['diff_pdf'], r['diff_word'] = wdiff(a['text'], b['text'])
        res.append(r)
    wfp = collections.defaultdict(list)
    for n in only_w: wfp[W[n]['fp']['fp']].append(n)
    used = set(merged)
    for n in only_p:
        a = P[n]['fp']
        cand = [x for x in wfp.get(a['fp'], []) if x not in used]
        r = {'num': n, 'pdf': a['fp'], 'pdf_chars': a['chars'], 'word': None, 'head': a['text'][:100]}
        if cand and a['chars'] >= 8:
            used.add(cand[0]); r.update(status='номер сбит' if '#' in cand[0] else 'номер сдвинут', word_num=cand[0], word=a['fp'])
        else:
            r['status'] = 'только в PDF'; r['diff_pdf'] = a['text'][:300]
        res.append(r)
    for n in only_w:
        if n in used: continue
        b = W[n]['fp']
        res.append({'num': n, 'pdf': None, 'head': b['text'][:100], 'word': b['fp'], 'word_chars': b['chars'], 'status': 'только в Word', 'diff_word': b['text'][:300]})
    return res


# ---------------------------------------------------------------- документ
def ref_pdf(doc):
    fs = sorted(glob.glob(os.path.join(FULL, 'src', doc, 'files', '*')))
    fs = [f for f in fs if f.lower().endswith('.pdf')]
    m = [f for f in fs if REF_RE.search(os.path.basename(f))]
    m = m or (fs if len(fs) == 1 else [])
    import pagediff
    return pagediff.latest_edition(m)   # несколько редакций эталона без «Часть N» — последняя (как в сборке, решение human 03.10.2026)


def run_doc(doc, row):
    out = {'doc': doc, 'title': row.get('title', ''), 'changes': row.get('changes', ''), 'build_status': row.get('status', ''), 'flags': []}
    pdfs = ref_pdf(doc)
    if len(pdfs) != 1:
        out['skip'] = f'эталонов {len(pdfs)}'; return out
    ct = os.path.join(STEP1, doc, 'canon_text.txt')   # пересобранный документ — новее
    out['source'] = 'step1'
    if not os.path.exists(ct): ct = os.path.join(FULL, 'out', doc, 'canon_text.txt'); out['source'] = os.path.basename(FULL)
    if not os.path.exists(ct):
        out['skip'] = 'нет canon_text.txt'; return out
    pl, pl_en, fl, pgs, bad = pdf_lines(pdfs[0]); out['flags'] += sorted(fl)
    wl = word_lines(ct)
    pp, e1, st = segment(pl, allow_dup=True); wp, e2, stw = segment(wl, allow_dup=True)
    for nm, ls, i0 in (('PDF', pl, st), ('Word', wl, stw)):
        if i0 is not None and re.match(r'\d+\.\d', ls[i0].lstrip(TCELL).strip()):
            out['flags'].append(f'{nm}: заголовка раздела 6 нет, старт по пункту «{ls[i0].lstrip(TCELL)[:8].strip()}»')
    if pp is not None and e1: out['flags'].append('PDF ' + e1)
    if wp is not None and e2: out['flags'].append('Word ' + e2)
    if pp is None: out['skip'] = 'PDF: ' + e1; return out
    if wp is None:
        out['flags'].append('Word: ' + e2); wp = []
    if len(pl_en) > 20:   # английская колонка двуязычных страниц: свой разбор, номера с суффиксом @en
        s0 = next((i for i, x in enumerate(pl_en) if re.match(r'6\.1\s+\S', x.strip())), None)
        pe, e3, _ = segment(pl_en, s0, lenient=True) if s0 is not None else (None, '', None)
        if pe:
            for q in pe: q['num'] += '@en'
            pp = pp + pe
        else: out['flags'].append('английская колонка не разобрана на пункты')
    late = [b for b in bad if b >= pgs[st]]
    if late: out['flags'].append('битый текстовый слой в содержательной части: стр. ' + ', '.join(map(str, late[:6])))
    if bad and not late: out['notes'] = f'битый текстовый слой до раздела 6 (титул/лист регистрации): стр. {bad[:6]} — не влияет'
    vocab = vocab_of(wl)
    for q in pp + wp: q['fp'] = fingerprint(q, vocab)
    res = compare(pp, wp)
    order = {q['num']: i for i, q in enumerate(pp)}
    res.sort(key=lambda r: order.get(r['num'], 10 ** 6 + len(r['num'])))
    out['points'] = res
    out['counts'] = dict(collections.Counter(r['status'] for r in res))
    out['bilingual'] = bool(fl and any('двуязычная' in x for x in fl))
    out['n_pdf'] = len(pp); out['n_word'] = len(wp)
    nums = [q['num'] for q in pp]
    if len(pp) > 3 and max(q['fp']['chars'] for q in pp) > 0.5 * sum(q['fp']['chars'] for q in pp):
        out['flags'].append('один пункт >50% текста (сегментация ненадёжна?)')
    if len(pp) < 5: out['flags'].append('мало пунктов в PDF (<5)')
    if any('#' in n for n in nums): out['flags'].append('повтор номеров в PDF')
    if any('#' in q['num'] for q in wp): out['flags'].append('повтор номеров в Word')
    return out


def is_app(r):
    return r['num'].startswith('прил.')


def summarize(out):
    """Пункты 6+ БЕЗ приложений: (всего, совпало, счётчики статусов)."""
    pts = [r for r in out.get('points', []) if not is_app(r)]
    c = collections.Counter(r['status'] for r in pts)
    return len(pts), c.get('совпадает', 0) + c.get('совпадает (порядок иной)', 0), dict(c)


def summarize_apps(out):
    """Приложения отдельно: (всего, совпало, из них по набору знаков, счётчики)."""
    pts = [r for r in out.get('points', []) if is_app(r)]
    c = collections.Counter(r['status'] for r in pts)
    return len(pts), c.get('совпадает', 0) + c.get('совпадает (порядок иной)', 0), c.get('совпадает (порядок иной)', 0), dict(c)


def main():
    args = sys.argv[1:]
    rows = list(csv.DictReader(open(os.path.join(FULL, 'summary.csv'), encoding='utf-8-sig'), delimiter=';'))
    byd = {r['doc_num']: r for r in rows}
    scope = [r['doc_num'] for r in rows if not r['doc_num'].startswith(('ИОТ', 'РПП', 'РОТО'))]
    os.makedirs(PTS, exist_ok=True)
    docs = scope if '--all' in args else [a for a in args if not a.startswith('--')]
    results = []
    for d in docs:
        row = byd.get(d, {})
        if '--all' in args and row.get('status') not in ('ready', 'not_ready'):
            out = {'doc': d, 'title': row.get('title', ''), 'changes': row.get('changes', ''), 'build_status': row.get('status', ''),
                   'skip': 'статус сборки ' + row.get('status', ''), 'flags': []}
        else:
            try: out = run_doc(d, row)
            except Exception as e:
                out = {'doc': d, 'title': row.get('title', ''), 'changes': row.get('changes', ''), 'build_status': row.get('status', ''), 'skip': 'ошибка: %r' % e, 'flags': []}
        json.dump(out, open(os.path.join(PTS, d + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        tot, ok, c = summarize(out)
        print(f"{d}: пунктов {tot}, совпало {ok} ({100 * ok / tot:.1f}%)" if tot else f"{d}: {out.get('skip')}", dict(c), out['flags'], flush=True)
        results.append(out)
    if '--all' in args or '--readme' in args:
        write_summary(scope, byd)


def write_summary(scope, byd):
    res = []
    for d in scope:
        p = os.path.join(PTS, d + '.json')
        if os.path.exists(p): res.append(json.load(open(p, encoding='utf-8')))
    pc = lambda a, b: f'{100 * a / b:.1f}' if b else ''
    with open(os.path.join(PTS, 'summary.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['doc', 'title', 'изменений', 'статус сборки', 'источник Word', 'bilingual', 'пунктов 6+ (без приложений)', 'совпало', 'текст отличается', 'номер сдвинут',
                    'номер сбит', 'только PDF', 'только Word', '% пунктов 6+', 'приложений', 'приложений совпало', 'из них по набору знаков (схема/таблица)', '% приложений', 'флаги', 'пропущен'])
        for o in res:
            tot, ok, c = summarize(o); at, ak, aset, _ = summarize_apps(o)
            w.writerow([o['doc'], o['title'], o['changes'], o['build_status'], o.get('source', ''), 'да' if o.get('bilingual') else '', tot, ok, c.get('текст отличается', 0),
                        c.get('номер сдвинут', 0), c.get('номер сбит', 0), c.get('только в PDF', 0), c.get('только в Word', 0), pc(ok, tot), at, ak, aset, pc(ak, at),
                        '; '.join(o['flags']), o.get('skip', '')])
    done = [o for o in res if not o.get('skip') and o.get('points')]
    skipped = [o for o in res if o.get('skip')]
    full = [o for o in done if summarize(o)[0] == summarize(o)[1]]
    pct = lambda o: 100 * summarize(o)[1] / summarize(o)[0] if summarize(o)[0] else 0
    bins = collections.Counter()
    for o in done:
        x = pct(o)
        bins['100 %' if x == 100 else '95–99,9 %' if x >= 95 else '80–94,9 %' if x >= 80 else '50–79,9 %' if x >= 50 else '< 50 %'] += 1
    tp = sum(summarize(o)[0] for o in done); tk = sum(summarize(o)[1] for o in done)
    ap = sum(summarize_apps(o)[0] for o in done); ak = sum(summarize_apps(o)[1] for o in done); aset = sum(summarize_apps(o)[2] for o in done)
    L = ['# Сверка по отпечаткам пунктов 6+ (эталон PDF ↔ канон Word)', '',
         'Каждому пункту раздела 6 и далее даётся отпечаток — хэш текста без регистра, пробелов, знаков и номера пункта. '
         'Пункт совпал, если отпечаток в PDF и в Word одинаков. Метод не подгоняется под 100 %: где разбор на пункты ненадёжен, документ помечен флагом. '
         'Строки оглавления (точки-заполнители и номер страницы) пунктами не считаются; заголовок в теле — пункт, даже если регистр иной.', '',
         '**Пункты 6+ и приложения считаются раздельно. «% документа» — только по пунктам 6+.**', '',
         f'- Документов в объёме: {len(res)}; сверено: {len(done)}; пропущено: {len(skipped)} (статус сборки не ready/not_ready, нет эталона и т. п.).',
         f'- Пункты 6+: на 100 % совпали **{len(full)}** из {len(done)} документов; всего пунктов {tp}, совпало {tk} ({100 * tk / max(tp, 1):.1f} %).',
         f'- Приложения: всего {ap}, совпало {ak} ({100 * ak / max(ap, 1):.1f} %), из них только по набору знаков (схема/таблица — сверка по fp_set): {aset}.',
         '- Источник Word: если документ пересобран в `data/canon_reeng/step1/out/<doc>/`, берётся оттуда (новее), иначе из `full2/out/` (столбец «источник Word» в summary.csv).', '',
         '## Распределение документов по доле совпавших пунктов 6+', '']
    for k in ('100 %', '95–99,9 %', '80–94,9 %', '50–79,9 %', '< 50 %'): L.append(f'- {k}: {bins.get(k, 0)}')
    L += ['', 'Статусы: «совпадает (порядок иной)» — тот же набор знаков, другой порядок строк (таблицы); засчитано как совпавшее. '
          '«Номер сдвинут» — такой же текст в Word под другим номером. «Номер сбит» — в Word номер повторился (`N#2`), а текст совпал с пунктом PDF под соседним номером: это дефект нашей сборки/нумерации, не дефект документа.', '',
          '## Что метод не умеет (честные ограничения)', '',
          '- Схемы и рисунки: в PDF текст схемы идёт кусками, в Word — надписями; приложения со схемами/таблицами сверяются по набору знаков (fp_set) и помечены.',
          '- Таблицы: в PDF строка читается слева направо, в Word — по ячейкам; ловится «порядок иной»; переносы слов внутри ячеек и сноски дают «текст отличается».',
          '- Двуязычные документы (флаг bilingual): колонки делятся по x-середине блока fitz относительно середины страницы; английская колонка — отдельный поток (номера «N@en»). Если английского текста в Word нет — пункты «только в PDF».',
          '- Номера пунктов принимаются только по последовательности (6 → 6.1 → 6.2 …); потерянный или пропущенный номер в одном из источников ломает отпечаток соседнего пункта.',
          '- Колонтитулы снимаются в верхних 12,5 % и нижних 8 % страницы; нестандартный колонтитул может оставить строку.', '',
          '## Документы с флагами ненадёжной сегментации', '']
    for o in [o for o in done if o['flags']][:80]: L.append(f"- {o['doc']}: {'; '.join(o['flags'])} ({pct(o):.0f} %)")
    L += ['', '## Топ-20 документов с расхождениями (пункты 6+)', '']
    for o in sorted([o for o in done if pct(o) < 100], key=lambda o: (pct(o), -summarize(o)[0]))[:20]:
        tot, ok, c = summarize(o)
        L.append(f"### {o['doc']} — {o['title']} ({pct(o):.1f} %, {ok}/{tot}; изменений {o['changes']}, сборка {o['build_status']})")
        n = 0
        for r in o['points']:
            if r['status'].startswith('совпадает') or is_app(r): continue
            if r['status'] == 'текст отличается':
                L.append(f"- п. {r['num']}: текст отличается. PDF: «{r.get('diff_pdf', '')[:160]}» / Word: «{r.get('diff_word', '')[:160]}»")
            elif r['status'] in ('номер сдвинут', 'номер сбит'):
                L.append(f"- п. {r['num']} в PDF — в Word под номером {r.get('word_num')} ({r['status']})")
            elif r['status'] == 'только в PDF':
                L.append(f"- п. {r['num']}: только в PDF: «{r.get('diff_pdf', '')[:160]}»")
            else:
                L.append(f"- п. {r['num']}: только в Word: «{r.get('diff_word', '')[:160]}»")
            n += 1
            if n >= 3: break
        L.append('')
    if skipped:
        L += ['## Пропущены', ''] + [f"- {o['doc']}: {o['skip']}" for o in skipped]
    vp = os.path.join(PTS, 'verification.md')   # проверка глазами (пишется вручную)
    if os.path.exists(vp): L += ['', open(vp, encoding='utf-8').read().rstrip()]
    open(os.path.join(PTS, 'README.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
