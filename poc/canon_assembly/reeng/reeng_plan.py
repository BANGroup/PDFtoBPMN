"""Планирование сборки канона: регионы замены, якоря в базе, фрагменты листов замены (XML).

python reeng_plan.py <папка документа> <slug>   -> reeng/<doc>/plan.json (+ Temp Windows: base_marked.docx, frag_*.docx)
"""
import itertools, sys, re, os, glob, json, zipfile, copy, shutil
from lxml import etree
import pagediff as pd
from pagediff import key, W, R, MINLEN, LIST_MARK, garbage, canon_pages, classify, label_key, protocol_pages
import wordrun, wtext, hashlib
import pdf_frag
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

NUM = re.compile(r'^\s*(\d+(\.\d+)*\.?|[а-яa-z]\)|[-–•·▪])\s+', re.I)


def stripnum(s):
    return NUM.sub('', s, count=1)


def txt(el):
    return ''.join(t.text or '' for t in el.iter(W + 't'))


# ---------- листы замены: разделы с индексами элементов ----------
def sections2(path, nums=None):
    z = zipfile.ZipFile(path)
    rels = etree.fromstring(z.read('word/_rels/document.xml.rels'))
    rid = {r.get('Id'): r.get('Target') for r in rels}
    body = etree.fromstring(z.read('word/document.xml')).find(W + 'body')
    kids = list(body)
    def header_label(sp):
        for h in sp.findall(W + 'headerReference'):
            if h.get(W + 'type') != 'default': continue
            try: hx = etree.fromstring(z.read('word/' + rid[h.get(R + 'id')]))
            except KeyError: continue
            t = ''.join(x.text or '' for x in hx.iter(W + 't'))
            field = any('PAGE' in (x.text or '') for x in hx.iter(W + 'instrText')) or \
                any('PAGE' in (x.get(W + 'instr') or '') for x in hx.iter(W + 'fldSimple'))
            m = re.search(r'Стр\.?\s*/?\s*(?:page)?\s*(\d+\s*[а-яa-z]?)\s*из', t, re.I)
            if m: return m.group(1).replace(' ', ''), field
        return None, False
    out, s0, breaks = [], 0, 0
    for i, el in enumerate(kids):
        breaks += sum(1 for b in el.iter(W + 'br') if b.get(W + 'type') == 'page')
        sp = el.find('.//' + W + 'sectPr') if el.tag != W + 'sectPr' else el
        if sp is not None:
            pn = sp.find(W + 'pgNumType')
            start = pn.get(W + 'start') if pn is not None else None
            lab, field = header_label(sp)
            e = i if el.tag != W + 'sectPr' else i - 1
            out.append({'lab': start if (field and start) else lab, 'start': start if not field else None,
                        's': s0, 'e': e, 'breaks': breaks, 'sect_in_p': el.tag != W + 'sectPr'})
            s0 = i + 1; breaks = 0
    if out and out[-1]['e'] < out[-1]['s'] and not out[-1]['sect_in_p']:
        out.pop()  # пустой хвост
    for i in range(1, len(out)):
        if out[i]['lab'] is None: out[i]['lab'] = out[i - 1]['lab']
    fr = re.search(r'Страниц\w*\s+(\d+\s*[а-я]?)\s*[-–]\s*(\d+\s*[а-я]?)', os.path.basename(path))
    res = []
    own = {o['lab'] or o['start'] for o in out}
    for o in out:
        o['empty'] = not any(txt(kids[j]).strip() or kids[j].tag == W + 'tbl' or list(kids[j].iter(W + 'drawing')) or list(kids[j].iter(W + 'pict')) or list(kids[j].iter(W + 'object')) for j in range(o['s'], o['e'] + 1))
    for o in out:
        first = o['lab'] or o['start']
        labs = [first] if first else [None]
        if fr and len(out) == 1:
            a, b = fr.group(1).replace(' ', ''), fr.group(2).replace(' ', '')
            labs = [str(x) for x in range(int(a), int(b) + 1)] if a.isdigit() and b.isdigit() else [a, b]
        elif o['breaks'] and first and first.isdigit():
            labs = [first] + [str(int(first) + j) for j in range(1, o['breaks'] + 1) if str(int(first) + j) not in own]
        o['labs'] = labs
        o['text'] = ' '.join(txt(kids[j]) for j in range(o['s'], o['e'] + 1))
        o['labs_src'] = 'file' if (fr and len(out) == 1) else ('breaks' if (o['breaks'] and first and first.isdigit()) else 'header')
        o['first'] = next((txt(kids[j]).strip() for j in range(o['s'], o['e'] + 1) if txt(kids[j]).strip()), '')
        o['file'] = path
        o['ntext'] = ' '.join(elem_ntext(kids[j], j, nums or {}) for j in range(o['s'], o['e'] + 1))
        o['k'] = key(o['text']); o['kn'] = key(o['ntext'])
        res.append(o)
    nk = [key(elem_ntext(kids[j], j, nums or {})) for j in range(len(kids))]
    for o in res: o['nkeys'] = nk
    return res


_NUMCACHE = {}


def load_rows(path):
    rows = []
    if not os.path.exists(path): return rows
    for ln in open(path, encoding='utf-8'):
        p_ = ln.rstrip('\n').split('\t', 4)
        if len(p_) < 4: continue
        try: st = int(p_[4]) if len(p_) > 4 else -1
        except ValueError: st = -1
        rows.append({'i': int(p_[0]), 't': p_[1], 'ls': p_[2].strip(), 'text': p_[3].strip(), 'start': st})
    return rows


def word_numbers(docx_path, dump_path):
    """Номера абзацев по ListString Word (выгрузка dump), сопоставленные с XML-абзацами по тексту: {(ki,pi): номер|None}."""
    import difflib
    rows_all = load_rows(dump_path)
    if not rows_all: return {}
    rows = [(key(r['text']), r['ls']) for r in rows_all if r['t'] in ('T', '-') and key(r['text'])]
    root = etree.fromstring(zipfile.ZipFile(docx_path).read('word/document.xml')).find(W + 'body')
    xp = []
    for ki, el in enumerate(root):
        paras = [el] if el.tag == W + 'p' else list(el.iter(W + 'p')) if el.tag == W + 'tbl' else []
        for pi, p in enumerate(paras):
            k = key(txt(p))
            if k: xp.append(((ki, pi), k))
    sm = difflib.SequenceMatcher(None, [k for _, k in xp], [k for k, _ in rows], autojunk=False)
    out = {}
    for a, b, n in sm.get_matching_blocks():
        for t in range(n):
            ls = rows[b + t][1]
            out[xp[a + t][0]] = ls if re.search(r'[0-9A-Za-zА-Яа-я]', ls) else None
    out['_match'] = (sum(n for _, _, n in sm.get_matching_blocks()), len(xp), len(rows))
    return out


def elem_ntext(el, ki, nums):
    """Текст элемента тела с номерами автонумерации перед абзацами."""
    if el.tag == W + 'p':
        n = nums.get((ki, 0)); return ((n + ' ') if n else '') + txt(el)
    if el.tag == W + 'tbl':
        out = []
        for pi, p in enumerate(el.iter(W + 'p')):
            n = nums.get((ki, pi)); out.append(((n + ' ') if n else '') + txt(p))
        return ' '.join(out)
    return txt(el)


def dump_path_for(workdir, path):
    return os.path.join(workdir, 'sd', hashlib.md5(path.encode()).hexdigest()[:10] + '.txt')


def ensure_dumps(slug, workdir, files):
    """Выгрузки Word (ListString, фигуры, сноски) для docx-файлов, у которых их ещё нет."""
    os.makedirs(os.path.join(workdir, 'sd'), exist_ok=True); os.makedirs(os.path.join(workdir, 'sh'), exist_ok=True)
    steps = []
    for f in files:
        dp = dump_path_for(workdir, f)
        if os.path.exists(dp): continue
        h = os.path.basename(dp)[:-4]
        shutil.copy(f, os.path.join(workdir, 'sh', h + '.docx'))
        steps.append({'op': 'dump', 'src': wordrun.winpath(f'{slug}/sh/{h}.docx'), 'out': wordrun.winpath(f'{slug}/sd/{h}.txt')})
    if steps:
        r = wordrun.run(steps, slug + '_sd', 3000)
        if 'ERROR' in r['log'] or r['out'].startswith('TIMEOUT'): print('WARN dumps', r['log'][-300:])


def para_numbers(path):
    """{(индекс элемента тела, индекс абзаца внутри): номер автонумерации|None} по docx_numbering (счётчики идут по всему документу)."""
    if path in _NUMCACHE: return _NUMCACHE[path]
    res = {}
    try:
        import docx
        from docx.oxml.ns import qn
        import docx_numbering as dn
        d = docx.Document(path)
        nb = dn.Numbering(d)
        for ki, el in enumerate(d.element.body.iterchildren()):
            paras = [el] if el.tag == qn('w:p') else list(el.iter(qn('w:p'))) if el.tag == qn('w:tbl') else []
            for pi, p in enumerate(paras):
                res[(ki, pi)] = nb.number(p)
    except Exception as e:
        print('WARN numbering', os.path.basename(path), repr(e)[:100])
    _NUMCACHE[path] = res
    return res


PPR_BEFORE_NUMPR = ('pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl')


def freeze_para(p, num):
    """Заменить автонумерацию абзаца напечатанным номером (нумерацию Word после вставок не пересчитывать)."""
    ppr = p.find(W + 'pPr')
    if ppr is None:
        ppr = etree.Element(W + 'pPr'); p.insert(0, ppr)
    npr = ppr.find(W + 'numPr')
    if npr is None:
        npr = etree.Element(W + 'numPr')
        pos = 0
        for i, ch in enumerate(ppr):
            if etree.QName(ch).localname in PPR_BEFORE_NUMPR: pos = i + 1
        ppr.insert(pos, npr)
    for ch in list(npr): npr.remove(ch)
    etree.SubElement(npr, W + 'ilvl').set(W + 'val', '0')
    etree.SubElement(npr, W + 'numId').set(W + 'val', '0')
    r = etree.Element(W + 'r'); t = etree.SubElement(r, W + 't'); t.text = num + ' '
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    p.insert(list(p).index(ppr) + 1, r)


