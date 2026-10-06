"""Проверка целостности docx перед сохранением/после сборки (пилот шага 9): порядок дочерних элементов по схеме (pPr, rPr, sectPr, tblPr, tcPr, trPr),
numbering (abstractNum до num, numPicBullet первыми, ссылки), styles (уникальные id, ссылки basedOn/next/link), r:id в document.xml, content types, уникальность id.
python3 ooxml_check.py file.docx [ref.docx]  -> список проблем (пусто = ок)"""
import sys, zipfile, re, collections, posixpath
from lxml import etree
NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'; W = '{%s}' % NS
RN = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
ORDER = {   # headerReference/footerReference — один ранг (choice)
 'pPr': 'pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange'.split(),
 'rPr': 'ins del moveFrom moveTo rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange'.split(),
 'sectPr': 'headerReference footerReference footnotePr endnotePr type pgSz pgMar paperSrc pgBorders lnNumType pgNumType cols formProt vAlign noEndnote titlePg textDirection bidi rtlGutter docGrid printerSettings sectPrChange'.split(),
 'tblPr': 'tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing tblInd tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription tblPrChange'.split(),
 'tcPr': 'cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark headers cellIns cellDel cellMerge tcPrChange'.split(),
 'trPr': None,
}
LVL = 'start numFmt lvlRestart pStyle isLgl suff lvlText lvlPicBulletId legacy lvlJc pPr rPr'.split()


def check(path):
    out = []; z = zipfile.ZipFile(path); names = set(z.namelist())
    def rd(n): return etree.fromstring(z.read(n))
    ct = rd('[Content_Types].xml'); defaults = {e.get('Extension').lower() for e in ct if e.tag.endswith('Default')}; overr = {e.get('PartName') for e in ct if e.tag.endswith('Override')}
    for n in names:
        if n.endswith('/') or n == '[Content_Types].xml': continue
        if '/' + n not in overr and n.rsplit('.', 1)[-1].lower() not in defaults: out.append('нет content type: ' + n)
    for n in names:   # все XML-части разбираются
        if n.endswith(('.xml', '.rels')):
            try: rd(n)
            except Exception as e: out.append(f'XML {n}: {e}')
    # rels: цели существуют
    for n in names:
        if n.endswith('.rels'):
            base = posixpath.dirname(posixpath.dirname(n))
            for r in rd(n):
                if r.get('TargetMode') == 'External': continue
                t = r.get('Target'); p = t.lstrip('/') if t.startswith('/') else posixpath.normpath(posixpath.join(base, t))
                if p not in names: out.append(f'{n}: цель {t} не найдена')
    parts = [n for n in names if re.match(r'word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$', n)]
    for n in parts:
        root = rd(n); rels = {}
        rn = 'word/_rels/' + posixpath.basename(n) + '.rels'
        if rn in names: rels = {r.get('Id') for r in rd(rn)}
        for el in root.iter():
            for a in ('id', 'embed', 'link', 'pict', 'dm', 'lo', 'qs', 'cs'):
                v = el.get(RN + a)
                if v and v not in rels: out.append(f'{n}: r:{a}={v} нет в rels')
        cnt = collections.Counter()
        for tag, order in ORDER.items():
            if not order: continue
            for el in root.iter(W + tag):
                idx = []
                for c in el:
                    ln = etree.QName(c).localname
                    if ln == 'footerReference' and tag == 'sectPr': ln = 'headerReference'
                    if ln in order: idx.append(order.index(ln))
                if idx != sorted(idx): cnt[tag] += 1
        for tag, k in cnt.items(): out.append(f'{n}: нарушен порядок дочерних {tag}: {k}')
    doc = rd('word/document.xml')
    WP = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr'
    dp = collections.Counter(e.get('id') for n in names if re.match(r'word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$', n) for e in rd(n).iter(WP))   # уникальны по всему пакету
    if any(v > 1 for v in dp.values()): out.append('docPr id повторяются (в т.ч. между document и header/footer)')
    bs = collections.Counter(e.get(W + 'id') for e in doc.iter(W + 'bookmarkStart')); be = collections.Counter(e.get(W + 'id') for e in doc.iter(W + 'bookmarkEnd'))
    if any(v > 1 for v in bs.values()): out.append('bookmarkStart id повторяются')
    if set(bs) != set(be): out.append('закладки start/end не парны: %d/%d' % (len(set(bs) - set(be)), len(set(be) - set(bs))))
    bn = collections.Counter(e.get(W + 'name') for e in doc.iter(W + 'bookmarkStart'))
    if any(v > 1 for v in bn.values()): out.append('имена закладок повторяются: %d' % sum(1 for v in bn.values() if v > 1))
    sty = rd('word/styles.xml'); sid = [s.get(W + 'styleId') for s in sty.findall(W + 'style')]
    if len(sid) != len(set(sid)): out.append('styles: styleId повторяются')
    S = set(sid)
    for s in sty.findall(W + 'style'):
        for t in ('basedOn', 'next', 'link'):
            e = s.find(W + t)
            if e is not None and e.get(W + 'val') not in S: out.append(f'styles: {s.get(W + "styleId")}.{t} -> {e.get(W + "val")} нет')
    for tag in ('pStyle', 'rStyle', 'tblStyle'):
        miss = {e.get(W + 'val') for e in doc.iter(W + tag)} - S
        if miss: out.append(f'document: {tag} без стиля: {sorted(miss)[:5]}')
    numids = {'0'}
    if 'word/numbering.xml' in names:
        nm = rd('word/numbering.xml'); tags = [etree.QName(c).localname for c in nm]
        seq = ''.join({'numPicBullet': 'p', 'abstractNum': 'a', 'num': 'n'}.get(t, 'o') for t in tags)
        if not re.fullmatch(r'p*a*n*o?', seq): out.append('numbering: нарушен порядок numPicBullet/abstractNum/num/numIdMacAtCleanup')
        A = [c.get(W + 'abstractNumId') for c in nm if c.tag == W + 'abstractNum']; N = [c.get(W + 'numId') for c in nm if c.tag == W + 'num']
        if len(A) != len(set(A)) or len(N) != len(set(N)): out.append('numbering: повторы id')
        numids |= set(N)
        for c in nm.findall(W + 'num'):
            if c.find(W + 'abstractNumId').get(W + 'val') not in set(A): out.append('numbering: num -> нет abstractNum')
        for a in nm.findall(W + 'abstractNum'):
            ls = [l.get(W + 'ilvl') for l in a.findall(W + 'lvl')]
            if ls != sorted(ls, key=int) or len(ls) != len(set(ls)): out.append(f'numbering: уровни abstractNum {a.get(W + "abstractNumId")}')
            for l in a.findall(W + 'lvl'):
                idx = [LVL.index(etree.QName(c).localname) for c in l if etree.QName(c).localname in LVL]
                if idx != sorted(idx): out.append('numbering: порядок в lvl'); break
        nsid = [a.find(W + 'nsid').get(W + 'val') for a in nm.findall(W + 'abstractNum') if a.find(W + 'nsid') is not None]
        if len(nsid) != len(set(nsid)): out.append('numbering: nsid повторяются')
    bad = {e.get(W + 'val') for e in doc.iter(W + 'numId')} - numids
    if bad: out.append(f'document: numId без w:num: {sorted(bad)[:5]}')
    return sorted(set(out))


if __name__ == '__main__':
    for f in sys.argv[1:]:
        print(f); [print('  ', p) for p in check(f)]
