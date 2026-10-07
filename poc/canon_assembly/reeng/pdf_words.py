"""Расхождение по сути (A2, круг 3, решение human: канон = утверждённый PDF): абзац канона отличается от абзаца эталона 1–3 словами
(«службы качества» ↔ «управления качества») -> слова канона заменяются словами PDF (правка внутри абзаца: формат, номер, стиль сохраняются),
закладка PDF_src_p<стр>_w<n>. Абзацы сопоставляются по якорям (начало/конец абзаца, 24 знака key) — только однозначные пары.
patch_words(sd, od, ref_pdf, srcs) правит od/canon.docx, пересчитывает canon_text.txt и verify.json; отчёт od/pdf_words.json.
"""
import os, re, sys, json, difflib, unicodedata, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import docx
from docx.oxml.ns import qn
import pagediff as P
import pdf_frag as F
import pdf_lines as L

CLEAN = re.compile(r'^[А-Яа-яЁёA-Za-z«»"()\-–—.,;:!?/]+$')
MAX_WORDS = 3
MAX_REPL = 3


def pdf_paragraphs(GL):
    """Абзацы эталона по страницам (геометрия pdf_frag), абзац, оборванный границей страницы, склеивается со следующей страницей."""
    out = []; i = 0
    while i < len(GL):
        j = i
        while j < len(GL) and GL[j]['label'] == GL[i]['label'] and GL[j]['pn'] == GL[i]['pn']: j += 1
        for q in F.build_paras(F.merge_visual([dict(x) for x in GL[i:j]])):
            out.append({'t': q['t'].strip(), 'kind': q['kind'], 'label': GL[i]['label'], 'pn': GL[i]['pn'], 'first_page_para': not out or out[-1]['pn'] != GL[i]['pn'] and q is None})
        i = j
    # межстраничные продолжения: предыдущий абзац без конца предложения + следующий без маркера на новой странице
    res = []
    for q in out:
        if res and res[-1]['pn'] != q['pn'] and not q['kind'] and not F.TERM.search(res[-1]['t']) and q is next(o for o in out if o["pn"] == q["pn"]):
            res[-1]['t'] += ' ' + q['t']; continue
        res.append(dict(q))
    return res


def _cstrip(t):
    m = F.marker(t, False)
    return (m[2], len(t) - len(m[2])) if m else (t, 0)


def toks_of(s, shift=0):
    return [(m.start() + shift, m.end() + shift, m.group()) for m in re.finditer(r'\S+', s)]


def _script(t):
    cyr = len(re.findall(r'[А-Яа-яЁё]', t)); lat = len(re.findall(r'[A-Za-z]', t))
    return 'cyr' if cyr >= lat else 'lat'


