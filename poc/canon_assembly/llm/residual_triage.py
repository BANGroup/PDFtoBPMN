"""TASK-021: отчёт по остатку (непринятые документы live): пункты 6+ со статусом не «совпадает» -> compare_pair. Ничего в live не меняет.
  python3 residual_triage.py [--limit-docs N]   Перезапускаемый: берёт live/points как есть (после смены сегментации пересчитывает пары; вердикты модели по тем же текстам — из кэша).
Результат: data/canon_reeng/llm/residual_triage.json (+ .md)"""
import os, sys, json, re, collections
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
os.environ['FP_RUN'] = 'live'; os.environ['FP_STEP1'] = '/nonexistent'
sys.path.insert(0, os.path.join(HERE, '../reeng')); sys.path.insert(0, HERE)
import exam_compare as X, compare as C
LIVE = os.path.join(REPO, 'data/canon_reeng/live'); OUT = C.OUT
CAP = int(os.environ.get('RESID_CAP', 12))   # пунктов на документ, отправляемых модели (остальные — NOT_CHECKED, кроме решённых кодом); повторный запуск с большим RESID_CAP добирает по кэшу
def main():
    st = json.load(open(os.path.join(LIVE, 'state.json')))['docs']
    docs = sorted(d for d, v in st.items() if not v.get('accepted'))
    resf = os.path.join(OUT, 'residual_triage.json'); res = {'docs': {}, 'stopped': None}
    for d in docs:
        p = os.path.join(LIVE, 'points', d + '.json')
        if not os.path.exists(p): res['docs'][d] = {'note': 'нет live/points'}; continue
        pts = [q for q in json.load(open(p)).get('points', []) if q['status'] != 'совпадает' and not q['num'].startswith('прил.')]
        try: pt = X.point_texts(d)
        except Exception as e: res['docs'][d] = {'note': f'ошибка текстов: {e}'}; continue
        e = {'points': [], 'counts': collections.Counter(), 'no_text': []}; sent = 0
        for q in pts:
            if q['num'] not in pt: e['no_text'].append({'num': q['num'], 'status': q['status']}); continue
            a, b = pt[q['num']]
            cached = C.code_diff(a, b)['same'] or C._cache().get(__import__('hashlib').sha1((a + '\x00' + b).encode()).hexdigest())
            try: r = C.compare_pair(a, b, d + ':' + q['num'], use_llm=bool(cached) or sent < CAP)
            except C.GatewayStop as ex: res['stopped'] = f'{d} {q["num"]}: {ex}'; break
            sent += 0 if cached else 1
            e['counts'][r['result']] += 1
            e['points'].append({'num': q['num'], 'status': q['status'], 'result': r['result'], 'code_a_only': r['code_a_only'][:300], 'code_b_only': r['code_b_only'][:300],
                                'llm_reason': (r['llm'] or {}).get('reason'), 'A_len': len(a), 'B_len': len(b)})
        e['counts'] = dict(e['counts']); res['docs'][d] = e
        json.dump(res, open(resf, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); print(d, e['counts'], 'без текста', len(e['no_text']), flush=True)
        if res['stopped']: print('СТОП', res['stopped']); break
    tot = collections.Counter()
    for e in res['docs'].values(): tot.update(e.get('counts', {}))
    res['total'] = dict(tot); json.dump(res, open(resf, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    md = ['# Остаток: разбор непринятых документов (код + модель v4.1-flash)', '',
          'SAME — код: после нормализации текст равен. SAME_LLM — код видит различие, модель считает его оформлением (НЕ принято автоматически, нужен человек). DIFF — различие по сути. UNKNOWN — нет вердикта.', '',
          f'Всего пунктов: {dict(tot)}; вызовов модели за сессию: {C._count()}.' + (f' ОСТАНОВЛЕНО: {res["stopped"]}' if res['stopped'] else ''), '',
          '| Документ | SAME | SAME_LLM | DIFF | UNKNOWN | без текста | пример DIFF |', '|---|---|---|---|---|---|---|']
    for d, e in res['docs'].items():
        c = e.get('counts', {}); ex = next((p for p in e.get('points', []) if p['result'] == 'DIFF'), None)
        exs = (f"п.{ex['num']}: A−«{ex['code_a_only'][:60]}» B−«{ex['code_b_only'][:60]}»").replace('|', '/') if ex else e.get('note', '')
        md.append(f"| {d} | {c.get('SAME',0)} | {c.get('SAME_LLM',0)} | {c.get('DIFF',0)} | {c.get('UNKNOWN',0)} | {len(e.get('no_text', []))} | {exs} |")
    open(os.path.join(OUT, 'residual_triage.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
if __name__ == '__main__': main()
