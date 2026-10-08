"""Поштучные правки канона (TASK-021, шаг 11.1): data/canon_reeng/patches/<doc>.json накладываются после сборки (pyengine.run_doc).

Формат файла правок (разборщик пишет руками; описание — data/canon_reeng/stepP11/notes.md):
  {"doc": "...", "files_sha": {"word/x.docx": "<sha256>", ...},   # sha всех файлов документа на момент разбора (live/src/<doc>)
   "ops": [{"op": "insert_after|insert_before|delete|replace|set_number", "anchor": "текст абзаца канона (или начало >= 30 знаков)",
            "anchor_occurrence": 1, "text": "...", "number": "7.2.5", "style_like": "anchor|prev|next", "pdf_page": 12, "reason": "...",
            "part": "part_1"}]}
Якорь ищется по pagediff.key текста абзаца (или «ListString + текст»); несколько совпадений без anchor_occurrence — операция не выполняется.
Вставленный/заменённый абзац помечается закладкой PATCH_<n> (n — номер операции в файле), формат берётся у соседнего абзаца (style_like),
номер: у соседних пунктов живая нумерация — продолжается их numId (ListString обязан совпасть с number, иначе номер набирается текстом); у набранных — набирается текстом.
py_numfix НЕ запускается; после операций сравнивается выгрузка до/после: изменение вне затронутых абзацев (текст; ListString — вне списков затронутых) = откат всего патча.

  python3 patch_ops.py --sha <doc>   # files_sha для патча
  python3 patch_ops.py --try <doc>   # наложить правки на копию live/out/<doc> в scratch, показать verify до/после и verify_extra
"""
import os, sys, re, json, glob, copy, shutil, hashlib, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
import docx
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import pagediff as P
import pdf_frag as F
import pdf_lines as PL
import pynum

W = P.W
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
PATCH_DIR = os.environ.get('CANON_PATCHES_DIR') or os.path.join(REPO, 'data/canon_reeng/patches')
LIVE = os.path.join(REPO, 'data/canon_reeng/live')
OPS = ('insert_after', 'insert_before', 'delete', 'replace', 'set_number', 'delete_hidden_before')
NUMBER = re.compile(r'^\d{1,3}(\.\d{1,3}){0,7}$')
VKEYS = ('lines', 'missing', 'numbered', 'numbered_bad', 'duplicates', 'frozen_numbers', 'live_numbering', 'coverage')


def bad(v): return v['missing'] + v['numbered_bad'] + v['duplicates'] + v['frozen_numbers']


# ---------------------------------------------------------------- файлы документа и sha
def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def doc_files_sha(sd):
    """{путь относительно sd: sha256} исходных файлов документа (без производных: __parts, главы, .docx рядом с .doc)."""
    out = {}
    for f in glob.glob(os.path.join(sd, '**', '*'), recursive=True):
        if not os.path.isfile(f): continue
        rel = os.path.relpath(f, sd)
        if rel.split(os.sep)[0] == '__parts' or os.path.basename(f) == '__главы.docx': continue
        if f.lower().endswith('.docx') and os.path.exists(f[:-1]): continue   # конвертация .doc (ensure_docx_siblings)
        out[rel] = sha256(f)
    return out


def stale_reasons(sd, patch):
    """Причины, по которым правки устарели (пусто — содержимое файлов документа то же). Сравнение по содержимому: множество (раздел, sha256);
    переименование файла (суффикс Lotus _XXXXXXXX) не изменение. Весь документ — множества равны; часть многочастного — её файлы входят в множество патча."""
    want = patch.get('files_sha') or {}
    if not want: return ['в файле правок нет files_sha']
    part = '__parts' in sd.split(os.sep)
    # часть многочастного: split_parts переносит лист замены в word/ как базу части — раздел другой, содержимое то же -> только sha
    top = (lambda rel: '') if part else (lambda rel: rel.split('/')[0].split(os.sep)[0])
    w = {(top(r), h) for r, h in want.items()}
    cur = {(top(r), h): r for r, h in doc_files_sha(sd).items()}
    why = [f'новое содержимое: {r}' for k, r in cur.items() if k not in w]
    if not part:   # весь документ: файл из правок пропал
        names = {(top(r), h): r for r, h in want.items()}
        why += [f'удалено содержимое: {r}' for k, r in names.items() if k not in cur]
    return why


