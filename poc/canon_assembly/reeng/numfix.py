"""Живая нумерация канона: после сборки ListString каждого нумерованного абзаца должен совпасть с номером эталона.
Метод: canon_raw.docx -> выгрузка Word (ListString) -> сопоставление абзацев с строками эталона по тексту (монотонный указатель) ->
там, где номер не совпал, абзац и последующие абзацы того же списка переводятся на новый w:num (тот же abstractNum) со startOverride
на уровнях 0..ilvl; дальше счёт идёт сам (живая автонумерация Word). Номера, набранные в источнике текстом, не трогаются.
python numfix.py <slug> <эталон.pdf>   -> Temp/<slug>/canon.docx
"""
import sys, os, re, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import docx
from docx.oxml.ns import qn
from lxml import etree
import docx_numbering as dn  # ../docx_numbering.py
from pagediff import key, canon_pages, LIST_MARK
import reeng_plan as rp
import refidx
import wordrun

HERE = os.path.dirname(os.path.abspath(__file__))
NUMONLY = re.compile(r'^\d{1,3}(\.\d{1,3}){0,5}\.?$')
LET = 'abcdefghijklmnopqrstuvwxyz'


def ref_logical_lines(pdf):
    pages = canon_pages(pdf)
    head = rp.header_keys(pages)
    cstart = next((i for i, p in enumerate(pages) if any(rp.CONTENT_HEAD.match(l) for l in p['lines'])), 0)
    hl = next((l for l in pages[cstart]['lines'] if rp.CONTENT_HEAD.match(l)), '')
    lines = [l for i in range(cstart, len(pages)) for l in rp.usable_lines(pages[i], head)]
    out = []
    n = 0
    while n < len(lines):
        l = lines[n].strip()
        if NUMONLY.match(l) and n + 1 < len(lines): out.append(l + ' ' + lines[n + 1].strip()); n += 2
        else: out.append(l); n += 1
    return out, hl


def lvl_info(nb, nid, il):
    ld = nb.lvl_def(nid, il)
    if ld is None: return None
    return {'fmt': dn._val(ld, 'w:numFmt') or 'decimal', 'text': dn._val(ld, 'w:lvlText') or '', 'start': nb.start_of(nid, il)}


def pat_for(lt):
    """Регулярное выражение по lvlText (%1.%2 …) -> (regex, [уровни в порядке групп])."""
    parts = re.split(r'(%\d)', lt); rx = ''; lv = []
    for p in parts:
        m = re.fullmatch(r'%(\d)', p)
        if m: rx += r'([0-9]+|[A-Za-zА-Яа-я]{1,3})'; lv.append(int(m.group(1)) - 1)
        else: rx += re.escape(p).replace(r'\ ', r'\s*')
    return re.compile(r'^\s*' + rx + r'\s*'), lv


def parse_comp(s, fmt):
    if fmt in ('decimal', 'decimalZero'): return int(s) if s.isdigit() else None
    if fmt in ('lowerLetter', 'upperLetter'):
        s = s.lower(); return (LET.index(s[0]) + 1 + 26 * (len(s) - 1)) if s and s[0] in LET and len(set(s)) == 1 else None
    if fmt in ('russianLower', 'russianUpper'):
        s = s.lower(); return (dn.RU.index(s[0]) + 1 + len(dn.RU) * (len(s) - 1)) if s and s[0] in dn.RU and len(set(s)) == 1 else None
    return None


def norm(s): return re.sub(r'[\s­]+', '', (s or '')).rstrip('.')


def numpr_of(nb, p):
    ppr = p.find(qn('w:pPr')); nid = il = None
    if ppr is not None:
        np_ = ppr.find(qn('w:numPr'))
        if np_ is not None: nid, il = dn._val(np_, 'w:numId'), dn._val(np_, 'w:ilvl')
        sn, sl = nb.style_numpr(dn._val(ppr, 'w:pStyle'))
    else: sn, sl = nb.style_numpr(None)
    nid = nid if nid is not None else sn
    il = int(il if il is not None else (sl or 0))
    if nid in (None, '0') or nid not in nb.num: return None
    return nid, il


