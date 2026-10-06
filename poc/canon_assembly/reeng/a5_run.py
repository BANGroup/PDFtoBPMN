"""Автономный прогон вставки строк PDF на копии канона из live/out: python a5_run.py <doc> [out_root]  (Word не нужен)."""
import sys, os, shutil, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pdf_lines as L, pagediff as P
R = '/home/budnik_an/Obligations/data/canon_reeng/'
doc = sys.argv[1]; root = sys.argv[2] if len(sys.argv) > 2 else R + 'stepA5/out'
sd = R + 'live/src/' + doc; od = f'{root}/{doc}'
os.makedirs(od, exist_ok=True)
for f in ('canon.docx', 'canon_text.txt', 'verify.json'): shutil.copy(f'{R}live/out/{doc}/{f}', od)
import pynum, verify_canon
pynum.dump(od + '/canon.docx', od + '/canon_text.txt')
before = verify_canon.verify(sd, od + '/canon_text.txt', od + '/canon.docx', L.sources_of(sd))
json.dump(before, open(od + '/verify.json', 'w'), ensure_ascii=False)
res = L.patch_canon(sd, od, P.ref_pdfs(sd)[0])
print(json.dumps({'doc': doc, 'before': {k: before[k] for k in ('lines', 'missing', 'numbered_bad', 'duplicates', 'frozen_numbers')}, 'after': res.get('verify'), 'inserted': res['inserted'],
                  'cls': {c: sum(1 for i in res['items'] if i['cls'] == c) for c in {i['cls'] for i in res['items']}}}, ensure_ascii=False))
for r in res['report']: print(' ', json.dumps(r, ensure_ascii=False)[:600])
