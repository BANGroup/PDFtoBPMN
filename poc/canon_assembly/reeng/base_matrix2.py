import sys, glob, os, zipfile
from lxml import etree
import pagediff as P
sd = sys.argv[1]
parts = sorted(glob.glob(sd + '/__parts/p*'), key=lambda x: int(x.rsplit('/p', 1)[1]))
def xt(f):
    r = etree.fromstring(zipfile.ZipFile(f).read('word/document.xml'))
    return P.key(''.join(t.text or '' for t in r.iter(P.W + 't')))
bases = [glob.glob(p + '/word/*.docx')[0] for p in parts]
pdfs = [glob.glob(p + '/files/*.pdf')[0] for p in parts]
txt = [xt(f) for f in bases]
print('строка: PDF части i; столбец: база части j; доля строк PDF, найденных в базе (key)')
for i, pdf in enumerate(pdfs):
    pages = P.canon_pages(pdf); cnt = {}
    for pg in pages:
        for k in {P.key(l) for l in pg['lines']}: cnt[k] = cnt.get(k, 0) + 1
    head = {k for k, c in cnt.items() if c > 0.3 * len(pages)}
    keys = {P.key(l) for pg in pages for l in pg['lines'] if len(P.key(l)) >= 12 and P.key(l) not in head and not P.garbage(l)}
    sc = [sum(1 for k in keys if k in t) / len(keys) for t in txt]
    print(f'ч{i+1} ({len(keys):5d} строк)', ' '.join(f'{x:.2f}' for x in sc), ' argmax=ч%d' % (sc.index(max(sc)) + 1), os.path.basename(bases[i])[:34])
