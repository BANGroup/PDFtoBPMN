"""Применение протоколов (логика apply_ops.py) с отслеживанием источника каждого абзаца + улучшения human 30.09:
 (а) old не найден -> пункт целиком из листа замены того же изменения;
 (б) двуязычные документы: русский и английский блоки пункта меняются вместе по номеру пункта;
 (в) таблицы и рисунки из листов замены переносятся целиком (элементы листа несут структуру).

apply_tracked(ddir, base_items, sheets_by_izm) -> (S, L, results, pairs)
  S — список абзацев (строки, как в apply_ops); L — параллельный список меток {src, meta, was};
  src: word_base | protocol:izmK | sheet:izmK
"""
import os, re, sys, glob, json, difflib, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_ops as AO
import word_parse as WP

HERE = os.path.dirname(os.path.abspath(__file__))
META_KEYS = ('kind', 'tbl', 'cell', 'role', 'docling', 'num', 'gfx')


def meta_of(it):
    return {k: it[k] for k in META_KEYS if k in it}


class Pool:
    """Элементы листов замены изменения: поиск метаданных по тексту с сохранением порядка."""
    def __init__(self, items):
        self.items = items
        self.by = collections.defaultdict(list)
        for i, it in enumerate(items):
            self.by[it['text']].append(i)
        self.last = -1

    def take(self, text):
        c = self.by.get(text)
        if not c:
            return None
        nxt = next((i for i in c if i > self.last), c[0])
        self.last = nxt
        return meta_of(self.items[nxt])


def track(before, after, L, src, pool=None, inherit=False):
    """Метки для after по разнице before -> after."""
    sm = difflib.SequenceMatcher(None, before, after, autojunk=False)
    out = []
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == 'equal':
            out += L[a0:a1]
        elif tag == 'delete':
            continue
        else:
            same_len = tag == 'replace' and a1 - a0 == b1 - b0
            for k, text in enumerate(after[b0:b1]):
                meta = None
                if inherit and same_len and text not in WP.TOKENS:
                    meta = dict(L[a0 + k]['meta'])
                if meta is None and (pool is not None or text in WP.TOKENS):
                    meta = pool.take(text) if pool is not None else None
                    if meta is None and text in WP.TOKENS:
                        meta = {'kind': 'gfx', 'gfx': WP.TOKENS[text]}
                if meta is None and same_len and pool is None:
                    meta = dict(L[a0 + k]['meta'])
                out.append({'src': src, 'meta': meta or {'kind': 'p'},
                            'was': before[a0 + k] if same_len else None})
    assert len(out) == len(after), (len(out), len(after))
    return out


TOC = re.compile(r'(\.{4,}|…|[^\d\s.]\d{1,3}$)')


class SDoc(AO.Doc):
    """Doc для листов замены: строки оглавления (страницы содержания в листах) не считаются заголовками."""
    def __init__(self, paras, sheet=False):
        super().__init__(paras, sheet)
        self.heads = [(i, t) for i, t in self.heads if not TOC.search(self.p[i].strip())]

    def appendix_area(self, name):
        m = AO.APX.match(name)
        kind, n = m.group(1).lower(), int(m.group(2))

        def is_h(j):
            mm = AO.APX.match(self.p[j].strip())
            return mm if mm and len(self.p[j].split()) < 25 and not TOC.search(self.p[j].strip()) else None
        best = None
        for i in range(self.ax, len(self.p)):
            mm = is_h(i)
            if mm and mm.group(1).lower() == kind and int(mm.group(2)) == n and not (best and i < best[1]):
                hi = next((j for j in range(i + 1, len(self.p)) if is_h(j) and int(is_h(j).group(2)) != n), len(self.p))
                if best is None or hi - i > best[1] - best[0]:
                    best = (i, hi)
        return best


# ---------- (а)+(б)+(в): область пункта из листа замены, RU и EN вместе ----------
def lang(t):
    """ru, если кириллических букв не меньше латинских (латиница в русском тексте: ЦОПИ/ФАП/SAP — не в счёт)."""
    t = re.sub(r'^(\d+(?:\.\d+)*[.)]?|[а-яa-z]\))\s+', '', t.strip())
    head = t.split('/')[0]
    t = head if re.search(r'[A-Za-zА-Яа-я]{3}', head) else t     # «Цель/ Purpose»: язык — по первой части
    cyr = len(re.findall(r'[А-Яа-яЁё]', t))
    lat = len(re.findall(r'[A-Za-z]', t))
    return 'ru' if cyr >= lat else 'en'


