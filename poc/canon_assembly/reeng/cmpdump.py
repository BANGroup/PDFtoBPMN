"""Сравнение canon_text.txt (Word) и py-выгрузки: строки, key текста, ListString. python3 cmpdump.py a.txt b.txt [-v]"""
import sys, difflib, re
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from pagediff import key

def rows(p):
    out = []
    for l in open(p, encoding='utf-8', errors='replace').read().split('\n'):
        r = l.rstrip('\r').split('\t')
        if len(r) >= 4: out.append((r[1], r[2].strip(), r[3]))
    return out

def compare(a, b):
    """a — эталон Word, b — py. -> dict"""
    A, B = rows(a), rows(b)
    import collections
    sa = collections.Counter(key(t) for k, ls, t in A if k in 'SF' and key(t)); sb = collections.Counter(key(t) for k, ls, t in B if k in 'SF' and key(t))
    shp = (sum(sa.values()), sum(sb.values()), sum((sa - sb).values()), sum((sb - sa).values()))
    A = [r for r in A if r[0] not in 'SF']; B = [r for r in B if r[0] not in 'SF']
    ka = [(key(t), k) for k, ls, t in A if key(t)]   # непустые по тексту
    kb = [(key(t), k) for k, ls, t in B if key(t)]
    sm = difflib.SequenceMatcher(None, [x[0] for x in ka], [x[0] for x in kb], autojunk=False)
    mt = sum(n for _, _, n in sm.get_matching_blocks())
    # номера: по сопоставленным строкам (непустые по тексту)
    la = [(key(t), ls) for k, ls, t in A if key(t)]; lb = [(key(t), ls) for k, ls, t in B if key(t)]
    num_tot = num_ok = 0; bad = []
    for i, j, n in sm.get_matching_blocks():
        for t in range(n):
            x, y = la[i + t][1], lb[j + t][1]
            if x or y:
                num_tot += 1
                if x.strip('.') == y.strip('.') or re.sub(r'\s', '', x) == re.sub(r'\s', '', y): num_ok += 1
                else: bad.append((i + t, x, y, ka[i + t][0][:30]))
    # нумерованные в Word строки (с цифро-буквенным номером)
    wn = sum(1 for k, ls, t in A if re.search(r'[0-9A-Za-zА-Яа-я]', ls) and key(t))
    only_a = [ka[i][0][:50] for blk in _gaps(sm, len(ka), True) for i in blk][:10]
    only_b = [kb[i][0][:50] for blk in _gaps(sm, len(kb), False) for i in blk][:10]
    return {'rows_a': len(A), 'rows_b': len(B), 'text_a': len(ka), 'text_b': len(kb), 'text_match': mt, 'text_only_a': len(ka) - mt, 'text_only_b': len(kb) - mt,
            'num_cmp': num_tot, 'num_ok': num_ok, 'num_bad': bad, 'word_numbered': wn, 'shapes_notes': shp, 'ex_only_a': only_a, 'ex_only_b': only_b}

def _gaps(sm, n, first):
    cov = set()
    for i, j, k in sm.get_matching_blocks():
        s = i if first else j
        cov.update(range(s, s + k))
    return [[x] for x in range(n) if x not in cov]

if __name__ == '__main__':
    r = compare(sys.argv[1], sys.argv[2])
    bad = r.pop('num_bad')
    print({k: v for k, v in r.items()}); print(len(bad), bad[:15] if '-v' in sys.argv else '')
