"""Детерминированная сводка различий: PDF-эталон ↔ Word (база + листы замены по страницам).

Сопоставление страниц — по номеру «Стр. P» и штампу «Изменение № K» в эталоне и по номеру
в колонтитуле каждого раздела листа замены. Сравнение текста — точное вхождение строки
эталона в текст источника после удаления пробелов и знаков (разрывы слов в PDF не мешают).

python3 pagediff.py <папка документа> [--json out.json]
"""
import sys, re, glob, os, json, zipfile, unicodedata
import fitz
from lxml import etree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
BASE_OVERRIDE = None  # reeng: путь к docx базы (для .doc — конвертированная копия)
MINLEN = 12  # короче — строка не несёт текста (номера, «1», «Да»)


REF_RE = re.compile(r'[Ээ]т[а-я]{0,2}(?:ал|ла)он', re.I)   # «Эталон», «Этлаон» (опечатка в корпусе), «Эталонт»


PART_RE = re.compile(r'(?:[Чч]асти|[Чч]асть|[Чч]\.)\s*\d')
EDITION_RE = re.compile(r'([Ээ]т[а-я]{0,2}(?:ал|ла)он[а-я]*)(?:\s*(?:№\s*)?(\d+))?', re.I)   # «Эталон», «Эталон 1», «Эталон №7»


def edition_of(path):
    m = EDITION_RE.search(os.path.basename(path))
    return int(m.group(2)) if m and m.group(2) else 0


def latest_edition(refs):
    """Несколько действующих эталонов — версии одного документа (решение human 03.10.2026: канон — последняя утверждённая редакция),
    если в именах нет номера части («Часть N») и имена различаются только номером эталона. Берётся эталон с наибольшим номером
    (без номера = 0); при равенстве — новее по времени файла (в манифесте дат загрузки нет), затем по имени. Иначе — список без изменений."""
    if len(refs) < 2 or any(PART_RE.search(os.path.basename(f)) for f in refs): return refs
    norm = lambda f: re.sub(r'_[0-9A-F]{8}', '', EDITION_RE.sub(lambda m: m.group(1), os.path.basename(f))).lower()   # суффикс _XXXXXXXX — приписка корпуса при совпадении имён
    if len({norm(f) for f in refs}) != 1: return refs
    return [max(refs, key=lambda f: (edition_of(f), os.path.getmtime(f), f))]


def ref_pdfs(ddir):
    """Эталоны документа: действующие PDF в files/ (манифест: scope=current, kind=pdf). По маске «эталон»; если маске не отвечает
    ни один, а PDF в files/ ровно один — он и есть эталон. Остальные файлы files/ (docx-шаблоны) не учитываются.
    Версии одного документа («Эталон», «Эталон 1») сводятся к последней (latest_edition); части («Часть N») — все."""
    fs = sorted(f for f in glob.glob(ddir + '/files/*') if f.lower().endswith('.pdf'))
    m = [f for f in fs if REF_RE.search(os.path.basename(f))]
    return latest_edition(m) if m else (fs if len(fs) == 1 else [])


RECURSE_AMD = False   # документы из файлов-глав: главы замены лежат в подпапках папки изменения


def adocx(adir):
    """docx-файлы папки изменения (с подпапками, если RECURSE_AMD)."""
    return sorted(glob.glob(adir + ('/**/*.docx' if RECURSE_AMD else '/*.docx'), recursive=RECURSE_AMD))


_KEY_VAR = str.maketrans({'ё': 'е', 'ѐ': 'е', 'ѝ': 'и'})


def key(s):
    """Ключ сравнения: нижний регистр, только буквы и цифры. NFC: Word хранит «й» как «и»+U+0306, PDF — одним знаком (A2, 05.10);
    ё/ѐ -> е, ѝ -> и (варианты написания, не различие текста)."""
    s = unicodedata.normalize('NFC', s).lower().translate(_KEY_VAR)
    return re.sub(r'[^0-9a-zа-яй]', '', s)


