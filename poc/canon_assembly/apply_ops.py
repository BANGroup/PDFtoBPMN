"""Применение протокола правок (ops/<документ>/izm<N>.json) к базовому Word по адресам пунктов + сверка с эталоном.

python3 apply_ops.py <папка документа> [--dump out.txt]
"""
import sys, re, glob, os, json, difflib, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assemble as A
import body as B
import docx_numbering as N

HERE = os.path.dirname(os.path.abspath(__file__))
POINT = re.compile(r'^(\d+(?:\.\d+)+)\.?\s+\S')
SECT = re.compile(r'^(\d+)\.?\s+[А-ЯЁA-Z]')
APX = re.compile(r'^(приложение|annex)\s*(?:№\s*)?(\d+)\b', re.I)
FRONT = {'предисловие': 'Предисловие', 'лист регистрации внесения изменений': 'Лист регистрации',
         'перечень рассылки': 'Перечень рассылки', 'содержание': 'Содержание'}
QUAL = re.compile(r'абзац|дефис|строк|номер|к\.т|подпункт|пп\.|заголовок|название|определени|таблиц|сокращени', re.I)


# ---------- нормализация текста ----------
def key(s):
    return A.norm(B.strip_num(s))


def ratio(a, b):
    a, b = key(a), key(b)
    if not a or not b or abs(len(a) - len(b)) > max(len(a), len(b)) * 0.6:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def rx(s):
    """Регэксп для точного поиска фрагмента с допуском: пробелы, ё/е, кавычки, тире."""
    out, sp = [], False
    for ch in s.strip():
        if ch.isspace():
            if not sp: out.append(r'\s+')
            sp = True; continue
        sp = False
        if ch in 'её': out.append('[её]')
        elif ch in 'ЕЁ': out.append('[ЕЁ]')
        elif ch in '«»"“”„‟\'’‘': out.append('["«»“”„‟\'’‘]')
        elif ch in '-–—−‐‑': out.append('[-–—−‐‑]')
        else: out.append(re.escape(ch))
    return re.compile(''.join(out))


def tidy(t):
    t = re.sub(r'[ \t]{2,}', ' ', t)
    t = re.sub(r'\s+([,;.:])', r'\1', t)
    return t.strip()


def num_tuple(s):
    return tuple(int(x) for x in s.split('.') if x)


def quoted(s):
    return re.findall(r'[«"“]([^»"”]+)[»"”]', s or '')


# ---------- состояние ----------
def load_paras(path):
    out = []
    for num, t in N.numbered_paragraphs(path):
        if num:
            num = re.sub(r'^(\d+)\.$', r'\1)', num)   # одноуровневые «1.» автосписка — не заголовок раздела
            t = f'{num} {t}'
        out.append(t)
    return out


def base_file(ddir):
    return max([f for f in glob.glob(ddir + '/word/*.docx') if A.classify(f) == 'sheets'], key=os.path.getsize)


def sheets_paras(ddir, izm):
    """Абзацы листов замены изменения izm (по порядку страниц)."""
    out = []
    for adir in glob.glob(ddir + f'/amendments/*изм{izm}.0'):
        for f in sorted([f for f in glob.glob(adir + '/*.docx') if A.classify(f) == 'sheets'], key=A.page_key):
            out += load_paras(f)
    return out


