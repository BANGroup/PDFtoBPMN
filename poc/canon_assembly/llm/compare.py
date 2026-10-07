"""TASK-021: сравнение пары (A — PDF, B — Word) «сначала код, потом модель». Модель канон и статусы НЕ меняет — только вердикт для отчёта.
compare_pair(A, B) -> {'result': SAME|SAME_LLM|DIFF|UNKNOWN, 'by': 'code'|'llm'|None, 'code_a_only', 'code_b_only', 'llm': {...}, 'calls': N}
  SAME      — после нормализации последовательности слов равны (модель не звали);
  SAME_LLM  — код видел различие, модель сказала «оформление»: НЕ принимается автоматически, решает человек/orchestrator;
  DIFF      — модель подтвердила различие сути; UNKNOWN — нет вердикта после 3 попыток (пустой ответ/нет JSON/CJK в reason).
Нагрузка: строго по одному вызову, пауза 0,5 с, всего <= LIMIT вызовов (счётчик в compare_calls_count.txt), стоп при 3 ошибках шлюза подряд.
Кэш вердиктов модели по паре текстов (compare_cache.json) — перезапуск не повторяет вызовы."""
import os, re, sys, json, time, hashlib, difflib
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import llm_client as L
OUT = os.path.join(L.REPO, 'data/canon_reeng/llm')
CNT = os.path.join(OUT, 'compare_calls_count.txt'); CACHE = os.path.join(OUT, 'compare_cache.json')
LIMIT = 700; PAUSE = 0.5
CJK = re.compile(r'[⺀-鿿가-힯豈-﫿぀-ヿ]')
SYSTEM = ('Ты — специалист нормоконтроля нормативной документации авиакомпании. Тебе дают два варианта одного пункта документа: '
          'A — из утверждённого PDF-эталона (текст извлечён из PDF, возможны переносы слов, разрывы строк, колонтитулы, '
          'разделители ячеек таблиц «|», другие кавычки и маркеры списков), B — из Word-копии. '
          'Определи, совпадает ли СОДЕРЖАНИЕ. Отличия только оформления (переносы, пробелы, кавычки, маркеры, ё/е, порядок ячеек таблицы, '
          'попавший колонтитул или номер страницы) — это SAME. Любое отличие сути (числа, сроки, даты, отрицание, должности, '
          'подразделения, документы, добавленные или пропущенные требования, слова, меняющие смысл) — это DIFF. '
          'Сравни тексты по словам от начала до конца: пропуск даже короткого фрагмента (слова, перечисления, придаточного) в одном из '
          'вариантов — это DIFF. Ничего не придумывай: опирайся только на два текста. Пиши только по-русски. Ответ строго JSON без пояснений вокруг: '
          '{"verdict": "SAME" | "DIFF", "reason": "кратко", "a_only": "фрагмент, который есть только в A", "b_only": "фрагмент, который есть только в B"}')


class GatewayStop(Exception): pass

# ---------- код: нормализация и сравнение
_FOOT = [re.compile(p, re.I) for p in (r'стр\.?\s*\d+\s*из\s*\d+', r'изменение\s*№\s*\d+', r'дата\s+введения\s+изменени\w*(\s+\d{1,2}\.\d{1,2}\.\d{2,4})?')]
_PT = re.compile(r'\bп\.\s*(?=\d|\w)', re.I)
def norm_tokens(t):
    t = re.sub(r'(\w)[-­]\s*\n\s*(\w)', r'\1\2', t)          # перенос «слово-\nслово»
    for p in _FOOT: t = p.sub(' ', t)
    t = t.replace('|', ' ').replace('ё', 'е').replace('Ё', 'Е').lower()
    t = _PT.sub('пункт ', t)
    t = re.sub(r'\bпунктах?\b', 'пункт', t)
    ws = []
    for w in t.split():
        w = w.strip('«»"\'“”„‹›()[]{}.,;:!?')
        if not w or re.fullmatch(r'[-–—•·▪●○■□*_/\\]+', w) or re.fullmatch(r'(\d+|[а-яa-z])\)', w): continue   # маркеры списков, «1)», «а)»
        ws.append(w)
    if ws and re.fullmatch(r'\d+(\.\d+)*\.?', ws[0]): ws = ws[1:]   # номер пункта в начале
    return ws

