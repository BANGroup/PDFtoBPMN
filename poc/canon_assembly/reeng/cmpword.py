"""Построчное сравнение выгрузки Word (dump на нашем canon.docx) и pynum.dump: число строк, текст (strip), ListString. python3 cmpword.py [run ...]"""
import sys, os, glob, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import pynum
R = os.path.abspath(os.path.join(HERE, '..', '..', '..', 'data', 'canon_reeng'))

def rows(p):
    out = []
    for l in open(p, encoding='utf-8-sig', errors='replace').read().split('\n'):
        r = l.rstrip('\r').split('\t')
        if len(r) >= 4: out.append((r[1], r[2].strip(), r[3].strip()))
    return out

def cmp_doc(run, d, tmp='/tmp/_cw.txt'):
    wt = f'{R}/{run}/wordopen/{d}.word.txt'; dx = f'{R}/{run}/out/{d}/canon.docx'
    pynum.dump(dx, tmp); A, B = rows(wt), rows(tmp)
    res = {'run': run, 'doc': d, 'rows': (len(A), len(B)), 'text_diff': 0, 'ls_diff': 0, 'kind_diff': 0, 'ex': []}
    for i, (a, b) in enumerate(zip(A, B)):
        if a[0] != b[0]: res['kind_diff'] += 1
        if a[2] != b[2]:
            res['text_diff'] += 1
            if len(res['ex']) < 4: res['ex'].append((i + 1, a[2][:90], b[2][:90]))
        if a[1] != b[1]: res['ls_diff'] += 1
    return res

if __name__ == '__main__':
    runs = sys.argv[1:] or ['py1', 'stepP']; tot = collections.Counter()
    for run in runs:
        for f in sorted(glob.glob(f'{R}/{run}/wordopen/*.word.txt')):
            d = os.path.basename(f)[:-9]
            if not os.path.exists(f'{R}/{run}/out/{d}/canon.docx'): continue
            r = cmp_doc(run, d); ok = r['rows'][0] == r['rows'][1] and not r['text_diff'] and not r['ls_diff']
            tot['ok' if ok else 'bad'] += 1
            print(('OK  ' if ok else 'DIFF'), run, d, r['rows'], 'text', r['text_diff'], 'ls', r['ls_diff'], 'kind', r['kind_diff'])
            if not ok:
                for e in r['ex'][:3]: print('     ', e)
    print(dict(tot))
