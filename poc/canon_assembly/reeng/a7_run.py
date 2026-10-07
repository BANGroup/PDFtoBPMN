import sys, os, shutil, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pdf_words as W, pdf_lines as L, pagediff as P, pynum, verify_canon
R = '/home/budnik_an/Obligations/data/canon_reeng/'
doc = sys.argv[1]; root = R + 'stepA7/probe'; sd = R + 'live/src/' + doc; od = f'{root}/{doc}'
os.makedirs(od, exist_ok=True)
for f in ('canon.docx',): shutil.copy(f'{R}live/out/{doc}/{f}', od)
pynum.dump(od + '/canon.docx', od + '/canon_text.txt')
b = verify_canon.verify(sd, od + '/canon_text.txt', od + '/canon.docx', L.sources_of(sd))
r = W.patch_words(sd, od, P.ref_pdfs(sd)[0])
print(doc, 'before missing', b['missing'], 'after', (r.get('verify') or {}).get('missing'), 'replaced', r['replaced'])
for x in r['report'][:12]: print('  ', json.dumps(x, ensure_ascii=False)[:500])
