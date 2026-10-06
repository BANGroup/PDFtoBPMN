"""Сверка артефактов сборки двух plan-only прогонов (base_marked.docx, frag_*.docx, inserts): одинаковы -> Word даст тот же результат.
python plan_identity.py <dirA> <dirB>  (dir = выход corpus_plan.py: <doc>/<part>/)"""
import sys, os, json, zipfile, hashlib, glob
A, B = sys.argv[1:3]
def sig(d):
    out = {}
    for f in sorted(glob.glob(d + '/*.docx')):
        b = os.path.basename(f)
        if b.startswith(('base_orig', 'base_src')): continue
        try: out[b] = hashlib.md5(zipfile.ZipFile(f).read('word/document.xml')).hexdigest()
        except Exception as e: out[b] = 'ERR'
    try: out['inserts'] = json.dumps(json.load(open(d + '/plan.json')).get('inserts'), sort_keys=True)
    except Exception: out['inserts'] = None
    return out
same, diff, miss = [], [], []
for doc in sorted(os.listdir(A)):
    if not os.path.isdir(A + '/' + doc): continue
    for pn in sorted(os.listdir(A + '/' + doc)):
        a, b = f'{A}/{doc}/{pn}', f'{B}/{doc}/{pn}'
        if not os.path.exists(b + '/plan.json') or not os.path.exists(a + '/plan.json'): miss.append((doc, pn)); continue
        (same if sig(a) == sig(b) else diff).append((doc, pn))
print('одинаковы', len(same), 'различаются', len(diff), 'нет plan', len(miss))
for d in diff: print('DIFF', d)
json.dump({'same': same, 'diff': diff, 'miss': miss}, open(os.path.join(A, 'identity.json'), 'w'), ensure_ascii=False)
