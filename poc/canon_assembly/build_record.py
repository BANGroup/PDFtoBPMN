"""Структурированная запись документа БНД (TASK-021, шаг 5) + карточка приёмки.

venv/bin/python poc/canon_assembly/build_record.py <папка документа> [--no-sheet-pass]
(--no-sheet-pass: без шага (г) «листы замены без адреса в протоколе»; запись пишется в records/<doc>.nopass.json)
-> poc/canon_assembly/records/<doc_num>.json  (+ records/<doc_num>_media/ с исходными файлами рисунков, Visio, Excel)

Корпус только читается. Word — Docling 2.131 + свой разбор (word_parse.py); правки — apply_tracked.py (логика
apply_ops.py + улучшения human 30.09); эталон — текстовый слой PDF (логика body.py).
"""
import os, re, sys, json, glob, shutil, zipfile, collections, difflib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fitz
import assemble as A
import body as B
import apply_ops as AO
import apply_tracked as AT
import word_parse as WP

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
REC = os.path.join(HERE, 'records')
K_CHAR = 12          # длина посимвольной «черепицы» для проверки абзаца
V_THR = 0.85         # доля черепиц абзаца, найденных в эталоне -> verified
PDF_THR = 0.6        # близость фрагмента эталона для подстановки текста из PDF
NUMRE = B.NUM
NO_PASS = '--no-sheet-pass' in sys.argv
FRONT_KEYS = AO.FRONT


# ---------------------------------------------------------------- эталон
def pdf_pages_lines(path):
    """Как body.pdf_lines, но с номером страницы: [(страница, строка)] и число страниц."""
    d = fitz.open(path)
    pages = [d[i].get_text() for i in range(d.page_count)]
    cnt = collections.Counter()
    for pg in pages:
        for l in set(A.norm(x) for x in pg.splitlines()):
            if l: cnt[l] += 1
    rep = {l for l, c in cnt.items() if c > max(3, 0.3 * len(pages))}
    out = []
    for pn, pg in enumerate(pages, 1):
        raw = pg.splitlines()
        cut = next((i for i, l in enumerate(raw[:14]) if re.search(r'Стр\.?.{0,12}\d+\s*\w?\s*из', l, re.I)), -1)
        for l in raw[cut + 1:]:
            n = A.norm(l)
            if not n or n in rep: continue
            if re.fullmatch(r'(изменение|revision|№|\d+|\s)+', n): continue
            out.append((pn, l.strip()))
    return out, d


def despace(s):
    return re.sub(r'\s+', '', A.norm(s))


