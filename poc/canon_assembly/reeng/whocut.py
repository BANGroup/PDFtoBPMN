"""Какой регион вырезал строки, не найденные в сборке: python whocut.py <plan-only dir> <src dir>  (по base_orig.docx и a_elem/b_elem регионов)"""
import sys, os, json, zipfile, re, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lxml import etree
import simverify, pagediff as P
W = P.W
pod, src = sys.argv[1:3]
r = simverify.run(pod, src)
pl = json.load(open(pod + '/plan.json'))
body = etree.fromstring(zipfile.ZipFile(pod + '/base_orig.docx').read('word/document.xml')).find(W + 'body')
kids = list(body)
ks = [P.key(''.join(t.text or '' for t in el.iter(W + 't'))) for el in kids]
cnt = collections.Counter(); ex = {}
for e in r['examples_missing']:
    m = re.match(r'стр\.(\S+): (.*)', e); lab, line = m.group(1), m.group(2)
    k = P.key(P.LIST_MARK.sub('', line))
    hit = [i for i, kk in enumerate(ks) if k and k in kk]
    reg = None
    for rg in pl['regions']:
        if rg.get('a_elem') is None: continue
        for i in hit:
            if rg['a_elem'] < i < rg['b_elem'] or (i in (rg['a_elem'], rg['b_elem']) and kids[i].tag == W + 'tbl'): reg = (rg['n'], rg['pages'][0] + '-' + rg['pages'][-1]); break
        if reg: break
    key_ = reg or ('нет в базе' if not hit else 'в базе, не вырезано')
    cnt[key_] += 1; ex.setdefault(key_, []).append((lab, line[:50], hit[:2]))
for k_, n in cnt.most_common(): print(n, k_, ex[k_][:3])
