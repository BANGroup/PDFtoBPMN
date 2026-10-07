"""TASK-021: проверка compare_pair. python3 verify_compare.py code|real|synth  (code — только код, без вызовов модели)
Результаты: data/canon_reeng/llm/compare_{real,synth}.json"""
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare as C
OUT = C.OUT
def load(n): return json.load(open(os.path.join(OUT, n), encoding='utf-8'))
def run(kind, code_only=False):
    items = load('real_pairs.json' if kind == 'real' else 'exam2_hard.json')
    ref = {k: v[0] for k, v in load('real_mine.json').items()} if kind == 'real' else {x['id']: x['gold'] for x in items}
    res = []; fn = os.path.join(OUT, f'compare_{kind}.json')
    for it in items:
        if code_only: cd = C.code_diff(it['A'], it['B']); r = {'result': 'SAME' if cd['same'] else 'NEEDS_LLM', 'calls': 0, **{'code_a_only': cd['a_only'], 'code_b_only': cd['b_only']}}
        else:
            try: r = C.compare_pair(it['A'], it['B'], it['id'])
            except C.GatewayStop as e: print('СТОП:', e); break
        res.append({'id': it['id'], 'ref': ref[it['id']], **r}); print(it['id'], ref[it['id']], r['result'], flush=True)
        if not code_only: json.dump(res, open(fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    cnt = collections.Counter((x['ref'], x['result']) for x in res)
    print(sorted(cnt.items())); print('вызовов', sum(x['calls'] for x in res), 'решил код', sum(1 for x in res if x['result'] == 'SAME' and x.get('by', 'code') == 'code'))
if __name__ == '__main__':
    k = sys.argv[1]; run('real' if k == 'code' else k, k == 'code') if k != 'code' else (run('real', True), run('synth', True))