class Etalon:
    def __init__(self, path):
        self.path = path
        self.pl, self.doc = pdf_pages_lines(path)
        self.n = self.doc.page_count
        self.lines = [l for _, l in self.pl]
        self.line_page = [p for p, _ in self.pl]
        # зоны: служебные/титул (до раздела 1), основной текст, приложения
        body, appx = B.split_body(self.lines)
        self.s = len(self.lines) - len(body) - len(appx)
        self.e = self.s + len(body)
        self.pstr = collections.defaultdict(str)
        for p, l in self.pl:
            self.pstr[p] += despace(l)
        self.pshingles = {p: {s[i:i + K_CHAR] for i in range(len(s) - K_CHAR + 1)} for p, s in self.pstr.items()}
        self.allsh = set().union(*self.pshingles.values()) if self.pshingles else set()
        self.allstr = ' '.join(self.pstr.values())
        # индекс слов -> строки для поиска фрагмента
        self.widx = collections.defaultdict(set)
        for i, l in enumerate(self.lines):
            for w in set(A.norm(l).split()):
                if len(w) >= 5: self.widx[w].add(i)

    def check(self, text):
        """(verified True/False/None, [страницы], доля)"""
        t = despace(text)
        if len(t) < 6:
            return None, [], 0.0
        if (AO.POINT.match(text.strip()) or AO.SECT.match(text.strip())) and len(t) >= K_CHAR and t[:K_CHAR] not in self.allsh:
            return False, [], 0.0      # номер пункта с началом текста в эталоне не найден: текст на другом месте/другой номер
        if len(t) < K_CHAR:
            pg = [p for p, s in self.pstr.items() if t in s]
            return (True if pg else False), sorted(pg)[:6], 1.0 if pg else 0.0
        sh = {t[i:i + K_CHAR] for i in range(len(t) - K_CHAR + 1)}
        tot = len(sh)
        hit = len(sh & self.allsh)
        pg = sorted(p for p, ps in self.pshingles.items() if len(sh & ps) >= max(3, 0.2 * tot) or (len(sh & ps) >= 1 and tot < 6))
        return hit / tot >= V_THR, pg, hit / tot

    def find_fragment(self, text):
        """Ближайший фрагмент эталона (окно строк) для абзаца: (ratio, i, j)"""
        u = A.norm(B.strip_num(text))
        if len(u) < 15:
            return 0.0, None, None
        words = set(w for w in u.split() if len(w) >= 5)
        starts = collections.Counter()
        for w in words:
            for i in self.widx.get(w, ()):
                starts[i] += 1
        best = (0.0, None, None)
        for i, c in starts.most_common(40):
            acc = ''
            for j in range(i, min(i + 40, len(self.lines))):
                acc = (acc + ' ' + self.lines[j]).strip()
                a = A.norm(B.strip_num(acc))
                if len(a) < 0.6 * len(u):
                    continue
                if len(a) > 1.5 * len(u) + 20:
                    break
                sm = difflib.SequenceMatcher(None, u, a, autojunk=False)
                if sm.quick_ratio() < best[0]:
                    continue
                r = sm.ratio()
                if r > best[0]:
                    best = (r, i, j)
        return best


# ---------------------------------------------------------------- вспомогательное
def title_of(doc_num):
    m = json.load(open(os.path.join(ROOT, 'data/bnd_corpus/manifest.json'), encoding='utf-8'))
    for d in m['documents']:
        if d['doc_num'] == doc_num:
            return d.get('title') or ''
    return ''


def amendment_dirs(ddir):
    out = {}
    for d in glob.glob(ddir + '/amendments/*'):
        m = re.match(r'(\d{4}-\d{2}-\d{2})_изм(\d+)(?:\.\d+)?', os.path.basename(d))
        if m: out[int(m.group(2))] = (m.group(1), d)
    return out


def strip_marker(text):
    """(маркер, текст без него)"""
    m = NUMRE.match(text)
    if m: return m.group(1), text[m.end():].strip()
    m = re.match(r'^[-–•·]\s*', text)
    if m: return '-', text[m.end():].strip()
    return None, text.strip()


def num_of(text):
    t = text.strip()
    m = AO.POINT.match(t) or AO.SECT.match(t)
    return (m.group(1), len(m.group(1).split('.'))) if m else (None, 0)


def fkey(text):
    t = B.strip_num(text)
    return A.norm(t.split('/')[0]) if len(t) < 90 else ''


def layout_tables(entries):
    """Таблицы-вёрстка (двуязычный текст в две колонки и т.п.): в ячейках заголовки/пункты, а не данные."""
    cnt = collections.Counter()
    for text, lab in entries:
        m = lab['meta']
        t = text.strip()
        if m.get('kind') == 'cell' and m.get('tbl') is not None and len(t) >= 25 and \
                (AO.POINT.match(t) or AO.SECT.match(t) or AO.APX.match(t) or fkey(t) in FRONT_KEYS):
            cnt[m['tbl']] += 1
    return {t for t, c in cnt.items() if c >= 2}


def item_kind(text, meta):
    lab = (meta.get('docling') or (None,))[0]
    marker, rest = strip_marker(text)
    if lab == 'list_item' or (marker and not AO.POINT.match(text) and not AO.SECT.match(text)) or \
       (meta.get('num') and not AO.POINT.match(text)):
        return 'list_item'
    return 'paragraph'


