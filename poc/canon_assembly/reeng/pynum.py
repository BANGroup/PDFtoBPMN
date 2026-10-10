"""Нумерация и выгрузка текста docx без Word (пилот TASK-021, шаг 9, run stepP).

Класс Numbering считает ListString абзацев по numbering.xml/styles.xml (lxml, без python-docx):
стиль с numPr (цепочка basedOn, ilvl из pStyle уровня), lvlOverride/startOverride, сброс уровней (lvlRestart),
isLgl, нестандартные lvlText, маркеры (ListString = знак маркера), скрытые пустые абзацы (w:vanish в rPr абзаца: Word сливает
такой абзац со следующим, номер слитого — номер скрытого).
dump(docx, out): canon_text.txt в формате word_run.ps1 (idx, kind, ListString, text, pos).
python3 pynum.py <file.docx> [dump.txt]
"""
import sys, re, zipfile
from lxml import etree

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{%s}' % NS
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'
XMLSPACE = '{http://www.w3.org/XML/1998/namespace}space'
RU = 'абвгдежзиклмнопрстуфхцчшщэюя'   # русская нумерация Word пропускает ё, й, ъ, ы, ь
SKIP = {W + 'txbxContent', MC + 'Fallback', W + 'drawing', W + 'pict', W + 'object'}


def _val(el, tag):
    c = el.find(W + tag) if el is not None else None
    return c.get(W + 'val') if c is not None else None


_CTX = None
_PUA = re.compile('[\uf000-\uf0ff]')


