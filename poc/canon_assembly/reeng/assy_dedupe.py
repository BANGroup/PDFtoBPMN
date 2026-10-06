"""Повторы, созданные сборкой (A3): абзац >60 знаков, которого в сборке (база без вырезанного + фрагменты) больше, чем в эталоне.
Лишние копии убираются ДО Word, в файлах сборки: сначала копии из базы (остаток старой редакции вне границ вырезания), затем из фрагментов
более ранних изменений. Критерий — как в verify_canon: ожидаемое число = max(1, число вхождений key абзаца в тексте эталона); повтор,
разорванный колонтитулом/ячейкой эталона (не больше, чем в базе Word; начало и конец абзаца встречаются в эталоне не реже), не трогается.
Абзацы с рисунками/объектами/надписями/разрывом раздела не удаляются. Абзац внутри таблицы не удаляется, а очищается (структура таблицы цела).
python assy_dedupe.py <plan-only dir>   (запуск из plan_doc: dedupe(workdir, plan, canon_pdf, base_orig))"""
import os, re, sys, json, zipfile, collections, shutil
from lxml import etree
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pagediff as P


def _read(path): return zipfile.ZipFile(path).read('word/document.xml')


def _write(path, root):
    tmp = path + '.tmp'
    with zipfile.ZipFile(path) as zi, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zo:
        for it in zi.infolist():
            data = zi.read(it.filename)
            if it.filename == 'word/document.xml': data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            zo.writestr(it, data)
    os.replace(tmp, path)


def _text(p): return ''.join(t.text or '' for t in p.iter(W + 't'))


def _removable(p):
    if p.find('.//' + W + 'sectPr') is not None: return False
    for tag in ('drawing', 'pict', 'object', 'txbxContent', 'fldChar', 'bookmarkStart', 'footnoteReference', 'endnoteReference'):
        if p.find('.//' + W + tag) is not None: return False
    return True


def _nested(p):
    a = p.getparent()
    while a is not None:
        if a.tag == W + 'p': return True
        a = a.getparent()
    return False


def _in_table(p):
    a = p.getparent()
    while a is not None:
        if a.tag == W + 'tc': return True
        a = a.getparent()
    return False


def dedupe(workdir, plan, canon_pdf, base_orig):
    """-> список удалённых [{key, from, izm, where}]; правит base_marked.docx и frag_*.docx в workdir."""
    if os.environ.get('A3_DEDUPE', '1') != '1': return []
    mk = os.path.join(workdir, 'base_marked.docx')
    ins = {x['marker']: [os.path.basename(f.replace('\\', '/')) for f in x['frags']] for x in plan.get('inserts', [])}
    izm_of = {}
    for r in plan['regions']:
        for f in r.get('fragments', []):
            m = re.match(r'изм(\d+)', f.get('src', ''))
            izm_of[f['file']] = int(m.group(1)) if m else -1
    base_root = etree.fromstring(_read(mk)); body = base_root.find(W + 'body')
    # порядок сборки: проход по абзацам базы; маркер -> фрагменты
    order = []   # (seg_idx, p)
    frag_root = {}
    for fn in {f for fs in ins.values() for f in fs}:
        fp = os.path.join(workdir, fn)
        if os.path.exists(fp): frag_root[fn] = etree.fromstring(_read(fp))
    for p in body.iter(W + 'p'):
        t = _text(p); m = re.search(r'@@REG\d+@@', t)
        if m and m.group(0) in ins:
            for fn in ins[m.group(0)]:
                if fn in frag_root:
                    for q in frag_root[fn].find(W + 'body').iter(W + 'p'): order.append((fn, q))
        else: order.append(('base', p))
    pages = P.canon_pages(canon_pdf); pdfk = P.key(' '.join(' '.join(p['lines']) for p in pages))
    occ = collections.defaultdict(list)
    for pos, (src, p) in enumerate(order):
        if p.find('.//' + W + 'txbxContent') is not None and src == 'base': pass
        if _nested(p) or p.find('.//' + W + 'txbxContent') is not None: continue   # надписи: внешний абзац содержит текст внутренних
        k = P.key(_text(p))
        if len(k) > 60: occ[k].append((pos, src, p))
    base_k = P.key(P.docx_text(base_orig)) if base_orig and base_orig.endswith('.docx') and os.path.exists(base_orig) else ''
    removed, touched = [], set()
    for k, lst in occ.items():
        c = len(lst); want = max(1, pdfk.count(k))
        if c <= want: continue
        if base_k and c <= base_k.count(k) and pdfk.count(k[:30]) >= c and pdfk.count(k[-30:]) >= c: continue   # допустимый повтор (как dup_ok)
        # кандидаты на удаление: сначала база, затем фрагменты по возрастанию изм, при равенстве — более поздние в документе
        cand = sorted([x for x in lst if _removable(x[2])], key=lambda x: (0 if x[1] == 'base' else 1, izm_of.get(x[1], -1), -x[0]))
        # группа «база» — удаляем раньше фрагментов; но если все копии из базы (б-б), сборка не при чём — не трогаем
        if all(x[1] == 'base' for x in lst): continue
        for pos, src, p in cand[:c - want]:
            tb = _in_table(p); tx = _text(p)[:70]
            if tb:
                for t in list(p.iter(W + 't')): t.text = ''
            else: p.getparent().remove(p)
            touched.add(src); removed.append({'from': src, 'izm': izm_of.get(src), 'text': tx, 'in_table': tb})
    for src in touched:
        if src == 'base': _write(mk, base_root)
        else: _write(os.path.join(workdir, src), frag_root[src])
    return removed


if __name__ == '__main__':
    d = sys.argv[1]
    pl = json.load(open(d + '/plan.json'))
    r = dedupe(d, pl, pl['canon_pdf'], os.path.join(d, 'base_orig.docx'))
    print(len(r), 'удалено'); [print(x) for x in r[:10]]