# ---------------------------------------------------------------- сборка блоков
class Ctx:
    def __init__(self, ddir, et, parsed):
        self.ddir, self.et, self.parsed = ddir, et, parsed
        self.tables = {}
        for src, ps in parsed.items():
            for tid, t in ps.tables.items(): self.tables[tid] = t
        self.gfx = {}
        for ps in parsed.values():
            self.gfx.update(ps.gfx)
        self.gaps = []
        self.media = {}
        self.stat = collections.Counter()


def media_copy(ctx, g, rel, src, docname):
    """Скопировать исходный файл рисунка/встроенного объекта в records/<doc>_media/<источник>/"""
    if not rel:
        return None
    sub = re.sub(r'[^\w.-]+', '_', src.replace(':', '_'))
    dst = os.path.join(ctx.media_dir, sub)
    os.makedirs(dst, exist_ok=True)
    z = zipfile.ZipFile(g['docx'])
    if rel not in z.namelist():
        ctx.gaps.append({'type': 'media_missing', 'where': src, 'detail': f'{rel} нет в {os.path.basename(g["docx"])}'})
        return None
    data = z.read(rel)
    out = os.path.join(dst, os.path.basename(rel))
    with open(out, 'wb') as f:
        f.write(data)
    return os.path.relpath(out, REC), data


def gfx_block(ctx, gid, src, where):
    g = ctx.gfx[gid]
    b = {'type': 'figure', 'source': src, 'verified': None, 'pdf_pages': [], 'alt': g.get('alt') or None,
         'origin_docx': os.path.basename(g['docx'])}
    if g['type'] == 'figure':
        r = media_copy(ctx, g, g['rel'], src, None)
        if r:
            b['file'] = r[0]
            b.update(WP.image_info(r[1], g['fmt']))
            if g['fmt'] in ('emf', 'wmf'):
                frs = (WP.emf_text if g['fmt'] == 'emf' else WP.wmf_text)(r[1])
                if frs:
                    b['text_fragments'], b['text_source'] = frs, g['fmt'] + '_text'
                    ctx.stat['fig_text_fragments'] += len(frs)
                elif g['fmt'] == 'emf':
                    b['note'] = 'EMF без текстовых записей (растровая вставка): текст только в картинке'
                    ctx.stat['fig_emf_bitmap'] += 1
            ctx.stat['fig_' + ('readable' if b['readable'] else 'unreadable')] += 1
            if not b['readable']:
                ctx.gaps.append({'type': 'figure_unreadable_format', 'where': where,
                                 'detail': f'{g["name"]} ({g["fmt"]}): файл сохранён как есть, Pillow не открывает'})
        else:
            ctx.stat['fig_nofile'] += 1
    elif g['type'] == 'visio':
        b['type'] = 'visio'
        r = media_copy(ctx, g, g['rel'], src, None)
        if g.get('preview'):
            rp = media_copy(ctx, g, g['preview'], src, None)
            if rp:
                b['preview_file'] = rp[0]
                b['preview'] = WP.image_info(rp[1], os.path.splitext(g['preview'])[1].lstrip('.').lower())
        if r and g['rel'].lower().endswith('.vsdx'):
            b['file'] = r[0]
            try:
                v = WP.read_visio(r[1])
                b['pages'] = v['pages']
                b['shapes'] = [s for p in v['pages'] for s in p['shapes']]
                b['links'] = [l for p in v['pages'] for l in p['links']]
                ctx.stat['visio'] += 1
                ctx.stat['visio_shapes'] += len(b['shapes'])
                ctx.stat['visio_links'] += len(b['links'])
            except Exception as ex:
                ctx.gaps.append({'type': 'visio_parse_error', 'where': where, 'detail': f'{type(ex).__name__}: {ex}'})
        else:
            ctx.gaps.append({'type': 'visio_no_vsdx', 'where': where,
                             'detail': f'встроенный Visio без vsdx ({g["rel"]}): фигуры не прочитаны, файл сохранён'})
            if r: b['file'] = r[0]
            ctx.stat['visio_unreadable'] += 1
    elif g['type'] == 'excel':
        b['type'] = 'excel'
        r = media_copy(ctx, g, g['rel'], src, None)
        if g.get('preview'):
            rp = media_copy(ctx, g, g['preview'], src, None)
            if rp: b['preview_file'] = rp[0]
        if r and g['rel'].lower().endswith('.xlsx'):
            b['file'] = r[0]
            try:
                b['sheets'] = WP.read_excel(r[1])
                ctx.stat['excel'] += 1
                ctx.stat['excel_cells'] += sum(len(s['cells']) for s in b['sheets'])
            except Exception as ex:
                ctx.gaps.append({'type': 'excel_parse_error', 'where': where, 'detail': f'{type(ex).__name__}: {ex}'})
        else:
            ctx.gaps.append({'type': 'excel_unreadable', 'where': where, 'detail': f'встроенный Excel не xlsx ({g["rel"]}), файл сохранён'})
            if r: b['file'] = r[0]
            ctx.stat['excel_unreadable'] += 1
    else:   # ole / chart
        b['type'] = 'figure'
        r = media_copy(ctx, g, g['rel'], src, None)
        if r: b['file'] = r[0]
        b['format'] = g['type']
        b['readable'] = False
        ctx.stat['gfx_other'] += 1
        ctx.gaps.append({'type': 'gfx_unparsed', 'where': where, 'detail': f'{g["type"]} {g.get("prog") or g["name"]}: содержимое не разобрано, файл сохранён'})
    return b


