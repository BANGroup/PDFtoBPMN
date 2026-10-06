"""Экзамен LLM на задаче «сравнить пункт эталона PDF и канона Word» (TASK-021, контроль orchestrator; без влияния на канон).

Пары с известным ответом строятся из совпадающих пунктов готовых документов:
  SAME   — точная копия (контроль) или копия с искажениями ОФОРМЛЕНИЯ, как у PDF/таблиц (переносы, разделители ячеек,
           кавычки, маркеры, ё/е, колонтитул посреди текста, пробелы);
  DIFF   — копия с изменением СУТИ (число/срок, «не», должность, удалено/добавлено требование).
Плюс реальные пары «текст отличается» без ответа — для ручной проверки.
  python3 exam_compare.py build   -> data/canon_reeng/llm/exam.json
  python3 exam_compare.py run     -> data/canon_reeng/llm/exam_result.json + сводка
"""
import os, sys, re, json, random, csv
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
OUT = os.path.join(REPO, 'data/canon_reeng/llm')
os.environ.setdefault('FP_RUN', 'full4'); os.environ.setdefault('FP_STEP1', '/nonexistent')
sys.path.insert(0, os.path.join(HERE, '../reeng')); sys.path.insert(0, HERE)

SYSTEM = ('Ты — специалист нормоконтроля нормативной документации авиакомпании. Тебе дают два варианта одного пункта документа: '
          'A — из утверждённого PDF-эталона (текст извлечён из PDF, возможны переносы слов, разрывы строк, колонтитулы, '
          'разделители ячеек таблиц «|», другие кавычки и маркеры списков), B — из Word-копии. '
          'Определи, совпадает ли СОДЕРЖАНИЕ. Отличия только оформления (переносы, пробелы, кавычки, маркеры, ё/е, порядок ячеек таблицы, '
          'попавший колонтитул или номер страницы) — это SAME. Любое отличие сути (числа, сроки, даты, отрицание, должности, '
          'подразделения, документы, добавленные или пропущенные требования, слова, меняющие смысл) — это DIFF. '
          'Сравни тексты по словам от начала до конца: пропуск даже короткого фрагмента (слова, перечисления, придаточного) в одном из '
          'вариантов — это DIFF. Ничего не придумывай: опирайся только на два текста. Пиши только по-русски. Ответ строго JSON без пояснений вокруг: '
          '{"verdict": "SAME" | "DIFF", "reason": "кратко", "a_only": "фрагмент, который есть только в A", "b_only": "фрагмент, который есть только в B"}')


def point_texts(doc):
    """{num: (текст PDF, текст Word)} для пунктов 6+ документа (как в point_fingerprint.run_doc)."""
    import point_fingerprint as F
    pdfs = F.ref_pdf(doc)
    ct = os.path.join(F.FULL, 'out', doc, 'canon_text.txt')
    if len(pdfs) != 1 or not os.path.exists(ct): return {}
    pl, pl_en, fl, pgs, bad = F.pdf_lines(pdfs[0]); wl = F.word_lines(ct)
    pp, _, _ = F.segment(pl, allow_dup=True); wp, _, _ = F.segment(wl, allow_dup=True)
    if not pp or not wp: return {}
    W = {q['num']: q for q in wp}
    txt = lambda q: ' '.join(l.lstrip(F.TCELL).strip() for l in q['lines'])
    return {q['num']: (txt(q), txt(W[q['num']])) for q in pp if q['num'] in W}