def patch_path(doc): return os.path.join(PATCH_DIR, doc + '.json')


def load_patch(doc):
    p = patch_path(doc)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


# ---------------------------------------------------------------- абзацы канона
class View:
    """Абзацы канона (вне надписей) с текстом и ListString; пересоздаётся после каждой операции."""
    def __init__(self, d):
        nb = None
        try:
            nb = pynum.Numbering(d.part.numbering_part.element, d.styles.element)
        except Exception:
            nb = None
        self.paras, self.texts, self.labels = [], [], []
        if nb is not None:
            for k, el, ls in pynum.number_all(d.element, nb):
                if k == 'p': self.paras.append(el); self.labels.append(ls)
        else:
            self.paras = [p for k, p in pynum.walk_paras(d.element.find(W + 'body')) if k == 'p']; self.labels = [''] * len(self.paras)
        self.texts = [''.join(x for _, x in PL.ptext_runs(p)) for p in self.paras]
        self.keys = [P.key(t) for t in self.texts]
        self.lkeys = [P.key(l + ' ' + t) if l else k for l, t, k in zip(self.labels, self.texts, self.keys)]

    def find(self, anchor, occurrence=None):
        """-> (индекс, None) | (None, причина)."""
        ka = P.key(anchor or '')
        if not ka: return None, 'пустой якорь'
        c = [i for i in range(len(self.paras)) if self.keys[i] == ka or self.lkeys[i] == ka]
        if not c and len(ka) >= 30:
            c = [i for i in range(len(self.paras)) if self.keys[i].startswith(ka) or self.lkeys[i].startswith(ka)]
        if not c: return None, 'якорь не найден'
        if occurrence is None:
            if len(c) > 1: return None, f'якорь неоднозначен ({len(c)} совпадений), нужен anchor_occurrence'
            return c[0], None
        if not isinstance(occurrence, int) or occurrence < 1 or occurrence > len(c): return None, f'anchor_occurrence={occurrence}: совпадений {len(c)}'
        return c[occurrence - 1], None


def _next_bid(d):
    ids = [int(x.get(qn('w:id'))) for x in d.element.iter(W + 'bookmarkStart') if (x.get(qn('w:id')) or '').isdigit()]
    return max(ids + [9000]) + 1


def _bm_name(d, n):
    have = {x.get(qn('w:name')) for x in d.element.iter(W + 'bookmarkStart')}
    name = f'PATCH_{n}'
    while name in have: n += 1000; name = f'PATCH_{n}'
    return name


def _like(view, i, how):
    j = i + {'prev': -1, 'next': 1}.get(how, 0)
    if 0 <= j < len(view.paras) and view.paras[j].getparent() is view.paras[i].getparent(): return view.paras[j]
    return view.paras[i]


def _put_numpr(p, np_):
    """numPr в pPr абзаца на место по схеме (после pStyle/keepNext/... и до остальных)."""
    ppr = p.find(W + 'pPr')
    if ppr is None: ppr = OxmlElement('w:pPr'); p.insert(0, ppr)
    for e in ppr.findall(W + 'numPr'): ppr.remove(e)
    pos = 0
    for k, ch in enumerate(ppr):
        if ch.tag.split('}')[1] in ('pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl'): pos = k + 1
    ppr.insert(pos, np_)


def _inherit_list(v, i, how, p):
    """Список соседнего абзаца (numPr: numId + ilvl, живой номер или маркер) -> новый абзац p. -> True, если у образца был список."""
    np_ = _like(v, i, how).find(W + 'pPr/' + W + 'numPr')
    nid = np_.find(W + 'numId') if np_ is not None else None
    if nid is None or nid.get(qn('w:val')) == '0': return False
    _put_numpr(p, copy.deepcopy(np_)); return True