def plan_edits(ctext, ptext, next_text='', known=None):
    """-> (ops, ratio) | None. ops: [(i1,i2,j1,j2,tag)] над словами canon (i) и PDF (j); None — расхождение слишком большое/неподходящее."""
    c = [(a, b, w, L.nk(w)) for a, b, w in toks_of(ctext)]
    p = [(w, L.nk(w)) for w in ptext.split()]
    c = [x for x in c if x[3]]; p = [x for x in p if x[1]]
    if len(c) < 5 or len(p) < 5: return None
    sm = difflib.SequenceMatcher(None, [x[3] for x in c], [x[1] for x in p], autojunk=False)
    ratio = sm.ratio()
    ops = [o for o in sm.get_opcodes() if o[0] != 'equal']
    if not ops or ratio < 0.85: return None
    keep = []
    for o in ops:
        tag, i1, i2, j1, j2 = o
        if tag == 'replace':
            ck = [x[3] for x in c[i1:i2]]; pk = [x[1] for x in p[j1:j2]]
            if len(ck) > MAX_REPL or len(pk) > MAX_REPL: return None
            if any(a.startswith(b) or b.startswith(a) for a in ck for b in pk): return None   # обрезанное/удлинённое слово (перенос строки PDF)
            if _script(' '.join(x[2] for x in c[i1:i2])) != _script(' '.join(x[0] for x in p[j1:j2])): return None   # другой язык: сдвиг колонок RU/EN
            if i1 == 0 and c[i1][2][:1].isupper() and p[j1][0][:1].islower(): return None          # начало абзаца PDF — продолжение с прошлой страницы
            if known is not None and any(x[1] not in known for x in p[j1:j2]): return None         # слова нет нигде в каноне: ошибка текстового слоя PDF
        elif tag == 'insert' and (i1 == len(c)) and F.TERM.search(ptext) and j2 - j1 <= MAX_WORDS \
                and not (next_text and L.nk(next_text).startswith(''.join(x[1] for x in p[j1:j2])[:12])) and i1 > 0:
            pass    # недостающий конец законченного абзаца PDF («…при перевозке» → «…при перевозке багажа.»)
        else:
            return None   # вставки/удаления внутри абзаца: строки PDF теряют слова на переносах/колонках — ненадёжно
        keep.append(o)
    if not keep or len(keep) > 3: return None
    for tag, i1, i2, j1, j2 in keep:
        for w in [x[2] for x in c[i1:i2]] + [x[0] for x in p[j1:j2]]:
            if not CLEAN.match(w) or P.garbage(w): return None
    return [(c[i1][0] if i1 < len(c) else c[-1][1], c[i2 - 1][1] if i2 > i1 else (c[i1][0] if i1 < len(c) else c[-1][1]), ' '.join(x[0] for x in p[j1:j2]), tag, ' '.join(x[2] for x in c[i1:i2]))
            for tag, i1, i2, j1, j2 in keep], ratio


def apply_words(d, ref_pdf, skip=frozenset()):
    """-> отчёт [{'label','before','after','ops'}]; d правится на месте."""
    cn = L.Canon(d)
    GL = L.build_lines(ref_pdf)
    pps = pdf_paragraphs(GL)
    lists = F.Lists(d)
    pre, suf = {}, {}
    cs = []
    for i, t in enumerate(cn.texts):
        s, sh = _cstrip(t); k = L.nk(s); cs.append((s, sh, k))
        if len(k) >= 40: pre.setdefault(k[:24], []).append(i); suf.setdefault(k[-24:], []).append(i)
    known = {L.nk(w) for t in cn.texts for w in t.split()}
    pkeys = [L.nk(q['t']) for q in pps]
    pdf_stream = ''.join(L.nk(g['t']) for g in GL)
    raw_stream = ''.join(L.nk(l) for pg in P.canon_pages(ref_pdf) for l in pg['lines'])   # включая оглавление и колонтитулы
    exact = set(pkeys)
    rep = []; bid = max([int(x.get(qn('w:id'))) for x in d.element.iter(L.W + 'bookmarkStart') if (x.get(qn('w:id')) or '').isdigit()] + [9000]); n = 0
    done = set()
    for q, pk in zip(pps, pkeys):
        if len(pk) < 40 or pk in exact and any(cs[i][2] == pk for i in pre.get(pk[:24], [])): continue
        cand = set(pre.get(pk[:24], [])) | set(suf.get(pk[-24:], []))
        viable = []
        for i in cand:
            if i in done or i in skip: continue
            s_, sh_, ck_ = cs[i]
            if ck_ == pk or ck_ in exact: continue          # канон-абзац уже точно совпадает с другим абзацем эталона
            r = plan_edits(s_, q['t'], _cstrip(cn.texts[i + 1])[0] if i + 1 < len(cn.texts) else '', known)
            if r: viable.append((r[1], i, r))
        if not viable: continue
        viable.sort(key=lambda x: -x[0])
        if len(viable) > 1 and viable[0][0] - viable[1][0] < 0.03: continue
        ratio0, i, r = viable[0]
        s, sh, ck = cs[i]
        ops, ratio = r
        # проверка по потоку строк эталона: исправленный абзац должен лежать в нём целиком (подряд), исходный — нет
        new_s = s
        for a_, b_, nw_, tg_, _o in sorted(ops, key=lambda o: -o[0]):
            if tg_ == 'insert': new_s = new_s[:a_] + (' ' if a_ and not new_s[a_ - 1].isspace() else '') + nw_ + new_s[a_:]
            else: new_s = new_s[:a_] + nw_ + new_s[b_:]
        if L.nk(new_s) not in pdf_stream or ck in raw_stream: continue
        p = cn.paras[i]; before = cn.texts[i]; ok = True
        for a, b, new, tag, old in sorted(ops, key=lambda o: -o[0]):
            a += sh; b += sh
            if tag == 'delete':
                e = b + (1 if b < len(before) and before[b] == ' ' else 0)
                ok, _ = L.delete_chars(p, a, e)
            elif tag == 'insert':
                bid += 1; ok = L.inline_insert(p, a, new, bid, f"PDF_src_p{q['pn']}_w{bid - 9000}")
            else:
                ok, _ = L.delete_chars(p, a, b)
                if ok: bid += 1; ok = L.inline_insert(p, a, new, bid, f"PDF_src_p{q['pn']}_w{bid - 9000}")
            if not ok: break
        if ok:
            typed = re.match(r'\s*(\d{1,3}(?:\.\d{1,3}){1,7})', before)
            lv = L._liveify(p, lists)
            done.add(i); n += 1
            rep.append({'i': i, 'typed': typed.group(1) if (typed and lv) else None, 'p': p, 'label': q['label'], 'pdf_page': q['pn'], 'ratio': round(ratio, 3), 'ops': [{'tag': t, 'было': o, 'стало': nw} for _, _, nw, t, o in ops], 'before': before[:300], 'after_pdf': q['t'][:300]})
        else: rep.append({'label': q['label'], 'status': 'не применено: граница прогона', 'before': before[:200]})
    return rep