# ---------- адресация ----------
class Doc:
    """Индекс структуры списка абзацев: границы основного текста, заголовки пунктов, приложения."""
    def __init__(self, paras, sheet=False):
        self.p = paras
        if sheet:
            self.s, self.e = 0, len(paras)
            self.ax = 0
            self.fe = len(paras)
        else:
            body, appx = B.split_body(paras)
            self.s = len(paras) - len(body) - len(appx)
            self.e = self.s + len(body)
            self.ax = self.e
            self.fe = self.s
        self.heads = []   # (idx, tuple)
        for i in range(self.s, self.e):
            t = paras[i].strip()
            m = POINT.match(t)
            if not m:
                m = SECT.match(t)
                if not m or len(t) > 160: continue
            self.heads.append((i, num_tuple(m.group(1))))

    def head(self, num):
        tu = num_tuple(num)
        return next((i for i, t in self.heads if t == tu), None)

    def area_of(self, i):
        lvl = next(len(t) for j, t in self.heads if j == i)
        hi = next((j for j, t in self.heads if j > i and len(t) <= lvl), self.e)
        return i, hi

    def appendix_area(self, name):
        m = APX.match(name)
        kind, n = m.group(1).lower(), int(m.group(2))
        def is_h(j):
            mm = APX.match(self.p[j].strip())
            return mm and len(self.p[j].split()) < 25 and not re.search(r'\.{4,}|…', self.p[j]) and mm
        for i in range(self.ax, len(self.p)):
            mm = is_h(i)
            if mm and mm.group(1).lower() == kind and int(mm.group(2)) == n:
                # область — до заголовка другого приложения (двуязычные: «Приложение N» + «Annex N» — одно)
                hi = next((j for j in range(i + 1, len(self.p)) if is_h(j) and int(is_h(j).group(2)) != n), len(self.p))
                return i, hi
        return None

    def front_area(self, name):
        want = A.norm(name)
        marks = [(i, fkey(self.p[i])) for i in range(self.fe) if fkey(self.p[i]) in FRONT and not re.search(r'\d$', self.p[i].strip())]
        for k, (i, n) in enumerate(marks):
            if n == want:
                hi = marks[k + 1][0] if k + 1 < len(marks) else self.fe
                if self.fe != self.s:   # листы замены: служебный блок кончается там, где начинается пункт/приложение
                    hi = min(hi, next((j for j in range(i + 1, hi) if POINT.match(self.p[j].strip())
                                       or SECT.match(self.p[j].strip()) or APX.match(self.p[j].strip())), hi))
                return i, hi
        return None


def fkey(p):
    """Ключ служебного заголовка: русская часть до «/» (двуязычные документы)."""
    return A.norm(p.split('/')[0]) if len(p) < 90 else ''


def parse_range(pt):
    m = re.fullmatch(r'\s*(\d+(?:\.\d+)*)\s*[-–—]\s*(\d+(?:\.\d+)*)\s*', pt or '')
    return (m.group(1), m.group(2)) if m else None


def resolve(doc, loc):
    """-> ('area', lo, hi, kind, ident) | ('missing', why) | ('whole',) ."""
    pt, sec = (loc.get('point') or '').strip(), (loc.get('section') or '').strip()
    rg = parse_range(pt)
    if rg:
        a, b = num_tuple(rg[0]), num_tuple(rg[1])
        hits = [i for i, t in doc.heads if len(t) == len(a) and t[:-1] == a[:-1] and a[-1] <= t[-1] <= b[-1]]
        if not hits:
            return ('missing', f'пункты {pt} в тексте не найдены', 'range', rg[0])
        # union каждой области (не «от первой до последней»: в двуязычных блоках между ними чужие пункты)
        return ('area', hits[0], max(doc.area_of(i)[1] for i in hits), 'range', rg[0], [doc.area_of(i) for i in hits])
    for cand in (pt, sec):
        if not cand: continue
        if re.fullmatch(r'\d+(\.\d+)*', cand):
            i = doc.head(cand)
            if i is None:
                return ('missing', f'пункт {cand} в тексте не найден', 'num', cand)
            lo, hi = doc.area_of(i)
            # все одноимённые заголовки (двуязычные блоки: русский и английский пункт с одним номером)
            same = [doc.area_of(j) for j, t in doc.heads if t == num_tuple(cand)]
            return ('area', lo, hi, 'num', cand, same)
        if APX.match(cand):
            r = doc.appendix_area(cand)
            if r is None:
                return ('missing', f'«{cand}» в тексте не найдено', 'appx', cand)
            return ('area', r[0], r[1], 'appx', cand)
        if A.norm(cand.split('/')[0]) in FRONT:
            r = doc.front_area(cand)
            if r is None:
                return ('missing', f'раздел «{cand}» не найден', 'front', cand)
            return ('area', r[0], r[1], 'front', cand)
    return ('whole',)


def area_or_all(doc, loc):
    r = resolve(doc, loc)
    if r[0] == 'whole':
        # без адреса: основной текст (если section — число) иначе весь документ
        return ('area', doc.s, doc.e, 'whole', '') if re.fullmatch(r'\d+', (loc.get('section') or '')) else \
               ('area', 0, len(doc.p), 'whole', '')
    return r


def insert_pos(doc, num):
    """Индекс, перед которым вставить пункт num (по номеру)."""
    tu = num_tuple(num)
    return next((i for i, t in doc.heads if t > tu), doc.e)


def appendix_insert_pos(doc, name):
    m = APX.match(name)
    n = int(m.group(2)); kind = m.group(1).lower()
    for i in range(doc.ax, len(doc.p)):
        mm = APX.match(doc.p[i].strip())
        if mm and mm.group(1).lower() == kind and int(mm.group(2)) > n and len(doc.p[i].split()) < 25 \
                and not re.search(r'\.{4,}|…', doc.p[i]):
            return i
    return len(doc.p)