def sheets_bi(S, op, sheet):
    loc = op['locator']
    if not sheet:
        return AO.Res('NOT_IN_SHEETS', 'листов замены изменения нет')
    sd = SDoc(sheet, sheet=True)
    rs = AO.resolve(sd, loc)
    if rs[0] != 'area':
        return AO.Res('NOT_IN_SHEETS', 'адрес не найден в листах замены' + (f' ({rs[1]})' if rs[0] == 'missing' else ''))
    kind, ident = rs[3], rs[4]
    sareas = rs[5] if len(rs) > 5 else [(rs[1], rs[2])]
    sareas = sorted(set(sareas))
    if not any(hi > lo for lo, hi in sareas):
        return AO.Res('NOT_IN_SHEETS', 'область в листах пуста')
    doc = AO.Doc(S)
    r = AO.area_or_all(doc, loc)
    if r[0] == 'area' and r[3] != 'whole':
        careas = sorted(set(r[5] if len(r) > 5 else [(r[1], r[2])]))
        edits, used = [], set()
        for lg in ('ru', 'en'):
            cs = [a for a in careas if lang(S[a[0]]) == lg]
            ss = [a for a in sareas if lang(sheet[a[0]]) == lg]
            if len(sareas) == 1 and len(careas) == 1:     # без двуязычности: как в apply_ops
                cs, ss = careas, sareas
                lg = None
            for i in range(min(len(cs), len(ss))):
                edits.append((cs[i][0], cs[i][1], sheet[ss[i][0]:ss[i][1]]))
                used.add(ss[i])
            if lg is None:
                break
        if not edits:
            return AO.Res('NOT_IN_SHEETS', 'нет пары по языку в листах замены')
        for lo, hi, chunk in sorted(edits, key=lambda e: -e[0]):
            S[lo:hi] = chunk
        return AO.Res('APPLIED', f'область(и) пункта {ident} из листа замены: {len(edits)} блок(ов)')
    if kind in ('num', 'range'):
        pos = AO.insert_pos(doc, ident)
    elif kind == 'appx':
        pos = AO.appendix_insert_pos(doc, ident)
    else:
        return AO.Res('NOT_FOUND', 'области нет в состоянии, место вставки неизвестно')
    chunk = [t for lo, hi in sareas for t in sheet[lo:hi]]
    S[pos:pos] = chunk
    return AO.Res('APPLIED', f'область листа ({len(chunk)} абз.) вставлена перед абз. {pos}')


def clean(S):
    return [t for t in (x.strip() for x in S) if t]


def apply_tracked(ddir, base_items, sheets_by_izm, checker=None, pdf_count=None):
    ddir = ddir.rstrip('/')
    S = [it['text'] for it in base_items]
    L = [{'src': 'word_base', 'meta': meta_of(it), 'was': None} for it in base_items]
    results, pairs = [], []
    files = sorted(glob.glob(os.path.join(HERE, 'ops', os.path.basename(ddir), 'izm*.json')),
                   key=lambda p: int(re.search(r'izm(\d+)', p).group(1)))
    for jf in files:
        j = json.load(open(jf, encoding='utf-8'))
        izm = j['izm']
        sitems = sheets_by_izm.get(izm, [])
        sheet = [it['text'] for it in sitems]
        touched = set()
        for op in sorted(j['ops'], key=lambda o: o['n']):
            before = list(S)
            via = 'protocol'
            try:
                if op.get('new_in_sheets') and op['action'] != 'other':
                    res = sheets_bi(S, op, sheet)
                    via = 'sheet'
                else:
                    res = AO.run_op(S, ddir, izm, op, sheet)
                    if res.status == 'NOT_FOUND' and sheet and op['action'] in ('replace', 'restate', 'delete') \
                            and 'нет old/new' not in res.why:
                        r2 = sheets_bi(S, op, sheet)
                        if r2.status == 'APPLIED':
                            r2.why = 'old не найден -> ' + r2.why
                            res, via = r2, 'sheet'
            except Exception as ex:   # не прятать: статус + тип ошибки
                res = AO.Res('NOT_FOUND', f'ошибка применения {type(ex).__name__}: {ex}')
            if 'new уже присутствует' in res.why and res.status == 'NOT_FOUND':
                res.status = 'ALREADY_PRESENT'
            S = clean(S)
            src = f'{via}:izm{izm}' if via == 'sheet' else f'protocol:izm{izm}'
            if S != before:
                L = track(before, S, L, src, Pool(sitems) if via == 'sheet' else None, inherit=True)
            cb, ca = collections.Counter(before), collections.Counter(S)
            touched |= {t for t, c in ca.items() if c > cb[t]}
            res.via = via
            results.append((izm, op, res))
        if sheet:
            before = list(S)
            a, r = AO.pair_en(S, touched, sheet)
            if a or r:
                S = clean(S)
                L = track(before, S, L, f'sheet:izm{izm}', Pool(sitems), inherit=True)
                pairs.append((izm, a, r))
    passes = []
    if checker is not None:
        S, L, passes = sheet_pass(S, L, sheets_by_izm, checker, pdf_count)
    return S, L, results, pairs, passes


# ---------- (г) предложение coder'а: листы замены без адреса в протоколе; эталон — арбитр ----------
def leaf_areas(doc_heads, end):
    """[(idx, tuple, lo, hi)] — области пунктов до ближайшего заголовка любого уровня."""
    res = []
    for k, (i, t) in enumerate(doc_heads):
        hi = doc_heads[k + 1][0] if k + 1 < len(doc_heads) else end
        res.append((i, t, i, hi))
    return res