def _liststrings(d):
    import pynum as pn
    nb = pn.Numbering(d.part.numbering_part.element, d.styles.element)
    return {el: ls for k, el, ls in pn.number_all(d.element, nb) if k == 'p'}


def patch_words(sd, od, ref_pdf, srcs=None):
    import py_numfix, pynum, verify_canon, ooxml_check
    cd, ct = os.path.join(od, 'canon.docx'), os.path.join(od, 'canon_text.txt')
    srcs = srcs or L.sources_of(sd)
    try: v0 = json.load(open(os.path.join(od, 'verify.json'), encoding='utf-8')); vb = {k: v0[k] for k in ('lines', 'missing', 'numbered_bad', 'duplicates', 'frozen_numbers')}
    except Exception: vb = None
    skip = set(); reverted = []
    for attempt in range(3):
        d = docx.Document(cd)
        rep = apply_words(d, ref_pdf, skip)
        applied = [r for r in rep if 'ops' in r]
        if not applied: break
        py_numfix.run(d, ref_pdf)
        ls = _liststrings(d)
        bad = [r for r in applied if r['typed'] and re.sub(r'[\s.]', '', ls.get(r['p']) or '') != re.sub(r'[\s.]', '', r['typed'])]
        if not bad: break
        skip |= {r['i'] for r in bad}; reverted += [{'num': r['typed'], 'before': r['before'][:80]} for r in bad]   # numfix не выровнял номер -> правку этого абзаца откатываем
    else: applied = []
    for r in rep: r.pop('p', None)
    res = {'replaced': len(applied), 'report': rep, 'verify_before': vb, 'reverted_numbering': reverted}
    if applied:
        shutil.copy(cd, os.path.join(od, 'canon_before_pdfwords.docx'))
        d.save(cd)
        res['ooxml_problems'] = ooxml_check.check(cd)
        pynum.dump(cd, ct)
        v = verify_canon.verify(sd, ct, cd, srcs)
        json.dump(v, open(os.path.join(od, 'verify.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        res['verify'] = {k: v[k] for k in ('lines', 'missing', 'numbered', 'numbered_bad', 'duplicates', 'frozen_numbers', 'live_numbering', 'coverage')}
    json.dump(res, open(os.path.join(od, 'pdf_words.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return res