# ---- искажения оформления (SAME)
def f_hyphen(t, r):
    ws = t.split(' '); i = r.randrange(len(ws))
    w = ws[i]
    if len(w) > 6: ws[i] = w[:len(w) // 2] + '-\n' + w[len(w) // 2:]
    return ' '.join(ws)
def f_cells(t, r): return re.sub(r'(?<=[а-яa-z]) (?=[А-Я])', ' | ', t, count=3)
def f_quotes(t, r): return t.replace('«', '"').replace('»', '"')
def f_yo(t, r): return t.replace('ё', 'е') if 'ё' in t else t.replace('пункт', 'п.', 1).replace('Авиакомпании', 'авиакомпании', 1)   # реальные варианты написания
def f_bullets(t, r): return re.sub(r'(^|\s)[-–—]\s', lambda m: m.group(1) + '• ', t)
def f_header(t, r):
    ws = t.split(' '); i = r.randrange(1, max(2, len(ws)))
    return ' '.join(ws[:i] + ['Стр. 17 из 64', 'Изменение № 3'] + ws[i:])
def f_spaces(t, r): return re.sub(r' ', '  ', t, count=4).replace(', ', ' ,', 1)
FORMAT = [f_hyphen, f_cells, f_quotes, f_yo, f_bullets, f_header, f_spaces]


# ---- изменения сути (DIFF); каждая возвращает (текст, описание) или None
def d_number(t, r):
    m = list(re.finditer(r'\b\d{1,3}\b', t))
    if not m: return None
    x = r.choice(m); n = int(x.group()); v = str(n + r.choice([1, 2, 5, 10]))
    return t[:x.start()] + v + t[x.end():], f'число {n} -> {v}'
def d_negation(t, r):
    m = list(re.finditer(r'\b(должен|должна|должны|обязан|обязана|допускается|разрешается|осуществляет|проводит|выполняет|предоставляет|направляет)\b', t))
    if not m: return None
    x = r.choice(m); return t[:x.start()] + 'не ' + t[x.start():], 'вставлено «не» перед «' + x.group() + '»'
def d_role(t, r):
    roles = ['начальник', 'директор', 'заместитель', 'руководитель', 'специалист', 'инженер', 'менеджер', 'командир']
    m = [x for x in re.finditer(r'\b(' + '|'.join(roles) + r')\w*', t, re.I)]
    if not m: return None
    x = r.choice(m); new = r.choice([w for w in ['бухгалтер', 'диспетчер', 'юрист', 'аудитор'] ])
    return t[:x.start()] + new + t[x.end():], f'«{x.group()}» -> «{new}»'
def d_drop(t, r):
    parts = re.split(r'(?<=[,;])\s', t)
    if len(parts) < 3: return None
    i = r.randrange(1, len(parts)); return ' '.join(parts[:i] + parts[i + 1:]), 'удалено: «' + parts[i][:60] + '»'
def d_add(t, r):
    s = r.choice([' Срок исполнения — не позднее 3 рабочих дней.', ' Согласование с юридическим департаментом обязательно.',
                  ' Копия направляется в департамент безопасности полётов.'])
    return t + s, 'добавлено: «' + s.strip() + '»'
def d_time(t, r):
    m = list(re.finditer(r'\b(ежедневно|ежемесячно|ежегодно|ежеквартально|еженедельно)\b', t))
    if not m: return None
    x = r.choice(m); new = {'ежедневно': 'еженедельно', 'ежемесячно': 'ежеквартально', 'ежегодно': 'ежемесячно', 'ежеквартально': 'ежегодно', 'еженедельно': 'ежедневно'}[x.group()]
    return t[:x.start()] + new + t[x.end():], f'«{x.group()}» -> «{new}»'
CONTENT = [d_number, d_negation, d_role, d_drop, d_add, d_time]


def build(n_same=30, n_diff=30, n_ctrl=10, n_real=20, seed=20261005):
    r = random.Random(seed)
    rows = list(csv.DictReader(open(os.path.join(REPO, 'data/canon_reeng/full4/summary.csv'), encoding='utf-8-sig'), delimiter=';'))
    ready = [x['doc_num'] for x in rows if x['status'] == 'ready' and not x['parts'] and not x['doc_num'].startswith('ИОТ')]
    r.shuffle(ready)
    pool = []
    for d in ready[:40]:
        for num, (a, b) in point_texts(d).items():
            if 120 <= len(a) <= 1500 and a.replace(' ', '') == b.replace(' ', ''): pool.append((d, num, a))
    r.shuffle(pool)
    items, k = [], 0
    for d, num, a in pool[:n_ctrl]: items.append({'id': f'c{k}', 'doc': d, 'num': num, 'A': a, 'B': a, 'gold': 'SAME', 'what': 'точная копия'}); k += 1
    for d, num, a in pool[n_ctrl:n_ctrl + n_same]:
        fs = r.sample(FORMAT, 2); t = a
        for f in fs: t = f(t, r)
        items.append({'id': f's{k}', 'doc': d, 'num': num, 'A': t, 'B': a, 'gold': 'SAME', 'what': 'оформление: ' + ', '.join(f.__name__ for f in fs)}); k += 1
    for d, num, a in pool[n_ctrl + n_same:]:
        if sum(1 for x in items if x['gold'] == 'DIFF') >= n_diff: break
        for f in r.sample(CONTENT, len(CONTENT)):
            res = f(a, r)
            if res:
                t, what = res; fa = r.choice(FORMAT)   # плюс одно искажение оформления, чтобы суть не выдавал сам шум
                items.append({'id': f'd{k}', 'doc': d, 'num': num, 'A': fa(a, r), 'B': t, 'gold': 'DIFF', 'what': what + '; оформление: ' + fa.__name__}); k += 1
                break
    # реальные «текст отличается» из live (ответ неизвестен — ручная проверка)
    real = []
    for x in rows:
        if x['status'] != 'not_ready' or x['parts']: continue
        p = os.path.join(REPO, 'data/canon_reeng/full4/points', x['doc_num'] + '.json')
        if not os.path.exists(p): continue
        nums = [q['num'] for q in json.load(open(p)).get('points', []) if q['status'] == 'текст отличается' and not q['num'].startswith('прил.')]
        if nums: real.append((x['doc_num'], nums))
    r.shuffle(real)
    for d, nums in real:
        if sum(1 for x in items if x['gold'] is None) >= n_real: break
        pt = point_texts(d); num = r.choice(nums)
        if num in pt and len(pt[num][0]) <= 3000: items.append({'id': f'r{k}', 'doc': d, 'num': num, 'A': pt[num][0], 'B': pt[num][1], 'gold': None, 'what': 'реальный случай'}); k += 1
    json.dump(items, open(os.path.join(OUT, 'exam.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    import collections; print(collections.Counter(str(x['gold']) for x in items), '->', os.path.join(OUT, 'exam.json'))


def ask(item, model=None):
    import llm_client as L
    msg = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': f"A (PDF):\n{item['A']}\n\nB (Word):\n{item['B']}"}]
    ans, rec = L.chat(msg, **({'model': model} if model else {}), tag='exam:' + item['id'])
    v = None
    if ans:
        m = re.search(r'\{.*\}', ans, re.S)
        try: v = json.loads(m.group()) if m else None
        except Exception: v = None
    return v, rec


def run(model=None):
    items = json.load(open(os.path.join(OUT, 'exam.json'), encoding='utf-8'))
    res = []
    for it in items:
        v, rec = ask(it, model)
        res.append({**it, 'verdict': (v or {}).get('verdict'), 'reason': (v or {}).get('reason'), 'a_only': (v or {}).get('a_only'), 'b_only': (v or {}).get('b_only'),
                    'sec': rec['sec'], 'tokens': (rec.get('usage') or {}).get('total_tokens'), 'error': rec['error'], 'served_model': rec.get('served_model')})
        print(it['id'], it['gold'], '->', res[-1]['verdict'], f"{rec['sec']}с", flush=True)
    json.dump(res, open(os.path.join(OUT, 'exam_result.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    g = [x for x in res if x['gold']]
    ok = sum(1 for x in g if x['verdict'] == x['gold'])
    by = {k: (sum(1 for x in g if x['gold'] == k and x['verdict'] == k), sum(1 for x in g if x['gold'] == k)) for k in ('SAME', 'DIFF')}
    print(f'точность {ok}/{len(g)}; SAME {by["SAME"]}; DIFF {by["DIFF"]}; без ответа {sum(1 for x in res if not x["verdict"])}; '
          f'время {sum(x["sec"] for x in res):.0f} с; токенов {sum(x["tokens"] or 0 for x in res)}')


if __name__ == '__main__':
    {'build': build, 'run': run}[sys.argv[1]](*sys.argv[2:])
