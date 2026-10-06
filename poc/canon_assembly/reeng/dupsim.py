"""Повторы абзацев в собранном (plan-only) каноне без Word: python dupsim.py <plan-only dir> -> абзацы >60 знаков, встречающиеся
в нескольких источниках (база/фрагменты), с указанием откуда. Порядок: base_marked.docx, маркер @@REGn@@ заменяется фрагментами."""
import sys, os, re, json, zipfile, collections
from lxml import etree
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def paras(path):
    body = etree.fromstring(zipfile.ZipFile(path).read('word/document.xml')).find(W + 'body')
    return [''.join(t.text or '' for t in p.iter(W + 't')) for p in body.iter(W + 'p')]
def k(s): return re.sub(r'[\W_]+', '', s.lower())
def assemble(d):
    pl = json.load(open(d + '/plan.json')); ins = {x['marker']: x['frags'] for x in pl.get('inserts', [])}
    out = []
    for i, t in enumerate(paras(d + '/base_marked.docx')):
        m = re.search(r'@@REG\d+@@', t)
        if m and m.group(0) in ins:
            for f in ins[m.group(0)]:
                for tt in paras(os.path.join(d, os.path.basename(f.replace('\\', '/')))): out.append((tt, m.group(0) + ':' + os.path.basename(f.replace('\\', '/'))))
        else: out.append((t, 'base'))
    return out
def dups(d, minlen=60):
    a = assemble(d); c = collections.defaultdict(list)
    for t, o in a:
        if len(k(t)) >= minlen: c[k(t)].append((o, t))
    return {x: v for x, v in c.items() if len(v) > 1}
def dups_pdf(d, minlen=60):
    """как verify_canon: абзац >60 знаков, которого в сборке больше, чем в эталоне (PDF); ключи — pagediff.key"""
    import pagediff as P
    pl = json.load(open(d + '/plan.json')); pdfp = pl['canon_pdf']
    if not os.path.exists(pdfp): return None
    pages = P.canon_pages(pdfp); pdfk = P.key(' '.join(' '.join(p['lines']) for p in pages))
    a = assemble(d); c = collections.defaultdict(list)
    for t, o in a:
        kk = P.key(t)
        if len(kk) > 60: c[kk].append((o, t))
    return {x: v for x, v in c.items() if len(v) > 1 and pdfk.count(x) < len(v)}
if __name__ == '__main__':
    d = sys.argv[1]; r = dups(d)
    print('повторяющихся абзацев:', len(r), ' лишних копий:', sum(len(v) - 1 for v in r.values()))
    cnt = collections.Counter(tuple(o for o, _ in v) for v in r.values())
    for o, n in cnt.most_common(12): print(n, o)
    if '-v' in sys.argv:
        for v in r.values(): print([o for o, _ in v], v[0][1][:70])
    # -p: пары фрагментов с описанием из plan.json
    if '-p' in sys.argv:
        pl = json.load(open(d + '/plan.json')); info = {}
        for r in pl['regions']:
            for f in r.get('fragments', []): info[f['file']] = f"рег{r['n']} {f['src']} стр{f['labels']}{' (обрезан)' if f.get('trimmed') else ''}"
        r = dups_pdf(d) or {}
        cp = collections.Counter(tuple(sorted(set(info.get(o.split(':')[-1], o) if o != 'base' else 'base' for o, _ in v))) for v in r.values())
        for k_, n in cp.most_common(): print(n, ' <> '.join(k_))
    if '-w' in sys.argv:   # положение дублей относительно маркеров
        import pagediff as P
        a = assemble(d); r = dups_pdf(d) or {}
        marks = [(i, o) for i, (t, o) in enumerate(a) if o != 'base' and (i == 0 or a[i - 1][1] != o)]
        print('фрагменты с позиции:', [(i, o.split(':')[-1]) for i, o in marks])
        for k_, v in list(r.items())[:int(os.environ.get('N', '8'))]:
            print([(i, o.split(':')[-1] if o != 'base' else 'b') for i, (t, o) in enumerate(a) if P.key(t) == k_], v[0][1][:60])