def split_new(new):
    return [x.strip() for x in re.split(r'\n+', new or '') if x.strip()]


# ---------- операции ----------
class Res:
    def __init__(self, status, why=''):
        self.status, self.why = status, why


def elsewhere(S, old, lo, hi):
    r = rx(old)
    for i, t in enumerate(S):
        if not (lo <= i < hi) and r.search(t):
            return f'; текст есть вне области (абз. {i}: «{t[:50]}»)'
    return ''


def op_replace(S, doc, op, r):
    old, new = op.get('old'), op.get('new')
    if not old or new is None:
        return Res('NOT_FOUND', 'в правке нет old/new (текст в листе не приведён)')
    _, lo, hi = r[:3]
    pat, cnt = rx(old), 0
    for i in range(lo, hi):
        t, k = pat.subn(lambda m: new, S[i])
        if k: S[i] = t; cnt += k
    if cnt:
        return Res('APPLIED', f'замен: {cnt}')
    why = 'old не найден в области'
    if any(rx(new).search(S[i]) for i in range(lo, hi)):
        why += '; new уже присутствует'
    return Res('NOT_FOUND', why + elsewhere(S, old, lo, hi))


def similar(S, lo, hi, text, thr=0.5):
    best, bi = thr, None
    for i in range(lo, hi):
        rr = ratio(S[i], text)
        if rr >= best: best, bi = rr, i
    return bi, best


def op_restate(S, doc, op, r):
    new = op.get('new')
    if not new:
        return Res('SKIPPED', 'нет new')
    _, lo, hi, kind, ident = r[:5]
    part = op.get('locator', {}).get('part') or ''
    paras = split_new(new)
    if kind == 'num' and not QUAL.search(part):
        head = S[lo]
        m = re.match(r'^(\d+(?:\.\d+)*)\.?\s', head)
        if m and not POINT.match(paras[0]) and not SECT.match(paras[0]):
            paras[0] = f'{m.group(1)} {paras[0]}'
        S[lo:lo + 1] = paras
        return Res('APPLIED', f'абзац пункта {ident} заменён')
    i, rr = similar(S, lo, hi, new)
    if i is None:
        return Res('NOT_FOUND', f'в области нет абзаца, похожего на new (ratio<0.5; part «{part[:40]}»)')
    m = APX.match(S[i].strip())
    if m and not APX.match(paras[0]):
        pre = re.match(r'^(приложение|annex)\s*(?:№\s*)?\d+[.\s]*', S[i].strip(), re.I).group(0)
        paras[0] = pre + paras[0]
    S[i:i + 1] = paras
    return Res('APPLIED', f'заменён абзац {i} (ratio {rr:.2f})')


def del_spans(S, spans):
    """Удалить объединение областей [lo, hi); вернуть число удалённых абзацев."""
    idx = sorted({i for lo, hi in spans for i in range(lo, hi)}, reverse=True)
    for i in idx:
        del S[i]
    return len(idx)


def op_delete(S, doc, op, r):
    old = op.get('old')
    part = op.get('locator', {}).get('part') or ''
    kind, lo, hi = r[3], r[1], r[2]
    spans = r[5] if len(r) > 5 else [(lo, hi)]
    if kind == 'whole' and not old:
        return Res('NOT_FOUND', 'нет адреса и нет old')
    if kind != 'whole' and not old and not re.search(r'после сло\w+ «', part):
        if re.search(r'все пункты', part):
            spans = [(a + 1, b) for a, b in spans]   # заголовок раздела остаётся
        n = del_spans(S, spans)
        return Res('APPLIED', f'удалены области ({len(spans)}), {n} абз.')
    if not old:
        q = quoted(part)
        if q and re.search(r'до конца', part):
            pat = rx(q[0])
            for i in range(lo, hi):
                m = pat.search(S[i])
                if m:
                    S[i] = S[i][:m.end()].rstrip(' ,;') + ('.' if S[i].rstrip().endswith('.') else '')
                    return Res('APPLIED', f'усечён абз. {i} после «{q[0]}»')
            return Res('NOT_FOUND', f'слово «{q[0]}» не найдено в области')
        return Res('NOT_FOUND', 'нет old и способ удаления не определён')
    if kind != 'whole' and re.search(r'целиком', part):   # «приложение целиком»: старый текст не важен
        n = del_spans(S, spans)
        return Res('APPLIED', f'удалена область целиком, {n} абз.')
    whole = [i for i in range(lo, hi) if ratio(S[i], old) >= 0.9]
    if whole:
        for i in reversed(whole): del S[i]
        return Res('APPLIED', f'удалён абзац целиком ({len(whole)})')
    pat, cnt = rx(old), 0
    for i in range(lo, hi):
        t, k = pat.subn('', S[i])
        if k: S[i] = tidy(t); cnt += k
    if cnt:
        S[lo:hi] = [t for t in S[lo:hi] if t]
        return Res('APPLIED', f'удалён фрагмент ({cnt})')
    return Res('NOT_FOUND', 'old не найден в области' + elsewhere(S, old, lo, hi))