def set_num(p, numid, il):
    ppr = p.find(qn('w:pPr'))
    if ppr is None:
        ppr = etree.SubElement(p, qn('w:pPr')); p.remove(ppr); p.insert(0, ppr)
    np_ = ppr.find(qn('w:numPr'))
    if np_ is None:
        np_ = etree.Element(qn('w:numPr')); pos = 0
        for i, ch in enumerate(ppr):
            if etree.QName(ch).localname in rp.PPR_BEFORE_NUMPR: pos = i + 1
        ppr.insert(pos, np_)
    for ch in list(np_): np_.remove(ch)
    etree.SubElement(np_, qn('w:ilvl')).set(qn('w:val'), str(il))
    etree.SubElement(np_, qn('w:numId')).set(qn('w:val'), str(numid))


def hidden_empty(p):
    """Пустой абзац со скрытым знаком абзаца (w:vanish в rPr абзаца): Word сливает его со следующим абзацем, и номер слитого абзаца (ListString)
    берётся ИЗ ПЕРВОГО (скрытого) — собственная нумерация следующего абзаца не действует. Для выравнивания номера такой абзац убирается (A3)."""
    if p is None or p.tag != qn('w:p'): return False
    rpr = p.find(qn('w:pPr') + '/' + qn('w:rPr'))
    if rpr is None or rpr.find(qn('w:vanish')) is None: return False
    if ''.join(t.text or '' for t in p.iter(qn('w:t'))).strip(): return False
    for tag in ('w:sectPr', 'w:drawing', 'w:pict', 'w:object', 'w:fldChar', 'w:fldSimple', 'w:footnoteReference', 'w:endnoteReference', 'w:commentReference'):   # закладки не мешают: переносятся в следующий абзац
        if p.find('.//' + qn(tag)) is not None: return False
    return True