def freeze_kids(kids_idx_pairs, nums):
    n = 0
    for ki, el in kids_idx_pairs:
        paras = [el] if el.tag == W + 'p' else list(el.iter(W + 'p')) if el.tag == W + 'tbl' else []
        for pi, p in enumerate(paras):
            num = nums.get((ki, pi))
            if num:
                freeze_para(p, num); n += 1
    return n


def make_fragment(sec, dst, drop_first=False, drop_last=False):
    """docx-копия листа замены, из тела оставлены только элементы раздела (стили/нумерация/картинки сохраняются)."""
    zin = zipfile.ZipFile(sec['file'])
    root = etree.fromstring(zin.read('word/document.xml'))
    body = root.find(W + 'body')
    kids = list(body)
    final_sect = kids[-1] if kids[-1].tag == W + 'sectPr' else None
    keep = list(range(sec['s'], sec['e'] + 1))
    def nonempty(j): return bool(txt(kids[j]).strip()) or kids[j].tag == W + 'tbl' or bool(list(kids[j].iter(W + 'drawing')))
    if drop_first and keep:
        f_ = next((j for j in keep if nonempty(j)), None)
        if f_ is not None: keep.remove(f_)
    if drop_last and keep:
        l_ = next((j for j in reversed(keep) if nonempty(j)), None)
        if l_ is not None: keep.remove(l_)
    sect = None
    e0 = sec.get('e0', sec['e'])
    if sec['sect_in_p']:
        sp = kids[e0].find('.//' + W + 'sectPr')
        sect = copy.deepcopy(sp)
    elif final_sect is not None:
        sect = copy.deepcopy(final_sect)
    for k in kids: body.remove(k)
    for j in keep:
        el = kids[j]
        for sp in el.findall('.//' + W + 'sectPr'):
            sp.getparent().remove(sp)   # разрыв раздела внутри вставки не нужен
        body.append(el)
    if not len(body):
        body.append(etree.SubElement(body, W + 'p'))
    if sect is not None: body.append(sect)
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename == 'word/document.xml':
                data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            zout.writestr(it, data)


# ---------- эталон: содержательные строки ----------
HDR = re.compile(r'Стр\.?\s*/?\s*(page)?\s*\d|Изменение\s*(/\s*Revision)?\s*№')


def header_keys(pages):
    """Повторяющиеся строки колонтитулов: только из первых 12 / последних 4 строк страницы, key ≥ 8 знаков, на >30 % страниц."""
    import collections
    c = collections.Counter()
    for p in pages:
        ls = p['lines']
        c.update({key(l) for l in ls[:12] + ls[-4:] if len(key(l)) >= 8})
    return {k for k, n in c.items() if n > max(3, 0.3 * len(pages))}


def usable_lines(page, head):
    ls = []
    lines = page['lines']
    j = max([i for i, l in enumerate(lines[:12]) if HDR.search(l)] or [-1])
    if j >= 0: lines = lines[j + 1:]   # шапка страницы (наименование, реквизиты, «Стр.», штамп)
    for l in lines:
        if key(l) in head or garbage(l): continue
        if re.search(r'Стр\.?\s*/?\s*(page)?\s*\d', l) or re.match(r'(Дата введения|Основание\s*(:|_|Приказ)|Изменение\s*(/\s*Revision)?\s*№)', l.strip(), re.I): continue
        ls.append(l)
    return ls


def stream(kids):
    """Склеенный key-текст элементов тела + смещения начал."""
    keys = [key(txt(k)) for k in kids]
    offs, o = [], 0
    for k in keys: offs.append(o); o += len(k)
    return ''.join(keys), keys, offs


def elem_at(offs, pos):
    import bisect
    return bisect.bisect_right(offs, pos) - 1


def _ks(lines):
    out = []
    for l in lines:
        k = key(stripnum(l)) if len(key(stripnum(l))) >= MINLEN else key(l)
        if k: out.append(k)
    return out


def _score(S, p0, p1, ks, k, from_end):
    """Контекст кандидата: сколько соседних строк страницы подряд совпало вокруг иголки."""
    sc = 0
    if from_end:
        pos = p0
        for kk in reversed(ks[:-k] if k else ks):
            if pos - len(kk) >= 0 and S[pos - len(kk):pos] == kk: pos -= len(kk); sc += len(kk)
            else: break
    else:
        pos = p1
        for kk in ks[k:]:
            if S[pos:pos + len(kk)] == kk: pos += len(kk); sc += len(kk)
            else: break
    return sc


def _window_hits(S, p0, p1, ks, from_end):
    """Сколько разных строк страницы находится в окне размером со страницу до (A) / после (B) кандидата."""
    span = sum(len(k) for k in ks)
    w = S[max(0, p0 - span):p0] if from_end else S[p1:p1 + span]
    return sum(1 for k in set(ks) if len(k) >= MINLEN and k in w)


def find_seq(S, lines, after, from_end):
    """Позиция последовательности key-строк (k=3..1) в потоке базы после смещения after; при нескольких
    вхождениях — с лучшим совпадением соседних строк страницы. -> (start,end,k,nocc)."""
    ks = _ks(lines)
    for k in (3, 2, 1):
        if len(ks) < k: continue
        seq = ks[-k:] if from_end else ks[:k]
        needle = ''.join(seq)
        if len(needle) < MINLEN: continue
        occ, p = [], S.find(needle, after)
        while p != -1:
            occ.append(p); p = S.find(needle, p + 1)
        if occ:
            best = max(occ, key=lambda p: (_score(S, p, p + len(needle), ks, k, from_end), _window_hits(S, p, p + len(needle), ks, from_end), -p))
            return best, best + len(needle), k, len(occ)
    return None


def find_line(S, lines, after, from_end):
    """Резерв: одна строка (с конца/с начала страницы) длиной ≥12, затем ≥6 key-символов."""
    ks_all = _ks(lines)
    seq = list(reversed(range(len(ks_all)))) if from_end else list(range(len(ks_all)))
    first = None   # первый кандидат (прежнее поведение); берётся, если ни у одного нет опоры
    for minl in (MINLEN, 6):
        for idx in seq:
            k = ks_all[idx]
            if len(k) < minl: continue
            occ, p = [], S.find(k, after)
            while p != -1:
                occ.append(p); p = S.find(k, p + 1)
            if occ:
                ctx = ks_all[:idx + 1] if from_end else ks_all[idx:]
                best = max(occ, key=lambda p: (_score(S, p, p + len(k), ctx, 1, from_end), _window_hits(S, p, p + len(k), ks_all, from_end), -p))
                cand = (best, best + len(k), 1, len(occ))
                if first is None: first = cand
                # опора: другая строка страницы (>= MINLEN, однозначная во всей базе) в окне страницы рядом с кандидатом; одиночное случайное вхождение короткой
                # строки диаграммы (текст которой вне потока базы) якорем не считается
                span = sum(len(x) for x in ks_all)
                w = S[max(0, best - span):best] if from_end else S[best + len(k):best + len(k) + span]
                if any(x != k and len(x) >= MINLEN and x in w and S.count(x, after) == 1 for x in set(ks_all)): return cand
    return first


REPO = '/home/budnik_an/Obligations/'


def rel(path):
    return os.path.relpath(os.path.abspath(path), REPO)


CONTENT_HEAD = re.compile(r'^\s*1\s+[А-ЯЁ][А-ЯЁ\s,\-–]+$')


def page_score(ul, k, kn=None):
    """Число строк эталона, точно (по key) входящих в текст раздела; kn — текст с номерами автонумерации."""
    kn = kn or k
    return sum(1 for l in ul if key(l) in kn or key(l) in k or key(stripnum(l)) in k)


def relabel(secs, K, pages, plist):
    """Разделы листа без метки или с повторной меткой: метка = страница со штампом K с наибольшим числом строк,
    точно содержащихся в тексте раздела (порядок файла и перечень протокола соблюдаются). -> список записей журнала."""
    log = []
    cand = [p for p in pages if p['label']]   # любая страница эталона: раздел листа мог быть заменён позже или не применён (штамп 0)
    if not cand: return log
    idx = {p['label']: i for i, p in enumerate(cand)}
    head = header_keys(pages)
    ul_c = [[LIST_MARK.sub('', l) for l in usable_lines(p, head)] for p in cand]
    ul_c = [[l for l in ul if len(key(l)) >= MINLEN] for ul in ul_c]
    seen, need, zero = set(), {}, set()
    live = [i for i, s in enumerate(secs) if not s['empty']]
    for i in live:
        f = secs[i]['labs'][0] if secs[i]['labs'] else None
        if f is None or f in seen: need[i] = True
        else:
            seen.add(f)
            if f in idx and page_score(ul_c[idx[f]], key(secs[i]['text']), secs[i]['kn']) == 0:   # метка из колонтитула не подтверждена текстом: ни одной строки страницы эталона в разделе
                need[i] = True; zero.add(i)
    nxt_known = {}
    for pos, i in enumerate(live):
        later = [idx[secs[j]['labs'][0]] for j in live[pos + 1:] if j not in need and secs[j]['labs'] and secs[j]['labs'][0] in idx]
        nxt_known[i] = min(later) if later else len(cand)
    prev = -1
    for i in live:
        s = secs[i]; f = s['labs'][0] if s['labs'] else None
        if i not in need:
            if f in idx: prev = idx[f]
            continue
        k = key(s['text'])
        win = list(range(max(prev, 0), nxt_known[i]))
        full = []   # страница вне перечня протокола, ВСЕ строки которой есть в тексте раздела (протокол написан до сдвига нумерации страниц)
        if plist:
            full = [j for j in win if cand[j]['label'] not in plist and ul_c[j] and page_score(ul_c[j], k, s['kn']) == len(ul_c[j])]
            w2 = [j for j in win if cand[j]['label'] in plist]
            win = w2 or win
        sc = [(page_score(ul_c[j], k, s['kn']), -j) for j in win]
        best = max(range(len(win)), key=lambda t: sc[t]) if win else None
        if full and (best is None or sc[best][0] < len(ul_c[win[best]])):   # лучшая по перечню страница раздел целиком не содержит
            win = full; sc = [(page_score(ul_c[j], k, s['kn']), -j) for j in win]; best = max(range(len(win)), key=lambda t: sc[t])
        if best is not None and sc[best][0] > 0:
            new = cand[win[best]]['label']
            if new != f or f is None:
                log.append({'file': s['file'], 'first': s['first'], 'old': f, 'new': new, 'score': sc[best][0], 'name': s['name']})
            s['labs'] = [new]; s['relabeled'] = True; prev = win[best]
        elif i in zero:
            if f in idx: prev = idx[f]   # другой страницы с текстом раздела нет (раздел заменён позже/не применён): метка колонтитула остаётся
        else:
            log.append({'file': s['file'], 'first': s['first'], 'old': f, 'new': None, 'score': 0, 'name': s['name']})
            s['labs'] = [None]
    return log