def code_diff(a, b):
    ta, tb = norm_tokens(a), norm_tokens(b)
    ao, bo = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op != 'equal': ao += ta[i1:i2]; bo += tb[j1:j2]
    isn = lambda w: bool(re.search(r'\d', w)); neg = lambda w: w in ('не', 'ни', 'без', 'нет')
    ca, cb = Counter(ta), Counter(tb)
    nums = {'a': sorted(x for x in (ca - cb).elements() if isn(x)), 'b': sorted(x for x in (cb - ca).elements() if isn(x))}
    negs = {'a': sorted(x for x in (ca - cb).elements() if neg(x)), 'b': sorted(x for x in (cb - ca).elements() if neg(x))}
    return {'same': ta == tb, 'a_only': ' '.join(ao), 'b_only': ' '.join(bo), 'numbers': nums, 'negations': negs}

# ---------- модель
def _count():
    try: return int(open(CNT).read().strip() or 0)
    except Exception: return 0
_state = {'fails': 0}
def _cache():
    try: return json.load(open(CACHE, encoding='utf-8'))
    except Exception: return {}

def ask_model(a, b, tag=''):
    """(verdict dict | None, число вызовов). Повтор до 2 раз при пустом ответе / без JSON / CJK в reason."""
    key = hashlib.sha1((a + '\x00' + b).encode()).hexdigest(); cache = _cache()
    if key in cache: return cache[key]['v'], 0
    msg = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': f'A (PDF):\n{a}\n\nB (Word):\n{b}'}]
    calls = 0; v = None; errored = False
    for attempt in range(3):
        if _count() >= LIMIT: raise GatewayStop(f'лимит {LIMIT} вызовов')
        ans, rec = L.chat(msg, tag='compare:' + tag); calls += 1
        n0 = _count() + 1
        with open(CNT, 'w') as f: f.write(str(n0))
        time.sleep(PAUSE)
        if rec['error']:   # ошибка шлюза: повтор не делаем (L.chat уже повторял); 3 пары подряд с ошибкой — стоп
            _state['fails'] += 1; v = None; errored = True
            if _state['fails'] >= 3: raise GatewayStop('3 ошибки шлюза подряд: ' + str(rec['error']))
            break
        _state['fails'] = 0
        v = None
        if ans:
            m = re.search(r'\{.*\}', ans, re.S)
            try: v = json.loads(m.group()) if m else None
            except Exception: v = None
        if isinstance(v, dict) and v.get('verdict') in ('SAME', 'DIFF') and not any(CJK.search(str(v.get(k) or '')) for k in ('reason', 'a_only', 'b_only')): break
        v = None
    if not errored: cache[key] = {'v': v}; json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    return v, calls

def compare_pair(a, b, tag='', use_llm=True):
    cd = code_diff(a, b)
    r = {'code_a_only': cd['a_only'], 'code_b_only': cd['b_only'], 'code_numbers': cd['numbers'], 'code_negations': cd['negations'], 'llm': None, 'calls': 0}
    if cd['same']: return {**r, 'result': 'SAME', 'by': 'code'}
    if not use_llm: return {**r, 'result': 'NOT_CHECKED', 'by': None}   # различие есть, модель не звали (лимит)
    v, n = ask_model(a, b, tag); r['llm'] = v; r['calls'] = n
    res = 'UNKNOWN' if not v else 'DIFF' if v['verdict'] == 'DIFF' else 'SAME_LLM'
    return {**r, 'result': res, 'by': 'llm' if v else None}