LIST_MARK = re.compile(r'^\s*([-–•·▪]|[а-яa-z]\)|\d{1,2}\)|\d{1,2}\.(?=\s))\s*', re.I)


def hf_key(docx_paths):
    """key текста колонтитулов (header*/footer*.xml) Word-источников: строка эталона, найденная только там, — колонтитул, не контент (05.10)."""
    out = []
    for f in docx_paths:
        if not str(f).lower().endswith('.docx'): continue
        try: z = zipfile.ZipFile(f)
        except Exception: continue
        for n in z.namelist():
            if re.match(r'word/(header|footer)\d*\.xml$', n): out.append(' '.join(re.findall(r'<w:t[^>]*>([^<]*)', z.read(n).decode('utf-8', 'ignore'))))
    return key(' '.join(out))


def garbage_ocr(l):
    """Строка скана с битым распознаванием (латиница вместо кириллицы с «шумом»: II/Jr/crpa) — A2 pdf_lines, 05.10."""
    lat = len(re.findall(r'[A-Za-z]', l)); cyr = len(re.findall(r'[А-Яа-яЁё]', l))
    return lat >= 8 and cyr == 0 and bool(re.search(r'[^\w\s.,()\-«»:;/]|II|Jr|\b[a-z]{1,2}\b.*\b[a-z]{1,2}\b', l))


def garbage(line):
    """Текстовый слой с битой кодировкой шрифта: латиница вместо кириллицы в русском документе."""
    if re.search(r'\w@\w[\w.-]*\.\w+', line): return False   # адрес электронной почты — не мусор
    lat = len(re.findall(r'[A-Za-z]', line)); cyr = len(re.findall(r'[А-Яа-яЁё]', line))
    return (lat > 8 and cyr == 0 and re.search(r'[@{}_]|[a-z][A-Z][a-z]', line) is not None) or garbage_ocr(line)


def classify(fn):
    n = os.path.basename(fn).lower()
    if re.search(r'замен|зам\s+лист', n): return 'sheets'   # reeng: «Замена листов изм №1», «Зам лист изм №5»
    if re.search(r'лист\w*\s+изм', n): return 'changelog'
    n = re.sub(r'\bк\s+приказ\w*', '', n)   # «пр к приказу», «приложение к приказу» — не сам приказ
    if re.search(r'приказ|о внесении|об изменении|служебн|пояснит', n): return 'order'
    return 'sheets'


def label_key(p):
    m = re.match(r'(\d+)(\D*)', p)
    return (int(m.group(1)), m.group(2)) if m else (10**6, p)


# ---------- эталон ----------
PAGES_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../../data/canon_reeng/_cache/pdfpages')
_pages_mem = {}


def canon_pages(pdf):
    """Страницы эталона (номер, метка «Стр. N», номер изменения, строки). Разбор PDF — один раз на содержимое файла:
    кэш в памяти процесса и на диске (_cache/pdfpages/<sha1>.json); раньше каждый шаг (сборка, проверка, классификация,
    сверка по пунктам, статусы) заново разбирал тот же PDF (05.10.2026)."""
    import hashlib, json
    h = hashlib.sha1(open(pdf, 'rb').read()).hexdigest()
    if h in _pages_mem: return [dict(p, lines=list(p['lines'])) for p in _pages_mem[h]]   # копия: вызывающие могут менять строки
    cp = os.path.join(PAGES_CACHE, h + '.json')
    try:
        pages = json.load(open(cp, encoding='utf-8'))
    except Exception:
        pages = _canon_pages(pdf)
        try:
            os.makedirs(PAGES_CACHE, exist_ok=True)
            tmp = cp + f'.{os.getpid()}.tmp'
            json.dump(pages, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False); os.replace(tmp, cp)
        except OSError: pass
    if len(_pages_mem) > 8: _pages_mem.clear()
    _pages_mem[h] = pages
    return [dict(p, lines=list(p['lines'])) for p in pages]