LEADNUM = re.compile(r'\s*(\d{1,3}(?:\.\d{1,3}){1,7})\.?\s+')
NUMLABEL = re.compile(r'^\d{1,3}(\.\d{1,3})*\.?$')


def _nbr(d):
    try: return pynum.Numbering(d.part.numbering_part.element, d.styles.element)
    except Exception: return None


def _ref_numbering(d, p):
    """Ближайший выше p (до 40 абзацев) пункт с номером: ('live', numId) | ('typed', None) | (None, None)."""
    v = View(d); nb = _nbr(d)
    if p not in v.paras: return None, None
    k = v.paras.index(p)
    for j in range(k - 1, max(k - 41, -1), -1):
        np_ = nb.numpr(v.paras[j]) if nb is not None else None
        if np_ and NUMLABEL.match(v.labels[j].strip() or 'x'): return 'live', np_[0]
        if LEADNUM.match(v.texts[j]): return 'typed', None
    return None, None


def _place_number(d, p, number):
    """Номер пункта в абзац p (текст без номера): у соседних пунктов живая нумерация — продолжить их numId (ListString обязан стать равным
    number, иначе номер набирается текстом); соседи с набранными номерами или их нет — номер набирается текстом (допустимо по правилам качества)."""
    kind, nid = _ref_numbering(d, p)
    if kind == 'live':
        np_ = OxmlElement('w:numPr')
        e = OxmlElement('w:ilvl'); e.set(qn('w:val'), str(number.count('.'))); np_.append(e)
        e = OxmlElement('w:numId'); e.set(qn('w:val'), str(nid)); np_.append(e)
        _put_numpr(p, np_)
        v = View(d)
        if P.key(v.labels[v.paras.index(p)]) == P.key(number): return 'живой номер, numId=' + str(nid)
        _strip_numpr(p)
    nb = _nbr(d)
    if nb is not None and nb.numpr(p): raise ValueError(f'номер {number}: стиль абзаца несёт нумерацию, набрать текстом нельзя')
    t = next((t for t, _ in PL.ptext_runs(p)), None)
    if t is None: raise ValueError('в абзаце нет текста для номера')
    t.text = number + ' ' + (t.text or ''); t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    return 'номер текстом'


def _strip_numpr(p):
    ppr = p.find(W + 'pPr')
    if ppr is not None:
        for e in ppr.findall(W + 'numPr'): ppr.remove(e)


def _replace_content(p, text, bid, name):
    like = next((r for r in p.iter(W + 'r') if r.find(W + 't') is not None), None)
    for ch in list(p):
        if ch.tag not in (W + 'pPr', W + 'bookmarkStart', W + 'bookmarkEnd'): p.remove(ch)
    r = PL._new_run(like, text); p.append(r)
    PL._bookmark(r, r, bid, name)


def _unhide(p):
    """webHidden в прогонах нового текста: Word-выгрузка (Range.Text) такой текст не отдаёт (проверено по Word-выгрузкам full2/full4), verify считает строку ненайденной."""
    for r in p.iter(W + 'r'):
        for e in r.findall(W + 'rPr/' + W + 'webHidden'): e.getparent().remove(e)


def _drop_bookmarks(p):
    """Закладки удаляемого абзаца вместе с парными концами/началами вне его (иначе висящие w:bookmarkStart/End)."""
    root = p.getroottree().getroot()
    for tag, pair in (('bookmarkStart', 'bookmarkEnd'), ('bookmarkEnd', 'bookmarkStart')):
        for b in list(p.iter(W + tag)):
            i = b.get(qn('w:id'))
            for o in root.iter(W + pair):
                if o.get(qn('w:id')) == i and o.getparent() is not None and o not in p.iter(W + pair): o.getparent().remove(o)