def fix(src, dump, out, pdf):
    d = docx.Document(src); nb = dn.Numbering(d)
    RI = refidx.RefIndex(pdf); hl = RI.head_line
    truth = rp.word_numbers(src, dump); truth.pop('_match', None)
    numroot = d.part.numbering_part.element
    maxid = max([int(x) for x in nb.num] + [0])
    paras = []
    for ki, el in enumerate(d.element.body.iterchildren()):
        ps = [el] if el.tag == qn('w:p') else list(el.iter(qn('w:p'))) if el.tag == qn('w:tbl') else []
        for pi, p in enumerate(ps): paras.append((ki, pi, p))
    plain = lambda p: ''.join(t.text or '' for t in p.iter(qn('w:t')))
    hk = key(hl); pstart = 0
    for n, (ki, pi, p) in enumerate(paras):
        if key(((truth.get((ki, pi)) or '') + ' ' + plain(p))) == hk or key(plain(p)) == key(rp.stripnum(hl)): pstart = n
    stats = {'numeric': 0, 'with_target': 0, 'mismatch': 0, 'chains': 0, 'unmatched': 0, 'typed_removed': 0, 'residual': 0, 'detail': [], 'unmatched_list': []}
    groups = {}; ptr = 0; lastb = None
    BUL = re.compile(r'^[\-–−‒•·▪■□◦\uf02d\uf0b7\uf0a7\u2022]')
    # 1) цели по эталону (монотонный указатель по потоку эталона)
    for n, (ki, pi, p) in enumerate(paras):
        if n < pstart: continue
        np_ = numpr_of(nb, p)
        if not np_:
            T0 = plain(p).strip()
            if re.match(r'\d+(\.\d+)+\.?\s', T0):   # номер набран текстом: абзац тоже занимает место в потоке эталона (иначе соседний абзац с тем же началом найдёт его строку)
                loc = RI.locate(key(rp.stripnum(T0)), ptr)
                if loc: ptr = loc[0] + 1
            continue
        nid, il = np_
        li = lvl_info(nb, nid, il)
        if li and li['fmt'] == 'bullet': lastb = (nid, il)
        if not li or li['fmt'] in ('bullet', 'none'): continue
        A = nb.num[nid][0]; stats['numeric'] += 1
        T = plain(p).strip(); kt = key(T); ls = truth.get((ki, pi))
        rx, lv = refidx.pat_for(li['text']); tgt = None; refpref = None
        if kt:
            loc = RI.locate(kt, ptr)
            if loc:
                pos, L = loc
                if RI.typed_at_line_start(pos, L) and re.match(r'\s*\d', T) and norm(ls):
                    set_num(p, 0, il); stats['typed_removed'] += 1; stats['detail'].append(['typed', T[:40], ls]); ptr = pos + 1
                    continue
                nb_ = RI.number_before(pos, L, kt, rx)
                if nb_ is None and norm(ls):
                    # в эталоне перед текстом нет номера: автонумерацию, добавленную при вставке листа, снимаем (маркер списка — берём список-маркер документа)
                    prevl = RI.lines[L - 1][1] if L > 0 and RI.off[L] == pos else ''
                    bullet = bool(BUL.match(RI.lines[L][1])) or (bool(prevl) and len(prevl) <= 2 and bool(BUL.match(prevl)))
                    pref = RI.S[RI.off[L - 1 if (prevl and (bullet or refidx.NUMONLY.fullmatch(prevl))) else L]:pos]
                    if not pref:
                        if bullet and lastb: set_num(p, lastb[0], lastb[1]); stats['to_bullet'] = stats.get('to_bullet', 0) + 1
                        else: set_num(p, 0, il); stats['removed_no_number'] = stats.get('removed_no_number', 0) + 1
                        stats['detail'].append(['no-number-in-ref', T[:40], ls, 'bullet' if bullet else '']); ptr = pos + 1
                        continue
                if nb_:
                    m, raw, L0 = nb_; comps = {}
                    for g, lvv in zip(m.groups(), lv):
                        comps[lvv] = parse_comp(g, (lvl_info(nb, nid, lvv) or {}).get('fmt', 'decimal'))
                    if all(v is not None for v in comps.values()) and il in comps: tgt = comps; refpref = norm(m.group(0)); ptr = pos + 1
        if tgt is not None: stats['with_target'] += 1
        else: stats['unmatched'] += 1; stats['unmatched_list'].append([T[:40], ls])
        groups.setdefault(A, []).append({'p': p, 'il': il, 'nid': nid, 'li': li, 'T': T, 'tgt': tgt, 'ref': refpref, 'ls': ls, 'rx': rx, 'lv': lv})
    def parse_ls(e):
        m = e['rx'].match(e['ls'] or '')
        if not m: return None
        c = {}
        for g, lvv in zip(m.groups(), e['lv']):
            c[lvv] = parse_comp(g, (lvl_info(nb, e['nid'], lvv) or {}).get('fmt', 'decimal'))
        return c if all(v is not None for v in c.values()) else None
    import copy, random
    abstracts = {a.get(qn('w:abstractNumId')): a for a in numroot.findall(qn('w:abstractNum'))}
    state_ab = {'max': max([int(k) for k in abstracts] + [0])}
    def new_chain(A, starts):
        """Клон abstractNum A со стартовыми значениями уровней (родители показываются значением start) + новый w:num."""
        nonlocal maxid
        src = abstracts[str(A)]
        cl = copy.deepcopy(src); state_ab['max'] += 1
        cl.set(qn('w:abstractNumId'), str(state_ab['max']))
        for tag in ('w:nsid', 'w:tmpl'):
            el = cl.find(qn(tag))
            if el is not None: el.set(qn('w:val'), '%08X' % random.randint(0x10000000, 0x7FFFFFFF))
        for lvl in cl.findall(qn('w:lvl')):
            ps = lvl.find(qn('w:pStyle'))
            if ps is not None: lvl.remove(ps)
            m_ = int(lvl.get(qn('w:ilvl')))
            if m_ in starts:
                st = lvl.find(qn('w:start'))
                if st is None:
                    st = etree.Element(qn('w:start')); lvl.insert(0, st)
                st.set(qn('w:val'), str(starts[m_]))
        last = numroot.findall(qn('w:abstractNum'))[-1]
        last.addnext(cl); abstracts[str(state_ab['max'])] = cl
        maxid += 1
        num = etree.SubElement(numroot, qn('w:num')); num.set(qn('w:numId'), str(maxid))
        etree.SubElement(num, qn('w:abstractNumId')).set(qn('w:val'), str(state_ab['max']))
        stats['chains'] += 1
        return maxid
    # 2) по спискам: счёт Word + цепочки (клон abstractNum со стартами) там, где номер не совпал
    for A, ents in groups.items():
        mode, numid, cur, virgin = 'orig', None, {}, set()
        for e in ents:
            il = e['il']
            if mode == 'orig':
                pr = parse_ls(e)
                pred = dict(pr) if pr is not None else None
                if pred is None:
                    c = dict(cur); c[il] = c[il] + 1 if il in c else e['li']['start']; pred = {il: c[il]}
                nv = virgin
            else:
                c = dict(cur); nv = set(virgin)
                if il in nv: c[il] = (lvl_info(nb, e['nid'], il) or {}).get('start', 1) if False else cstart.get(il, 1); nv.discard(il)
                else: c[il] = c[il] + 1 if il in c else e['li']['start']
                for m_ in [k for k in c if k > il]: del c[m_]
                pred = dict(c)
            tgt = e['tgt']
            diff = [k for k, v in (tgt or {}).items() if pred.get(k) != v]
            if tgt and diff:
                stats['mismatch'] += 1; stats['detail'].append(['mismatch', e['T'][:40], e['ls'], e['ref']])
                pv = e['p'].getprevious()
                while e['T'] and hidden_empty(pv):   # Word показывает номер скрытого пустого абзаца, а не этого: убираем скрытые (A3), закладки (_Toc…) переносятся в этот абзац
                    ppr_ = e['p'].find(qn('w:pPr')); pos_ = 0 if ppr_ is None else list(e['p']).index(ppr_) + 1
                    for bm in [c for c in pv if c.tag in (qn('w:bookmarkStart'), qn('w:bookmarkEnd'))]:
                        e['p'].insert(pos_, bm); pos_ += 1
                    nxt_pv = pv.getprevious(); pv.getparent().remove(pv); stats['hidden_removed'] = stats.get('hidden_removed', 0) + 1
                    pv = nxt_pv
                starts = {}
                for m_ in range(il + 1):
                    starts[m_] = tgt[m_] if m_ in tgt else (cur.get(m_) if m_ in cur else (lvl_info(nb, e['nid'], m_) or {}).get('start', 1))
                numid = new_chain(A, starts); mode = 'chain'; cstart = dict(starts)
                virgin = set(range(il)); cur = dict(starts)
                for k in [k for k in cur if k > il]: del cur[k]
                set_num(e['p'], numid, il)
                continue
            if mode == 'chain': set_num(e['p'], numid, il); cur = pred; virgin = nv
            else: cur = {**cur, **pred}
    mac = numroot.find(qn('w:numIdMacAtCleanup'))
    if mac is not None: numroot.remove(mac); numroot.append(mac)
    d.save(out)
    return stats


