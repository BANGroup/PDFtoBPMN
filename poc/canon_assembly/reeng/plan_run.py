"""Последовательный plan-only (без Word, один процесс, RLIMIT_AS 5 ГБ): python plan_run.py <run dir> <out dir> [DOC,DOC|ALL]
Флаги среды A3_GATE/A3_SALVAGE/A3_DEDUPE/A3_SORT=0 отключают правки A3 (базовая линия). Результат: <out>/<doc>/<p0|pN>/plan.json, <out>/status.tsv."""
import sys, os, glob, subprocess, resource, json, csv
HERE = os.path.dirname(os.path.abspath(__file__))
run, out = sys.argv[1:3]; arg = sys.argv[3] if len(sys.argv) > 3 else 'ALL'
rows = list(csv.DictReader(open(os.path.join(run, 'summary.csv'), encoding='utf-8-sig'), delimiter=';'))
docs = [r['doc_num'] for r in rows] if arg == 'ALL' else arg.split(',')
def lim(): resource.setrlimit(resource.RLIMIT_AS, (5 << 30, 5 << 30))
os.makedirs(out, exist_ok=True); tsv = open(os.path.join(out, 'status.tsv'), 'a')
for d in docs:
    sd = os.path.join(run, 'src', d)
    parts = sorted(glob.glob(sd + '/__parts/p*')) or [sd]
    for p in parts:
        pn = os.path.basename(p) if p != sd else 'p0'; od = os.path.join(out, d, pn)
        if os.path.exists(od + '/plan.json'): continue
        os.makedirs(od, exist_ok=True)
        try: r = subprocess.run([sys.executable, os.path.join(HERE, 'plan_only.py'), p, od], capture_output=True, text=True, timeout=900, preexec_fn=lim); st = 'ok' if os.path.exists(od + '/plan.json') else (r.stderr.strip().splitlines() or ['?'])[-1][:80]
        except subprocess.TimeoutExpired: st = 'timeout'
        tsv.write(f'{d}\t{pn}\t{st}\n'); tsv.flush()
