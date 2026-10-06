"""Сортировка расхождений канона по причинам (TASK-021, шаг 2). Только чтение, без ИИ.

python3 classify_missing.py [--docs A,B] [--run data/canon_reeng/full3] [--out <папка>]   (по умолчанию <run>/classify)

Логика поиска ненайденных строк, неверных номеров и повторов — копия verify_canon.verify (критерии те же),
но с полными списками и привязкой к странице/разделу. Классы строк эталона:
A есть в Word-источнике (база/лист замены), но в каноне не встала -> дефект сборки
B нет ни в одном прочитанном Word -> расхождение Word и PDF
C внутри картинки/объекта (EMF/WMF/OLE) -> не дефект
D битый текстовый слой PDF (латиница вместо кириллицы) -> скан
U источник .doc не прочитан (нет .docx рядом и не сконвертирован в classify/converted, сырой поиск не нашёл) -> A/B не определить
E надпись схемы (не дефект): подпись без кода блока найдена в Word/объектах/каноне, либо строка лежит в области схемы PDF (кандидат)
Объекты (C): EMF/WMF, вложения word/embeddings (zip: vsdx/xlsx/docx рекурсивно, OLE-потоки), word/diagrams|charts|drawings.
Конвертация .doc: --convert (Word, как batch_run) -> <out>/converted/<doc>/<файл>.docx.
"""
import sys, os, re, io, glob, csv, json, zipfile, difflib, collections, argparse, html, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pagediff as P

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
EXCL = ('ИОТ', 'РПП', 'РОТО')


def raw_doc_key(path):
    """Грубый текст .doc: поток WordDocument в UTF-16/cp1251 (как verify для объектов). Только для запасного поиска."""
    try:
        import olefile
        o = olefile.OleFileIO(path)
        b = o.openstream('WordDocument').read()
        try: b += o.openstream('1Table').read() + o.openstream('0Table').read()
        except Exception: pass
    except Exception:
        b = open(path, 'rb').read()
    import blobtext as BT
    return P.key(' '.join(BT.raw_runs(b)))   # участки текста, а не весь поток трижды (память)


def _xml_text(b):
    return html.unescape(re.sub(r'<[^>]+>', ' ', b.decode('utf-8', 'ignore')))


def object_key(docx_paths):
    """Текст встроенных объектов и XML диаграмм/схем — blobtext (без декодирования картинок целиком; было до 16 ГБ, OOM 05.10)."""
    import blobtext as BT
    return P.key(' '.join(r for f in docx_paths for r in BT.docx_object_runs(f, charts=True)))


CODE = re.compile(r'^\s*\(?[A-ZА-ЯЁ]{1,3}\d+(?:\.\d+)*\)?[\s.]+')
CODE_PAR = re.compile(r'\(\s*[A-ZА-ЯЁ]{1,3}\d+(?:\.\d+)*\s*\)')


def caption_of(line):
    """Подпись схемы без кода блока («A2.3.4.1 Рассылка…», «…(М2)») или None."""
    c = CODE.sub('', line, count=1) if CODE.match(line) else line
    c2 = CODE_PAR.sub('', c)
    return c2 if c2 != line else None


_GEOM = {}