def _do(d, n, op):
    """Одна операция -> (bookmark|None, комментарий, затронутые абзацы, удалённые абзацы) или ValueError(причина)."""
    kind = op.get('op')
    if kind not in OPS: raise ValueError(f'неизвестная операция {kind!r}')
    num = op.get('number')
    if num is not None and not NUMBER.match(str(num)): raise ValueError(f'number {num!r}: нужен формат N.N.N')
    text = op.get('text')
    if kind in ('insert_after', 'insert_before', 'replace') and not (text or '').strip(): raise ValueError('нет text')
    if kind == 'set_number' and not num: raise ValueError('set_number без number')
    ll = op.get('list_like')
    if ll is not None:
        if kind not in ('insert_after', 'insert_before'): raise ValueError('list_like только для insert_after/insert_before')
        if ll not in ('anchor', 'prev', 'next'): raise ValueError(f'list_like {ll!r}: anchor|prev|next')
        if num: raise ValueError('list_like и number несовместимы (номер задайте одним способом)')
    v = View(d)
    i, why = v.find(op.get('anchor'), op.get('anchor_occurrence') if 'anchor_occurrence' in op else None)
    if i is None: raise ValueError(why)
    a = v.paras[i]; name = _bm_name(d, n); bid = _next_bid(d)
    if kind == 'delete':
        if a.find(W + 'pPr/' + W + 'sectPr') is not None: raise ValueError('абзац несёт разрыв раздела')
        par = a.getparent()
        if par is not None and par.tag == W + 'tc' and len(par.findall(W + 'p')) == 1: raise ValueError('единственный абзац ячейки таблицы')
        _drop_bookmarks(a); par.remove(a)
        return None, 'удалён: ' + v.texts[i][:60], [], [a]
    if kind == 'delete_hidden_before':
        nb = _nbr(d); par = a.getparent(); k = list(par).index(a); gone = []
        while k > 0:
            q = list(par)[k - 1]
            if q.tag != W + 'p' or not pynum.is_hidden_empty(q) or not (nb is not None and nb.numpr(q)): break
            if q.find(W + 'pPr/' + W + 'sectPr') is not None: break
            gone.append(q); k -= 1
        if not gone: raise ValueError('перед якорем нет скрытых пустых нумерованных абзацев')
        for q in gone:   # закладки (_Toc…) переносятся в якорь, как делает numfix
            ppr = a.find(W + 'pPr'); pos = 0 if ppr is None else list(a).index(ppr) + 1
            for bm in [c for c in q if c.tag in (W + 'bookmarkStart', W + 'bookmarkEnd')]: a.insert(pos, bm); pos += 1
            par.remove(q)
        return None, f'удалено скрытых пустых нумерованных абзацев: {len(gone)}', [a], gone
    body = (text or '').strip()
    if not num:   # номер набран в начале text: обрабатывается как number
        m = LEADNUM.match(body)
        if m and (kind != 'replace' or a.find(W + 'pPr/' + W + 'numPr') is None): num = m.group(1); body = body[m.end():].strip()
    info = kind
    backup = [copy.deepcopy(ch) for ch in a] if kind in ('replace', 'set_number') else None   # откат абзаца, если операция не дошла до конца
    p = a
    try:
        if kind in ('insert_after', 'insert_before'):
            p = PL.new_paragraph(_like(v, i, op.get('style_like', 'anchor')), body, a, kind == 'insert_after', bid, name)
            if ll and not _inherit_list(v, i, ll, p): info += ' (list_like: у образца нет списка, абзац без нумерации)'
        elif kind == 'replace':
            p = a
            if num: _strip_numpr(p)
            _replace_content(p, body, bid, name)
        else:   # set_number
            p = a
            _strip_numpr(p)
            m = LEADNUM.match(v.texts[i])
            if m and not PL.delete_chars(p, 0, m.end())[0]: raise ValueError('граница прогона: нельзя снять набранный номер')
            name = None
        if kind != 'set_number': _unhide(p)
        if num: info += '; ' + _place_number(d, p, str(num))
    except Exception:
        if backup is None:
            if p is not a and p.getparent() is not None: p.getparent().remove(p)
        else:
            for ch in list(a): a.remove(ch)
            for ch in backup: a.append(ch)
        raise
    return name, info, [p], []


