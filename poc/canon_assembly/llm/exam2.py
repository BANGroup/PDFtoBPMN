"""Экзамен 2 (TASK-021): трудный набор, устойчивость, сравнение моделей. Строго последовательно, пауза 0,5 с, лимит вызовов, стоп при 3 ошибках подряд.
  python3 exam2.py build | run <имя_набора> <модель> <метка> [прогон] | stab
"""
import os, sys, re, json, random, time, statistics
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import exam_compare as E
OUT = E.OUT; LIMIT = 600; CNT = os.path.join(OUT, 'exam2_calls_count.txt')
M1, M2 = 'ag.yc/deepseek-v4-flash/latest', 'deepseek-v4.1-flash'   # 06.10 имена ag.yc/…; с 07.10 на шлюзе только deepseek-v4.1-flash

def sents(t): return [s for s in re.split(r'(?<=[.;:])\s+', t) if s]
def cut(t, r, n, k):  # граница по словам
    ws = t.split(' ');  return ws
# ---- DIFF-тонкие
def x_del_short(t, r):
    ms = list(re.finditer(r'\b(не|или|и|в течение|также|только|все|каждый)\s', t))
    ms = [m for m in ms if m.start() > 0]
    if not ms: return None
    m = r.choice(ms); return t[:m.start()] + t[m.end():].lstrip() if False else t[:m.start()] + ' ' + t[m.end():], f'удалено «{m.group().strip()}»'
def x_digit(t, r):
    ms = list(re.finditer(r'\d+', t))
    if len(t) <= 800 or not ms: return None
    m = r.choice(ms); s = m.group(); i = r.randrange(len(s)); d = str((int(s[i]) + r.randint(1, 8)) % 10)
    return t[:m.start()] + s[:i] + d + s[i+1:] + t[m.end():], f'цифра {s} -> {s[:i]+d+s[i+1:]}'
UNITS = [('отдел', 'управление'), ('управление', 'отдел'), ('департамент', 'дирекция'), ('служба', 'отдел'), ('дирекция', 'департамент'), ('отдела', 'управления'), ('управления', 'отдела'), ('службы', 'отдела'), ('департамента', 'дирекции')]
def x_unit(t, r):
    c = [(a, b) for a, b in UNITS if re.search(r'\b' + a + r'\b', t)]
    if not c: return None
    a, b = r.choice(c); return re.sub(r'\b' + a + r'\b', b, t, count=1), f'«{a}» -> «{b}»'
def x_swap(t, r):
    m = re.search(r'([Ее]сли [^,.;]{5,80}), ([^,.;]{5,80})([.;])', t)
    if not m: return None
    c1, c2 = m.group(1), m.group(2)
    return t[:m.start()] + 'Если ' + c2[0].lower() + c2[1:] + ', ' + c1[5:] + m.group(3) + t[m.end():], 'условие и следствие «если/то» переставлены'
def x_dropitem(t, r):
    p = re.split(r'(?<=;)\s', t)
    if len(p) < 3: return None
    i = r.randrange(1, len(p) - 1); return ' '.join(p[:i] + p[i+1:]), 'удалён пункт перечисления: «' + p[i][:50] + '»'
