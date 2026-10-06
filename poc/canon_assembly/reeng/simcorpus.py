"""simverify по документам: python simcorpus.py <plan-only dir> <live run dir> <docs.txt|ALL> [-j N] -> TSV doc, missing, dups (одночастные)."""
import sys, os, json, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
pod, run, arg = sys.argv[1:4]
docs = sorted(os.listdir(pod)) if arg == 'ALL' else open(arg).read().split()
def one(d):
    import simverify
    p = os.path.join(pod, d, 'p0')
    if not os.path.exists(p + '/plan.json'): return d, None
    try:
        r = simverify.run(p, os.path.join(run, 'src', d))
        return d, (r['missing'], r['duplicates'], r['lines'])
    except Exception as e: return d, 'ERR ' + str(e)[:60]
with cf.ProcessPoolExecutor(int(os.environ.get('J', '6'))) as ex:
    for d, r in ex.map(one, docs): print(d, r, sep='\t')