def build_blocks(ctx, entries, where):
    """entries: [(text, label{src, meta, was})] -> блоки узла"""
    blocks, i = [], 0
    while i < len(entries):
        text, lab = entries[i]
        meta, src = lab['meta'], lab['src']
        kind = meta.get('kind', 'p')
        if kind == 'gfx' or text in WP.TOKENS:
            blocks.append(gfx_block(ctx, meta.get('gfx') or WP.TOKENS[text], src, where))
            i += 1
        elif kind == 'cell' and meta.get('tbl') in ctx.tables:
            tid = meta['tbl']
            j = i
            while j < len(entries) and entries[j][1]['meta'].get('tbl') == tid and entries[j][1]['meta'].get('kind') == 'cell':
                j += 1
            blocks.append(table_block(ctx, tid, entries[i:j], where))
            i = j
        else:
            marker, rest = strip_marker(text)
            typ = item_kind(text, meta)
            b = {'type': typ, 'text': rest if typ == 'list_item' else text.strip(), 'source': src.split(':')[0] if False else src}
            if typ == 'list_item': b['marker'] = marker
            if kind == 'tb': b['in_textbox'] = True
            if meta.get('docling'): b['docling'] = meta['docling'][0]
            b['_was'] = lab.get('was')
            b['_raw'] = text
            blocks.append(b)
            i += 1
    return blocks


def table_block(ctx, tid, ents, where):
    t = ctx.tables[tid]
    cells = {}
    for text, lab in ents:
        ci = lab['meta']['cell']
        c = cells.setdefault(ci, {'paras': [], 'src': collections.Counter(), 'was': []})
        c['paras'].append(text.strip())
        c['src'][lab['src']] += 1
        if lab.get('was'): c['was'].append(lab['was'])
    out = []
    for ci, c in sorted(cells.items()):
        d = t['cells'][ci]
        out.append({'r': d['r'], 'c': d['c'], 'rowspan': d['rs'], 'colspan': d['cs'], 'text': '\n'.join(c['paras']),
                    'source': c['src'].most_common(1)[0][0], '_paras': c['paras']})
    srcs = collections.Counter(c['source'] for c in out)
    return {'type': 'table', 'rows': t['rows'], 'cols': t['cols'], 'cells': out,
            'source': srcs.most_common(1)[0][0] if srcs else 'word_base', '_table': tid}


