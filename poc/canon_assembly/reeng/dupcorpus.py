"""dupsim по списку документов: python dupcorpus.py <plan-only dir> <docs.txt|ALL> [live run dir]  — plan-only повторы vs verify.duplicates прогона."""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dupsim
pd = sys.argv[1]; arg = sys.argv[2]; run = sys.argv[3] if len(sys.argv) > 3 else None
docs = sorted(os.listdir(pd)) if arg == 'ALL' else open(arg).read().split()
for d in docs:
    base = os.path.join(pd, d)
    if not os.path.isdir(base): print(d, 'нет'); continue
    parts = [p for p in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, p))]
    tot = 0; org = collections.Counter()
    for p in parts:
        try:
            r = dupsim.dups_pdf(os.path.join(base, p))
        except Exception as e: print(d, p, 'ERR', e); continue
        if r is None: print(d,p,'нет PDF'); continue
        tot += sum(len(v) - 1 for v in r.values())
        for v in r.values(): org[('ф-ф' if all(o != 'base' for o, _ in v) else 'б-ф' if any(o != 'base' for o, _ in v) else 'б-б')] += 1
    ver = ''
    if run:
        try: ver = json.load(open(f'{run}/out/{d}/verify.json'))['duplicates']
        except Exception: ver = '?'
    print(d, 'sim', tot, 'verify', ver, dict(org))
