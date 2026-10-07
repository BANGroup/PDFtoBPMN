"""TASK-021: независимая проверка LLM на реальных парах «текст отличается» из live (без влияния на канон).
  python3 real_check.py build  -> data/canon_reeng/llm/real_pairs.json   (пары для ручного вердикта)
  python3 real_check.py run    -> data/canon_reeng/llm/real_result.json  (вердикт модели + проверка кода + сводка)
Нагрузка: строго последовательно, пауза 0,5 с, <=200 вызовов, стоп при 3 ошибках шлюза подряд."""
import os, sys, re, json, csv, time, random
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
OUT = os.path.join(REPO, 'data/canon_reeng/llm')
os.environ['FP_RUN'] = 'live'; os.environ['FP_STEP1'] = '/nonexistent'
sys.path.insert(0, os.path.join(HERE, '../reeng')); sys.path.insert(0, HERE)
import exam_compare as X

def build(n=100, seed=7):
    r = random.Random(seed)
    rows = list(csv.DictReader(open(os.path.join(REPO, 'data/canon_reeng/live/status.csv'), encoding='utf-8-sig'), delimiter=';'))
    st = json.load(open(os.path.join(REPO, 'data/canon_reeng/live/state.json')))['docs']
    pri = {'прочее': 0, 'наша ошибка': 1}
    docs = []
    for x in rows:
        d = x['doc']
        if st.get(d, {}).get('accepted'): continue
        p = os.path.join(REPO, 'data/canon_reeng/live/points', d + '.json')
        if not os.path.exists(p): continue
        nums = [q['num'] for q in json.load(open(p)).get('points', []) if q['status'] == 'текст отличается' and not q['num'].startswith('прил.')]
        if nums: docs.append((pri.get(x['class'].split('+')[0], 2), d, x['class'], nums))
    docs.sort(key=lambda t: t[0]); items = []
    pools = []
    for _, d, cl, nums in docs:
        pt = X.point_texts(d); r.shuffle(nums)
        c = [(d, cl, k, pt[k]) for k in nums if k in pt and 40 <= len(pt[k][0]) <= 2500 and len(pt[k][1]) <= 2500]
        if c: pools.append(c)
    i = 0
    while len(items) < n and any(pools):   # по кругу, чтобы не набрать всё из одного документа
        for c in pools:
            if c and len(items) < n and i < 3 + len(items) // 40:
                d, cl, k, (a, b) = c.pop(); items.append({'id': f'p{len(items)}', 'doc': d, 'class': cl, 'num': k, 'A': a, 'B': b})
        i += 1
        if i > 50: break
    json.dump(items, open(os.path.join(OUT, 'real_pairs.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(len(items), 'пар из', len({x['doc'] for x in items}), 'документов')

def toks(t):
    import pagediff
    k = pagediff.key(t)
    return k
def code_check(a, b):
    """Потерянные содержательные токены: числа/даты, отрицания, слова >=4 между A и B (в обе стороны)."""
    import pagediff
    wa = [w for w in map(pagediff.key, re.split(r'[\s/|]+', a)) if w]; wb = [w for w in map(pagediff.key, re.split(r'[\s/|]+', b)) if w]
    num = lambda w: [x for x in w if re.search(r'\d', x)]
    neg = lambda w: [x for x in w if x in ('не', 'ни', 'без')]
    big = lambda w: [x for x in w if len(x) >= 4 and not re.search(r'\d', x)]
    from collections import Counter
    out = {}
    for nm, f in (('числа', num), ('отрицания', neg), ('слова', big)):
        ca, cb = Counter(f(wa)), Counter(f(wb))
        out[nm] = {'A_only': sorted((ca - cb).elements()), 'B_only': sorted((cb - ca).elements())}
    out['flag'] = any(v['A_only'] or v['B_only'] for v in out.values())
    return out

def run():
    items = json.load(open(os.path.join(OUT, 'real_pairs.json'), encoding='utf-8'))
    mine = json.load(open(os.path.join(OUT, 'real_mine.json'), encoding='utf-8'))   # {id: [SAME|DIFF, note]}
    res, errs, calls = [], 0, 0
    for it in items:
        if calls >= 200: break
        v, rec = X.ask(it); calls += 1
        errs = errs + 1 if rec['error'] else 0
        res.append({**it, 'mine': mine[it['id']][0], 'mine_note': mine[it['id']][1], 'model': (v or {}).get('verdict'), 'reason': (v or {}).get('reason'),
                    'a_only': (v or {}).get('a_only'), 'b_only': (v or {}).get('b_only'), 'code': code_check(it['A'], it['B']), 'sec': rec['sec'], 'error': rec['error']})
        print(it['id'], mine[it['id']][0], '->', res[-1]['model'], flush=True)
        json.dump(res, open(os.path.join(OUT, 'real_result.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        if errs >= 3: print('3 ошибки шлюза подряд — СТОП'); break
        time.sleep(0.5)
    print('calls', calls)

if __name__ == '__main__':
    {'build': build, 'run': run}[sys.argv[1]]()