# ---------------------------------------------------------------- сверка с эталоном
def verify_blocks(ctx, blocks, where, used_pdf):
    et = ctx.et
    verified_text = ''
    for b in blocks:
        if b['type'] in ('paragraph', 'list_item'):
            v, pg, _ = et.check(b['text'])
            b['verified'], b['pdf_pages'] = v, pg
            verified_text += ' ' + despace(b['text']) if v else ''
        elif b['type'] == 'table':
            allv = True
            for c in b['cells']:
                if not c['text'].strip():
                    c['verified'], c['pdf_pages'] = None, []
                    continue
                vs = [et.check(p) for p in c.pop('_paras', [c['text']])]
                sig = [x for x in vs if x[0] is not None]
                c['verified'] = (all(x[0] for x in sig) if sig else None)
                c['pdf_pages'] = sorted({p for x in vs for p in x[1]})[:6]
                if c['verified'] is False: allv = False
            b['verified'] = allv if any(c['verified'] is not None for c in b['cells']) else None
            b['pdf_pages'] = sorted({p for c in b['cells'] for p in c['pdf_pages']})[:12]
        elif b['type'] == 'figure' and b.get('text_fragments'):
            vs = [et.check(x) for x in b['text_fragments']]
            sig = [x for x in vs if x[0] is not None]
            b['text_verified_share'] = round(sum(1 for x in sig if x[0]) / len(sig), 3) if sig else None
            b['verified'] = None
            b['pdf_pages'] = sorted({p for x in vs for p in x[1]})[:12]
        else:
            b.setdefault('verified', None)


def pdf_substitute(ctx, blocks, where):
    """Не подтверждённый абзац с близким фрагментом эталона (ratio >= 0.6) -> текст из PDF."""
    et = ctx.et
    for b in blocks:
        if b['type'] not in ('paragraph', 'list_item') or b.get('verified') is not False:
            continue
        r, i, j = et.find_fragment(b['text'])
        if i is None or r < PDF_THR:
            ctx.gaps.append({'type': 'unverified_paragraph', 'where': where, 'detail': f'нет близкого фрагмента в эталоне (best {r:.2f}): «{b["text"][:90]}»'})
            ctx.stat['unverified_kept'] += 1
            continue
        frag = ' '.join(et.lines[i:j + 1])
        fd = despace(frag)
        if fd and fd in ctx.verified_concat:   # этот фрагмент уже подтверждён другим абзацем — не подменять
            ctx.gaps.append({'type': 'unverified_paragraph', 'where': where,
                             'detail': f'фрагмент эталона (ratio {r:.2f}) уже занят другим абзацем: «{b["text"][:90]}»'})
            ctx.stat['unverified_kept'] += 1
            continue
        b['replaced_word_text'] = b['text']
        b['replaced_word_source'] = b['source']
        m, rest = strip_marker(frag)
        b['text'] = rest if b['type'] == 'list_item' else frag
        b['source'] = 'pdf'
        b['verified'] = True
        b['pdf_pages'] = sorted(set(et.line_page[i:j + 1]))
        b['pdf_ratio'] = round(r, 3)
        ctx.stat['pdf_substituted'] += 1
        if r < 0.8:
            b['low_confidence'] = True      # близость 0.6–0.8: подстановка ненадёжна, нужна проверка человеком
            ctx.stat['pdf_substituted_low'] += 1


# ---------------------------------------------------------------- структура записи
def split_front(entries):
    """Служебные разделы до раздела 1: title (не входит), meta_sections, registry (не входит)."""
    secs, cur, name = [], [], '__title__'
    for text, lab in entries:
        if lab['meta'].get('kind') in ('p', 'cell') and fkey(text) in FRONT_KEYS and not re.search(r'\d$', text.strip()):
            secs.append((name, cur)); name, cur = FRONT_KEYS[fkey(text)], []
        else:
            cur.append((text, lab))
    secs.append((name, cur))
    return secs


