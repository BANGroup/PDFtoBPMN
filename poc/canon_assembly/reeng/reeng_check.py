"""Проверка канона против эталона. python reeng_check.py <папка документа> <slug>

Сравнение везде с номерами автонумерации (ListString Word), текстом фигур/надписей/сносок, EMF/WMF и OLE."""
import sys, os, re, json, glob, zipfile, collections, bisect
import fitz
from lxml import etree
import pagediff as pd
from pagediff import key, W, MINLEN, LIST_MARK, canon_pages, classify
import reeng_plan as rp
import wtext
import refidx
import wordrun

HEAD_RE = rp.CONTENT_HEAD
RN = re.compile(r'[0-9A-Za-zА-Яа-я]')


def norm(s): return re.sub(r'[\s­]+', '', (s or '')).rstrip('.')


def ref_logical(pages, start, head):
    lines = [(i, l.strip()) for i in range(start, len(pages)) for l in rp.usable_lines(pages[i], head)]
    out, n = [], 0
    while n < len(lines):
        i, l = lines[n]
        if refidx.NUMONLY.fullmatch(l) and n + 1 < len(lines): out.append((i, l + ' ' + lines[n + 1][1])); n += 2
        else: out.append((i, l)); n += 1
    return out


def match_rows(rows, RL):
    """Монотонное сопоставление абзацев с логическими строками эталона по тексту: [(row, j|None, prefix_key|None)]."""
    res, ptr = [], 0
    kl = [key(t) for _, t in RL]
    for r in rows:
        kt = key(r['text']); n = min(len(kt), 24)
        hit = None
        if n >= 6:
            for j in range(ptr, min(ptr + 800, len(RL))):
                pos = kl[j].find(kt[:n])
                if 0 <= pos <= 40: hit = (j, kl[j][:pos]); break
        if hit: ptr = hit[0] + 1
        res.append((r, hit[0] if hit else None, hit[1] if hit else None))
    return res


