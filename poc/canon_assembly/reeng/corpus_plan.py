"""plan-only по документам прогона (без Word): python corpus_plan.py <run dir> <out dir> [--status ready|all] [--docs A,B] [-j N]
Для каждого документа/части: plan.json нового кода + сводка против plan.json исходного прогона."""
import sys, os, json, glob, subprocess, argparse, csv, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('run'); ap.add_argument('out'); ap.add_argument('--status', default='all'); ap.add_argument('--docs'); ap.add_argument('-j', type=int, default=3)
a = ap.parse_args()
rows = list(csv.DictReader(open(os.path.join(a.run, 'summary.csv'), encoding='utf-8-sig'), delimiter=';'))
docs = [r['doc_num'] for r in rows if a.status == 'all' or r['status'] == a.status]
if a.docs: docs = [d for d in docs if d in a.docs.split(',')]
tasks = []
for d in docs:
    sd = os.path.join(a.run, 'src', d)
    parts = sorted(glob.glob(sd + '/__parts/p*'))
    if parts:
        for p in parts: tasks.append((d, os.path.basename(p), p, os.path.join(a.run, 'out', d, 'part_' + os.path.basename(p)[1:], 'plan.json')))
    else: tasks.append((d, '', sd, os.path.join(a.run, 'out', d, 'plan.json')))
def one(t):
    d, pn, sd, oldp = t
    od = os.path.join(a.out, d, pn or 'p0')
    if os.path.exists(od + '/summary.json'): return json.load(open(od + '/summary.json'))
    os.makedirs(od, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'plan_only.py'), sd, od], capture_output=True, text=True, timeout=1500)
    res = {'doc': d, 'part': pn}
    try:
        n = json.load(open(od + '/plan.json'))
        res.update(regions=len(n['regions']), ok=sum(r_['ok'] for r_ in n['regions']), pdf=len(n.get('pdf_candidates', {})), placed=sum(len(x['labels']) for x in n.get('pdf_source', [])),
                   rej=[(r_['n'], r_.get('destroyed')) for r_ in n['regions'] if r_.get('fail') == 'вырезание затрагивает сохраняемые страницы'],
                   destroyed=[r_.get('destroyed') for r_ in n['regions'] if r_['ok'] and r_.get('destroyed')])
        if os.path.exists(oldp):
            o = json.load(open(oldp)); res['old_ok'] = sum(r_['ok'] for r_ in o['regions']); res['old_regions'] = len(o['regions'])
    except Exception as e:
        res['error'] = (r.stderr or str(e))[-300:]
    json.dump(res, open(od + '/summary.json', 'w'), ensure_ascii=False)
    return res
with cf.ThreadPoolExecutor(a.j) as ex:
    out = list(ex.map(one, tasks))
json.dump(out, open(os.path.join(a.out, 'all.json'), 'w'), ensure_ascii=False, indent=0)
print(len(out), 'parts')