def is_heading(text, meta):
    num, lvl = num_of(text)
    if not num: return None
    lab = (meta.get('docling') or (None,))[0]
    rest = re.sub(r'^\d+(?:\.\d+)*\.?\s+', '', text.strip())
    short = len(text) <= 160
    if lab == 'section_header' and short: return num, lvl, rest
    if lvl == 1 and short and re.match(r'[А-ЯЁA-Z]', rest): return num, lvl, rest
    if lvl >= 2 and len(rest) <= 100 and not re.search(r'[.;:,]$', rest) and short: return num, lvl, rest
    return num, lvl, None       # нумерованный пункт с текстом: узел без заголовка


def build_nodes(ctx, entries):
    nodes, cur = [], None
    pre = []
    for text, lab in entries:
        meta = lab['meta']
        h = is_heading(text, meta) if meta.get('kind') == 'p' else None
        if h:
            num, lvl, head = h
            cur = {'id': num, 'level': lvl, 'heading': head, 'lang': None, '_entries': []}
            if head is None:
                cur['_entries'].append((re.sub(r'^\d+(?:\.\d+)*\.?\s+', '', text.strip()), lab))
            else:
                cur['_head_lab'] = lab
            nodes.append(cur)
        elif cur is None:
            pre.append((text, lab))
        else:
            cur['_entries'].append((text, lab))
    if pre:
        nodes.insert(0, {'id': None, 'level': 0, 'heading': None, 'lang': None, '_entries': pre})
    return nodes


def interleave(nodes):
    """Двуязычные документы: английский узел ставится сразу после русского узла с тем же номером (порядок эталона)."""
    en = collections.defaultdict(list)
    for n in nodes:
        if n['id'] and n['lang'] == 'en':
            en[n['id']].append(n)
    ru_ids = {n['id'] for n in nodes if n['id'] and n['lang'] == 'ru'}
    out, placed = [], set()
    for n in nodes:
        if n['id'] and n['lang'] == 'en' and n['id'] in ru_ids:
            continue
        out.append(n)
        if n['id'] and n['lang'] == 'ru' and n['id'] not in placed:
            placed.add(n['id'])
            out += en.get(n['id'], [])
    return out


APX_H = re.compile(r'^(приложение|annex)\s*(?:№\s*)?(\d+)\s*(?:[.:]|\s+(?![кk]\s+приказу)[А-ЯЁA-Z]|$)', re.I)


def split_appendices(entries):
    apps, cur = [], None
    for text, lab in entries:
        m = APX_H.match(text.strip())
        if lab['meta'].get('kind') == 'p' and m and len(text.split()) < 25 and not re.search(r'\.{4,}|…', text):
            n = int(m.group(2))
            if cur is None or cur['num'] != n:
                cur = {'num': n, 'kind': m.group(1).capitalize(), 'heading': text.strip(), '_entries': []}
                apps.append(cur)
                continue
        if cur is None:
            cur = {'num': None, 'kind': None, 'heading': None, '_entries': []}
            apps.append(cur)
        cur['_entries'].append((text, lab))
    return apps


# ---------------------------------------------------------------- главная
def clean_block(b):
    for k in [k for k in b if k.startswith('_')]:
        del b[k]
    if b['type'] == 'table':
        for c in b['cells']:
            c.pop('_paras', None)
    return b