def op_renumber(S, doc, op, r):
    old, new = (op.get('old') or '').strip(), (op.get('new') or '').strip()
    if not old or not new: return Res('NOT_FOUND', 'нет old/new')
    lo, hi = r[1], r[2]
    if r[3] == 'whole':
        return Res('NOT_FOUND', 'нет адреса')
    pat = re.compile(r'^' + re.escape(old) + r'(?=\.?\s)')
    for i in range(lo, hi):
        if pat.match(S[i].strip()):
            S[i] = pat.sub(new, S[i].strip(), count=1)
            return Res('APPLIED', f'номер {old} → {new} (абз. {i})')
    return Res('NOT_FOUND', f'абзац с номером {old} не найден')


def op_insert(S, doc, op, r, sheet_doc=None):
    new = op.get('new')
    if not new:
        return Res('SKIPPED', 'нет new')
    loc = op.get('locator', {})
    part = loc.get('part') or ''
    paras = split_new(new)
    _, lo, hi, kind, ident = r[:5] if r[0] == 'area' else (None, 0, len(S), 'missing', ident_of(loc))
    # дубль
    rng = range(lo, hi) if r[0] == 'area' else range(len(S))
    m = POINT.match(paras[0]) or SECT.match(paras[0])
    if m:   # пункт с номером считается дублем только при том же номере
        i0 = doc.head(m.group(1))
        dup = i0 is not None and ratio(S[i0], paras[0]) >= 0.95
    else:
        dup = any(key(S[i]) == key(paras[0]) for i in rng)
    if dup:
        return Res('SKIPPED', 'такой абзац уже есть (дубль не вставлен)')
    if m:   # новый пункт с номером
        num = m.group(1)
        pos = insert_pos(doc, num)
        S[pos:pos] = paras
        return Res('APPLIED', f'пункт {num} вставлен перед абз. {pos}')
    if r[0] == 'missing' and r[2] == 'num' and ident_of(loc):
        # адресуемого пункта нет; создаём пункт с номером из локатора
        num = ident_of(loc)
        if not POINT.match(num + ' x'):
            return Res('NOT_FOUND', r[1])
        paras[0] = f'{num} {paras[0]}'
        S[insert_pos(doc, num):insert_pos(doc, num)] = paras
        return Res('APPLIED', f'пункта {num} нет — создан из new (номер из локатора)')
    if r[0] == 'missing':
        return Res('NOT_FOUND', r[1])
    # вставка внутрь текста
    q = quoted(part)
    mb = re.search(r'после\s+(слов\w*|текст\w*|слова)\s+«', part)
    mf = re.search(r'перед\s+(слов\w*|текст\w*)\s+«', part)
    if (mb or mf) and q:
        anchor = q[-1].strip().rstrip(';.,: ')
        pat = rx(anchor)
        cands = [i for i in range(lo, hi) if pat.search(S[i])]
        if len(cands) > 1 and len(q) > 1:
            c2 = [i for i in cands if A.norm(S[i]).startswith(A.norm(q[0]))]
            cands = c2 or cands
        if not cands:
            return Res('NOT_FOUND', f'якорь «{anchor[:50]}» не найден в области')
        i = cands[0]; m2 = pat.search(S[i]); t = S[i]
        if mb:
            rest = t[m2.end():]
            if not re.sub(r'[\s.,;:]', '', rest):
                S[i + 1:i + 1] = paras
                return Res('APPLIED', f'новый абзац после абз. {i} (якорь в конце абзаца)')
            S[i] = t[:m2.end()] + ' ' + ' '.join(paras) + rest
            return Res('APPLIED', f'вставка внутрь абз. {i} после якоря')
        S[i] = t[:m2.start()] + ' '.join(paras) + ' ' + t[m2.start():]
        return Res('APPLIED', f'вставка внутрь абз. {i} перед якорем')
    if re.search(r'новый первый абзац', part) and kind == 'num':
        mm = re.match(r'^(\d+(?:\.\d+)*)\.?\s+', S[lo])
        if mm:
            S[lo] = S[lo][mm.end():]
            paras[0] = f'{mm.group(1)} {paras[0]}'
        S[lo:lo] = paras
        return Res('APPLIED', f'новый первый абзац пункта {ident}')
    # в конец области адреса (сокращения, документы, «дополнить текстом»)
    if kind == 'whole':
        return Res('NOT_FOUND', 'нет адреса для вставки')
    S[hi:hi] = paras
    return Res('APPLIED', f'в конец области ({kind} {ident}) перед абз. {hi}')