def vshare(texts, checker):
    """Доля подтверждённых эталоном абзацев среди тех, что можно проверить; None — проверить нечего."""
    vs = [checker(t) for t in texts if t not in WP.TOKENS and len(re.sub(r'\W+', '', t)) >= 20]   # короткое — не свидетельство
    vs = [v for v in vs if v is not None]
    return (sum(1 for v in vs if v) / len(vs)) if vs else None


def sheet_pass(S, L, sheets_by_izm, checker, pdf_count=None, thr=0.9):
    """Для пунктов листов замены (новые — от последнего изменения к первому): абзацы состояния, которые эталон не
    подтверждает, заменяются подтверждённым текстом листа; подтверждённые листом абзацы, которых в состоянии нет,
    вставляются; пункт, которого нет в состоянии, вставляется целиком. Подтверждённое эталоном не трогается.
    Пункт «закрыт», когда состояние совпало с листом или правка применена; до 3 кругов (вставки зависят от замен)."""
    log = []
    done = set()
    for _round in range(3):
        n0 = len(log)
        for izm in sorted(sheets_by_izm, reverse=True):
            sitems = sheets_by_izm[izm]
            sheet = [it['text'] for it in sitems]
            if not sheet:
                continue
            sd = SDoc(sheet, sheet=True)
            aps = [j for j in range(len(sheet)) if AO.APX.match(sheet[j].strip()) and len(sheet[j].split()) < 25
                   and not TOC.search(sheet[j].strip())]
            sareas = [(t, slo, min([shi] + [j for j in aps if j > slo]))          # область листа не переходит границу приложения
                      for _i, t, slo, shi in leaf_areas(sd.heads, len(sheet))]
            before = list(S)
            doc = AO.Doc(S)
            by = collections.defaultdict(list)
            for _i, t, lo, hi in leaf_areas(doc.heads, doc.e):
                by[(t, lang(S[lo]))].append((lo, hi))
            scount = collections.Counter(AO.key(x) for x in S)

            def stale(items):
                """В состоянии текст встречается чаще, чем в эталоне: лишний (устаревший) дубль."""
                return pdf_count is not None and any(
                    len(AO.key(x)) >= 40 and 1 <= pdf_count(x) < scount[AO.key(x)] for x in items)
            seen, edits = collections.Counter(), []      # edits: (lo, hi, chunk); вставка: lo == hi
            for t, slo, shi in sareas:
                key = (t, lang(sheet[slo]))
                occ = seen[key]; seen[key] += 1
                if (key, occ) in done:
                    continue
                chunk, pid = sheet[slo:shi], '.'.join(map(str, t))
                cands = by.get(key, [])
                if occ >= len(cands):                     # пункта нет в состоянии
                    sc = vshare(chunk, checker)
                    new_ = [x for x in chunk if x in WP.TOKENS or AO.key(x) not in scount]
                    if sc is not None and sc >= thr and 1 <= len(chunk) <= 60 and len(new_) >= 0.5 * len(chunk):
                        pos = AO.insert_pos(doc, pid)
                        edits.append((pos, pos, chunk))
                        log.append((izm, pid, 'вставлен пункт из листа', len(chunk)))
                        done.add((key, occ))
                    continue
                lo, hi = cands[occ]
                cur = S[lo:hi]
                ops = difflib.SequenceMatcher(None, [AO.key(x) for x in cur], [AO.key(x) for x in chunk],
                                              autojunk=False).get_opcodes()
                closed = True
                for tag, a0, a1, b0, b1 in ops:
                    if tag not in ('replace', 'insert'):
                        continue
                    cb, ca = chunk[b0:b1], cur[a0:a1]
                    sc = vshare(cb, checker)
                    if sc is None or sc < thr:
                        closed = False if tag == 'replace' and not ca else closed
                        continue
                    if tag == 'insert':
                        cb = [x for x in cb if x in WP.TOKENS or AO.key(x) not in scount]
                    if not cb or len(cb) > 40:
                        closed = False
                        continue
                    if tag == 'replace':
                        sa_ = vshare(ca, checker)
                        if sa_ is not None and sa_ >= 0.5 and not stale(ca):
                            continue                       # состояние подтверждено эталоном — не трогаем
                    edits.append((lo + a0, lo + a1, cb))
                    log.append((izm, pid, tag, len(cb)))
                if closed:
                    done.add((key, occ))
            if edits:
                for _k, (lo, hi, chunk) in sorted(enumerate(edits), key=lambda e: (-e[1][0], -e[1][1], -e[0])):
                    S[lo:hi] = chunk
                S = clean(S)
                L = track(before, S, L, f'sheet:izm{izm}', Pool(sitems), inherit=True)
        if len(log) == n0:
            break
    return S, L, log
