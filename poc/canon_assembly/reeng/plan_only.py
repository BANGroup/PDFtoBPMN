"""plan-only (без Word): python plan_only.py <src dir части/документа> <out dir>  -> plan.json, статистика."""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if not os.environ.get('A2_BASE') else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')))
import reeng_plan as rp, wordrun
def _noword(*a, **k): raise RuntimeError('plan-only: Word запрещён')
wordrun.run = _noword
rp.ensure_dumps = lambda *a, **k: None   # без Word: номера по docx_numbering
sd, od = sys.argv[1], sys.argv[2]
os.makedirs(od, exist_ok=True)
pl = rp.plan_doc(sd, 'po', od)
json.dump(pl, open(os.path.join(od, 'plan.json'), 'w'), ensure_ascii=False, indent=1)
print(collections.Counter(d['type'] for d in pl['defects']))
print('regions', len(pl['regions']), 'ok', sum(r['ok'] for r in pl['regions']))
if not os.environ.get('A2_BASE'): print('pdf cand', len(pl['pdf_candidates']), 'placed', sum(len(x['labels']) for x in pl['pdf_source']), 'unplaced', len(pl['pdf_unplaced']))