def _canon_pages(pdf):
    d = fitz.open(pdf)
    pages = []
    for i in range(d.page_count):
        pg = d[i]
        raw = pg.get_text()
        lab = re.search(r'Стр\.?\s*/?\s*(?:page)?\s*(\d+\s*[а-яa-z]?)\s*из', raw, re.I)
        izm = re.search(r'Изменение\s*(?:/\s*Revision)?\s*№\s*(\d+)', raw)
        lines = []
        for b in pg.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                t = ''.join(s['text'] for s in l['spans']).strip()
                if t: lines.append(t)
        pages.append({'n': i + 1, 'label': lab.group(1).replace(' ', '') if lab else None,
                      'izm': int(izm.group(1)) if izm else 0, 'lines': lines})
    return pages


# ---------- Word ----------
def docx_sections(path):
    """[(метка страницы из колонтитула, текст раздела)] — раздел листа замены = страница."""
    z = zipfile.ZipFile(path)
    rels = etree.fromstring(z.read('word/_rels/document.xml.rels'))
    rid = {r.get('Id'): r.get('Target') for r in rels}
    body = etree.fromstring(z.read('word/document.xml')).find(W + 'body')
    out, buf = [], []
    def header_label(sp):
        for h in sp.findall(W + 'headerReference'):
            if h.get(W + 'type') != 'default': continue
            hx = etree.fromstring(z.read('word/' + rid[h.get(R + 'id')]))
            txt = ''.join(t.text or '' for t in hx.iter(W + 't'))
            field = any('PAGE' in (x.text or '') for x in hx.iter(W + 'instrText')) or \
                any('PAGE' in (x.get(W + 'instr') or '') for x in hx.iter(W + 'fldSimple'))
            m = re.search(r'Стр\.?\s*/?\s*(?:page)?\s*(\d+\s*[а-яa-z]?)\s*из', txt, re.I)
            if m: return m.group(1).replace(' ', ''), field
        return None, False
    breaks = 0
    for el in body:
        buf.append(''.join(t.text or '' for t in el.iter(W + 't')))
        breaks += sum(1 for b in el.iter(W + 'br') if b.get(W + 'type') == 'page')
        sp = el.find('.//' + W + 'sectPr') if el.tag != W + 'sectPr' else el
        if sp is not None:
            pn = sp.find(W + 'pgNumType')
            start = pn.get(W + 'start') if pn is not None else None
            lab, field = header_label(sp)
            # поле PAGE хранит последнее отображённое значение — при заданном start верна настройка раздела
            out.append([start if (field and start) else lab, ' '.join(buf), breaks, start if not field else None]); buf = []; breaks = 0
    if buf and out: out[-1][1] += ' ' + ' '.join(buf)
    for i in range(1, len(out)):
        if out[i][0] is None: out[i][0] = out[i - 1][0]
    # диапазон страниц из имени файла: «Страницы 16-17», «Страницы 24-24а»
    fr = re.search(r'Страниц\w*\s+(\d+\s*[а-я]?)\s*[-–]\s*(\d+\s*[а-я]?)', os.path.basename(path))
    res = []
    for lab, txt, br, start in out:
        first = lab or start
        labs = [first] if first else [None]
        if fr and len(out) == 1:
            a, b = fr.group(1).replace(' ', ''), fr.group(2).replace(' ', '')
            labs = [str(x) for x in range(int(a), int(b) + 1)] if a.isdigit() and b.isdigit() else [a, b]
        elif br and first and first.isdigit():
            labs = [str(int(first) + j) for j in range(br + 1)]
        res.append((labs, txt))
    return res


def docx_text(path):
    z = zipfile.ZipFile(path)
    body = etree.fromstring(z.read('word/document.xml')).find(W + 'body')
    return ' '.join(''.join(t.text or '' for t in el.iter(W + 't')) for el in body)