def validate_break_labels(secs, plist, pages):
    """Метка от разрыва страницы внутри раздела листа: только если она в перечне протокола и раздел — argmax по строкам эталона."""
    head = header_keys(pages)
    by = {p['label']: p for p in pages if p['label']}
    log = []
    live = [s for s in secs if not s['empty']]
    for s in live:
        if s.get('labs_src') != 'breaks' or len(s['labs']) < 2: continue
        keep = [s['labs'][0]]
        for x in s['labs'][1:]:
            ok = False
            if plist and x in plist and x in by:
                ul = [l for l in usable_lines(by[x], head) if len(key(l)) >= MINLEN]
                sc = {id(t): page_score(ul, t['k'], t['kn']) for t in live}
                mx = max(sc.values()) if sc else 0
                ok = mx > 0 and sc[id(s)] == mx
            if ok: keep.append(x)
            else: log.append({'file': s['file'], 'label': x, 'name': s['name']})
        s['labs'] = keep
    return log


def extend_anchor(S, ul, A, end_side):
    """Порядок строк в текстовом слое PDF ≠ порядку в документе (таблицы, надписи): граница страницы — по самой дальней (A) / самой ранней (B)
    из строк страницы, найденных в базе в окне размером со страницу вокруг якоря. A=(start,end,k,occ) -> обновлённый A."""
    ks = [key(stripnum(l)) if len(key(stripnum(l))) >= MINLEN else key(l) for l in ul]
    ks = [k for k in ks if len(k) >= MINLEN and S.count(k) == 1]   # только строки, однозначные во всей базе
    span = sum(len(k) for k in ks)
    if not ks: return A
    s0, e0 = A[0], A[1]
    if end_side:   # A: конец страницы -> самый дальний конец в окне [s0, s0+span]
        best = e0
        for k in ks:
            q = S.find(k, s0, s0 + span + len(k))
            if q != -1 and q + len(k) > best: best = q + len(k)
        return (A[0], best, A[2], A[3])
    best = s0
    for k in ks:
        q = S.rfind(k, max(0, s0 - span), s0 + len(k))
        if q != -1 and q < best: best = q
    return (best, A[1], A[2], A[3])


def back_extend(S, ul, B):
    """Начало следующей страницы: якорь B мог встать на строку внутри страницы (первые строки — короткие обрывки заголовка, номер автонумерации не совпал);
    начало сдвигается назад на строки этой же страницы, стоящие в потоке базы вплотную перед якорем (с номером и без). B=(start,end,k,occ) -> B."""
    ks = [(key(l), key(stripnum(l))) for l in ul]
    ks = [(a, b) for a, b in ks if a]
    if B[2] != 1: return B
    needle = S[B[0]:B[1]]
    best = B[0]
    for idx in [i for i, (a, b) in enumerate(ks) if needle in (a, b)]:
        p = B[0]
        for a, b in reversed(ks[:idx]):
            if a and p >= len(a) and S[p - len(a):p] == a: p -= len(a)
            elif b and p >= len(b) and S[p - len(b):p] == b: p -= len(b)
            else: break
        best = min(best, p)
    return (best, B[1], B[2], B[3])


def trim_range(sec, need, pages, head):
    """Границы раздела листа по страницам эталона: от элемента с первой строкой первой страницы региона до элемента с последней строкой
    последней страницы (таблицы/рисунки между ними включительно). -> (s, e) | None."""
    by = {p['label']: (i, p) for i, p in enumerate(pages) if p['label']}
    pg = sorted([by[l] for l in need if l in by], key=lambda t: t[0])
    if not pg: return None
    def cand_lines(p, first):
        ls = [l for l in usable_lines(p, head) if len(key(l)) >= 6]
        return (ls[:3] if first else ls[-3:])
    nk = sec['nkeys']
    def best(line, lo, hi, tier_end):
        """Элемент раздела с ключевой строкой: точное совпадение > начало > вхождение; в ярусе — самый ранний."""
        kl, kp = key(line), key(stripnum(line))
        tiers = ([], [], [])
        for j in range(lo, hi + 1):
            k = nk[j]
            if not k: continue
            if k == kl or k == kp: tiers[0].append(j)
            elif k.startswith(kl) or k.startswith(kp): tiers[1].append(j)
            elif kl in k or kp in k: tiers[2].append(j)
        for t in tiers:
            if t: return t[0]
        return None
    st = [best(l, sec['s'], sec['e'], False) for l in cand_lines(pg[0][1], True)]
    st = [x for x in st if x is not None]
    if not st: return None
    s0 = min(st)
    en = [best(l, s0, sec['e'], True) for l in cand_lines(pg[-1][1], False)]
    en = [x for x in en if x is not None]
    if not en: return None
    e0 = max(en)
    # проверка без потерь: все строки нужных страниц, найденные в разделе, остаются внутри границ
    need_lines = [l for _, pgx in pg for l in usable_lines(pgx, head) if len(key(l)) >= 6]
    def in_rng(l, lo, hi):
        kl, kp = key(l), key(stripnum(l))
        return any(kl in nk[j] or kp in nk[j] for j in range(lo, hi + 1))
    for l in need_lines:
        if in_rng(l, sec['s'], sec['e']) and not in_rng(l, s0, e0): return None
    kids_ = sheet_kids(sec['file'])
    while s0 > sec['s'] and not txt(kids_[s0 - 1]).strip() and kids_[s0 - 1].find('.//' + W + 'sectPr') is None: s0 -= 1
    while e0 < sec['e'] and not txt(kids_[e0 + 1]).strip() and kids_[e0 + 1].find('.//' + W + 'sectPr') is None: e0 += 1
    return s0, e0


PLAIN_RUN_CHILDREN = ('rPr', 't', 'tab', 'br')


def plain_runs(p):
    """Абзац листа состоит из текстовых прогонов без связей с частями пакета (картинки, гиперссылки, поля) -> можно слить с абзацем базы."""
    if p.tag != W + 'p' or p.find(W + 'pPr/' + W + 'numPr') is not None: return None
    runs = []
    for ch in p:
        ln = etree.QName(ch).localname
        if ln in ('pPr', 'bookmarkStart', 'bookmarkEnd', 'proofErr'): continue
        if ln != 'r': return None
        for c in ch.iter():
            if any(etree.QName(a).namespace == R[1:-1] for a in c.attrib): return None   # r:embed / r:id — связь с частью пакета
            cl = etree.QName(c).localname
            if cl in ('fldChar', 'instrText', 'fldSimple', 'footnoteReference', 'endnoteReference', 'object'): return None
            if cl == 'br' and c.get(W + 'type') == 'page': return None
        runs.append(ch)
    return runs


_KIDS = {}


def sheet_kids(path):
    if path not in _KIDS:
        _KIDS[path] = list(etree.fromstring(zipfile.ZipFile(path).read('word/document.xml')).find(W + 'body'))
    return _KIDS[path]


class NoBase(Exception):
    """Нет Word-базы: явный статус документа (не падение)."""
    def __init__(self, status, msg): super().__init__(msg); self.status = status