def ident_of(loc):
    p = (loc.get('point') or '').strip()
    return p if re.fullmatch(r'\d+(\.\d+)+', p) else ''


def op_sheets(S, doc, op, r, sheet):
    """new_in_sheets: заменить/вставить область того же адреса из листов замены."""
    loc = op['locator']
    if not sheet:
        return Res('NOT_IN_SHEETS', 'листов замены изменения нет')
    sd = Doc(sheet, sheet=True)
    rs = resolve(sd, loc)
    if rs[0] != 'area':
        return Res('NOT_IN_SHEETS', 'адрес не найден в листах замены' + (f' ({rs[1]})' if rs[0] == 'missing' else ''))
    _, slo, shi, kind, ident = rs[:5]
    chunk = sheet[slo:shi]
    if not chunk:
        return Res('NOT_IN_SHEETS', 'область в листах пуста')
    if r[0] == 'area' and r[3] != 'whole':
        lo, hi = r[1], r[2]
        S[lo:hi] = chunk
        return Res('APPLIED', f'область абз. {lo}-{hi - 1} ({hi - lo}) заменена областью листа ({len(chunk)} абз.)')
    if kind == 'num' or kind == 'range':
        pos = insert_pos(doc, ident)
    elif kind == 'appx':
        pos = appendix_insert_pos(doc, ident)
    else:
        return Res('NOT_FOUND', 'области нет в состоянии, место вставки неизвестно')
    S[pos:pos] = chunk
    return Res('APPLIED', f'область листа ({len(chunk)} абз.) вставлена перед абз. {pos}')


def run_op(S, ddir, izm, op, sheet):
    act = op['action']
    if act == 'other':
        return Res('SKIPPED', 'action=other (точный текст/место не определены)')
    doc = Doc(S)
    loc = op['locator']
    if op.get('new_in_sheets'):
        r = area_or_all(doc, loc)
        return op_sheets(S, doc, op, r, sheet)
    r = area_or_all(doc, loc)
    if act == 'insert':
        return op_insert(S, doc, op, r)
    if r[0] == 'missing':
        return Res('NOT_FOUND', r[1] + ' (GAP базы?)')
    return {'replace': op_replace, 'restate': op_restate, 'delete': op_delete, 'renumber': op_renumber}[act](S, doc, op, r)


CYR = re.compile(r'[А-Яа-яЁё]')
LAT = re.compile(r'[A-Za-z]{3}')


def is_en(t):
    return bool(LAT.search(t)) and not CYR.search(t)


def en_run(L, i):
    j = i
    while j < len(L) and is_en(L[j]) and j - i < 6: j += 1
    return j


def lead(t):
    m = re.match(r'^(\d+(?:\.\d+)*)\.?\s', t.strip())
    return m.group(1) if m else None


def pair_en(S, touched, sheet):
    """Двуязычные документы: протокол даёт только русский текст; английские абзацы-пары берём из листов замены
    (абзац листа, совпадающий с изменённым русским абзацем, и следующие за ним англоязычные абзацы).
    Каждый английский абзац листа заменяет самый похожий английский абзац состояния (ratio>=0.5, тот же номер),
    иначе вставляется после русского абзаца."""
    added = replaced = 0
    for i in range(len(S)):
        t = S[i]
        if t not in touched or not CYR.search(t) or is_en(t):
            continue
        j = next((k for k, x in enumerate(sheet) if CYR.search(x) and ratio(x, t) >= 0.9), None)
        if j is None:
            continue
        pos = i
        for e in sheet[j + 1:en_run(sheet, j + 1)]:
            cands = [(ratio(S[k], e), k) for k in range(len(S)) if is_en(S[k]) and lead(S[k]) == lead(e)]
            rr, k = max(cands, default=(0, None))
            if rr >= 0.999:
                pos = k
            elif rr >= 0.5:
                S[k] = e; replaced += 1; pos = k
            else:
                S.insert(pos + 1, e); added += 1; pos += 1
    return added, replaced


