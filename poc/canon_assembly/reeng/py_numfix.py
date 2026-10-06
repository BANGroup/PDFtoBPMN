"""numfix без Word (пилот TASK-021, шаг 9): выравнивание живой нумерации канона с эталоном на XML.

Логика fix() из numfix.py (цели по эталону, цепочки abstractNum со стартами, снятие скрытых пустых абзацев) без изменений; ListString берётся
не из выгрузки Word, а считается pynum.Numbering по текущему дереву. Итерации (до NF_MAXIT, как в numfix.run) идут в памяти, без сохранений.
Вспомогательные функции — из numfix.py (импорт). Копия тела fix() сделана 05.10.2026 с numfix.py (A3: hidden_empty).
"""
import sys, os, re, copy, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx.oxml.ns import qn
from lxml import etree
import numfix as nf
from numfix import lvl_info, parse_comp, norm, numpr_of, set_num, hidden_empty
import docx_numbering as dn
import pynum as pn
import refidx, reeng_plan as rp
from pagediff import key


def fix_once(d, RI):
    """Один проход numfix.fix на XML: ListString (truth) считается pynum по текущему дереву, а не Word. d — python-docx Document (правится на месте)."""
    numroot = d.part.numbering_part.element
    nb = pn.Numbering(numroot, d.styles.element)
    hl = RI.head_line
    byel = {}
    for k_, el_, ls_ in pn.number_all(d.element, nb):
        if k_ == 'p': byel[el_] = ls_
    truth = {}
    maxid = max([int(x) for x in nb.num] + [0])
    paras = []
    for ki, el in enumerate(d.element.body.iterchildren()):
        ps = [el] if el.tag == qn('w:p') else list(el.iter(qn('w:p'))) if el.tag == qn('w:tbl') else []
        for pi, p in enumerate(ps):
            paras.append((ki, pi, p))
            if p in byel: truth[(ki, pi)] = byel[p] if re.search(r'[0-9A-Za-zА-Яа-я]', byel[p]) else None
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
            if loc and RI.number_before(loc[0], loc[1], kt, rx) is None:
                # (py) первое вхождение — хвост предыдущего абзаца («…разрабатывается Перечень профессий…» перед «8.3 Перечень профессий…»): берём ближайшее следующее вхождение с номером
                nxt_ = loc; 
                for _ in range(3):
                    nxt_ = RI.locate(kt, nxt_[0] + 1)
                    if not nxt_ or nxt_[0] - loc[0] > 3000: break
                    if RI.number_before(nxt_[0], nxt_[1], kt, rx) is not None: loc = nxt_; break
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
    return stats




def run(d, pdf, maxit=int(os.environ.get('NF_MAXIT', '8'))):
    """d — python-docx Document канона (правится на месте). -> лог итераций."""
    try: d.part.numbering_part
    except Exception: return [{'skipped': 'нет numbering.xml', 'mismatch': 0}]
    RI = refidx.RefIndex(pdf); log = []
    for it in range(1, maxit + 1):
        st = fix_once(d, RI); st['iteration'] = it; log.append(st)
        if st['mismatch'] == 0: break
    return log