DIFFS = [x_del_short, x_digit, x_unit, x_swap, x_dropitem]
# ---- SAME-трудные
def y_table(t, r):
    s = sents(t)
    if len(s) < 4: return None
    k = max(2, len(s) // 3); ch = [' '.join(s[i:i + k]) for i in range(0, len(s), k)]
    o = ch[:]; r.shuffle(o)
    if o == ch: o = ch[::-1]
    return ' | '.join(o), 'ячейки таблицы в другом порядке', ch   # B остаётся a
def y_header(t, r):
    ws = t.split(' '); i = r.randrange(len(ws) // 3, 2 * len(ws) // 3 + 1)
    h = 'Авиакомпания «Utair» ' + 'Система менеджмента качества Положение о процессе управления документацией Редакция 4 Стр. 23 из 71 Не подлежит копированию без разрешения'
    return ' '.join(ws[:i] + [h] + ws[i:]), 'длинный колонтитул внутри'
def y_wrap(t, r):
    ws = t.split(' '); out = []; i = 0
    while i < len(ws): k = r.randint(5, 10); out.append(' '.join(ws[i:i + k])); i += k
    return '\n'.join(out), 'разрывы строк каждые 5-10 слов'
def y_marker(t, r):
    p = re.split(r'(?<=;)\s|\s(?=\d+\)\s)', t)
    if len(p) < 3: return None
    return '\n'.join('• ' + re.sub(r'^\d+[).]\s*', '', x) for x in p), 'маркеры вместо нумерации'
def y_abbr(t, r):
    n = re.sub(r'\bпунктом\b', 'п.', re.sub(r'\bпункте\b', 'п.', re.sub(r'\bпункт\b', 'п.', t)))
    n = n.replace('Пункт ', 'п. ')
    return (n, 'пункт -> п.') if n != t else None
def y_yo(t, r):
    n = t
    for a, b in [('еще', 'ещё'), ('объем', 'объём'), ('учет', 'учёт'), ('отчет', 'отчёт'), ('отчеты', 'отчёты'), ('осуществляется', 'осуществляется')]:
        if re.search(r'\b' + a + r'\b', t, re.I): n = re.sub(r'\b' + a + r'\b', b, t); break
    return (n, 'ё/е') if n != t else None
SAMES = [y_table, y_header, y_wrap, y_marker, y_abbr, y_yo]

def build(seed=20261006):
    r = random.Random(seed); pool = json.load(open('/tmp/pool.json')) if os.path.exists('/tmp/pool.json') else None
    if pool is None: raise SystemExit('нет /tmp/pool.json')
    pool = [p for p in pool if len(p[2]) <= 4000]
    r.shuffle(pool); items = []; used = set()
    long_ = [p for p in pool if len(p[2]) > 800]; short = [p for p in pool if len(p[2]) <= 800]
    def make(kind, fs, n, need_long):
        got = {f.__name__: 0 for f in fs}; per = n // len(fs)
        for f in fs:
            for d, num, a in (long_ if (need_long or f.__name__ in ('x_digit', 'y_header', 'y_wrap')) else pool):
                if got[f.__name__] >= per: break
                if (d, num) in used: continue
                if f.__name__ in ('y_header', 'y_wrap') and len(a) < 300: continue
                res = f(a, r)
                if not res: continue
                used.add((d, num)); got[f.__name__] += 1
                if kind == 'SAME':
                    A, what = res[0], res[1]; B = a
                else: A, B, what = a, res[0], res[1]
                if r.random() < .5 and kind == 'DIFF': A = a
                items.append({'id': f'{kind[0].lower()}{len(items)}', 'doc': d, 'num': num, 'A': A, 'B': B, 'gold': kind, 'what': what, 'type': f.__name__, 'len': len(a)})
        return got
    g1 = make('DIFF', DIFFS, 75, False); g2 = make('SAME', SAMES, 75, False)
    print(g1, g2, len(items))
    json.dump(items, open(os.path.join(OUT, 'exam2_hard.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def calls_total(): return int(open(CNT).read()) if os.path.exists(CNT) else 0
def run(setname, model, label, items=None, run_no=1):
    items = items or json.load(open(os.path.join(OUT, setname + '.json'), encoding='utf-8'))
    res = []; fails = 0
    for it in items:
        if calls_total() >= LIMIT: print('ЛИМИТ 600'); break
        v, rec = E.ask(it, model); n_ = calls_total() + 1; open(CNT, 'w').write(str(n_))
        bad = bool(rec['error']); fails = fails + 1 if bad else 0
        txt = json.dumps(v or {}, ensure_ascii=False) + (rec.get('answer') or '')
        res.append({**it, 'verdict': (v or {}).get('verdict'), 'reason': (v or {}).get('reason'), 'a_only': (v or {}).get('a_only'), 'b_only': (v or {}).get('b_only'),
                    'cjk': bool(re.search(r'[一-鿿]', txt)), 'sec': rec['sec'], 'tokens': (rec.get('usage') or {}).get('total_tokens'), 'error': rec['error'], 'run': run_no})
        print(it['id'], it['gold'], '->', res[-1]['verdict'], res[-1]['sec'], flush=True)
        if fails >= 3: print('СТОП: 3 ошибки шлюза подряд'); break
        time.sleep(0.5)
    json.dump(res, open(os.path.join(OUT, f'exam2_{label}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return res

if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'build': build()
    elif a[1] == 'run': run(a[2], a[3], a[4])
    elif a[1] == 'stab':   # 50 пар (25 базовых gold + 25 трудных); прогон 1 берётся из уже сделанных, добавляются 2 и 3
        base = [x for x in json.load(open(os.path.join(OUT, 'exam2_base.json'))) if x['gold']]
        hard = json.load(open(os.path.join(OUT, 'exam2_hard_v4flash.json')))
        r = random.Random(7); pick = r.sample(base, 25) + r.sample(hard, 25)
        pick = [{k: x[k] for k in ('id', 'doc', 'num', 'A', 'B', 'gold', 'what')} for x in pick]
        for n in (2, 3): run(None, M1, f'stab_run{n}', pick, n)