def run(slug, pdf, maxit=int(os.environ.get('NF_MAXIT', '8'))):   # A3: 4 -> 8 (скрытые абзацы убираются по мере выравнивания, сходимость медленнее)
    wd = wordrun.wsl(slug)
    src = 'canon_raw.docx'; log = []
    import zipfile
    if 'word/numbering.xml' not in zipfile.ZipFile(os.path.join(wd, src)).namelist():   # автонумерации нет — исправлять нечего
        shutil.copy(os.path.join(wd, src), os.path.join(wd, 'canon.docx'))
        log = [{'numeric': 0, 'with_target': 0, 'mismatch': 0, 'chains': 0, 'unmatched': 0, 'typed_removed': 0, 'residual': 0, 'iteration': 0, 'skipped': 'в canon_raw.docx нет numbering.xml'}]
        json.dump(log, open(os.path.join(wd, 'numfix_log.json'), 'w')); return log
    for it in range(1, maxit + 1):
        dump = f'nf_dump{it}.txt'
        r = wordrun.run([{'op': 'dump', 'src': wordrun.winpath(f'{slug}/{src}'), 'out': wordrun.winpath(f'{slug}/{dump}')}], f'{slug}_nf{it}', 1500)
        out = f'nf_fix{it}.docx'
        st = fix(os.path.join(wd, src), os.path.join(wd, dump), os.path.join(wd, out), pdf)
        st['iteration'] = it; log.append(st); print(json.dumps({k: v for k, v in st.items() if k not in ('detail', 'unmatched_list')}))
        if os.environ.get('NF_VERBOSE'): print(json.dumps(st, ensure_ascii=False, indent=0)[:4000])
        if st['mismatch'] == 0:
            shutil.copy(os.path.join(wd, src), os.path.join(wd, 'canon.docx')); break
        src = out
    else:
        shutil.copy(os.path.join(wd, src), os.path.join(wd, 'canon.docx'))
    json.dump(log, open(os.path.join(wd, 'numfix_log.json'), 'w'))
    return log


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