def run(ddir, slug):
    ddir = os.path.abspath(ddir); docname = os.path.basename(ddir)
    here = os.path.dirname(os.path.abspath(__file__)); od = os.environ.get('REENG_OUT') or os.path.join(here, docname)   # batch_run: каталог результатов вне репозитория
    plan = json.load(open(os.path.join(od, 'plan.json')))
    wd = wordrun.wsl(slug)
    rows_all = rp.load_rows(os.path.join(wd, 'canon_dump.txt'))
    prow = [r for r in rows_all if r['t'] in ('T', '-')]
    srow = [r for r in rows_all if r['t'] in ('S', 'F')]
    pages = canon_pages(plan['canon_pdf'])
    head = rp.header_keys(pages)
    defects = list(plan['defects'])
    explained = []
    pdf_rel = rp.rel(plan['canon_pdf'])
    def defect(typ, sev, where, what, cause, **kw):
        defects.append({'doc': docname, 'type': typ, 'severity': sev, 'where': where, 'what': what, 'cause': cause, 'cat': kw.pop('cat', 'asm'), **kw})
    # --- ключи источников: текст XML, ListString-дамп, фигуры/сноски, EMF/OLE ---
    def alltext(path):
        z = zipfile.ZipFile(path); out = []
        for part in ('word/document.xml', 'word/footnotes.xml', 'word/endnotes.xml'):
            if part in z.namelist():
                out.append(''.join(t.text or '' for t in etree.fromstring(z.read(part)).iter(W + 't')))
        return key(' '.join(out))
    def src_key(docx, dumpf):
        rows = rp.load_rows(dumpf)
        return alltext(docx) + ''.join(key(r['ls'] + ' ' + r['text']) for r in rows) + wtext.media_key(docx)
    sources = [('база', os.path.join(wd, 'base_orig.docx'), src_key(os.path.join(wd, 'base_orig.docx'), os.path.join(wd, 'base_dump.txt')))]
    for adir in sorted(glob.glob(ddir + '/amendments/*')):
        m = re.search(r'изм([\d.]+)', adir)
        if not m: continue
        for f in pd.adocx(adir):
            if classify(f) == 'sheets': sources.append((f'лист изм{int(float(m.group(1)))}', f, src_key(f, rp.dump_path_for(wd, f))))
    def where_src(k):
        w = [n for n, f, t in sources if k in t]
        return ', '.join(w[:4]) or 'нигде в Word'
    # --- эталон: содержательные страницы ---
    # двуязычный заголовок «1 ЦЕЛЬ ... / PURPOSE ...» тоже начало контента; не найдено -> явный флаг, старт с 4-й страницы, проверка идёт
    HEAD_BI = re.compile(r'^\s*1\.?\s+[А-ЯЁ][А-ЯЁ\s,\-–]+\s*/')
    head_line = None
    for hre in (HEAD_RE, HEAD_BI):
        for i, p in enumerate(pages):
            head_line = next((l for l in p['lines'] if hre.match(l)), None)
            if head_line: start = i; break
        if head_line: break
    content_start_found = head_line is not None
    if not content_start_found: start = min(4, max(len(pages) - 1, 0))
    plan['content_start_pdf_page'] = pages[start]['n']
    RL = ref_logical(pages, start, head)
    ref = []
    for i in range(start, len(pages)):
        for l in rp.usable_lines(pages[i], head):
            l2 = LIST_MARK.sub('', l)
            if len(key(l2)) >= MINLEN: ref.append((i, l2))
    Sref = ''.join(key(l) for i in range(start, len(pages)) for l in rp.usable_lines(pages[i], head))
    pageoff, o = [], 0
    for i in range(len(pages)):
        pageoff.append(o)
        if i >= start: o += sum(len(key(l)) for l in rp.usable_lines(pages[i], head))
    RI0 = refidx.RefIndex(plan['canon_pdf'])
    # --- канон: содержательная часть ---
    hk = key(head_line or '')
    cands = [] if not head_line else [j for j, r in enumerate(prow) if key(r['ls'] + ' ' + r['text']) == hk or key(r['ls'] + r['text']) == hk]
    cs = cands[-1] if cands else (next((j for j, r in enumerate(prow) if hk in key(r['ls'] + r['text'])), 0) if head_line else 0)
    crow = prow[cs:]
    canon_docx = os.path.join(wd, 'canon.docx')
    cmedia = wtext.media_key(canon_docx)
    Snum = ''.join(key(r['ls'] + ' ' + r['text']) for r in crow)
    Sextra = ''.join(key(r['text']) for r in srow) + cmedia
    Stxt = ''.join(key(r['text']) for r in crow)
    Sall = ''.join(key(r['ls'] + ' ' + r['text']) for r in prow) + Sextra
    nod = lambda s: re.sub(r'\d', '', key(s))
    Snod = re.sub(r'\d', '', Snum + Sextra)
    # a) строки эталона в каноне
    total = found = 0; via_extra = 0
    perpage = collections.defaultdict(list)
    for i, l in ref:
        total += 1; k = key(l)
        if k in Snum: found += 1; continue
        if k in Sextra: found += 1; via_extra += 1; continue
        k2 = key(rp.stripnum(l))
        if len(k2) >= MINLEN and k2 in Stxt: perpage[i].append((l, 'номер'))
        elif len(nod(l)) >= MINLEN - 4 and nod(l) in Snod: perpage[i].append((l, 'цифры'))
        else: perpage[i].append((l, 'нет'))
    ncnt = sum(1 for v in perpage.values() for l, t in v if t == 'номер')
    ndig = sum(1 for v in perpage.values() for l, t in v if t == 'цифры')
    metrics = {'content_lines_ref': total, 'found_exact': found, 'found_via_shapes_media': via_extra, 'wrong_number': ncnt, 'digits_only_diff': ndig, 'missing_text': total - found - ncnt - ndig}
    svcpage = lambda i: i < start
    _cz = zipfile.ZipFile(canon_docx); _cx = etree.fromstring(_cz.read('word/document.xml'))
    n_sup = len(_cx.xpath('.//w:vertAlign[@w:val="superscript"]', namespaces={'w': W[1:-1]})) + len(_cx.findall('.//' + W + 'footnoteReference'))
    metrics['superscript_runs_and_footnote_refs_in_canon'] = n_sup
    metrics['paragraphs_numId0_in_canon'] = len(_cx.xpath('.//w:numPr/w:numId[@w:val="0"]', namespaces={'w': W[1:-1]}))   # автонумерация снята (номер набран текстом в источнике или отсутствует в эталоне); напечатанных номеров сборка не добавляет
    metrics['frozen_numbers_added_by_assembly'] = 0
    z0 = {'typed_number_in_text_and_found_verbatim_in_source': 0, 'auto_number_removed_no_number_in_ref': 0, 'unverified': []}
    for p0 in _cx.xpath('.//w:p[w:pPr/w:numPr/w:numId[@w:val="0"]]', namespaces={'w': W[1:-1]}):
        t0 = ''.join(t.text or '' for t in p0.iter(W + 't')).strip()
        if rp.NUM.match(t0 + ' '):
            k0 = key(t0)
            if any(k0 in t_ for _, _, t_ in sources): z0['typed_number_in_text_and_found_verbatim_in_source'] += 1
            else: z0['unverified'].append(t0[:60])
        else: z0['auto_number_removed_no_number_in_ref'] += 1
    metrics['numId0_breakdown'] = z0
    n_expl_digits = 0
    for i, v in perpage.items():
        p = pages[i]; lab = p['label'] or f"pdf{p['n']}"
        srcs = [x['src'] for r in plan['regions'] if lab in r['pages'] for x in r.get('fragments', [])]
        nn = [l for l, t in v if t == 'номер']; nt = [l for l, t in v if t == 'нет']; nd_ = [l for l, t in v if t == 'цифры']
        if nd_ and n_sup > 0:
            for l in nd_:
                explained.append({'type': 'строка эталона = строка канона без цифр: надстрочный индекс сноски склеен в текстовом слое PDF', 'text': l[:100], 'ref_page': lab, 'proof': f'равенство key после удаления цифр (по содержательной части канона, без оглавления); в canon.docx {n_sup} надстрочных прогонов/ссылок на сноски'})
            n_expl_digits += len(nd_); nd_ = []
        if nd_:
            defect('строка эталона: отличие только в цифрах', 'косметика', f"стр.{lab} (pdf {p['n']})", 'эталон: ' + ' | '.join(l[:70] for l in nd_[:3]), 'надстрочные индексы сносок/склейка цифр в текстовом слое PDF', pdf_page=p['n'], sources=srcs, lines=len(nd_))
        if nn:
            defect('номер пункта в каноне ≠ эталон', 'смысл', f"стр.{lab}", '; '.join(f"эталон «{l[:70]}»" for l in nn[:3]) + (f" (+{len(nn)-3})" if len(nn) > 3 else ''), 'ListString канона ≠ номеру эталона (см. numfix_log)', pdf_page=p['n'], sources=srcs, lines=len(nn))
        if nt:
            nowhere = [l for l in nt if where_src(key(l)) == 'нигде в Word' and where_src(key(rp.stripnum(l))) == 'нигде в Word']
            if nowhere:
                defect('строка эталона отсутствует во всех Word-файлах документа', 'смысл' if any(len(re.findall(r'[A-Za-zА-Яа-я]', l)) >= 6 for l in nowhere) else 'косметика', f"стр.{lab} (pdf {p['n']})", f"{len(nowhere)} строк нет ни в базе, ни в листах (проверены: текст XML, ListString, фигуры, сноски, EMF/WMF, OLE): " + ' | '.join(l[:70] for l in nowhere[:3]), 'текст эталона отсутствует во всех Word-источниках',
                       cat='doc', quote=[{'file': pdf_rel, 'text': l} for l in nowhere[:3]], level='L1', verified_by='key строки не найден в XML/ListString-дампе/фигурах/сносках/EMF/OLE ни базы, ни листов', pdf_page=p['n'])
                nt = [l for l in nt if l not in nowhere]
            if nt:
                defect('строка эталона отсутствует в каноне', 'смысл' if any(len(key(l)) >= 25 for l in nt) else 'косметика', f"стр.{lab} (pdf {p['n']})",
                       'эталон: ' + ' | '.join(l[:70] for l in nt[:3]) + (f" (+{len(nt)-3})" if len(nt) > 3 else '') + f"; первая строка есть в: {where_src(key(nt[0]))}", 'текст не попал в канон', pdf_page=p['n'], sources=srcs, lines=len(nt))
    # b) абзацы канона, которых нет в эталоне
    ref_media_pages = {i for i in range(start, len(pages)) if pages[i] is not None}
    doc = fitz.open(plan['canon_pdf'])
    def page_graphics(i):
        try: return len(doc[i].get_images()) > 0 or len(doc[i].get_drawings()) >= 5
        except Exception: return False
    def ref_page_of(key_text):
        pos = Sref.find(key_text)
        if pos < 0: return None
        return bisect.bisect_right(pageoff, pos + pageoff[start]) - 1 if False else max(i for i in range(start, len(pages)) if pageoff[i] <= pos + pageoff[start])
    starts = [r['start'] for r in prow]
    extra = []; renum = 0; scheme = 0
    for j, r in enumerate(crow):
        k = key(r['text'])
        if len(k) >= 20 and k not in Sref and key(r['ls'] + ' ' + r['text']) not in Sref:
            k2 = key(rp.stripnum(r['text']))
            if len(k2) >= 20 and k2 in Sref: renum += 1; continue
            extra.append((j, r))
    # текст фигур/надписей: не «лишний», если рядом на странице эталона рисунок
    for r in srow:
        if r['t'] != 'S': continue
        k = key(r['text'])
        if len(k) < 12 or k in Sref: continue
        idx = bisect.bisect_right(starts, r['start']) - 1 if r['start'] >= 0 else -1
        pg = None
        for q in range(idx, -1, -1):
            kq = key(prow[q]['text'])
            if len(kq) >= 12 and kq in Sref:
                pos = Sref.find(kq); pg = max(i for i in range(start, len(pages)) if pageoff[i] <= pos + pageoff[start]); break
        ok = pg is not None and any(page_graphics(x) for x in (pg, pg + 1) if x < len(pages))
        if ok: scheme += 1; explained.append({'type': 'текст схемы в Word, в PDF — графика', 'text': r['text'][:100], 'ref_page': pages[pg]['label'], 'proof': 'fitz get_images/get_drawings на странице эталона рядом'})
        else:
            extra.append((None, dict(r, tbl=False, ls='')))
    metrics['canon_paragraphs_not_in_ref'] = len(extra); metrics['canon_paragraphs_renumbered'] = renum; metrics['scheme_text_in_word_graphic_in_pdf'] = scheme
    numat, lastnum = {}, ''
    for j, r in enumerate(crow):
        if r['ls']: lastnum = r['ls']
        numat[j] = lastnum
    for j, r in extra:
        k = key(r['text'])
        typo = next((cut for cut in (1, 2, 3) if len(k[cut:]) >= 20 and k[cut:] in Sref), None)
        sf = next((f for n_, f, t_ in sources[1:] if k in t_), None)
        if typo and sf:
            defect('лист замены: посторонние символы в начале абзаца', 'косметика', f"абзац Word №{r['i']}", f"в листе «{os.path.basename(sf)}» абзац начинается с лишних символов «{r['text'][:typo]}»: «{r['text'][:60]}»; в эталоне текст без них", 'опечатка в листе замены', cat='doc',
                   quote=[{'file': rp.rel(sf), 'text': r['text'][:40]}], level='L1', verified_by='key абзаца найден в листе (XML/ListString), key без первых символов найден в эталоне', files=[rp.rel(sf)])
            continue
        srcs_ = [(n_, f_) for n_, f_, t_ in sources if k in t_]
        if srcs_:
            n_, f_ = srcs_[0]
            fpath = plan['base_src'] if n_ == 'база' else f_
            kp = k[:24]
            ref_line = None
            if kp in Sref:
                pos = Sref.find(kp); L = bisect.bisect_right(RI0.off, pos) - 1
                ref_line = RI0.lines[L][1]
            sev = 'смысл' if len(k) >= 40 else 'косметика'
            if True:
                pass
            if True:
                defect('текст есть в Word-источнике, в эталоне отсутствует', sev, f"абзац Word №{r['i']}" + (', таблица' if r['t'] == 'T' else ''), f"Word ({n_}): «{r['text'][:110]}»" + (f"; начало (24 знака) встречается в эталоне в другом месте: «{ref_line[:60]}»" if ref_line else ''), 'абзац присутствует в источнике (база/лист замены), в текстовом слое эталона его целиком нет', cat='doc',
                       quote=[{'file': rp.rel(fpath), 'text': r['text'][:70]}], level='L1', verified_by='точный поиск key абзаца во всех страницах содержательной части эталона (шапки страниц вырезаны): не найден; в источнике найден точным вхождением key', files=[rp.rel(fpath)])
            continue
        defect('абзац канона отсутствует в эталоне', 'смысл' if len(k) >= 40 else 'косметика', f"после пункта {numat.get(j) or '?'} (абзац Word №{r['i']}{', таблица' if r['t'] == 'T' else ''})",
               f"канон: «{(r['ls'] + ' ' + r['text'])[:140]}»; есть в: {where_src(k)}", 'лишний/устаревший текст (источник не определён)', canon_par=r['i'])
    # c) дубли
    seen = set(); ndup = 0
    cnt = collections.Counter(key(r['text']) for r in crow if len(key(r['text'])) >= 25)
    for j, r in enumerate(crow):
        k = key(r['text'])
        if len(k) >= 25 and cnt[k] > 1 and k not in seen:
            seen.add(k); rc = Sref.count(k[:24])   # в эталоне абзац может быть разорван шапкой страницы: считаем по началу
            if cnt[k] > rc and rc <= 1:
                ndup += 1
                defect('дубль текста в каноне', 'граф', f"после пункта {numat.get(j) or '?'} (абзац Word №{r['i']})", f"«{r['text'][:110]}» в каноне {cnt[k]} раз, в эталоне {rc}", 'дубль на стыке региона/остаток базы', canon_par=r['i'])
    metrics['duplicates'] = ndup
    # d) живая нумерация: ListString каждого нумерованного абзаца = номер в эталоне (монотонный поиск по потоку эталона)
    RI = RI0
    def ref_prefix(T, frm):
        loc = RI.locate(key(T), frm)
        if not loc: return None
        pos, L = loc
        L0 = L - 1 if L > 0 and refidx.NUMONLY.fullmatch(RI.lines[L - 1][1]) and RI.off[L] == pos else L
        return pos, L, RI.S[RI.off[L0]:pos], RI.lines[L0:L + 1]
    numbered = [r for r in crow if RN.search(r['ls']) and key(r['text'])]
    ok = bad = nomatch = 0; ptr = 0
    for r in numbered:
        rr = ref_prefix(r['text'], ptr)
        if not rr: nomatch += 1; continue
        pos, L, pref, ll = rr; ptr = pos + 1
        if pref == key(r['ls']): ok += 1
        else:
            bad += 1
            defect('нумерация канона: ListString ≠ номеру эталона', 'смысл', f"абзац Word №{r['i']}", f"канон: «{r['ls']} {r['text'][:60]}»; эталон: «{' '.join(t for _, t in ll)[:80]}»", 'живая нумерация не совпала (numfix)', canon_par=r['i'])
    metrics['numbering'] = {'numbered_paragraphs': len(numbered), 'equal_to_ref': ok, 'differ': bad, 'not_matched_to_ref_text': nomatch}
    # нумерация базы vs эталон на нештампованных страницах (дефект документа)
    brows = [r for r in rp.load_rows(os.path.join(wd, 'base_dump.txt')) if r['t'] in ('T', '-')]
    bnum = [r for r in brows if RN.search(r['ls']) and key(r['text'])]
    base_rel = rp.rel(plan['base_src'])
    cntbase = collections.Counter(key(r['text'])[:24] for r in bnum)
    nbd = 0; ptr = 0
    for r in bnum:
        rr = ref_prefix(r['text'], ptr)
        if not rr: continue
        pos, L, pref, ll = rr; ptr = pos + 1
        if pref == key(r['ls']): continue
        pgi = RI.lines[L][0]
        if plan['pages'][pgi]['eff_stamp'] != 0: continue
        kt24 = key(r['text'])[:24]
        if cntbase[kt24] != 1 or RI.S.count(kt24) != 1: continue
        nbd += 1
        defect('нумерация: база ≠ эталон (страница без штампа)', 'смысл', f"стр.{pages[pgi]['label']}", f"эталон «{' '.join(t for _, t in ll)[:80]}»; база (ListString Word): «{r['ls']} {r['text'][:70]}»", 'номер пункта в базе Word отличается от эталона на странице без штампа', cat='doc',
               quote=[{'file': pdf_rel, 'text': ll[-1][1][:100]}, {'file': base_rel, 'text': r['text'][:100]}], level='L1', verified_by='ListString базы (Word) vs префикс перед текстом в эталоне; текст один раз в базе и один раз в эталоне', sources=[base_rel])
    metrics['base_numbering_differs_from_ref'] = nbd
    # f) цепочка (метки листов — после argmax)
    info = plan.get('izm_info', {})
    stamped = {pg['label']: pg['stamp'] for pg in plan['pages'] if pg['label']}
    latest = {}
    for k in sorted(info, key=int):
        for lab in info[k]['labels']: latest[lab] = int(k)
    ks = sorted(int(k) for k in info)
    gaps = [k for k in range(1, (ks[-1] if ks else 0) + 1) if k not in ks]
    if gaps: defect('цепочка: нет изменения', 'граф', 'амендменты', f"нет папок изменений: {gaps}", 'пустая карточка Lotus / нет вложений (GAP)')
    idx_of = {p['label']: i for i, p in enumerate(pages) if p['label']}
    for k in sorted(info, key=int):
        inf = info[k]; kk = int(k)
        pl, lb = set(inf['plist']), set(inf['labels'])
        q = [{'file': inf['changelog'], 'text': inf['pline']}] if inf['changelog'] and inf['pline'] else []
        excl = []
        for m_ in re.finditer(r'страниц\w*\s+([^()]*?)\s*исключить', inf['pline'] or '', re.I):
            for a_, b_ in re.findall(r'(\d+\s*[а-я]?)\s*[–-]\s*(\d+\s*[а-я]?)', m_.group(1)): excl.append((a_.replace(' ', ''), b_.replace(' ', '')))
            for a_ in re.findall(r'\b(\d+[а-я]?)\b', re.sub(r'(\d+\s*[а-я]?)\s*[–-]\s*(\d+\s*[а-я]?)', ' ', m_.group(1))): excl.append((a_, a_))
        miss = sorted((l for l in pl - lb if not any(rp.label_key(a_) <= rp.label_key(l) <= rp.label_key(b_) for a_, b_ in excl) and not any(rp.label_key(x) < rp.label_key(l) for x in lb)), key=rp.label_key)
        svc = lambda l: l in idx_of and idx_of[l] < start
        if miss:
            defect('цепочка: страница в протоколе, листа нет', 'косметика' if all(svc(l) for l in miss) else 'смысл', f"изм{kk}", f"протокол называет страницы {miss}, разделов листов замены с такой меткой нет (после argmax по содержимому)", 'нет листа замены / вложение потеряно / протокол называет страницу, которой нет в листе',
                   cat='doc', quote=q, level='L1', verified_by='перечень протокола vs метки разделов листов после argmax (ListString, EMF/OLE учтены)', files=[inf['changelog']] if inf['changelog'] else [])
        extra_l = sorted(lb - pl, key=rp.label_key)
        if extra_l and pl:
            defect('цепочка: лист есть, в протоколе нет', 'косметика', f"изм{kk}", f"страницы {extra_l}", 'протокол неполон', cat='doc', quote=q, level='L1', verified_by='перечень протокола vs метки листов', files=[inf['changelog']] if inf['changelog'] else [])
        bad = [l for l in sorted(lb, key=rp.label_key) if latest.get(l) == kk and stamped.get(l) != kk and l in stamped and l not in plan.get('override_labels', [])]
        if bad:
            qq = list(q)
            for l in bad[:2]:
                pg = pages[idx_of[l]]
                qq += [{'file': pdf_rel, 'text': x} for x in pg['lines'] if re.search(r'Стр\.?\s*/?\s*(page)?\s*\d', x)][:1]
            defect('цепочка: последний лист не отражён штампом эталона', 'косметика' if all(svc(l) for l in bad) else 'смысл', f"изм{kk}", f"страницы {bad}: последний лист замены — изм{kk}, штамп эталона другой ({[stamped.get(l) for l in bad]})", 'штамп ≠ последний лист', cat='doc', quote=qq, level='L1', verified_by='метка раздела листа (колонтитул, argmax) и штамп страницы эталона')
    # служебные страницы (отдельно)
    svc_l = [(i, l) for i in range(0, start) for l in rp.usable_lines(pages[i], head) if len(key(l)) >= MINLEN]
    sf = sum(1 for i, l in svc_l if key(l) in Sall or key(rp.stripnum(l)) in Sall)
    toc = lambda l: bool(re.search(r'[.…]{4,}', l))
    svc_n = [(i, l) for i, l in svc_l if not toc(l)]
    sfn = sum(1 for i, l in svc_n if key(l) in Sall or key(rp.stripnum(l)) in Sall)
    nf_ = [l for i, l in svc_n if not (key(l) in Sall or key(rp.stripnum(l)) in Sall)]
    metrics['service_lines'] = {'ref': len(svc_l), 'found': sf, 'non_toc_ref': len(svc_n), 'non_toc_found': sfn, 'non_toc_missing_examples': [l[:60] for l in nf_[:8]]}
    metrics['content_start_found'] = content_start_found
    metrics['pages_total'] = len(pages); metrics['pages_content'] = len(pages) - start
    metrics['regions'] = len(plan['regions']); metrics['regions_ok'] = sum(1 for r in plan['regions'] if r.get('ok'))
    metrics['pct_lines'] = round(100 * found / max(total, 1), 2)
    metrics['pct_lines_with_number_only_diff'] = round(100 * (found + ncnt + ndig) / max(total, 1), 2)
    metrics['digits_only_explained_by_superscripts'] = n_expl_digits
    nf = os.path.join(wd, 'numfix_log.json')
    metrics['numfix'] = json.load(open(nf)) if os.path.exists(nf) else None
    metrics['defects'] = dict(collections.Counter(d['severity'] for d in defects))
    json.dump({'metrics': metrics, 'defects': defects, 'explained': explained}, open(os.path.join(od, 'check.json'), 'w'), ensure_ascii=False, indent=1)
    return metrics, defects


if __name__ == '__main__':
    m, d = run(sys.argv[1], sys.argv[2])
    print(json.dumps(m, ensure_ascii=False, indent=1))
    for x in d[:80]: print(x['severity'], '|', x['type'], '|', x['where'], '|', x['what'][:160])