def plan_doc(ddir, slug, workdir):
    ddir = os.path.abspath(ddir)
    docname = os.path.basename(ddir)
    canon = pd.ref_pdfs(ddir)[0]
    pages = canon_pages(canon)
    wall = [f for f in glob.glob(ddir + '/word/*') if f.lower().endswith(('.doc', '.docx'))]
    nm = lambda f: re.sub(r'\bк\s+приказ\w*', '', os.path.basename(f), flags=re.I)   # «пр к приказу» — не приказ
    words = [f for f in wall if not re.search('пояснит|приказ|ЭСЗ', nm(f), re.I)]
    words = [f for f in words if not (f.lower().endswith('.doc') and os.path.exists(f + 'x'))]   # .doc с готовой конвертацией рядом (batch_run)
    chap = [f for f in words if os.path.basename(f).startswith('__главы')]   # склейка файлов-глав (batch_run): единственная база
    words = chap or words
    if not words:
        arch = [f for f in glob.glob(ddir + '/word/*') if f.lower().endswith(('.7z', '.zip', '.rar'))]
        if arch: raise NoBase('base_in_archive', 'база в архиве: ' + ', '.join(os.path.basename(f) for f in arch))
        raise NoBase('no_base_word', 'в word/ нет Word-базы (только приказ/записка/ЭСЗ или не Word): ' + (', '.join(os.path.basename(f) for f in glob.glob(ddir + '/word/*')) or 'пусто'))
    base_src = max(words, key=os.path.getsize)
    os.makedirs(workdir, exist_ok=True)
    plan = {'doc': docname, 'slug': slug, 'canon_pdf': canon, 'base_src': base_src, 'defects': [], 'regions': [], 'notes': [], 'pdf_source': []}
    D = plan['defects']
    def defect(typ, sev, where, what, cause, **kw):
        D.append({'doc': docname, 'type': typ, 'severity': sev, 'where': where, 'what': what, 'cause': cause, 'cat': kw.pop('cat', 'asm'), **kw})
    def pq(p, pat):
        l = next((x for x in p['lines'] if re.search(pat, x)), None)
        return [{'file': rel(canon), 'text': l}] if l else []
    plan['relabel'] = []
    # база в docx
    base_docx = os.path.join(workdir, 'base_orig.docx')
    import doc2docx
    if base_src.lower().endswith('.docx'):
        shutil.copy(base_src, base_docx)
    elif doc2docx.cached(base_src):   # разовая конвертация .doc в Word уже сделана (шаг 9: кэш _cache/doc2docx)
        shutil.copy(doc2docx.cached(base_src), base_docx); plan['notes'].append('convert: из кэша doc2docx')
    else:
        shutil.copy(base_src, os.path.join(workdir, 'base_src.doc'))
        r = wordrun.run([{'op': 'convert', 'src': wordrun.winpath(slug + '/base_src.doc'), 'dst': wordrun.winpath(slug + '/base_orig.docx')}], slug + '_conv', 600)
        plan['notes'].append('convert: ' + r['log'].strip().replace('\n', ' | '))
        if not os.path.exists(base_docx):
            plan['fatal'] = 'не удалось конвертировать .doc: ' + r['log']; return plan
    # листы замены: выгрузки Word (ListString) для базы и листов
    amend = {}
    for adir in glob.glob(ddir + '/amendments/*'):
        m = re.search(r'изм([\d.]+)', adir)
        if not m: continue
        k = int(float(m.group(1)))
        amend[k] = (sorted(f for f in pd.adocx(adir) if classify(f) == 'sheets'), [f for f in pd.adocx(adir) if classify(f) == 'changelog'])
    allsheets = [f for k in sorted(amend) for f in amend[k][0]]
    base_dump = os.path.join(workdir, 'base_dump.txt')
    ensure_dumps(slug, workdir, allsheets)
    head = header_keys(pages)
    izms = {}
    for k in sorted(amend):
        sh, cl = amend[k]
        secs = []
        for f in sh:
            nums = word_numbers(f, dump_path_for(workdir, f)); nums.pop('_match', None)
            if not nums: nums = {kk: v for kk, v in para_numbers(f).items()}
            for s in sections2(f, nums):
                if s['e'] < s['s']: continue
                s['izm'] = k; s['name'] = os.path.basename(f)
                secs.append(s)
        plist, pline, _ = protocol_pages(cl[0]) if cl else (None, None, '')
        for lg in relabel(secs, k, pages, plist):
            plan['relabel'].append({**lg, 'izm': k})
            if lg['new']:
                defect('лист замены: метка страницы не задана/повторена в колонтитуле', 'косметика', f"изм{k}, {lg['name']}", f"раздел листа начинается «{lg['first'][:80]}»; метка {lg['old']} → стр.{lg['new']} (по точному вхождению строк эталона, с номерами автонумерации: {lg['score']})", 'колонтитул раздела без «Стр. N из M» или метка повторяется', cat='doc', quote=[{'file': rel(lg['file']), 'text': lg['first'][:80]}], level='L1', verified_by='argmax по числу строк эталона (key, с ListString), порядок файла и перечень протокола', files=[rel(lg['file'])])
            else:
                defect('лист замены: раздел не сопоставлен странице эталона', 'косметика', f"изм{k}, {lg['name']}", f"раздел «{lg['first'][:80]}» без метки, строк эталона со штампом изм{k} и позже в нём нет", 'колонтитул раздела без метки, текст не найден в эталоне', cat='doc', quote=[{'file': rel(lg['file']), 'text': lg['first'][:80]}], level='L1', verified_by='argmax по числу строк эталона (key, с ListString): 0', files=[rel(lg['file'])])
        bl = validate_break_labels(secs, plist, pages)
        for lg in bl: plan['notes'].append(f"изм{k} {lg['name']}: метка стр.{lg['label']} от разрыва страницы отброшена (нет в протоколе или не argmax)")
        labmap = {}   # метка -> [разделы] (пустые разделы без текста/графики не занимают метку)
        for s in secs:
            for lab in s['labs']:
                if not lab or s['empty']: continue
                if lab in labmap and labmap[lab][0]['name'] != s['name']: labmap[lab] = []
                labmap.setdefault(lab, []).append(s)
        expl = set(labmap)
        plan.setdefault('izm_info', {})[k] = {'plist': sorted(plist or [], key=label_key), 'pline': pline, 'changelog': rel(cl[0]) if cl else None, 'labels': sorted(expl, key=label_key)}
        for miss in sorted((plist or set()) - set(labmap), key=label_key):
            prev = [l for l in labmap if label_key(l) < label_key(miss)]
            if prev: labmap[miss] = list(labmap[max(prev, key=label_key)])
        izms[k] = {'secs': secs, 'labmap': labmap, 'plist': plist}
    latest = {}
    for k in sorted(izms):
        for lab in izms[k]['labmap']: latest[lab] = k
    # база: XML, номера Word (ListString), поток key-текста с номерами
    zb = zipfile.ZipFile(base_docx)
    broot = etree.fromstring(zb.read('word/document.xml'))
    bbody = broot.find(W + 'body')
    kids = list(bbody)
    bnums = word_numbers(base_docx, base_dump)
    plan['word_numbers_match'] = bnums.pop('_match', None)
    if not bnums: bnums = dict(para_numbers(base_docx))
    ntexts = [elem_ntext(k_, i_, bnums) for i_, k_ in enumerate(kids)]
    keys, pkeys = [key(t) for t in ntexts], [key(txt(k_)) for k_ in kids]
    offs, o_ = [], 0
    for k_ in keys: offs.append(o_); o_ += len(k_)
    S = ''.join(keys)
    lslen = [len(key(bnums.get((i_, 0)) or '')) if k_.tag == W + 'p' else 0 for i_, k_ in enumerate(kids)]
    brows = load_rows(base_dump)
    base_xml_all = key(''.join(t.text or '' for t in broot.iter(W + 't')))   # весь текст XML: надписи, фигуры, холсты
    base_extra = ''.join(key(r['text']) for r in brows if r['t'] in ('S', 'F')) + base_xml_all + wtext.media_key(base_docx)
    # B: страницы без штампа, строк которых нет в базе (с ListString, фигурами, сносками, EMF/OLE) — источник = лист замены с максимумом строк
    sec_all = [s_ for k_ in sorted(izms) for s_ in izms[k_]['secs'] if not s_['empty']]
    cstart = next((i for i, p in enumerate(pages) if any(CONTENT_HEAD.match(l) for l in p['lines'])), 0)
    plan['content_start_index'] = cstart
    override = {}
    hl = next((l for l in pages[cstart]['lines'] if CONTENT_HEAD.match(l)), None)
    bidx = 0
    if hl:
        hk = key(stripnum(hl))
        cands = [i_ for i_, k_ in enumerate(pkeys) if (k_ == hk or key(stripnum(txt(kids[i_]))) == hk) and i_ < len(keys) // 2]
        bidx = cands[-1] if cands else 0
    Sfull = S[offs[bidx]:] + base_extra
    plan['base_body_from_elem'] = bidx
    for i, p in enumerate(pages):
        if p['izm'] != 0 or not p['label']: continue
        Sx = Sfull if i >= cstart else (S + base_extra)   # служебные страницы сверяем со всей базой
        ul = [LIST_MARK.sub('', l) for l in usable_lines(p, head)]
        ul = [l for l in ul if len(key(l)) >= MINLEN]
        if not ul: continue
        inb = sum(1 for l in ul if key(l) in Sx or key(stripnum(l)) in Sx)
        if inb == len(ul): continue
        best = None
        for s_ in sec_all:
            sc = page_score(ul, s_['k'], s_['kn'])
            st = 1 if (s_['kn'].startswith(key(ul[0])) or s_['k'].startswith(key(stripnum(ul[0]))) or s_['kn'].startswith(key(stripnum(ul[0])))) else 0
            if sc and (best is None or (sc, st, s_['izm']) >= (best[0], best[2], best[1]['izm'])): best = (sc, s_, st)
        if best and best[0] <= inb: best = None; continue   # база содержит не меньше строк страницы, чем лучший лист: источник — база
        if best:
            p['izm_orig'] = 0; p['izm'] = best[1]['izm']; override[p['label']] = [best[1]]
            defect('страница в эталоне без штампа изменения', 'смысл', f"стр.{p['label']}", f"страница без штампа; строк страницы в базе Word (ListString, фигуры, сноски, EMF/OLE учтены) {inb} из {len(ul)}, в листе изм{best[1]['izm']} ({best[1]['name']}) {best[0]} из {len(ul)}", 'эталон: страница из листа замены без штампа «Изменение №»', cat='doc',
                   quote=[{'file': rel(canon), 'text': next(l for l in p['lines'] if key(l) == key(ul[0]) or key(LIST_MARK.sub('', l)) == key(ul[0]))}] + pq(p, r'Стр\.?\s*/?\s*(page)?\s*\d'), level='L1', verified_by=f'argmax: строк страницы в базе {inb}/{len(ul)} < в лучшем листе {best[0]}/{len(ul)} (ListString, фигуры, сноски, EMF/OLE учтены)', files=[rel(best[1]['file'])])
        elif inb == 0:
            defect('страница без штампа отсутствует в базе и в листах', 'смысл', f"стр.{p['label']}", 'строк страницы нет ни в базе, ни в листах замены', 'GAP: нет источника текста', cat='doc', quote=[{'file': rel(canon), 'text': p['lines'][min(4, len(p['lines']) - 1)]}], level='L1', verified_by='key строк не найден ни в базе, ни в листах')
    # A3: источник штампованной страницы подтверждается СОДЕРЖИМЫМ. Разделы листа по метке (в т.ч. заполнением пропуска протокола меткой
    # предыдущей страницы, в т.ч. разделы с одинаковой меткой колонтитула) проверяются по строкам страницы эталона:
    # (1) раздел без строк страницы отбрасывается; если страница покрыта на >=80 %, разделы, не добавляющие ни одной строки страницы, тоже;
    # (2) если покрытие < 80 % — разделы листов (изм >= K, затем любые) подбираются по содержимому жадно (>= 60 % строк и на 3+ строки лучше метки);
    # (3) если страницу не покрывает ни один лист, а в базе (тело) есть >= 80 % её строк — страница остаётся из базы (штамп без замены текста).
    gate_src = {}
    if os.environ.get('A3_GATE', '1') == '1':
        def covers(ulp, s_): return {j for j, l in enumerate(ulp) if key(l) in s_['kn'] or key(l) in s_['k'] or key(stripnum(l)) in s_['k']}
        def greedy(ulp, pool, limit=3):
            cov_, out_ = set(), []
            while len(out_) < limit:
                gain = [(len(covers(ulp, s_) - cov_), s_) for s_ in pool if s_ not in out_]
                gain = [g for g in gain if g[0] >= (3 if out_ else 1)]
                if not gain: break
                g, s_ = max(gain, key=lambda t: (t[0], t[1]['izm'] == K))
                out_.append(s_); cov_ |= covers(ulp, s_)
            return out_, cov_
        gi = {}   # метка -> (индекс страницы, строки, разделы по метке, подтверждённые, покрытие)
        for i, p in enumerate(pages):
            lab, K = p['label'], p['izm']
            if K <= 0 or not lab or (p.get('izm_orig') == 0 and lab in override): continue
            secl = izms.get(K, {}).get('labmap', {}).get(lab)
            if secl is None and latest.get(lab) is not None: secl = izms[latest[lab]]['labmap'][lab]
            ulp = [LIST_MARK.sub('', l) for l in usable_lines(p, head)]
            ulp = [l for l in ulp if len(key(l)) >= MINLEN]
            if not ulp: continue
            good = [s_ for s_ in (secl or []) if covers(ulp, s_)]
            gi[lab] = (i, ulp, secl, good, set().union(*[covers(ulp, s_) for s_ in good]) if good else set())
        def needed_elsewhere(lab, s_):
            """раздел даёт другой штампованной странице >= 2 строк, которых нет в её собственных разделах (лист разбит не по границам страниц)"""
            for lab2, (i2, ulp2, secl2, good2, cov2) in gi.items():
                if lab2 == lab: continue
                oth = set().union(*[covers(ulp2, o_) for o_ in good2 if o_ is not s_]) if good2 else set()
                if len(covers(ulp2, s_) - oth) >= 2: return True
            return False
        for lab, (i, ulp, secl, good, cov) in gi.items():
            p = pages[i]; K = p['izm']
            n_ = len(ulp)
            if os.environ.get('A3_DEBUG'): print('GATE', lab, K, n_, len(secl or []), [(s_['izm'], s_['name'][:20], s_['s'], len(covers(ulp, s_))) for s_ in (secl or [])], len(cov))
            if good and all(s_['izm'] != K for s_ in good):   # источник по метке — лист более ранней редакции, а лист изм K содержит страницу полнее
                bk = [s_ for s_ in sec_all if s_['izm'] == K and len(covers(ulp, s_)) > len(cov) and len(covers(ulp, s_)) >= 0.9 * n_]
                bk = [s_ for s_ in bk if not any(lab2 != lab and any(g_ is s_ for g_ in good2) and len(covers(ulp2, s_)) >= len(covers(ulp, s_)) and len({key(ulp[j]) for j in covers(ulp, s_)} & {key(ulp2[j]) for j in covers(ulp2, s_)}) >= 0.5 * len(covers(ulp, s_)) for lab2, (i2, ulp2, secl2, good2, cov2) in gi.items())]
                if bk:
                    bs = max(bk, key=lambda s_: len(covers(ulp, s_))); gate_src[lab] = [bs]
                    defect('лист замены: раздел страницы взят из листа штампа', 'косметика', f"стр.{lab}", f"по метке взят лист изм{good[0]['izm']}, но штамп изм{K}: в листе изм{K} ({bs['name']}) строк страницы больше ({len(covers(ulp, bs))} против {len(cov)} из {n_})", 'лист штампа не пронумерован/метка не совпала', cat='doc', level='L1', verified_by='строки страницы эталона (key) в разделе листа', files=[rel(bs['file'])])
                    continue
            if len(cov) >= 0.8 * n_:
                keep = list(good)
                for s_ in sorted(good, key=lambda s_: len(covers(ulp, s_))):
                    others = set().union(*[covers(ulp, o_) for o_ in keep if o_ is not s_]) if len(keep) > 1 else set()
                    if len(keep) > 1 and not (covers(ulp, s_) - others) and not needed_elsewhere(lab, s_) and os.environ.get('A3_PRUNE', '0') == '1': keep.remove(s_)
                if secl is None or len(keep) < len(secl):
                    gate_src[lab] = keep; plan['notes'].append(f"стр.{lab}: из разделов листа по метке оставлено {len(keep)} из {len(secl)} (остальные не добавляют строк страницы)")
                continue
            def claimed(s_):   # раздел — лучший по метке для другой страницы с тем же текстом (близнецы-страницы); общий раздел разных страниц не «занят»
                kp_ = {key(ulp[j]) for j in covers(ulp, s_)}
                for lab2, (i2, ulp2, secl2, good2, cov2) in gi.items():
                    if lab2 == lab or not any(g_ is s_ for g_ in good2): continue
                    kq_ = {key(ulp2[j]) for j in covers(ulp2, s_)}
                    if len(kq_) >= len(kp_) and len(kp_ & kq_) >= 0.5 * max(len(kp_), 1): return True
                return False
            pool = [s_ for s_ in sec_all if s_['izm'] >= K and not claimed(s_)] or [s_ for s_ in sec_all if not claimed(s_)]
            gs, gcov = greedy(ulp, pool)
            if len(cov) <= 0.5 * n_ and gs and len(gcov) >= 0.6 * n_ and len(gcov) >= len(cov) + 3:
                gate_src[lab] = sorted(gs, key=lambda s_: (s_['izm'], s_['s']))
                defect('лист замены: раздел страницы найден по содержимому', 'косметика', f"стр.{lab}", f"метка листа не подтверждена текстом ({'; '.join('«' + s_['first'][:40] + '»' for s_ in (secl or [])[:2]) or 'раздела с такой меткой нет'}); взяты по строкам страницы ({len(gcov)} из {n_}): " + '; '.join(f"изм{s_['izm']} {s_['name']} «{s_['first'][:40]}»" for s_ in gs), 'колонтитул/протокол не совпал со страницей', cat='doc', level='L1', verified_by='строки страницы эталона (key) найдены в разделах листов', files=[rel(s_['file']) for s_ in gs])
                continue
            if cov: continue   # частичное покрытие меткой, лучшего по содержимому нет — как раньше
            Sx = Sfull if i >= cstart else (S + base_extra)
            inb = sum(1 for l in ulp if key(l) in Sx or key(stripnum(l)) in Sx)
            if i >= cstart and inb >= 0.8 * n_:
                p['izm_orig'] = K; p['izm'] = 0
                defect('штамп без замены текста: страница из базы', 'косметика', f"стр.{lab}", f"штамп изм{K}, ни в одном листе замены строк страницы нет, в базе {inb} из {n_}", 'лист замены не содержит страницу; текст страницы в базе', cat='doc', level='L1', verified_by='key строк страницы: ни одной в листах замены')
            elif secl:
                gate_src[lab] = []
    # страницы эталона без источника в Word -> источник PDF (решение human 04.10.2026): штамп > 0 и ни в одном листе замены страницы нет
    # (а в базе её нет целиком) либо страница без штампа, которой нет в базе
    pdf_cand = {}
    SH = ''.join(s_['k'] + s_['kn'] for s_ in sec_all)   # весь текст листов замены (любая страница): строки, найденные там, источник в Word имеют
    for i, p in enumerate(pages):
        if i < cstart or not p['label']: continue
        ul = [LIST_MARK.sub('', l) for l in usable_lines(p, head) if not pdf_frag.TOC_LINE.search(l)]   # строки оглавления (точки-заполнители) не содержимое
        ul = [l for l in ul if len(key(l)) >= MINLEN]
        if not ul: continue
        M = [l for l in ul if not (key(l) in Sfull or key(stripnum(l)) in Sfull)]   # строки, которых нет в базе
        M = [l for l in M if not (key(l) in SH or key(stripnum(l)) in SH)]            # и нет ни в одном листе замены
        K, lab = p['izm'], p['label']
        if K > 0:
            has_src = ((lab in izms.get(K, {}).get('labmap', {})) or (lab in latest) or (p.get('izm_orig') == 0 and lab in override)) and gate_src.get(lab, True) != []
            if not has_src and len(M) >= max(2, 0.15 * len(ul)): pdf_cand[lab] = f'штамп изм{K}, листа замены с этой страницей нет; нет в Word строк {len(M)} из {len(ul)}'
        elif len(M) >= max(3, 0.5 * len(ul)):
            pdf_cand[lab] = f'без штампа; нет в Word строк {len(M)} из {len(ul)}'
    for p in pages:
        p['pdf'] = p['label'] in pdf_cand
    plan['pdf_candidates'] = pdf_cand
    # регионы по эффективному штампу (страницы источника PDF входят в регион как отдельные страницы)
    regs, cur = [], None
    for i, p in enumerate(pages):
        if p['izm'] > 0 or p['pdf']:
            if cur is None: cur = [i, i]
            else: cur[1] = i
        else:
            if cur: regs.append(cur); cur = None
    if cur: regs.append(cur)
    plan['override_labels'] = sorted(override)
    plan['pages'] = [{'pdf_page': p['n'], 'label': p['label'], 'stamp': p.get('izm_orig', p['izm']), 'eff_stamp': p['izm']} for p in pages]
    for p in pages:  # «штамп 0, но есть лист»
        if p['izm'] == 0 and p['label'] in latest:
            ul = [l for l in usable_lines(p, head) if len(key(l)) >= MINLEN]
            inb = sum(1 for l in ul if key(l) in Sfull or key(stripnum(l)) in Sfull)
            secl = izms[latest[p['label']]]['labmap'][p['label']]
            ins = max(page_score(ul, s_['k'], s_['kn']) for s_ in secl) if ul else 0
            defect('штамп 0, но есть лист замены', 'косметика', f"стр.{p['label']}", f"в эталоне без штампа, лист изм{latest[p['label']]} содержит страницу с этой меткой (колонтитул); строк эталона {len(ul)}: в базе {inb}, в листе {ins}", 'штамп не проставлен или лист не применён; взята база',
                   cat='doc', quote=pq(p, r'Стр\.?\s*/?\s*(page)?\s*\d'), level='L1', verified_by=f'key строк страницы: база {inb}/{len(ul)}, лист {ins}/{len(ul)}', files=[])
    ptr = 0
    inserts = []
    edits = []
    retained = {}   # key строки нештампованной страницы эталона -> позиция в S (строка однозначна в базе)
    retained_pg = {}   # key -> индекс страницы эталона
    for pi_, p_ in enumerate(pages):
        if p_['izm'] != 0 or p_['pdf'] or not p_['label']: continue
        for l_ in usable_lines(p_, head):
            for k_ in (key(stripnum(l_)), key(l_)):
                if len(k_) < MINLEN: continue
                q_ = S.find(k_)
                if q_ != -1:
                    if S.find(k_, q_ + 1) == -1: retained[k_] = q_; retained_pg[k_] = pi_
                    break
    GUARD_MAX = int(os.environ.get('A2_GUARD_MAX', '5'))
    tbl_rows_cache = {}
    def tbl_rows(i):
        """Строки таблицы базы: [(конец накопленной длины key с номерами, w:tr)]."""
        if i in tbl_rows_cache: return tbl_rows_cache[i]
        el = kids[i]
        out, cum, pc = [], 0, 0
        for tr in el.findall(W + 'tr'):
            n = 0
            for p_ in tr.iter(W + 'p'):
                num = bnums.get((i, pc)); pc += 1
                n += len(key(((num + ' ') if num else '') + txt(p_)))
            cum += n; out.append((cum, tr))
        tbl_rows_cache[i] = out
        return out
    def row_at(i, pos_in):
        for r_, (cend, tr) in enumerate(tbl_rows(i)):
            if pos_in < cend: return r_
        return len(tbl_rows(i)) - 1
    def sect_idx_before(i): return max([j for j in range(i) if kids[j].find('.//' + W + 'sectPr') is not None] or [-1])
    def sect_idx_from(i): return min([j for j in range(i, len(kids)) if kids[j].find('.//' + W + 'sectPr') is not None] or [len(kids) - 1])
    for ri, (i0, i1) in enumerate(regs, 1):
        rp = pages[i0:i1 + 1]
        reg = {'n': ri, 'pages': [p['label'] or f"pdf{p['n']}" for p in rp], 'stamps': sorted({p['izm'] for p in rp}), 'ok': False, 'service': i1 < cstart}
        plan['regions'].append(reg)
        where = f"регион {ri}: стр. {reg['pages'][0]}–{reg['pages'][-1]}"
        # источники по страницам
        chosen = []; used_override = set()
        for p in rp:
            lab, K = p['label'], p['izm']
            if p['pdf']:
                chosen.append((lab, ('pdf', p['n']))); continue
            secl = override[lab] if (p.get('izm_orig') == 0 and lab in override) else izms.get(K, {}).get('labmap', {}).get(lab)
            if p.get('izm_orig') == 0 and lab in override: used_override.add(lab)
            gated = lab in gate_src and not (p.get('izm_orig') == 0 and lab in override)   # A3: источник подтверждён содержимым
            if gated and gate_src[lab]: secl = gate_src[lab]
            svc = i1 < cstart
            sev = 'косметика' if svc else 'смысл'
            if gated and not gate_src[lab]:
                defect('нет источника страницы', sev, f"стр.{lab}", f"штамп изм{K}: раздел листа по метке строк страницы не содержит, другого листа с её текстом нет, в базе страницы нет", 'страница отсутствует в листах замены', cat='doc', quote=pq(p, r'Изменение\s*(/\s*Revision)?\s*№') + pq(p, r'Стр\.?\s*/?\s*(page)?\s*\d'), level='L1', verified_by='строки страницы не найдены в разделе листа')
                continue
            if secl is None:
                alt = latest.get(lab)
                if alt is not None:
                    secl = izms[alt]['labmap'][lab]
                    defect('нет листа для штампа', sev, f"стр.{lab}", f"штамп изм{K}, листа изм{K} с такой меткой нет; взят лист изм{alt}", 'метка/штамп не совпали с листами', files=[rel(secl[0]['file'])], cat='doc', quote=pq(p, r'Изменение\s*(/\s*Revision)?\s*№') + pq(p, r'Стр\.?\s*/?\s*(page)?\s*\d'), level='L1', verified_by='метки листов изм%d после argmax не содержат стр.%s' % (K, lab))
                else:
                    defect('нет источника страницы', sev, f"стр.{lab}", f"штамп изм{K}, ни в одном листе замены страницы нет", 'страница отсутствует в листах замены', cat='doc', quote=pq(p, r'Изменение\s*(/\s*Revision)?\s*№') + pq(p, r'Стр\.?\s*/?\s*(page)?\s*\d'), level='L1', verified_by='метки всех листов после argmax не содержат страницу')
                    continue
            elif latest.get(lab, K) > K:
                defect('штамп ≠ последний лист', sev, f"стр.{lab}", f"штамп изм{K}, но есть более поздний лист изм{latest[lab]}", 'чужая версия страницы (взята по штампу)', files=[rel(secl[0]['file'])], cat='doc', quote=pq(p, r'Изменение\s*(/\s*Revision)?\s*№') + pq(p, r'Стр\.?\s*/?\s*(page)?\s*\d'), level='L1', verified_by='метки листов после argmax')
            for sec in secl: chosen.append((lab, sec))
        uniq = []
        for lab, sec in chosen:
            if isinstance(sec, tuple):   # страница источника PDF: подряд идущие — один регион-фрагмент
                if uniq and uniq[-1][0][0] == 'pdf': uniq[-1][1]['nums'].append(sec[1]); uniq[-1][2].append(lab)
                else: uniq.append((('pdf', sec[1]), {'pdf': True, 'nums': [sec[1]]}, [lab]))
                continue
            idn = (sec['file'], sec['s'], sec['e'])
            hit = next((u for u in uniq if u[0] == idn), None)
            if hit is None: uniq.append((idn, sec, [lab]))
            elif lab not in hit[2]: hit[2].append(lab)
        if not uniq:
            reg['fail'] = 'нет ни одного листа замены для страниц региона'
            defect('регион не собран', 'смысл', where, 'для страниц региона нет листов замены; в каноне остаётся текст базы', 'листы замены отсутствуют')
            continue
        # границы раздела листа по страницам эталона
        uv = []
        for idn, sec, labs in uniq:
            sv = sec
            if sec.get('pdf'): uv.append((idn, sec, labs)); continue
            if True:
                tr = trim_range(sec, labs, pages, head)
                if tr and (tr[0] > sec['s'] or tr[1] < sec['e']):
                    sv = dict(sec, s=tr[0], e=tr[1], e0=sec['e'], trimmed=True)
                    reg.setdefault('trimmed', []).append({'file': sec['name'], 'from': [sec['s'], sec['e']], 'to': list(tr)})
                elif not tr:
                    reg.setdefault('untrimmed', []).append(sec['name'])
            uv.append((idn, sv, labs))
        uniq = uv
        # якоря
        A = B = None
        prevp = nextp = None
        aft = offs[ptr] if ptr < len(offs) else 0
        service_mode = False
        def fl(pg):
            u = [l for l in usable_lines(pg, head) if len(key(l)) >= 6]
            return {key(u[0]), key(stripnum(u[0])), key(re.sub(r'^[\d.\s]+', '', u[0]))} - {''} if u else set()   # заголовок страницы с номером автонумерации и без (в тексте базы номера нет)
        def fl3(pg):
            return [{key(l), key(stripnum(l)), key(re.sub(r'^[\d.\s]+', '', l))} - {''} for l in [l for l in usable_lines(pg, head) if len(key(l)) >= 6][:8]]
        def head_cand(i):
            """Элемент базы — заголовок первой строки страницы i (служебные страницы: предисловие, перечень рассылки, содержание)."""
            for h0 in fl3(pages[i]):
                c_ = [i_ for i_ in range(max(ptr, 0), bidx) if pkeys[i_] in h0]
                if c_: return c_
            return []
        if i1 < cstart:
            # служебные страницы: блок базы от заголовка первой страницы региона до следующего служебного заголовка / разрыва раздела
            SVC = {'предисловие', 'листрегистрациивнесенияизменений', 'переченьрассылки', 'содержание'}
            own = set().union(*[fl(pages[i]) for i in range(i0, i1 + 1)])
            cand = head_cand(i0)
            if cand:
                e0 = cand[0]; b_ = None; consumed = {pkeys[e0]}
                for j in range(e0 + 1, len(kids)):
                    if j >= bidx: b_ = bidx; break   # служебный блок не заходит в тело документа (заголовок «1 …»)
                    if kids[j].find('.//' + W + 'sectPr') is not None:
                        # следующий раздел базы начинается заголовком другой страницы этого же региона (перечень рассылки -> содержание): блок региона продолжается
                        nk = next((pkeys[t] for t in range(j + 1, min(j + 4, len(kids))) if pkeys[t]), None)
                        if nk in own and nk not in consumed: consumed.add(nk); continue
                        b_ = j + 1; break
                    if pkeys[j] in SVC and pkeys[j] not in own: b_ = j; break
                if b_ and e0 - 1 >= ptr - 1:
                    service_mode = True
                    reg['service_anchor'] = {'e0': e0, 'a': e0 - 1, 'b': b_}
        if not service_mode:
            for j in range(i0 - 1, -1, -1):
                pj = pages[j]
                if pj['izm'] != 0 or pj['pdf']: break
                ul = usable_lines(pj, head)
                if not ul or not pj['label']: continue
                A = find_seq(S, ul, aft, True) or find_line(S, ul, aft, True)
                if A:
                    # конец предыдущей страницы (сноски внизу страницы эталона стоят в потоке базы дальше, в теле раздела) не может лежать
                    # за однозначными строками самого региона: отбрасываем последние строки страницы, пока якорь не станет раньше
                    pm = [S.find(k_, aft) for k_ in {key(stripnum(l_)) for ip in range(i0, i1 + 1) for l_ in usable_lines(pages[ip], head)} if len(k_) >= MINLEN and S.count(k_, aft) == 1]
                    pm = min(pm) if pm else None
                    n_ = 0; A0 = A
                    while pm is not None and A[1] > pm and n_ < 6 and len(ul) - n_ > 1 and kids[elem_at(offs, A[1] - 1)].tag == W + 'p':   # только абзацы (порядок текста в таблицах ≠ порядку страницы)
                        n_ += 1
                        A2 = find_seq(S, ul[:-n_], aft, True) or find_line(S, ul[:-n_], aft, True)
                        if not A2: break
                        A = A2; reg['anchor_tail_dropped'] = n_
                    if pm is not None and A[1] > pm and n_:   # не помогло: прежний якорь (эвристика применяется, только если снимает противоречие)
                        A = A0; reg.pop('anchor_tail_dropped', None)
                    elif n_ and pm - A[1] > sum(len(k_) for k_ in _ks(ul)):   # новый якорь дальше от региона, чем страница: вырезался бы чужой текст (ложное совпадение хвоста)
                        A = A0; reg.pop('anchor_tail_dropped', None)
                    A = extend_anchor(S, ul, A, True); prevp = pj; break
                defect('страница без штампа не найдена в базе', 'смысл', f"стр.{pj['label']}", f"нештампованная страница: «{ul[0][:70]}» … в базе Word нет; якорем взята предыдущая", 'база Word не содержит страницы эталона (GAP базы)')
        if not prevp and not service_mode and i0 < cstart:
            # регион начинается среди служебных страниц и тянется в тело (перечень рассылки -> содержание -> разделы): перед ним нет страницы базы,
            # границей начала служит заголовок первой страницы региона в базе
            hc = head_cand(i0)
            if hc: A = (offs[hc[0]], offs[hc[0]], 0, 0); reg['head_anchor'] = hc[0]
        if not prevp and not service_mode and A is None:
            defect('якорь не найден', 'смысл', where, 'перед регионом нет нештампованной страницы, найденной в базе, и границы служебного раздела не определены', 'нет опоры для вырезания региона в базе; остаётся текст базы')
            continue
        if not service_mode:
            for j in range(i1 + 1, len(pages)):
                pj = pages[j]
                if pj['izm'] != 0 or pj['pdf']: break
                ul = usable_lines(pj, head)
                if not ul or not pj['label']: continue
                B = find_seq(S, ul, A[1], False) or find_line(S, ul, A[1], False)
                if B: B = back_extend(S, ul, B); B = extend_anchor(S, ul, B, False); B = (max(B[0], A[1]), B[1], B[2], B[3]); nextp = pj; break
                defect('страница без штампа не найдена в базе', 'смысл', f"стр.{pj['label']}", f"нештампованная страница: «{ul[0][:70]}» … в базе Word нет; якорем взята следующая", 'база Word не содержит страницы эталона (GAP базы)')
            if B is None and nextp is None and i1 + 1 < len(pages) and pages[i1 + 1]['izm'] == 0 and any(pages[j]['izm'] == 0 and pages[j]['label'] and usable_lines(pages[j], head) for j in range(i1 + 1, len(pages))):
                defect('якорь не найден', 'смысл', where, 'после региона нет страницы, найденной в базе', 'база не содержит текста нештампованных страниц'); continue
        if service_mode:
            a, b = reg['service_anchor']['a'], reg['service_anchor']['b']
        else:
            a = elem_at(offs, A[1] - 1)
            b = elem_at(offs, B[0]) if B else len(kids) - (1 if kids[-1].tag == W + 'sectPr' else 0)
            if B and b < a or (B and b == a and kids[a].tag != W + 'tbl'):
                defect('якорь не найден', 'смысл', where, f"якоря конца стр.{prevp['label'] if prevp else 'титул'} и начала стр.{nextp['label']} в одном абзаце базы", 'регион внутри одного абзаца'); continue
            if kids[a].tag == W + 'tbl': reg['row_a'] = row_at(a, A[1] - 1 - offs[a])
            if B and kids[b].tag == W + 'tbl': reg['row_b'] = row_at(b, B[0] - offs[b])
            if B and b == a and reg.get('row_b', 0) <= reg.get('row_a', 0):
                defect('якорь не найден', 'смысл', where, 'якоря региона в одной строке таблицы базы', 'регион внутри одной строки таблицы'); continue
        if not service_mode and A and prevp and kids[a].tag == W + 'p' and A[1] == offs[a] + len(keys[a]):
            # хвост предыдущей страницы эталона вне текстового потока базы (строки рисунка/объекта) -> рисунки без текста сразу после якоря её
            lk = _ks(usable_lines(prevp, head))
            if lk and S.find(lk[-1], aft) == -1:
                lim = b if B else len(kids)
                while a + 1 < lim and not keys[a + 1] and any(True for _ in itertools.chain(kids[a + 1].iter(W + 'drawing'), kids[a + 1].iter(W + 'pict'), kids[a + 1].iter(W + 'object'))):
                    a += 1
                reg['kept_objects_after_anchor'] = a - elem_at(offs, A[1] - 1)
        # разрезанные абзацы (только простые абзацы w:p)
        tail_a = head_b = ''
        if A and kids[a].tag == W + 'p' and not reg.get('kept_objects_after_anchor'):
            tail_a = keys[a][A[1] - offs[a]:]
            if not re.search(r'[а-яa-z]', tail_a): tail_a = ''
        if B and kids[b].tag == W + 'p':
            hb = keys[b][:B[0] - offs[b]]
            hb = hb[lslen[b]:] if hb.startswith(key(bnums.get((b, 0)) or '')) else hb
            head_b = hb if re.search(r'[а-яa-z]', hb) else ''
        removed = kids[a + 1:b]
        if not service_mode and b > a:
            lo_ = offs[a + 1] if a + 1 < len(kids) else len(S); hi_ = offs[b] if b < len(kids) else len(S)
            rlo_, rhi_ = lo_, hi_
            reg['destroyed'] = sum(1 for q_ in retained.values() if lo_ <= q_ < hi_)
        reg['destroyed_pre'] = reg.get('destroyed', 0)
        guard_pending = (not service_mode and b > a and reg.get('destroyed', 0) > GUARD_MAX)
        # A3: спасение — элементы базы внутри вырезаемого диапазона, содержащие (а) однозначную строку нештампованной страницы эталона или
        # (б) строку страницы региона, которой нет в вставляемых фрагментах, не вырезаются (иначе строка эталона пропадает из канона)
        keep_b, keep_a = [], []
        Ftxt_g = ''.join(''.join(sec['nkeys'][sec['s']:sec['e'] + 1]) for _, sec, _ in uniq if not sec.get('pdf'))
        if not service_mode and b > a + 1 and os.environ.get('A3_SALVAGE', '1') == '1':
            Ftxt = ''.join(''.join(sec['nkeys'][sec['s']:sec['e'] + 1]) for _, sec, _ in uniq if not sec.get('pdf'))
            pdfpg = {p_['label'] for _, sec, labs in uniq if sec.get('pdf') for p_ in rp if p_['label'] in labs}
            need_k = []
            for p_ in rp:
                if p_['pdf'] or p_['label'] in pdfpg: continue
                for l_ in usable_lines(p_, head):
                    l_ = LIST_MARK.sub('', l_); kl_, kp_ = key(l_), key(stripnum(l_))
                    if len(kl_) < MINLEN or kl_ in Ftxt or kp_ in Ftxt: continue
                    need_k.append((kl_, kp_))
            for j in range(a + 1, b):
                if kids[j].find('.//' + W + 'sectPr') is not None or not keys[j]: continue
                if len(pkeys[j]) > 60 and (pkeys[j] in Ftxt or keys[j] in Ftxt): continue   # такой абзац уже есть во фрагментах (спасение дало бы повтор)
                lo_, hi_ = offs[j], offs[j] + len(keys[j])
                rq = [retained_pg[k_] for k_, q_ in retained.items() if lo_ <= q_ < hi_]
                if rq: (keep_b if min(rq) < i0 else keep_a).append(j); continue
                if any(kl_ in keys[j] or kp_ in keys[j] or kp_ in pkeys[j] or kl_ in pkeys[j] for kl_, kp_ in need_k): keep_a.append(j)
            if keep_b or keep_a:
                reg['salvaged'] = {'before': len(keep_b), 'after': len(keep_a)}
                reg['destroyed'] = 0
        if guard_pending:   # A4: гард по-прежнему срабатывает, если сохраняемые строки остаются в вырезаемых элементах, которые спасти нельзя
            kept_ = set(keep_b) | set(keep_a)
            left = 0
            for q_ in retained.values():
                if rlo_ <= q_ < rhi_:
                    j_ = elem_at(offs, q_)
                    if j_ not in kept_ and not (len(pkeys[j_]) > 60 and (pkeys[j_] in Ftxt_g or keys[j_] in Ftxt_g)): left += 1
            reg['destroyed'] = left
            if left > GUARD_MAX or reg.get('destroyed_pre', 0) > int(os.environ.get('A4_GUARD_MAX', '100')) or os.environ.get('A4_GUARD', '1') != '1':   # слишком широкое вырезание = якоря неверны (сдвиг указателя ломает следующие регионы)
                defect('вырезание региона затрагивает сохраняемые страницы', 'смысл', where, f"между якорями {len(removed)} элементов базы, из них {left} однозначных строк нештампованных страниц эталона; регион не собран, остаётся текст базы", 'якоря региона выбраны неверно (неоднозначное вхождение строки страницы)')
                reg['fail'] = 'вырезание затрагивает сохраняемые страницы'
                continue
        plan['sect_breaks_removed'] = plan.get('sect_breaks_removed', 0) + sum(1 for k in removed if k.find('.//' + W + 'sectPr') is not None)
        reg.update({'a_elem': a, 'b_elem': b, 'anchor_prev': A and {'k': A[2], 'occ': A[3]}, 'anchor_next': B and {'k': B[2], 'occ': B[3]}, 'removed_elems': len(removed), 'tail_a': tail_a[:40], 'head_b': head_b[:40]})
        drop_first = drop_last = False
        first_sec, last_sec = uniq[0][1], uniq[-1][1]
        def sec_el(sec, idx): return sheet_kids(sec['file'])[idx]
        if len(tail_a) >= MINLEN and first_sec.get('pdf'):
            edits.append(('trim_tail', a, len(pkeys[a]) - len(tail_a))); reg['first_para'] = 'хвост абзаца базы убран (дальше страница из PDF)'
        elif len(tail_a) >= MINLEN:
            fi = next((j for j in range(first_sec['s'], first_sec['e'] + 1) if txt(sec_el(first_sec, j)).strip()), first_sec['s'])
            fe = sec_el(first_sec, fi); kf = key(txt(fe))
            if kf and (pkeys[a].endswith(kf) or kf == tail_a or tail_a.startswith(kf) or kf.startswith(tail_a)):
                drop_first = True; reg['first_para'] = 'хвост абзаца базы = первый абзац листа: дубль не вставлен'
            else:
                pl_ = plain_runs(fe)
                edits.append(('trim_tail', a, len(pkeys[a]) - len(tail_a)))
                if pl_ is not None:
                    edits.append(('merge_tail', a, first_sec['file'], fi)); drop_first = True
                    reg['first_para'] = 'хвост абзаца базы заменён хвостом из листа (слиты в один абзац)'
                else:
                    defect('разрез абзаца на границе (хвост из листа)', 'граф', where, f"абзац базы «{txt(kids[a])[-60:]}» разрезан границей стр.; хвост «{tail_a[:50]}» ≠ листу «{txt(fe)[:50]}» (в первом абзаце листа рисунки/поля — слить нельзя)", 'абзац разделён на два', files=[rel(first_sec['file'])])
        if len(head_b) >= MINLEN and last_sec.get('pdf'):
            edits.append(('trim_head', b, len(head_b))); reg['last_para'] = 'голова абзаца базы убрана (перед ней страница из PDF)'
        elif len(head_b) >= MINLEN:
            le_idx = last_sec['e']
            while le_idx > last_sec['s'] and not txt(sec_el(last_sec, le_idx)).strip(): le_idx -= 1
            le = sec_el(last_sec, le_idx); kl = key(txt(le))
            if kl and (pkeys[b].startswith(kl) or kl == head_b or head_b.endswith(kl) or kl.endswith(head_b)):
                drop_last = True; reg['last_para'] = 'начало абзаца базы = последний абзац листа: дубль не вставлен'
            else:
                pl_ = plain_runs(le)
                edits.append(('trim_head', b, len(head_b)))
                if pl_ is not None:
                    edits.append(('merge_head', b, last_sec['file'], le_idx)); drop_last = True
                    reg['last_para'] = 'голова абзаца базы заменена головой из листа (слиты в один абзац)'
                else:
                    defect('разрез абзаца на границе (голова из листа)', 'граф', where, f"абзац базы, начатый на стр. региона: голова «{head_b[:50]}» ≠ последнему абзацу листа «{kl[:50]}» (слить нельзя)", 'абзац разделён на два', files=[rel(last_sec['file'])])
        fl = []
        def base_sect(a_):
            j_ = min([j for j in range(max(a_ + 1, 0), len(kids)) if kids[j].find('.//' + W + 'sectPr') is not None] or [len(kids) - 1])
            return kids[j_] if kids[j_].tag == W + 'sectPr' else kids[j_].find('.//' + W + 'sectPr')
        for u, (idn, sec, labs) in enumerate(uniq):
            fn = f"frag_r{ri}_{u+1}.docx"
            if sec.get('pdf'):
                stt = pdf_frag.make_fragment(canon, sec['nums'], os.path.join(workdir, fn), head, sect=base_sect(a))
                fl.append({'file': fn, 'src': f"PDF: стр. {labs[0]}–{labs[-1]}", 'labels': labs, 'pdf': True, 'trimmed': False})
                plan['pdf_source'].append({'region': ri, 'file': fn, 'labels': labs, 'pdf_pages': sec['nums'], 'lines': stt['lines'], 'paras': stt['paras'], 'numbered': stt['numbered'],
                                           'tables': stt['tables'], 'missed': stt['missed'][:10], 'empty_pages': stt['empty_pages'], 'bookmarks': stt['bookmarks']})
                continue
            make_fragment(sec, os.path.join(workdir, fn), drop_first and u == 0, drop_last and u == len(uniq) - 1)
            fl.append({'file': fn, 'src': f"изм{sec['izm']}: {sec['name']}", 'labels': labs, 'trimmed': bool(sec.get('trimmed'))})
        reg['fragments'] = fl
        marker = f"@@REG{ri}@@"
        inserts.append({'marker': marker, 'frags': [wordrun.winpath(slug + '/' + f['file']) for f in fl]})
        edits.append(('cut', a, b, marker, reg.get('row_a'), reg.get('row_b'), set(keep_b) | set(keep_a), keep_a))
        reg['ok'] = True
        ptr = min(b, len(kids) - 1)
    # правки базы
    for e in edits:
        if e[0] in ('trim_tail', 'trim_head'): trim_para(kids[e[1]], e[2], tail=e[0] == 'trim_tail')
    for e in edits:
        if e[0] == 'merge_tail':
            src = sheet_kids(e[2])[e[3]]
            for r in plain_runs(src): kids[e[1]].append(copy.deepcopy(r))
        elif e[0] == 'merge_head':
            src = sheet_kids(e[2])[e[3]]
            ppr = kids[e[1]].find(W + 'pPr'); pos = 0 if ppr is None else list(kids[e[1]]).index(ppr) + 1
            for r in reversed(plain_runs(src)): kids[e[1]].insert(pos, copy.deepcopy(r))
    def mk_marker(marker):
        mp = etree.Element(W + 'p'); r = etree.SubElement(mp, W + 'r'); t = etree.SubElement(r, W + 't'); t.text = marker
        return mp
    for e in sorted([e for e in edits if e[0] == 'cut'], key=lambda e: (e[1], e[2], (e[4] or 0) if os.environ.get('A3_SORT', '1') == '1' else 0), reverse=True):   # одна таблица: сначала нижние по строкам регионы (A3)
        _, a, b, marker, ra, rb, keepset, keep_a = e
        mp = mk_marker(marker)
        if b == a and kids[a].tag == W + 'tbl' and ra is not None and rb is not None:
            # регион внутри одной таблицы: таблица делится на две, между ними маркер
            t1 = kids[a]; t2 = copy.deepcopy(t1)
            trs1, trs2 = t1.findall(W + 'tr'), t2.findall(W + 'tr')
            for tr in trs1[ra + 1:]: t1.remove(tr)
            for tr in trs2[:rb]: t2.remove(tr)
            t1.addnext(mp); mp.addnext(t2)
            continue
        if kids[a if a >= 0 else 0].tag == W + 'tbl' and a >= 0 and ra is not None:
            for tr in kids[a].findall(W + 'tr')[ra + 1:]: kids[a].remove(tr)
        if b < len(kids) and kids[b].tag == W + 'tbl' and rb is not None and b != a:
            for tr in kids[b].findall(W + 'tr')[:rb]: kids[b].remove(tr)
        # разделы: sectPr вырезаемых абзацев несёт колонтитулы/поля; сохраняем их, чтобы вставка осталась в своём разделе
        removed_ = [k for k in kids[a + 1:b] if k.find('.//' + W + 'sectPr') is not None]
        prev_sp = max([j for j in range(0, a + 1) if kids[j].find('.//' + W + 'sectPr') is not None] or [-1]) if a >= 0 else -1
        last_sp = copy.deepcopy(removed_[-1].find('.//' + W + 'sectPr')) if (removed_ and b - 1 > a and kids[b - 1] is removed_[-1]) else None
        first_sp = copy.deepcopy(removed_[0].find('.//' + W + 'sectPr')) if (len(removed_) > 1 or (removed_ and last_sp is None)) and a >= 0 and prev_sp < a else None
        for j_, k in enumerate(kids[a + 1:b], a + 1):
            if k.getparent() is bbody and j_ not in keepset: bbody.remove(k)
        anchor = kids[min(keep_a)] if keep_a else (kids[b] if b < len(kids) else None)   # A3: маркер перед первым сохранённым элементом «после»

        def sp_para(sp):
            q_ = etree.Element(W + 'p'); ppr_ = etree.SubElement(q_, W + 'pPr'); ppr_.append(sp); return q_
        new_els = ([sp_para(first_sp)] if first_sp is not None else []) + [mp] + ([sp_para(last_sp)] if last_sp is not None else [])
        if anchor is not None and anchor.getparent() is bbody:
            for el_ in new_els: anchor.addprevious(el_)
        else:
            pos_ = a + 1 if a >= 0 else 0
            for el_ in new_els: bbody.insert(pos_, el_); pos_ += 1
    out = os.path.join(workdir, 'base_marked.docx')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zo:
        for it in zb.infolist():
            data = zb.read(it.filename)
            if it.filename == 'word/document.xml':
                data = etree.tostring(broot, xml_declaration=True, encoding='UTF-8', standalone=True)
            zo.writestr(it, data)
    placed = {l for s_ in plan['pdf_source'] for l in s_['labels']}
    plan['pdf_unplaced'] = sorted(set(pdf_cand) - placed, key=label_key)
    for pg_ in plan['pages']:
        if pg_['label'] in pdf_cand: pg_['src'] = 'pdf' if pg_['label'] in placed else 'pdf_unplaced'
    for s_ in plan['pdf_source']:
        defect('источник страницы: PDF', 'смысл', f"регион {s_['region']}: стр. {s_['labels'][0]}–{s_['labels'][-1]}",
               f"страницы {', '.join(s_['labels'])} взяты из текстового слоя PDF-эталона (строк {s_['lines']}, абзацев {s_['paras']}, нумерованных {s_['numbered']}, таблиц {s_['tables']}); закладки {s_['bookmarks'][0]}…",
               'в Word нет источника этих страниц (ни в базе, ни в листах замены)', cat='doc', level='L1', verified_by='правило источника PDF: ' + '; '.join(sorted({pdf_cand[l] for l in s_['labels']}))[:200])
    for l in plan['pdf_unplaced']:
        defect('страница без источника в Word не вставлена из PDF', 'смысл', f"стр.{l}", pdf_cand[l] + '; регион не собран (нет якорей)', 'регион страницы не собран, PDF-фрагмент не вставлен', cat='doc', level='L1')
    plan['inserts'] = inserts
    import assy_dedupe
    plan['dedupe'] = assy_dedupe.dedupe(workdir, plan, canon, base_docx)   # A3: повторы, созданные сборкой, убираются до Word
    return plan


def trim_para(p, nkeep, tail):
    """tail=True: оставить первые nkeep key-символов абзаца; False: убрать первые nkeep key-символов."""
    ts = list(p.iter(W + 't'))
    seen = 0
    for t in ts:
        s = t.text or ''
        if tail:
            if seen >= nkeep: t.text = ''; continue
            new = ''
            for ch in s:
                if seen >= nkeep: break
                new += ch
                if key(ch): seen += 1
            t.text = new
        else:
            if seen >= nkeep: continue
            new = ''; started = False
            for ch in s:
                if seen >= nkeep: new += ch; continue
                if key(ch): seen += 1
            t.text = new


if __name__ == '__main__':
    ddir, slug = sys.argv[1], sys.argv[2]
    wd = wordrun.wsl(slug)
    pl = plan_doc(ddir, slug, wd)
    od = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.basename(os.path.abspath(ddir)))
    os.makedirs(od, exist_ok=True)
    json.dump(pl, open(os.path.join(od, 'plan.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in pl.items() if k in ('doc', 'notes', 'fatal')}, ensure_ascii=False))
    for r in pl['regions']:
        print(r['n'], r['pages'][0], r['pages'][-1], r['stamps'], 'ok' if r['ok'] else 'FAIL', r.get('removed_elems'), r.get('anchor_prev'), r.get('anchor_next'), [f['src'][:20] + str(f['labels']) for f in r.get('fragments', [])], r.get('first_para', ''), r.get('last_para', ''))
    for d in pl['defects']: print('DEF', d['type'], d['where'], d['what'][:100])