def apply_all(ddir):
    S = load_paras(base_file(ddir))
    base = list(S)
    results = []   # (izm, op, Res)
    pairs = []     # (izm, добавлено EN, заменено EN)
    for jf in sorted(glob.glob(os.path.join(HERE, 'ops', os.path.basename(ddir.rstrip('/')), 'izm*.json')),
                     key=lambda p: int(re.search(r'izm(\d+)', p).group(1))):
        j = json.load(open(jf, encoding='utf-8'))
        izm = j['izm']
        sheet = sheets_paras(ddir, izm)
        touched = set()
        for op in sorted(j['ops'], key=lambda o: o['n']):
            before = collections.Counter(S)
            try:
                res = run_op(S, ddir, izm, op, sheet)
            except Exception as ex:   # не прятать: статус + тип ошибки
                res = Res('NOT_FOUND', f'ошибка применения {type(ex).__name__}: {ex}')
            S[:] = [t for t in (x.strip() for x in S) if t]
            after = collections.Counter(S)
            touched |= {t for t, c in after.items() if c > before[t]}
            results.append((izm, op, res))
        if sheet:
            a, r = pair_en(S, touched, sheet)
            if a or r: pairs.append((izm, a, r))
    return base, S, results, pairs


def main(ddir, dump=None):
    ddir = ddir.rstrip('/')
    base, S, results, pairs = apply_all(ddir)
    print(f'{os.path.basename(ddir)}: база {os.path.basename(base_file(ddir))} — {len(base)} абз.; после протокола {len(S)} абз.')
    print('Правки:')
    for izm, op, res in results:
        print(f'  изм{izm} #{op["n"]:<2} {op["action"]:8} {res.status:13} {res.why[:110]}')
    cnt = collections.defaultdict(collections.Counter)
    for izm, op, res in results:
        cnt[izm][res.status] += 1
    for izm, a, r in pairs:
        print(f'  англ. пары из листов замены изм{izm}: добавлено {a}, заменено {r}')
    print('Итог по статусам:')
    tot = collections.Counter()
    for izm in sorted(cnt):
        tot.update(cnt[izm])
        print(f'  изм{izm}: ' + ', '.join(f'{k} {v}' for k, v in sorted(cnt[izm].items())))
    print('  всего: ' + ', '.join(f'{k} {v}' for k, v in sorted(tot.items())) + f' из {sum(tot.values())}')
    print('Не-APPLIED:')
    for izm, op, res in results:
        if res.status != 'APPLIED':
            print(f'  изм{izm} #{op["n"]} {res.status}: {res.why[:90]} | {op["source_line"][:120]}')
    # сверка с эталоном
    canon = [f for f in glob.glob(ddir + '/files/*.pdf') if re.search('[Ээ]талон', f)][0]
    ps, pb, pa = B.split_core(B.pdf_lines(canon))
    _, sheets_doc, _ = B.assemble_doc(ddir, False)
    print(f'Сверка с эталоном: служебные {len(B.words(ps))} слов, содержательный {len(B.words(pb))} слов (с «{pb[0][:30]}»), приложения {len(B.words(pa))} слов')
    for name, d in (('база', base), ('по листам', sheets_doc), ('по протоколу', S)):
        ws, wb, wa = B.split_core(d)
        r0, x0 = B.measure(name, B.words(ws), B.words(ps))
        r1, x1 = B.measure(name, B.words(wb), B.words(pb))
        r2, x2 = B.measure(name, B.words(wa), B.words(pa))
        print(f'  {name:12}: СОДЕРЖАТЕЛЬНЫЙ {r1:.1%} (лишнего {x1:.1%}) | служебные 1–4 {r0:.1%} (лишнего {x0:.1%}) | приложения {r2:.1%} (лишнего {x2:.1%})')
    _, wb, _ = B.split_core(S)
    print('  Крупнейшие расхождения содержательного текста (по протоколу vs эталон):')
    B.show_diff(B.words(wb), B.words(pb), 12)
    if dump:
        open(dump, 'w', encoding='utf-8').write('\n'.join(S))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[sys.argv.index('--dump') + 1] if '--dump' in sys.argv else None)