def _snap(d):
    """{абзац: (abstractNumId списка|None, ListString, текст)} всего документа (numId с общим abstractNum делят счётчики) — для проверки побочных изменений."""
    nb = _nbr(d); out = {}
    if nb is None: return out
    for k, el, ls in pynum.number_all(d.element, nb):
        if k == 'p':
            np_ = nb.numpr(el)
            out[el] = (nb.num[np_[0]][0] if np_ else None, ls, ''.join(x for _, x in PL.ptext_runs(el)))
    return out


def side_effects(before, after, touched, deleted):
    """Изменения (текст или ListString) вне затронутых абзацев. ListString допускается только у абзацев тех же списков, что у затронутых."""
    lists = {after[p][0] for p in touched if p in after} | {before[p][0] for p in list(touched) + list(deleted) if p in before}
    lists.discard(None)
    free = set(touched) | set(deleted)
    out = []
    for el, (nid, ls, t) in before.items():
        if el in free: continue
        if el not in after: out.append(f'пропал абзац «{t[:40]}»'); continue
        n2, l2, t2 = after[el]
        if t2 != t: out.append(f'изменён текст «{t[:40]}» -> «{t2[:40]}»')
        elif l2 != ls and not ({nid, n2} & lists): out.append(f'изменён номер «{t[:40]}»: {ls!r} -> {l2!r}')
    return out


# ---------------------------------------------------------------- наложение
def srcs_of(od, sd):
    """Источники Word для verify_canon: база из plan.json (если файл есть) + листы замены."""
    try: pl = json.load(open(os.path.join(od, 'plan.json'), encoding='utf-8'))
    except Exception: pl = {}
    b = pl.get('base_src', '')
    if b.lower().endswith('.doc'): b += 'x'
    if not (b and os.path.exists(b)): b = next(iter(sorted(glob.glob(sd + '/word/*.docx'))), '')
    return ([b] if b else []) + sorted(glob.glob(sd + '/amendments/**/*.docx', recursive=True))


def ref_pdf_of(od, sd):
    try: r = json.load(open(os.path.join(od, 'plan.json'), encoding='utf-8')).get('canon_pdf')
    except Exception: r = None
    if r and os.path.exists(r): return r
    refs = P.ref_pdfs(sd)
    return refs[0] if refs else None