def protocol_pages(changelog):
    txt = docx_text(changelog)
    m = re.search(r'(внести|внесены)\s+заменой\s+(лист|страниц)\w*.*', txt, re.I)
    if not m: return None, None, txt
    s = m.group(0)
    labels = set()
    for a, b in re.findall(r'(\d+\s*[а-я]?)\s*[-–]\s*(\d+\s*[а-я]?)(?=[,)\s.])', s):
        a, b = a.replace(' ', ''), b.replace(' ', '')
        if a.isdigit() and b.isdigit():
            labels |= {str(x) for x in range(int(a), int(b) + 1)}
        else:
            labels |= {a, b}
    s2 = re.sub(r'(\d+\s*[а-я]?)\s*[-–]\s*(\d+\s*[а-я]?)', ' ', s)
    labels |= {x.replace(' ', '') for x in re.findall(r'\b(\d+\s?[а-я]?)\b', s2) if not re.match(r'^0', x)}
    return labels, s.strip()[:200], txt


# ---------- сравнение ----------
def main(ddir, out_json=None):
    canon = ref_pdfs(ddir)[0]
    pages = canon_pages(canon)
    words = [f for f in glob.glob(ddir + '/word/*.docx') if classify(f) == 'sheets']
    base = BASE_OVERRIDE or max(words, key=os.path.getsize)
    base_key = key(docx_text(base))
    izms = {}
    for adir in glob.glob(ddir + '/amendments/*'):
        k = int(float(re.search(r'изм([\d.]+)', adir).group(1)))
        sh = sorted([f for f in adocx(adir) if classify(f) == 'sheets'])
        cl = [f for f in adocx(adir) if classify(f) == 'changelog']
        secs = [(lab, key(t), os.path.basename(f)) for f in sh for labs, t in docx_sections(f) for lab in labs]
        plist, pline, _ = protocol_pages(cl[0]) if cl else (None, None, '')
        # страница из протокола без своего раздела = продолжение предыдущего раздела (перенос текста Word без разрыва)
        have = {lab for lab, _, _ in secs}
        for miss in sorted((plist or set()) - have, key=label_key):
            prev = [x for x in secs if x[0] and label_key(x[0]) < label_key(miss)]
            if prev:
                lab0, t0, fn0 = max(prev, key=lambda x: label_key(x[0]))
                secs.append((miss, t0, fn0 + ' (перенос)'))
        izms[k] = {'dir': adir, 'sections': secs, 'plist': plist, 'pline': pline}
    # последняя версия каждой страницы по листам замены
    latest = {}
    for k in sorted(izms):
        for lab, t, fn in izms[k]['sections']:
            if lab: latest[lab] = (k, t, fn)
    rep = {'doc': os.path.basename(ddir), 'canon': canon, 'base': base, 'pages': [], 'chain': []}
    # цепочка: протокол ↔ листы ↔ штампы эталона
    stamped = {}
    for p in pages:
        if p['label']: stamped[p['label']] = p['izm']
    for k in sorted(izms):
        sec_labels = {lab for lab, _, _ in izms[k]['sections'] if lab}
        pl = izms[k]['plist'] or set()
        still = {l for l in sec_labels if stamped.get(l) == k}
        rep['chain'].append({'izm': k, 'protocol_pages': sorted(pl, key=label_key), 'sheet_pages': sorted(sec_labels, key=label_key),
                             'in_protocol_not_in_sheets': sorted(pl - sec_labels, key=label_key),
                             'in_sheets_not_in_protocol': sorted(sec_labels - pl, key=label_key),
                             'canon_pages_with_this_stamp': sorted([l for l, v in stamped.items() if v == k], key=label_key),
                             'sheet_pages_superseded_later': sorted([l for l in sec_labels if latest.get(l, (0,))[0] > k], key=label_key),
                             'sheet_pages_not_stamped_in_canon': sorted([l for l in sec_labels if latest.get(l, (0,))[0] == k and stamped.get(l) != k], key=label_key)})
    # постранично
    import collections
    cnt = collections.Counter(k2 for p in pages for k2 in {key(l) for l in p['lines']})
    head = {k2 for k2, c in cnt.items() if c > max(3, 0.3 * len(pages))}
    all_src = base_key + ''.join(t for v in izms.values() for _, t, _ in v['sections'])
    for i, p in enumerate(pages):
        lab = p['label']
        exp = latest.get(lab)
        src_name, src = ('база: ' + os.path.basename(base), base_key) if not exp else (f"изм{exp[0]}: {exp[2]} стр.{lab}", exp[1])
        lines = [LIST_MARK.sub('', l) for l in p['lines'] if key(l) not in head]
        bad = sum(1 for l in lines if garbage(l))
        lines = [l for l in lines if len(key(l)) >= MINLEN and not garbage(l) and not re.search(r'Стр\.?\s*/?\s*(page)?\s*\d', l)
                 and not re.match(r'(Дата введения|Основание|Изменение\s*(/\s*Revision)?\s*№)', l.strip(), re.I)]
        miss = [l for l in lines if key(l) not in src]
        where = []
        for l in miss:
            kl = key(l)
            if kl in base_key: where.append((l, 'в базе Word'))
            elif any(kl in t for v in izms.values() for _, t, _ in v['sections']):
                w = [f"изм{kk}/стр.{lb}" for kk, v in izms.items() for lb, t, _ in v['sections'] if kl in t]
                where.append((l, 'в листе ' + ', '.join(w[:3])))
            else: where.append((l, 'нигде в Word'))
        # дубль на стыке: строка страницы есть и на соседней странице эталона
        dup = []
        if i + 1 < len(pages):
            nxt = {key(LIST_MARK.sub('', x)) for x in pages[i + 1]['lines'] if len(key(x)) >= MINLEN and key(x) not in head}
            dup = [l for l in lines if key(l) in nxt]
        rep['pages'].append({'pdf_page': p['n'], 'label': lab, 'stamp_izm': p['izm'],
                             'expected_izm': exp[0] if exp else 0, 'source': src_name,
                             'lines': len(lines), 'garbage_lines': bad, 'missing': where, 'dup_with_next': dup})
    if out_json:
        json.dump(rep, open(out_json, 'w'), ensure_ascii=False, indent=1)
    # печать
    print(f"# {rep['doc']}\nэталон: {canon}\nбаза: {base}\n")
    print('## Цепочка: протокол ↔ листы замены ↔ штампы эталона')
    for c in rep['chain']:
        flags = []
        for k2, name in (('in_protocol_not_in_sheets', 'в протоколе, нет листа'), ('in_sheets_not_in_protocol', 'лист есть, в протоколе нет'),
                         ('sheet_pages_not_stamped_in_canon', 'лист последний, но в эталоне стоит другая страница')):
            if c[k2]: flags.append(f"{name}: {', '.join(c[k2])}")
        print(f"изм{c['izm']}: листов {len(c['sheet_pages'])}, по протоколу {len(c['protocol_pages'])}, в эталоне со штампом {len(c['canon_pages_with_this_stamp'])}"
              + (' | ' + ' | '.join(flags) if flags else ' | OK'))
    print('\n## Страницы с расхождениями')
    tot_l = tot_m = 0
    for r in rep['pages']:
        tot_l += r['lines']; tot_m += len(r['missing'])
        stamp_bad = r['stamp_izm'] != r['expected_izm']
        if r['garbage_lines'] and not r['lines']:
            print(f"стр.PDF {r['pdf_page']}: текстовый слой нечитаем (битая кодировка шрифта), строк {r['garbage_lines']} — вне сравнения"); continue
        if r['missing'] or stamp_bad or r['dup_with_next']:
            print(f"стр.PDF {r['pdf_page']} (метка {r['label']}), штамп изм{r['stamp_izm']}, ожидалось изм{r['expected_izm']}{'  ⚠ ШТАМП' if stamp_bad else ''} | источник: {r['source']} | строк {r['lines']}, нет в источнике {len(r['missing'])}")
            for l, w in r['missing'][:4]:
                print(f"    − «{l[:90]}» → {w}")
            for l in r['dup_with_next'][:2]:
                print(f"    ⧉ дубль со следующей страницей: «{l[:90]}»")
    print(f"\nИТОГО строк эталона {tot_l}, не найдено в своём источнике {tot_m} ({tot_m / max(tot_l,1):.1%})")


if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], a[a.index('--json') + 1] if '--json' in a else None)