def fmt_num(n, f):
    if f in ('decimal', None): return str(n)
    if f == 'none': return ''   # numFmt none: уровень в тексте ссылки пуст («%2%1.1» при none у уровня 1 -> «1.1»)
    if f == 'decimalZero': return '%02d' % n
    if f in ('lowerLetter', 'upperLetter'):
        s, m = '', n
        s = chr(97 + (n - 1) % 26) * ((n - 1) // 26 + 1)   # Word: aa, bbb (повтор буквы)
        return s.upper() if f == 'upperLetter' else s
    if f in ('lowerRoman', 'upperRoman'):
        s, m = '', n
        for v, r in ((1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'), (100, 'c'), (90, 'xc'), (50, 'l'), (40, 'xl'), (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i')):
            while m >= v: s += r; m -= v
        return s.upper() if f == 'upperRoman' else s
    if f in ('russianLower', 'russianUpper'):
        s = RU[(n - 1) % len(RU)] * ((n - 1) // len(RU) + 1)
        return s.upper() if f == 'russianUpper' else s
    if f == 'ordinal': return '%d.' % n
    return str(n)


class Numbering:
    def __init__(self, numbering_root, styles_root):
        self.styles = {}
        if styles_root is not None:
            for s in styles_root.findall(W + 'style'): self.styles[s.get(W + 'styleId')] = s
        self.abs, self.abs_el, self.num = {}, {}, {}
        self.style_lvl = {}   # styleId -> (abstractNumId, ilvl) по pStyle уровня
        if numbering_root is not None:
            for a in numbering_root.findall(W + 'abstractNum'):
                aid = a.get(W + 'abstractNumId'); self.abs_el[aid] = a
                self.abs[aid] = {l.get(W + 'ilvl'): l for l in a.findall(W + 'lvl')}
                for il, l in self.abs[aid].items():
                    ps = _val(l, 'pStyle')
                    if ps: self.style_lvl[(aid, ps)] = il
            # A6: abstractNum без уровней с numStyleLink берёт уровни abstractNum со styleLink того же стиля (Word так и считает; без этого ListString пустой)
            link = {}
            for a in numbering_root.findall(W + 'abstractNum'):
                sl = a.find(W + 'styleLink')
                if sl is not None and a.findall(W + 'lvl'): link[sl.get(W + 'val')] = a.get(W + 'abstractNumId')
            for a in numbering_root.findall(W + 'abstractNum'):
                ns = a.find(W + 'numStyleLink')
                if ns is not None and not a.findall(W + 'lvl') and link.get(ns.get(W + 'val')):
                    self.abs[a.get(W + 'abstractNumId')] = self.abs[link[ns.get(W + 'val')]]
            for n in numbering_root.findall(W + 'num'):
                ov = {o.get(W + 'ilvl'): o for o in n.findall(W + 'lvlOverride')}
                self.num[n.get(W + 'numId')] = (_val(n, 'abstractNumId'), ov)
        global _CTX
        _CTX = self; self.docdef_rpr = styles_root.find(W + 'docDefaults/' + W + 'rPrDefault/' + W + 'rPr') if styles_root is not None else None
        self._caps = {}
        self.vcnt = {}; self.vseen = set()
        self.cnt = {}      # abstractNumId -> {ilvl: n}
        self.seen = set()  # (numId, ilvl) с применённым startOverride
        self._sty = {}

    def style_flag(self, sid, flag):
        """Эффективное значение флага rPr (caps) стиля по цепочке basedOn: True/False/None (не задано)."""
        k = (sid, flag)
        if k in self._caps: return self._caps[k]
        v = None; seen = set(); s0 = sid
        while sid and sid in self.styles and sid not in seen:
            seen.add(sid); e = self.styles[sid].find(W + 'rPr/' + W + flag)
            if e is not None: v = e.get(W + 'val') not in ('0', 'false', 'off'); break
            sid = _val(self.styles[sid], 'basedOn')
        self._caps[k] = v
        return v

    def run_caps(self, r, psid):
        """Прописные в прогоне: прямое rPr > rStyle > стиль абзаца > docDefaults (как применяет Word в Range.Text)."""
        rpr = r.find(W + 'rPr')
        if rpr is not None:
            e = rpr.find(W + 'caps')
            if e is not None: return e.get(W + 'val') not in ('0', 'false', 'off')
            rs = _val(rpr, 'rStyle')
            if rs in self.styles and self.styles[rs].get(W + 'type') == 'character':   # rStyle на абзацный стиль Word игнорирует
                v = self.style_flag(rs, 'caps')
                if v is not None: return v
        v = self.style_flag(psid, 'caps')
        if v is not None: return v
        if self.docdef_rpr is not None:
            e = self.docdef_rpr.find(W + 'caps')
            if e is not None: return e.get(W + 'val') not in ('0', 'false', 'off')
        return False

    def style_numpr(self, sid):
        """(numId, ilvl) стиля по цепочке basedOn; ilvl из pStyle уровня, если в стиле его нет."""
        if sid in self._sty: return self._sty[sid]
        num = lvl = None; seen = set(); s0 = sid
        while sid and sid in self.styles and sid not in seen:
            seen.add(sid)
            st = self.styles[sid]; np_ = st.find(W + 'pPr/' + W + 'numPr')
            if np_ is not None:
                if num is None: num = _val(np_, 'numId')
                if lvl is None: lvl = _val(np_, 'ilvl')
            sid = _val(st, 'basedOn')
        if num is not None and lvl is None and num in self.num:
            # ilvl: уровень abstractNum, у которого pStyle = этот стиль (или базовый в цепочке)
            a = self.num[num][0]; sid = s0; seen = set()
            while sid and sid not in seen:
                seen.add(sid)
                if (a, sid) in self.style_lvl: lvl = self.style_lvl[(a, sid)]; break
                sid = _val(self.styles[sid], 'basedOn') if sid in self.styles else None
        self._sty[s0] = (num, lvl)
        return num, lvl

    def numpr(self, p):
        """(numId, ilvl) абзаца или None."""
        ppr = p.find(W + 'pPr'); nid = il = None; sid = None
        if ppr is not None:
            np_ = ppr.find(W + 'numPr')
            if np_ is not None: nid, il = _val(np_, 'numId'), _val(np_, 'ilvl')
            sid = _val(ppr, 'pStyle')
        sn, sl = self.style_numpr(sid)
        if nid is None:
            nid = sn
            if il is None: il = sl
        if nid in (None, '0') or nid not in self.num: return None
        return nid, int(il or 0)

    def lvl_def(self, nid, il):
        a, ov = self.num[nid]; o = ov.get(str(il))
        if o is not None and o.find(W + 'lvl') is not None: return o.find(W + 'lvl')
        return self.abs.get(a, {}).get(str(il))

    def start_of(self, nid, il):
        o = self.num[nid][1].get(str(il))
        if o is not None and _val(o, 'startOverride') is not None: return int(_val(o, 'startOverride'))
        ld = self.lvl_def(nid, il); s = _val(ld, 'start') if ld is not None else None
        return int(s) if s is not None else 1

    def step(self, p):
        """Сдвигает счётчики по абзацу; -> ListString ('' если абзац не нумерован)."""
        tc = next((a for a in p.iterancestors() if a.tag == W + 'tc'), None)
        if tc is not None:
            vm = tc.find(W + 'tcPr/' + W + 'vMerge')
            if vm is not None and vm.get(W + 'val') in (None, 'continue'):
                # абзацы в продолжении вертикально объединённой ячейки: Word ведёт им отдельный счёт (не влияет на основной список)
                main = (self.cnt, self.seen); self.cnt, self.seen = self.vcnt, self.vseen
                try: return self._step(p)
                finally: self.cnt, self.seen = main
        return self._step(p)

    def _step(self, p):
        np_ = self.numpr(p)
        if not np_: return ''
        nid, il = np_; a = self.num[nid][0]; ld = self.lvl_def(nid, il)
        if ld is None: return ''
        c = self.cnt.setdefault(a, {}); key = (nid, il)
        if p.find(W + 'pPr/' + W + 'sectPr') is not None and not para_text(p).strip() and p.find('.//' + W + 'drawing') is None and p.find('.//' + W + 'pict') is None:
            # пустой абзац-носитель разрыва раздела: Word показывает ТЕКУЩЕЕ значение уровня (0, если уровень не начат) и счётчик не двигает
            f = _val(ld, 'numFmt') or 'decimal'
            if f in ('bullet', 'none'): return '' if f == 'none' else (_val(ld, 'lvlText') or '')
            legal = ld.find(W + 'isLgl') is not None; lt = _val(ld, 'lvlText') or ''
            def sub0(m):
                k = int(m.group(1)) - 1; lk = self.lvl_def(nid, k)
                fk = (_val(lk, 'numFmt') if lk is not None else None) or 'decimal'
                n = c.get(k, 0 if k == il else self.start_of(nid, k))
                return fmt_num(n, 'decimal' if legal and fk != 'decimalZero' else fk)
            return re.sub(r'%(\d)', sub0, lt)
        ov = self.num[nid][1].get(str(il))
        if key not in self.seen and ov is not None and _val(ov, 'startOverride') is not None: c[il] = self.start_of(nid, il)
        elif il in c: c[il] += 1
        else: c[il] = self.start_of(nid, il)
        self.seen.add(key)
        for k in range(il):   # пропущенный родительский уровень считается начатым со своего start (следующий абзац того уровня даст start+1)
            if k not in c and self.lvl_def(nid, k) is not None: c[k] = self.start_of(nid, k)
        for m in list(c):   # сброс нижних уровней
            if m > il:
                r = _val(self.lvl_def(nid, m), 'lvlRestart') if self.lvl_def(nid, m) is not None else None
                if r is None or (r != '0' and il <= int(r) - 1): del c[m]
        f = _val(ld, 'numFmt') or 'decimal'
        lt = _val(ld, 'lvlText') or ''
        if f == 'bullet': return lt
        legal = ld.find(W + 'isLgl') is not None

        def sub(m):
            k = int(m.group(1)) - 1; lk = self.lvl_def(nid, k)
            fk = (_val(lk, 'numFmt') if lk is not None else None) or 'decimal'
            n = c.get(k, self.start_of(nid, k))
            return fmt_num(n, 'decimal' if legal and fk != 'decimalZero' else fk)
        return re.sub(r'%(\d)', sub, lt)


def walk_paras(el):
    """Абзацы потока в порядке документа (таблицы — по ячейкам); без надписей и fallback. Генерирует ('p', p) и ('rowend', tr)."""
    for ch in el:
        t = ch.tag
        if t == W + 'p': yield 'p', ch
        elif t == W + 'tbl':
            for tr in ch.iter(W + 'tr') if False else _rows(ch):
                yield from _row(tr)
        elif t in (W + 'sdt',):
            c = ch.find(W + 'sdtContent')
            if c is not None: yield from walk_paras(c)
        elif t in (W + 'ins', W + 'moveTo', W + 'customXml', W + 'smartTag') or t == MC + 'AlternateContent':
            yield from walk_paras(ch)


def _rows(tbl):
    for ch in tbl:
        if ch.tag == W + 'tr': yield ch
        elif ch.tag == W + 'sdt':
            c = ch.find(W + 'sdtContent')
            if c is not None:
                for x in c:
                    if x.tag == W + 'tr': yield x


def _row(tr):
    for tc in tr:
        if tc.tag == W + 'tc': yield from walk_paras(tc)
        elif tc.tag == W + 'sdt':
            c = tc.find(W + 'sdtContent')
            if c is not None:
                for x in c:
                    if x.tag == W + 'tc': yield from walk_paras(x)
    yield 'rowend', tr


WPN = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
MNS = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
MT = MNS + 't'


def math_text(t):
    """Текст m:t как отдаёт Word: латинские буквы формулы (стиль по умолчанию/курсив) — математические курсивные 𝐷 (U+1D434…), жирные — U+1D400…; m:nor и стиль «p» — как есть."""
    s = t.text or ''; r = t.getparent(); rpr = r.find(MNS + 'rPr') if r is not None else None
    sty = None
    if rpr is not None:
        if rpr.find(MNS + 'nor') is not None: return s
        e = rpr.find(MNS + 'sty'); sty = e.get(MNS + 'val') if e is not None else None
    if sty == 'p': return s
    base = {'b': (0x1D400, 0x1D41A), 'bi': (0x1D468, 0x1D482)}.get(sty, (0x1D434, 0x1D44E))
    out = []
    for c in s:
        if 'A' <= c <= 'Z': out.append(chr(base[0] + ord(c) - 65))
        elif 'a' <= c <= 'z': out.append('\u210e' if (c == 'h' and base[1] == 0x1D44E) else chr(base[1] + ord(c) - 97))
        else: out.append(c)
    return ''.join(out)


def para_text(p):
    """Текст абзаца как Range.Text Word: результат полей (без instrText), без надписей, табы/переводы строк -> ' '."""
    out = []; fields = []
    def emit(x):
        if fields and fields[-1]['state'] == 'code': return   # код поля (включая рисунки в нём) в текст не входит
        out.append(x)
    ppr0 = p.find(W + 'pPr'); psid = _val(ppr0, 'pStyle') if ppr0 is not None else None
    def rec(el, caps=False):
        for ch in el:
            t = ch.tag
            if t == W + 'r' and _CTX is not None: caps = _CTX.run_caps(ch, psid)
            if t == W + 'r' and ch.find(W + 'rPr/' + W + 'webHidden') is not None and ch.find(W + 'rPr/' + W + 'vanish') is None:
                continue   # номера страниц оглавления (webHidden): Range.Text Word их не возвращает
            if t == W + 'fldChar':
                ty = ch.get(W + 'fldCharType')
                if ty == 'begin': fields.append({'state': 'code', 'pos': len(out), 'instr': []})
                elif ty == 'separate' and fields: fields[-1]['state'] = 'result'
                elif ty == 'end' and fields: fields.pop()
                continue
            if t == W + 'instrText':
                if fields and fields[-1]['state'] == 'code': fields[-1]['instr'].append(ch.text or '')
                continue
            if t in (W + 'txbxContent', MC + 'Fallback', W + 'delText', W + 'pPr', W + 'rPr'): continue
            if t == W + 't':
                x = (ch.text or '').upper() if caps else (ch.text or '')
                emit(x)
            elif t == MNS + 'oMath': emit(' ' + ' '.join(math_text(x) for x in ch.iter(MT)) + ' ')   # формула OMML: Word отдаёт её текст (m:t через пробел) в Range.Text
            elif t == MT: emit(' ' + math_text(ch) + ' ')
            elif t in (W + 'tab', W + 'br', W + 'cr', W + 'ptab'): emit(' ' if (t != W + 'br' or ch.get(W + 'type') != 'page') else ' ')
            elif t == W + 'noBreakHyphen': emit('-')
            elif t == W + 'softHyphen': emit('\x1f')   # мягкий перенос: Word отдаёт chr(31)
            elif t == W + 'sym':
                ch_ = ch.get(W + 'char'); emit('(' if ch_ else '')   # w:sym (Symbol/Wingdings): Word отдаёт в Range.Text «(»
            elif t in (W + 'footnoteReference', W + 'endnoteReference'): emit('\x02')   # знак сноски
            elif t in (W + 'drawing', W + 'pict', W + 'object'):
                # Range.Text Word: chr(1) только у встроенных (inline) объектов; плавающие (wp:anchor, VML position:absolute) знака не дают
                # Range.Text Word: chr(1) ставится не всегда; ближе всего к Word (30 документов) — только встроенный OLE (w:object без position:absolute).
                # Потребители (verify, point_fingerprint) служебные знаки игнорируют.
                floating = any('position:absolute' in (e.get('style') or '') for e in ch.iter())
                if t == W + 'drawing':   # встроенный рисунок/фигура (wp:inline) — «/», плавающий (wp:anchor) знака не даёт
                    if ch.find(WPN + 'inline') is not None: emit('/')
                elif not floating: emit('\x01')   # встроенные VML-рисунок (w:pict) и OLE (w:object)
                rec(ch, caps)
            else: rec(ch, caps)
    rec(p)
    # поле TOC, начатое в этом абзаце и законченное в другом: у РГ-190-03 Word оставляет в тексте код поля, у ДП-Б8.006-04, КД-РГ-225-01 и др. — нет
    # (причина различия не найдена, в большинстве документов кода нет) — код в текст не добавляем
    return ''.join(out)


def is_hidden_empty(p):
    """Пустой абзац со скрытым знаком абзаца (vanish в rPr абзаца), без графики/полей/разделов."""
    rpr = p.find(W + 'pPr/' + W + 'rPr')
    if rpr is None or rpr.find(W + 'vanish') is None: return False
    if para_text(p).strip(): return False
    for tag in ('sectPr', 'drawing', 'pict', 'object', 'fldChar', 'fldSimple', 'footnoteReference', 'endnoteReference', 'commentReference'):
        if p.find('.//' + W + tag) is not None: return False
    return True


def hidden_mark(p):
    """Скрытый знак абзаца (vanish в pPr/rPr): Word сливает такой абзац со следующим (текст склеивается, строка в выгрузке одна), абзац с разрывом раздела не сливается."""
    rpr = p.find(W + 'pPr/' + W + 'rPr')
    return rpr is not None and (rpr.find(W + 'vanish') is not None or rpr.find(W + 'webHidden') is not None) and p.find(W + 'pPr/' + W + 'sectPr') is None


def number_all(doc_root, nb):
    """Список (kind, el, ListString|'') по порядку; kind: p | rowend | p_hidden. Абзацы со скрытым знаком абзаца сливаются со следующим (kind p_hidden — сам слитый,
    в выгрузке строки не имеет; строка — у последнего абзаца группы, nb.merged[el] = [слитые перед ним]). Номер строки — номер первого пронумерованного абзаца
    группы (счётчик двигает только он); если нумерованного нет — собственный номер последнего."""
    body = doc_root.find(W + 'body'); out = []
    items = list(walk_paras(body))
    nb.merged = {}; nb.absorbed = {}
    pend = []; skip_cell = None
    for i, (k, el) in enumerate(items):
        if k == 'rowend': out.append((k, el, '')); pend = []; continue
        nxt = items[i + 1] if i + 1 < len(items) else None
        if el is skip_cell:   # первый абзац таблицы, слитый с предшествующим абзацем со скрытым знаком: своей строки нет, нумерация шагает
            nb.step(el); out.append(('p_hidden', el, '')); skip_cell = None; continue
        if hidden_mark(el) and not pend and nxt is not None and nxt[0] == 'p' and nxt[1].getparent() is not el.getparent():
            sib = el.getnext()
            if sib is not None and sib.tag == W + 'tbl' and nxt[1] is next(sib.iter(W + 'p'), None):
                # абзац со скрытым знаком перед таблицей сливается с первым абзацем первой ячейки (Word: «…в таблице 7.2.Элемент»)
                nb.absorbed[el] = [nxt[1]]; skip_cell = nxt[1]; out.append((k, el, nb.step(el))); continue
        if hidden_mark(el) and nxt is not None and nxt[0] == 'p' and nxt[1].getparent() is el.getparent():
            pend.append((el, nb.step(el))); out.append(('p_hidden', el, '')); continue
        if pend:
            carry = next((l for _, l in pend if l), '')
            ls = nb.step(el) if not carry else carry   # у скрытого нет номера: счётчик последнего абзаца идёт, но Word показывает пустой номер строки; номер скрытого — действует, счётчик последнего не двигается
            if not carry: ls = ''
            nb.merged[el] = [e for e, _ in pend]; pend = []
            out.append((k, el, ls))
        else: out.append((k, el, nb.step(el)))
    return out


def load(path):
    z = zipfile.ZipFile(path)
    rd = lambda n: etree.fromstring(z.read(n)) if n in z.namelist() else None
    return z, rd('word/document.xml'), rd('word/numbering.xml'), rd('word/styles.xml')


def list_strings(path):
    """[(el, ListString)] абзацев (без row-end) для docx."""
    z, doc, num, sty = load(path)
    nb = Numbering(num, sty)
    return [(el, ls) for k, el, ls in number_all(doc, nb) if k == 'p']


def shapes_and_notes(z, doc):
    """Тексты надписей (S) и сносок (F), как в word_run.ps1 dump."""
    S, F = [], []
    def txbx(root):
        # Word: сначала плавающие фигуры по z-порядку (relativeHeight / z-index), затем встроенные в порядке документа; пустые надписи тоже дают строку
        items = []
        for k, tb in enumerate(root.iter(W + 'txbxContent')):
            if any(a.tag == MC + 'Fallback' for a in tb.iterancestors()): continue
            if any(a.tag == W + 'txbxContent' for a in tb.iterancestors()): continue
            t = re.sub(r'[\r\n\t\a\v]', ' ', ' '.join(para_text(p).strip() for p in tb.iter(W + 'p')))
            anc = next((a for a in tb.iterancestors() if a.tag == WPN + 'anchor' or a.tag == WPN + 'inline'), None)
            if anc is not None and anc.tag == WPN + 'anchor' and (anc.get('relativeHeight') or '').isdigit(): key = (0, int(anc.get('relativeHeight')), k)
            else:
                st = next((a.get('style') or '' for a in tb.iterancestors() if a.tag.endswith('}shape') or a.tag.endswith('}rect') or a.tag.endswith('}textbox')), '')
                m = re.search(r'z-index:(-?\d+)', st)
                key = (0, int(m.group(1)), k) if ('position:absolute' in st and m) else (1, 0, k)
            items.append((key, t))
        S.extend(t for _, t in sorted(items))
    txbx(doc)
    for n in ('word/footnotes.xml', 'word/endnotes.xml'):
        if n in z.namelist():
            r = etree.fromstring(z.read(n))
            refd = {x.get(W + 'id') for x in doc.iter(W + ('footnoteReference' if 'foot' in n else 'endnoteReference'))}
            for fn in r:
                if fn.get(W + 'id') not in refd: continue   # Word перечисляет только сноски, на которые есть ссылка в тексте
                if fn.get(W + 'type') in ('separator', 'continuationSeparator', 'continuationNotice'): continue
                t = ' '.join(para_text(p) for p in fn.iter(W + 'p'))
                if t.strip(): F.append(re.sub(r'[\r\n\t\a\v]', ' ', t))
    return S, F


def dump(path, out):
    """canon_text.txt: idx\\tkind\\tListString\\ttext\\tpos (T — абзац в таблице, - — вне; S — надпись; F — сноска). pos — условный (порядковый)."""
    z, doc, num, sty = load(path)
    nb = Numbering(num, sty)
    body = doc.find(W + 'body'); lines = []; i = 0; pos = 0
    intbl = lambda el: any(a.tag == W + 'tc' for a in el.iterancestors())
    for k, el, ls in number_all(doc, nb):
        if k.endswith('_hidden'): continue
        i += 1
        if k == 'rowend': lines.append(f'{i}\tT\t\t  \t{pos}')
        else:
            t = re.sub(r'[\r\n\t\a\v]', ' ', ''.join(para_text(m) for m in nb.merged.get(el, [])) + para_text(el) + ''.join(para_text(m) for m in nb.absorbed.get(el, []))) + (' ' if not intbl(el) else '  ')
            if intbl(el) and False: pass
            lines.append(f'{i}\t{"T" if intbl(el) else "-"}\t{ls}\t{t}\t{pos}'); pos += len(t) + 1
    S, F = shapes_and_notes(z, doc)
    for t in S: i += 1; lines.append(f'{i}\tS\t\t{t}\t-1')
    for t in F: i += 1; lines.append(f'{i}\tF\t\t{t}')
    with open(out, 'w', encoding='utf-8', newline='') as f: f.write('\r\n'.join(lines) + '\r\n')
    return len(lines)


if __name__ == '__main__':
    if len(sys.argv) > 2: print(dump(sys.argv[1], sys.argv[2]))
    else:
        for el, ls in list_strings(sys.argv[1]): print(ls or '-', '|', para_text(el)[:80])