def apply(od, patch, sd, part=None, srcs=None, ref_pdf=None):
    """Правки patch -> od/canon.docx (+ canon_text.txt, verify.json, patches.json). part — 'part_N' для части многочастного документа.
    -> {'applied': [...], 'skipped': [[op, причина], ...], 'verify': {...}|None, 'ooxml_problems': [...]}. Откат при ухудшении проверки — на вызывающем."""
    import verify_canon, ooxml_check
    cd, ct = os.path.join(od, 'canon.docx'), os.path.join(od, 'canon_text.txt')
    rep = {'applied': [], 'skipped': [], 'verify': None, 'ooxml_problems': []}
    ops = []
    for n, op in enumerate(patch.get('ops') or [], 1):
        if (op.get('part') or None) == part: ops.append((n, op))
        elif part is None: rep['skipped'].append([op, f'part={op.get("part")!r}, документ не многочастный'])
        elif not op.get('part'): rep['skipped'].append([op, f'нет поля part, документ многочастный ({part})'])
    if not ops: return rep
    d = docx.Document(cd)
    before = _snap(d); touched, deleted = [], []
    for n, op in ops:
        try:
            nm, info, t_, d_ = _do(d, n, op)
            touched += t_; deleted += d_
            rep['applied'].append({'n': n, 'op': op.get('op'), 'bookmark': nm, 'info': info})
        except ValueError as e: rep['skipped'].append([op, str(e)])
        except Exception as e: rep['skipped'].append([op, f'{type(e).__name__}: {e}'[:200]])
    if rep['applied']:
        import ooxml_check as _oc
        rep['bad_href_removed'] = _oc.fix_bad_href(d)   # прежняя сборка могла оставить r:href на не-image связь
        bad_ = side_effects(before, _snap(d), touched, deleted)
        if bad_:   # правки задели то, чего не касались операции: файл не сохраняется
            why = 'побочные изменения: ' + '; '.join(bad_[:3]) + (f' (всего {len(bad_)})' if len(bad_) > 3 else '')
            done = {a_['n'] for a_ in rep['applied']}
            rep['skipped'] += [[op, why] for n_, op in ops if n_ in done]
            rep['applied'] = []; rep['side_effects'] = bad_[:30]
            json.dump(rep, open(os.path.join(od, 'patches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            return rep
    if rep['applied']:
        bak = os.path.join(od, 'canon_before_patches.docx')
        shutil.copy(cd, bak)
        old_problems = ooxml_check.check(bak)
        d.save(cd)
        rep['ooxml_problems'] = ooxml_check.check(cd)
        new_problems = [x for x in rep['ooxml_problems'] if x not in old_problems]
        if new_problems:   # правки внесли ошибку целостности (риск «Файл поврежден» в Word): откат, причина в отчёте
            shutil.copy(bak, cd)
            why = 'откат: ooxml ' + '; '.join(new_problems)[:200]
            rep['skipped'] += [[o, why] for o in [op for n_, op in ops if n_ in {a_['n'] for a_ in rep['applied']}]]
            rep['applied'] = []; rep['ooxml_rollback'] = new_problems; rep['ooxml_problems'] = old_problems
            json.dump(rep, open(os.path.join(od, 'patches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            return rep
        pynum.dump(cd, ct)
        v = verify_canon.verify(sd, ct, cd, srcs or srcs_of(od, sd))
        json.dump(v, open(os.path.join(od, 'verify.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        rep['verify'] = {k: v[k] for k in VKEYS}
    json.dump(rep, open(os.path.join(od, 'patches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return rep


# ---------------------------------------------------------------- хук pyengine.run_doc
def run_hook(sd, od, doc, srcs, ref_pdf, v, st):
    """После всех шагов сборки: правки doc из PATCH_DIR -> канон в od. sha файлов не совпал -> не накладывать (stale);
    проверка стала хуже -> откат файлов. Результат в st['patches'] = {applied, skipped, stale}; -> актуальный verify."""
    ps = st.setdefault('patches', {'applied': 0, 'skipped': 0, 'stale': False})
    patch = load_patch(doc)
    if not patch: return v
    m = re.match(r'part_\d+$', os.path.basename(os.path.normpath(od)))
    part = m.group(0) if m else None
    mine = [o for o in patch.get('ops') or [] if (o.get('part') or None) == part]
    if not mine: return v   # у этой части (документа) своих операций нет — ни наложения, ни проверки устаревания (validator 08.10)
    why = stale_reasons(sd, patch)
    if why:
        ps['stale'] = True; st['warnings'].append('правки устарели: документ изменился, нужен повторный разбор (' + '; '.join(why[:2])[:150] + ')')
        return v
    names = ('canon.docx', 'canon_text.txt', 'verify.json')
    keep = {f: open(os.path.join(od, f), 'rb').read() for f in names if os.path.exists(os.path.join(od, f))}
    def restore():
        for f, b in keep.items(): open(os.path.join(od, f), 'wb').write(b)
    try: rep = apply(od, patch, sd, part, srcs, ref_pdf)
    except Exception as e:
        restore(); st['warnings'].append(f'правки пропущены: {type(e).__name__}: {e}'[:300]); return v
    ps['skipped'] = len(rep['skipped'])
    if rep['skipped']: st['warnings'].append('правки не выполнены: %d (%s)' % (len(rep['skipped']), '; '.join(f"{o.get('op')}: {w}" for o, w in rep['skipped'][:2])[:200]))
    if not rep['applied']: return v
    v2 = rep['verify']
    if bad(v2) > bad(v):
        restore(); ps['rolled_back'] = len(rep['applied'])
        json.dump(v, open(os.path.join(od, 'verify.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        st['warnings'].append(f'правки откатаны: проверка ухудшилась ({bad(v)} -> {bad(v2)})')
        return v
    ps['applied'] = len(rep['applied'])
    if rep['ooxml_problems']: st['warnings'].append('ooxml после правок: ' + '; '.join(rep['ooxml_problems'])[:300])
    return json.load(open(os.path.join(od, 'verify.json'), encoding='utf-8'))


# ---------------------------------------------------------------- --try
def unit_dirs(doc):
    """[(метка, live/out/..., src)] — документ или его части."""
    od = os.path.join(LIVE, 'out', doc); sd = os.path.join(LIVE, 'src', doc)
    if os.path.exists(os.path.join(od, 'canon_text.txt')): return [(None, od, sd)]
    return [(os.path.basename(u), u, os.path.join(sd, '__parts', 'p' + os.path.basename(u).split('_')[1])) for u in sorted(glob.glob(od + '/part_*'))]


def try_doc(doc, scratch=None):
    import nightly_canon, verify_extra
    patch = load_patch(doc)
    if not patch: print(f'нет {patch_path(doc)}'); return 1
    scratch = scratch or os.path.join(REPO, 'data/canon_reeng/stepP11/scratch', doc)
    shutil.rmtree(scratch, ignore_errors=True)
    scratch0 = scratch.rstrip('/') + '_before'   # копия без правок: для verify_extra «до»
    shutil.rmtree(scratch0, ignore_errors=True)
    for part, od, sd in unit_dirs(doc):
        tgt = os.path.join(scratch, part) if part else scratch
        os.makedirs(tgt, exist_ok=True)
        for f in ('canon.docx', 'canon_text.txt', 'verify.json', 'plan.json'):
            if os.path.exists(os.path.join(od, f)): shutil.copy(os.path.join(od, f), tgt)
        bp = os.path.join(od, 'canon_before_patches.docx')
        if os.path.exists(bp):   # в live правки уже наложены: берём канон до правок (иначе двойное наложение)
            shutil.copy(bp, os.path.join(tgt, 'canon.docx')); pynum.dump(bp, os.path.join(tgt, 'canon_text.txt'))
            for f in ('patches.json',):
                if os.path.exists(os.path.join(tgt, f)): os.remove(os.path.join(tgt, f))
        t0 = os.path.join(scratch0, part) if part else scratch0
        shutil.copytree(tgt, t0, dirs_exist_ok=True)
        import verify_canon
        before = verify_canon.verify(sd, os.path.join(tgt, 'canon_text.txt'), os.path.join(tgt, 'canon.docx'), srcs_of(tgt, sd))   # пересчёт теми же источниками, что и «после»
        st = stale_reasons(sd, patch)
        print(f'== {doc} {part or ""}: sha {"УСТАРЕЛИ: " + "; ".join(st[:3]) if st else "совпадает"}')
        rep = apply(tgt, patch, sd, part)
        after = rep['verify'] or before
        print('applied:', json.dumps(rep['applied'], ensure_ascii=False))
        for op, why in rep['skipped']: print('SKIP:', (op.get('op'), (op.get('anchor') or '')[:50]), why)
        print('verify до   :', {k: before[k] for k in VKEYS if k != 'live_numbering'}, 'bad =', bad(before))
        print('verify после:', {k: after[k] for k in VKEYS if k != 'live_numbering'}, 'bad =', bad(after))
        if rep['ooxml_problems']: print('ooxml:', rep['ooxml_problems'])
        print('канон:', os.path.join(tgt, 'canon.docx'))
    ex0 = nightly_canon.extra_text(doc, scratch0)
    ex1 = nightly_canon.extra_text(doc, scratch)   # scratch повторяет раскладку live/out/<doc>
    print('verify_extra до/после:', ex0.get('paras_extra'), '->', ex1.get('paras_extra'), ex1.get('examples', [])[:3] if ex1.get('paras_extra') else ex1.get('error', ''))
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--try', dest='try_doc', metavar='DOC')
    ap.add_argument('--sha', metavar='DOC', help='files_sha для патча: sha256 файлов live/src/<DOC>')
    ap.add_argument('--scratch')
    a = ap.parse_args()
    if a.sha: print(json.dumps(doc_files_sha(os.path.join(LIVE, 'src', a.sha)), ensure_ascii=False, indent=1)); sys.exit(0)
    if not a.try_doc: ap.error('нужен --try DOC или --sha DOC')
    sys.exit(try_doc(a.try_doc, a.scratch))