def shape_area(pdf_doc, n, text):
    """Строка внутри области рисунка PDF: изображение (не на всю страницу) или фигура (прямоугольник >=20x10) на странице со стрелками/кривыми."""
    import fitz
    if n not in _GEOM:
        pg = pdf_doc[n - 1]; non = 0; rects = []
        for d in pg.get_drawings():
            for it in d['items']:
                if it[0] == 'c': non += 1
                elif it[0] == 'l' and abs(it[1].x - it[2].x) > 1 and abs(it[1].y - it[2].y) > 1: non += 1
            r = d['rect']
            if r.width >= 20 and r.height >= 10: rects.append(r)
        imgs = [fitz.Rect(i['bbox']) for i in pg.get_image_info() if fitz.Rect(i['bbox']).get_area() < 0.6 * pg.rect.get_area()]
        boxes = {}
        for b in pg.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                t = ''.join(sp['text'] for sp in l['spans']).strip()
                boxes.setdefault(t, fitz.Rect(l['bbox']))
        _GEOM[n] = (non >= 4, rects, imgs, boxes)
    arrows, rects, imgs, boxes = _GEOM[n]
    bb = boxes.get(text.strip())
    if bb is None: return None
    c = fitz.Point((bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2)
    if any(r.contains(c) for r in imgs): return 'внутри изображения'
    if arrows and any(r.contains(c) for r in rects): return 'внутри фигуры схемы (страница со стрелками)'
    return None


def conv_path(conv, doc, f): return os.path.join(conv, doc, os.path.basename(f) + 'x')


def load_sources(sd, plan, conv=None):
    """-> [(метка, номер изменения, key-текст, исходный файл, режим)], непрочитанные .doc, docx-пути (для объектов)."""
    out, unread, docx = [], [], []
    def add(path, num, label):
        if path.lower().endswith('.docx'):
            try: out.append((label, num, P.key(P.docx_text(path)), os.path.basename(path), 'docx')); docx.append(path)
            except Exception as e: unread.append(f'{os.path.basename(path)} ({type(e).__name__})')
        elif path.lower().endswith('.doc'):
            if os.path.exists(path + 'x'): add(path + 'x', num, label); return
            cp = conv_path(conv, os.path.basename(sd), path) if conv else None
            if cp and os.path.exists(cp): add(cp, num, label); return
            try: out.append((label, num, raw_doc_key(path), os.path.basename(path), 'raw_doc'))
            except Exception: pass
            unread.append(os.path.basename(path))
    base = plan.get('base_src')
    if base and os.path.exists(base): add(base, 0, 'база')
    for f in sorted(glob.glob(sd + '/word/*')):
        if f != base and f.lower().endswith(('.doc', '.docx')) and P.classify(f) == 'sheets':
            add(f, 0, 'база (другой файл)')
    for adir in sorted(glob.glob(sd + '/amendments/*')):
        m = re.search(r'изм([\d.]+)', adir)
        n = int(float(m.group(1))) if m else 0
        for f in sorted(glob.glob(adir + '/**/*', recursive=True)):
            if f.lower().endswith(('.doc', '.docx')) and P.classify(f) == 'sheets':
                if f.lower().endswith('.doc') and os.path.exists(f + 'x'): continue   # .docx рядом уже учтён
                add(f, n, f'изм{n}')
    return out, unread, docx


def top_section(cur, line):
    """Раздел верхнего уровня по заголовку «N ТЕКСТ» (не оглавление): N от cur до cur+3 (заголовок раздела мог не попасть в текстовый слой); «ПРИЛОЖЕНИЕ» -> 'П'."""
    s = line.strip()
    if '....' in s or re.search(r'\.{3,}\s*\d*\s*$', s): return cur
    if re.match(r'^ПРИЛОЖЕНИЕ\b', s) or (len(s) <= 160 and re.match(r'^Приложение\s+(\d{1,2}|[А-ЯA-Z])\s*[.:\-–—]', s)): return 'П'   # «Приложение 4. Схема …» тоже начало приложений
    m = re.match(r'^(\d{1,2})(?:\.\d+)*\.?\s+(\S.*)$', s)
    if m and not re.search(r'[a-zа-яё]', m.group(2)) and len(re.findall(r'[A-Za-zА-ЯЁ]', m.group(2))) >= 3:
        n = int(m.group(1))
        if cur is None: return n if n == 1 else cur
        if isinstance(cur, int) and cur <= n <= cur + 3: return n   # пропущенный в PDF заголовок раздела не должен останавливать счёт
    return cur


def scope_of(sec):
    if sec is None: return 'не определён'
    return 'суть (>=6)' if sec == 'П' or sec >= 6 else '1-5'


def nearest_index(paras):
    idx = collections.defaultdict(set); keys = []
    for i, (ls, t) in enumerate(paras):
        k = P.key(t); keys.append(k)
        for j in range(0, max(len(k) - 5, 0) + 1, 3): idx[k[j:j + 6]].add(i)
    return idx, keys


def nearest(paras, idx, keys, line):
    k = P.key(P.LIST_MARK.sub('', line))
    if len(k) < 8: return None
    votes = collections.Counter()
    for j in range(0, len(k) - 5):
        s = idx.get(k[j:j + 6])
        if s and len(s) < 40:
            for i in s: votes[i] += 1
    best = (0, None)
    for i, _ in votes.most_common(8):
        kk = keys[i]
        r = difflib.SequenceMatcher(None, k, kk[:len(k) + 40], autojunk=False).ratio() if kk else 0
        if r > best[0]: best = (r, i)
    if best[1] is None or best[0] < 0.5: return None
    ls, t = paras[best[1]]
    return {'num': ls, 'text': t[:100], 'ratio': round(best[0], 2)}


def classify_doc(doc, run, conv=None):
    sd = os.path.join(run, 'src', doc); od = os.path.join(run, 'out', doc)
    if not os.path.exists(od + '/plan.json'):   # документ из частей (out/<doc>/part_N/): общий разбор не определён
        return {'doc': doc, 'multi_part': True}
    plan = json.load(open(od + '/plan.json', encoding='utf-8'))
    rows = [l.split('\t') for l in open(od + '/canon_text.txt', encoding='utf-8', errors='replace').read().split('\n')]
    paras = [(r[2].strip(), r[3]) for r in rows if len(r) >= 4]
    full = P.key(' '.join(n + ' ' + t for n, t in paras)); plain = P.key(' '.join(t for n, t in paras))
    pdf = [x for x in glob.glob(sd + '/files/*.pdf') if re.search('[Ээ]талон', x)][0]
    pages = P.canon_pages(pdf)
    cnt = collections.Counter(k for p in pages for k in {P.key(l) for l in p['lines']})
    head = {k for k, c in cnt.items() if c > 0.3 * len(pages)}
    start = next((i for i, p in enumerate(pages) if any(re.match(r'^\s*1\.?\s+(ЦЕЛЬ|НАЗНАЧЕНИЕ|ОБЩИЕ)', l, re.I)
                  and not re.search(r'\d\s*$', l.strip()) for l in p['lines'])), None)
    if start is None:   # нет «1 Цель/Назначение/Общие»: «1 Область применения», «РАЗДЕЛ/ЧАСТЬ 1», «Общие положения» не из оглавления; иначе без титула
        start = next((i for i, p in enumerate(pages) if any(re.match(r'^\s*(1\.?\s+ОБЛАСТЬ|(РАЗДЕЛ|ЧАСТЬ|ГЛАВА)\s+1\b|ОБЩИЕ ПОЛОЖЕНИЯ\s*$)', l, re.I)
                      and not re.search(r'[.…]{3,}|\d\s*$', l.strip()) for l in p['lines'])), 1 if len(pages) > 1 else 0)
    # строки эталона (как в verify) + раздел; мусорные строки отдельно
    L, garb = [], []
    for p in pages[start:]:
        sec = L[-1][5] if L else (garb[-1][5] if garb else None)
        gl = sum(1 for l in p['lines'] if P.key(l) not in head and P.garbage(l))
        tot = sum(1 for l in p['lines'] if P.key(l) not in head)
        pg_garb = tot > 0 and gl / tot > 0.3
        for l in p['lines']:
            sec = top_section(sec, l)
            if P.key(l) in head: continue
            rec = (p['n'], p['label'], l, P.key(P.LIST_MARK.sub('', l)), pg_garb, sec)
            if P.garbage(l): garb.append(rec); continue
            if len(P.key(l)) >= 12 and not re.search(r'Стр\.?\s*/?\s*(page)?\s*\d', l) and not re.search(r'[.…]{5,}\s*\d{1,3}\s*$', l) \
               and not re.match(r'(Дата введения|Дата замены листа|Основание|Изменение\s*(/\s*Revision)?\s*№)', l.strip(), re.I):
                L.append(rec)
    nodig = re.sub(r'\d', '', plain)
    miss = [r for r in L if r[3] not in full and r[3] not in plain and re.sub(r'\d', '', r[3]) not in nodig]
    srcs, unread, docx = load_sources(sd, plan, conv)
    hf = P.hf_key(docx); miss = [r for r in miss if not (len(r[3]) >= 12 and r[3] in hf)]   # колонтитул источника — не контент (как verify)
    obj_key = object_key(docx)
    def in_blob(line):
        k = P.key(P.LIST_MARK.sub('', line)); kn = P.key(re.sub(r'^\s*\d+(\.\d+)*\.?\s*', '', line))
        return (len(k) >= 12 and k in obj_key) or (len(kn) >= 12 and kn in obj_key)
    all_src = ' '.join(s_[2] for s_ in srcs) + ' ' + plain
    import fitz
    pdf_doc = fitz.open(pdf); _GEOM.clear()
    src_nodig = [re.sub(r'\d', '', s[2]) for s in srcs]
    idx, keys = nearest_index(paras)
    lines = []
    for n, lab, l, k, pg_garb, sec in miss:
        rec = {'page': n, 'label': lab, 'section': sec, 'scope': scope_of(sec), 'text': l}
        hit = [s for s in srcs if k in s[2]]
        hit_nd = [] if hit else [s for s, nd in zip(srcs, src_nodig) if re.sub(r'\d', '', k) in nd and len(re.sub(r'\d', '', k)) >= 12]
        if hit or hit_nd:
            h = sorted(hit or hit_nd, key=lambda s: (s[4] == 'raw_doc', s[1]))
            rec.update(cls='A', source=h[0][3], izm=h[0][1], where=h[0][0], note=('без цифр' if not hit else '') + ('; сырой поиск .doc' if h[0][4] == 'raw_doc' else ''))
        elif in_blob(l): rec['cls'] = 'C'
        elif (cap := caption_of(l)) and len(P.key(cap)) >= 8 and (P.key(cap) in all_src or P.key(cap) in obj_key):
            rec.update(cls='E', note='подпись схемы без кода найдена в Word/объектах: «' + cap.strip()[:60] + '»')
        elif pg_garb: rec['cls'] = 'D'
        elif unread: rec['cls'] = 'U'; rec['note'] = 'источник .doc не прочитан: ' + '; '.join(unread)[:200]
        elif (sa := shape_area(pdf_doc, n, l)):
            rec.update(cls='E', note='кандидат: ' + sa)
        else:
            rec['cls'] = 'B'; rec['nearest'] = nearest(paras, idx, keys, l)
        lines.append(rec)
    # номера
    nums = [r for r in L if re.match(r'^\s*\d+(\.\d+)+\.?\s+\S', r[2])]
    numbers = []
    for n, lab, l, k, _, sec in nums:
        if P.key(l) in full: continue
        m = re.match(r'^\s*(\d+(?:\.\d+)+)\.?\s+(.*)$', l)
        want, tail = m.group(1), P.key(m.group(2))
        found = []
        if len(tail) >= 8:
            for i, kk in enumerate(keys):
                if kk.startswith(tail[:40]) or (len(tail) >= 20 and tail[:40] in kk and len(kk) < len(tail) + 60):
                    found.append(i)
                    if len(found) >= 3: break
        cur = [{'num': paras[i][0], 'text': paras[i][1][:90]} for i in found]
        mc = next((x['cls'] for x in lines if x['text'] == l), None)
        cls = 'номер не тот' if cur else 'текст не найден в каноне' + (f' (строка класса {mc})' if mc else '')
        numbers.append({'page': n, 'label': lab, 'section': sec, 'scope': scope_of(sec), 'ref': l, 'want': want, 'canon': cur, 'cls': cls})
    # повторы
    ck = collections.Counter(P.key(t) for _, t in paras if len(P.key(t)) > 60)
    pdfk = P.key(' '.join(' '.join(p['lines']) for p in pages))
    dups, dups_ok = [], []
    base_k = next((s_[2] for s_ in srcs if s_[0] == 'база' and s_[4] == 'docx'), '')
    for k, c in ck.items():
        if c > 1 and pdfk.count(k) < c:
            ex = next(t for _, t in paras if P.key(t) == k)
            rec = {'text': ex[:120], 'canon_count': c, 'ref_count': pdfk.count(k), 'base_count': base_k.count(k) if base_k else None}
            # разорван колонтитулом/ячейкой эталона: в каноне не больше, чем в базе, начало и конец абзаца в эталоне — не реже (как verify_canon)
            if base_k and c <= rec['base_count'] and pdfk.count(k[:30]) >= c and pdfk.count(k[-30:]) >= c: dups_ok.append(rec)
            else: dups.append(rec)
    c = collections.Counter(r['cls'] for r in lines)
    c6 = collections.Counter(r['cls'] for r in lines if r['scope'] == 'суть (>=6)')
    scan = len(garb) > 0.3 * (len(L) + len(garb))
    return {'doc': doc, 'lines_ref': len(L), 'garbage_lines': len(garb), 'scan': scan, 'counts': dict(c), 'counts_ge6': dict(c6),
            'sources': [f'{s[0]}: {s[3]} [{s[4]}]' for s in srcs], 'unread': unread,
            'missing': lines, 'numbers': numbers, 'duplicates': dups, 'duplicates_explained': dups_ok}


def doc_class(r):
    c, c6 = r['counts'], r['counts_ge6']
    out = []
    if c.get('A') or r['duplicates']: out.append('наша ошибка сборки')
    if c6.get('B'): out.append('расхождение документа')
    elif c.get('B'): out.append('только технические разделы')
    if c.get('U'): out.append('источник .doc не прочитан')
    if r['scan'] or c.get('D'): out.append('скан')
    if r['numbers'] and not out: out.append('номера не те')
    elif r['numbers']: out.append('номера не те')
    if not out: out.append('только объекты и надписи схем (не дефект)' if (c.get('C') or c.get('E')) else 'прочее')
    return '+'.join(out)


def readme(res, rows, out):
    res = [r for r in res if 'error' not in r]
    cl = collections.Counter(); combo = collections.Counter(r['class'] for r in res)
    for r in res:
        for p in r['class'].split('+'): cl[p] += 1
    o = ['# Классификация расхождений канона (not_ready, в объёме)', '',
         f'Документов: {len(res)} (без РПП, РОТО, ИОТ). Разделы 1–5 технические, суть — 6 и далее.', '',
         'Строка эталона (PDF), которой нет в каноне, относится к одному из классов: **A** — есть в Word-источнике, но в канон не встала (наш дефект сборки); '
         '**B** — нет ни в одном Word (Word в Lotus расходится с утверждённым PDF); **C** — внутри картинки/объекта, в т.ч. вложенного Visio/Excel/Word (не дефект); '
         '**D** — битый текстовый слой PDF (скан); **E** — надпись схемы (подпись без кода блока найдена в Word, либо строка лежит в области схемы PDF — помечено «кандидат»); не дефект; **U** — источник .doc не прочитан, A/B не определить.', '',
         '## Сколько документов в каждом классе (документ может быть в нескольких)', '', '| Класс | Документов |', '|---|---|']
    o += [f'| {k} | {v} |' for k, v in cl.most_common()]
    o += ['', '### По точным сочетаниям', '', '| Сочетание | Документов |', '|---|---|'] + [f'| {k} | {v} |' for k, v in combo.most_common()]
    tot = collections.Counter(); tot6 = collections.Counter()
    for r in res: tot.update(r['counts']); tot6.update(r['counts_ge6'])
    o += ['', '## Строк эталона всего (все / в разделах >=6)', '', '| Класс | Всего | В разделах >=6 |', '|---|---|---|']
    o += [f'| {k} | {tot.get(k, 0)} | {tot6.get(k, 0)} |' for k in 'ABCDEU']
    o += [f'| номера не те | {sum(len(r["numbers"]) for r in res)} | |', f'| повторы (абзацев) | {sum(len(r["duplicates"]) for r in res)} | |']
    o += ['', '## Топ-15: «расхождение документа» (строки B в разделах >=6)', '',
          'Цитата — строка утверждённого PDF; «в Word рядом» — ближайший по тексту абзац канона (номер пункта, если есть).', '']
    for r in sorted([r for r in res if r['counts_ge6'].get('B')], key=lambda r: -r['counts_ge6']['B'])[:15]:
        bs = [m for m in r['missing'] if m['cls'] == 'B' and m['scope'] == 'суть (>=6)']
        bs = sorted(bs, key=lambda m: (not m.get('nearest'), -len(m['text'])))[:3]
        o.append(f"### {r['doc']} — {r['title']}: B в разделах >=6 — {r['counts_ge6']['B']} ({r['class']})")
        for m in bs:
            nr = m.get('nearest'); near = f"; в Word рядом: п. {nr['num'] or '(без номера)'} «{nr['text'][:70]}»" if nr else '; ближайшего места в Word нет'
            o.append(f"- стр. {m['label'] or m['page']}, раздел {m['section']}: «{m['text'][:90]}»{near}")
        o.append('')
    o += ['## Топ-10: «наша ошибка сборки» (строки A)', '', '| Документ | Строк A | Повторов | Файл-источник (изм.) | Пример |', '|---|---|---|---|---|']
    for r in sorted([r for r in res if r['counts'].get('A') or r['duplicates']], key=lambda r: -(r['counts'].get('A', 0) + len(r['duplicates'])))[:10]:
        a_ = [m for m in r['missing'] if m['cls'] == 'A']
        sc = collections.Counter((m['source'], m['izm']) for m in a_).most_common(1)
        src = f"{sc[0][0][0]} (изм.{sc[0][0][1]}, строк {sc[0][1]})" if sc else '—'
        ex = a_[0]['text'][:60] if a_ else (r['duplicates'][0]['text'][:60] if r['duplicates'] else '')
        o.append(f"| {r['doc']} | {r['counts'].get('A', 0)} | {len(r['duplicates'])} | {src} | {ex} |")
    o += ['', 'Изм.0 = база. Полные списки — `<doc>.json`, таблица — `summary.csv`. Скрипт: `poc/canon_assembly/reeng/classify_missing.py`.']
    open(os.path.join(out, 'README.md'), 'w', encoding='utf-8').write('\n'.join(o) + '\n')


MEM_CAP_GB = float(os.environ.get('CLASSIFY_MEM_GB', '5'))   # предел памяти процесса на документ: один документ съедал до 16 ГБ и вызывал OOM в WSL (05.10)


def _job(a):
    import resource, time as _t
    resource.setrlimit(resource.RLIMIT_AS, (int(MEM_CAP_GB * 2**30),) * 2)
    t0 = _t.time()
    try: r = classify_doc(*a)
    except MemoryError: r = {'doc': a[0], 'error': f'MemoryError: превышен предел {MEM_CAP_GB} ГБ'}
    except Exception as e: r = {'doc': a[0], 'error': f'{type(e).__name__}: {e}'}
    print(f"doc {a[0]}: {_t.time() - t0:.0f} с, пик {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20:.1f} ГБ", flush=True)
    return r


def convert_docs(sel, run, out):
    """.doc (база/листы замены) без .docx рядом -> Word -> <out>/converted/<doc>/<файл>.docx. Только свой WINWORD (wordrun.run)."""
    import wordrun as W
    for i, r in enumerate(sel):
        doc = r['doc_num']; sd = os.path.join(run, 'src', doc)
        try: plan = json.load(open(os.path.join(run, 'out', doc, 'plan.json'), encoding='utf-8'))
        except Exception: continue
        fs = [f for f in [plan.get('base_src')] + glob.glob(sd + '/word/*') + glob.glob(sd + '/amendments/**/*', recursive=True)
              if f and f.lower().endswith('.doc') and P.classify(f) == 'sheets' and not os.path.exists(f + 'x')]
        fs = [f for f in dict.fromkeys(fs) if not os.path.exists(conv_path(out + '/converted', doc, f))]
        if not fs: continue
        tag = f'clsconv{i}'; wd = W.wsl(tag); os.makedirs(wd, exist_ok=True); steps = []
        for j, f in enumerate(fs):
            shutil.copy(f, os.path.join(wd, f'c{j}.doc'))
            steps.append({'op': 'convert', 'src': W.winpath(f'{tag}/c{j}.doc'), 'dst': W.winpath(f'{tag}/c{j}.docx')})
        res = W.run(steps, tag, 600 + 60 * len(fs))
        ok = 0
        for j, f in enumerate(fs):
            src = os.path.join(wd, f'c{j}.docx')
            if os.path.exists(src):
                dst = conv_path(out + '/converted', doc, f); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy(src, dst); ok += 1
        print(f'convert {doc}: {ok}/{len(fs)} {res["out"][-80:] if "TIMEOUT" in res["out"] else ""}', flush=True)
        shutil.rmtree(wd, ignore_errors=True)
        for ext in ('.log', '.pid', '.plan.json'):
            try: os.remove(W.wsl(tag + ext))
            except OSError: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default=os.path.join(REPO, 'data/canon_reeng/full3'))
    ap.add_argument('--out'); ap.add_argument('--docs'); ap.add_argument('--readme-only', action='store_true'); ap.add_argument('--convert', action='store_true')
    a = ap.parse_args()
    out = a.out or os.path.join(a.run, 'classify'); os.makedirs(out, exist_ok=True)
    if a.readme_only:
        readme([json.load(open(f, encoding='utf-8')) for f in sorted(glob.glob(out + '/*.json'))], None, out); return
    srows = list(csv.DictReader(open(os.path.join(a.run, 'summary.csv'), encoding='utf-8-sig'), delimiter=';'))
    sel = [r for r in srows if r['status'] == 'not_ready' and not r['doc_num'].startswith(EXCL)]
    if a.docs: sel = [r for r in srows if r['doc_num'] in a.docs.split(',')]
    if a.convert: convert_docs(sel, a.run, out)
    import multiprocessing as mp   # spawn: fork после fitz/lxml зависал (процессы-сироты без нагрузки)
    # пул без зависаний: процесс на документ (maxtasksperchild=1), тайм-аут на документ (убитый OOM процесс иначе вешает pool.map навсегда);
    # большие эталоны (>1000 стр., РОНО ~12 ГБ) — последними, по одному
    big = lambda r: int(r.get('ref_pages') or 0) > 1000
    jobs = [(r['doc_num'], a.run, out + '/converted') for r in sel]
    res = [None] * len(sel)
    for grp, n in (([i for i, r in enumerate(sel) if not big(r)], 1), ([i for i, r in enumerate(sel) if big(r)], 1)):
        if not grp: continue
        with mp.get_context('spawn').Pool(n, maxtasksperchild=1) as pool:
            ar = {i: pool.apply_async(_job, (jobs[i],)) for i in grp}
            for i in grp:
                try: res[i] = ar[i].get(timeout=1200)
                except Exception as e: res[i] = {'doc': sel[i]['doc_num'], 'error': f'{type(e).__name__}: {e} (тайм-аут/процесс убит)'}
    rows = []
    for s, r in zip(sel, res):
        if 'error' in r: print('ERR', r); continue
        if r.get('multi_part'): json.dump(r, open(f"{out}/{r['doc']}.json", 'w', encoding='utf-8'), ensure_ascii=False); print('части, пропущен:', r['doc']); continue
        r['title'] = s['title']; r['changes'] = s['changes']; r['class'] = doc_class(r)
        json.dump(r, open(f"{out}/{r['doc']}.json", 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        c, c6 = r['counts'], r['counts_ge6']
        rows.append({'doc': r['doc'], 'title': s['title'], 'изменений': s['changes'],
                     'missing A': c.get('A', 0), 'missing B': c.get('B', 0), 'missing C': c.get('C', 0), 'missing D': c.get('D', 0), 'missing E': c.get('E', 0), 'из них E-кандидаты': sum(1 for m in r['missing'] if m['cls'] == 'E' and m.get('note', '').startswith('кандидат')), 'missing U': c.get('U', 0),
                     'из них в разделах >=6 (A/B/C/D/E/U)': '/'.join(str(c6.get(k, 0)) for k in 'ABCDEU'),
                     'B в разделах >=6': c6.get('B', 0), 'мусорных строк PDF': r['garbage_lines'],
                     'номера': len(r['numbers']), 'повторы': len(r['duplicates']), 'повторы объяснены': len(r['duplicates_explained']), 'итоговый класс': r['class']})
    if not rows: print('нет документов'); return
    with open(f'{out}/summary.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, list(rows[0]), delimiter=';'); w.writeheader(); w.writerows(rows)
    if not a.docs: readme([r for r in res if 'error' not in r and not r.get('multi_part')], rows, out)
    print(len(rows), 'документов ->', out)


if __name__ == '__main__':
    main()