def main(ddir):
    ddir = ddir.rstrip('/')
    doc_num = os.path.basename(ddir)
    os.makedirs(REC, exist_ok=True)
    media_dir = os.path.join(REC, doc_num + '_media')
    if os.path.isdir(media_dir):
        shutil.rmtree(media_dir)
    canon = [f for f in glob.glob(ddir + '/files/*.pdf') if re.search('[Ээ]талон', f)][0]
    m = re.search(r'Эталон\s*№?\s*(\d+)', os.path.basename(canon))
    etalon_no = int(m.group(1)) if m else None
    et = Etalon(canon)
    amd = amendment_dirs(ddir)
    # --- разбор Word
    base_file = AO.base_file(ddir)
    parsed = {'base': WP.parse_docx(base_file)}
    sheets_by_izm = {}
    for izm in sorted(amd):
        items = []
        for f in sorted([f for f in glob.glob(amd[izm][1] + '/*.docx') if A.classify(f) == 'sheets'], key=A.page_key):
            ps = WP.parse_docx(f)
            parsed[f'izm{izm}:{os.path.basename(f)}'] = ps
            items += ps.items
        sheets_by_izm[izm] = items
    # --- применение изменений
    S, L, results, pairs, passes = AT.apply_tracked(ddir, parsed['base'].items, sheets_by_izm,
                                                    None if NO_PASS else (lambda t: et.check(t)[0]),
                                                    lambda t: et.allstr.count(despace(t)))
    ctx = Ctx(ddir, et, parsed)
    ctx.media_dir = media_dir
    ctx.sheet_words = {izm: [it['text'] for it in its if it['kind'] != 'gfx'] for izm, its in sheets_by_izm.items()}
    entries = list(zip(S, L))
    lay = layout_tables(entries)
    ctx.layout = lay
    entries = [(t, dict(l, meta=dict(l['meta'], kind='p', layout=True)) if l['meta'].get('tbl') in lay and l['meta'].get('kind') == 'cell' else l)
               for t, l in entries]
    body, appx = B.split_body(S)
    s = len(S) - len(body) - len(appx)
    e = s + len(body)
    front, main_e, appx_e = entries[:s], entries[s:e], entries[e:]
    # --- узлы
    nodes = build_nodes(ctx, main_e)
    apps = split_appendices(appx_e)
    meta_secs, dropped = [], collections.Counter()
    for name, ents in split_front(front):
        if name == '__title__':
            dropped['титульный лист (кроме наименования из каталога)'] += len(ents)
        elif name == 'Лист регистрации':
            dropped['лист регистрации изменений'] += len(ents)
        else:
            meta_secs.append({'name': name, '_entries': ents})
    where_of = lambda n: f'узел {n}'
    # блоки
    for n in nodes:
        n['blocks'] = build_blocks(ctx, n.pop('_entries'), where_of(n['id']))
        hl = n.pop('_head_lab', None)
        n['source'] = hl['src'] if hl else (n['blocks'][0]['source'] if n['blocks'] else 'word_base')
        n['_hl'] = hl
    for a in apps:
        a['blocks'] = build_blocks(ctx, a.pop('_entries'), f'Приложение {a["num"]}')
    for ms in meta_secs:
        ms['blocks'] = build_blocks(ctx, ms.pop('_entries'), ms['name'])
    # проверка и подстановка из эталона
    allblocks = [(b, n['id']) for n in nodes for b in n['blocks']] + \
                [(b, f'Приложение {a["num"]}') for a in apps for b in a['blocks']]
    for n in nodes:
        n['verified'], n['pdf_pages'] = (None, [])
        if n['heading']:
            v, pg, _ = et.check(n['heading'])
            n['heading_verified'], n['heading_pdf_pages'] = v, pg
    for grp in (nodes, apps, meta_secs):
        for x in grp:
            verify_blocks(ctx, x['blocks'], x.get('id') or x.get('name') or f'Приложение {x.get("num")}', None)
    ctx.verified_concat = ' '.join(despace(b['text']) for b, _ in allblocks if b['type'] in ('paragraph', 'list_item') and b.get('verified'))
    for grp in (nodes, apps):
        for x in grp:
            pdf_substitute(ctx, x['blocks'], x.get('id') or f'Приложение {x.get("num")}')
    for n in nodes:
        if n['heading']:
            n['lang'] = AT.lang(n['heading'].split('/')[0])
        else:
            n['lang'] = AT.lang(n['blocks'][0]['text']) if n['blocks'] and n['blocks'][0].get('text') else 'ru'
    nodes = interleave(nodes)
    # --- история
    hist = collections.defaultdict(list)
    orphans = []
    for izm, op, res in results:
        loc = op['locator']
        ent = {'izm': izm, 'date': amd.get(izm, ('', ''))[0], 'n': op['n'], 'action': op['action'], 'old': op.get('old'),
               'new': op.get('new'), 'source_line': op['source_line'], 'status': res.status, 'via': getattr(res, 'via', 'protocol'),
               'why': res.why}
        pt, sec = (loc.get('point') or '').strip(), (loc.get('section') or '').strip()
        key = None
        rg = AO.parse_range(pt)
        if rg: pt = rg[0]
        if re.fullmatch(r'\d+(\.\d+)*', pt): key = ('node', pt)
        elif re.fullmatch(r'\d+(\.\d+)*', sec): key = ('node', sec)
        else:
            mm = AO.APX.match(pt or sec)
            if mm: key = ('appx', int(mm.group(2)))
            elif A.norm((pt or sec).split('/')[0]) in FRONT_KEYS: key = ('meta', FRONT_KEYS[A.norm((pt or sec).split('/')[0])])
        placed = False
        if key and key[0] == 'node':
            for n in nodes:
                if n['id'] == key[1]: n.setdefault('history', []).append(ent); placed = True
        elif key and key[0] == 'appx':
            for a in apps:
                if a['num'] == key[1]: a.setdefault('history', []).append(ent); placed = True
        elif key:
            for ms in meta_secs:
                if ms['name'] == key[1]: ms.setdefault('history', []).append(ent); placed = True
        if not placed:
            orphans.append(dict(ent, locator=loc.get('raw')))
    # --- запись
    def fin_blocks(bl): return [clean_block(b) for b in bl]
    rec_nodes = []
    for n in nodes:
        n.pop('_hl', None); n.pop('verified', None); n.pop('pdf_pages', None)
        n['blocks'] = fin_blocks(n['blocks']); n.setdefault('history', [])
        rec_nodes.append(n)
    for a in apps:
        a['id'] = f'{a["kind"]} {a["num"]}' if a['num'] else None
        a['blocks'] = fin_blocks(a['blocks']); a.setdefault('history', [])
    for ms in meta_secs:
        ms['blocks'] = fin_blocks(ms['blocks']); ms.setdefault('history', [])
    ids = sorted(amd)
    rec = {
        'doc_num': doc_num, 'title': title_of(doc_num),
        'canon': {'pdf': os.path.relpath(canon, ROOT), 'etalon_no': etalon_no,
                  'izm_applied': [i for i in ids if any(r[0] == i and r[2].status in ('APPLIED', 'ALREADY_PRESENT') for r in results)]},
        'meta_sections': meta_secs, 'body': rec_nodes, 'appendices': apps,
        'history_unassigned': orphans, 'gaps': ctx.gaps,
    }
    card = acceptance(ctx, rec, et, results, pairs, amd, etalon_no, dropped, parsed, s, e, main_e, appx_e, entries)
    rec['acceptance'] = card
    rec['gaps'] = ctx.gaps
    rec['sheet_pass'] = [{'izm': i, 'point': p, 'op': o, 'items': n} for i, p, o, n in passes]
    out = os.path.join(REC, doc_num + ('.nopass' if NO_PASS else '') + '.json')
    json.dump(rec, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print_card(doc_num, card, out)
    return rec


from acceptance import acceptance, print_card   # noqa: E402  (карточка приёмки — отдельный модуль)

if __name__ == '__main__':
    main(sys.argv[1])
