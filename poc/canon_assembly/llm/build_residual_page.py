"""Страница «Остаток канона БНД» (нейтральная вёрстка-источник; бренд Utair для портала накладывает Publisher todo).

Источники: data/canon_reeng/live/{state.json,status.csv}, llm/residual_triage.json (пары пунктов PDF↔Word: код + модель),
лишний текст — nightly_canon.extra_text. Группы: 1 — сложная сборка, 2 — расхождения/оформление/лишний текст, 3 — нет базы/скан.
  python3 build_residual_page.py   -> data/canon_reeng/qa/residual_qa.html
"""
import os, sys, json, csv, html, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '../reeng')); sys.argv = sys.argv[:1]
import nightly_canon as N
R = os.path.abspath(os.path.join(HERE, '../../../data/canon_reeng'))
e = lambda s: html.escape(str(s or ''))
LAB = {'DIFF': ('Проверить', 'diff'), 'SAME_LLM': ('Подтвердить', 'same'), 'UNKNOWN': ('Нет вердикта', 'unk'),
       'NOT_CHECKED': ('Различие (код)', 'unk')}


def main():
    st = json.load(open(R + '/live/state.json'))
    S = {x['doc']: x for x in csv.DictReader(open(R + '/live/status.csv', encoding='utf-8-sig'), delimiter=';')}
    tri = json.load(open(R + '/llm/residual_triage.json'))['docs']
    g1, g2, g3 = [], [], []
    for d, s in st['docs'].items():
        if s.get('accepted'): continue
        r = S.get(d, {}); i = lambda k: int(r.get(k) or 0) if str(r.get(k) or '').isdigit() else 0
        if r.get('status') in ('no_base_word', 'scan_skipped'): g3.append(d)
        elif s.get('review', '').startswith('лишний'): g2.append(d)
        elif r.get('status') in ('multi_part', 'base_outdated') or i('A6') or i('nums6') or i('dup_bad') or d.startswith('TPM'): g1.append(d)
        else: g2.append(d)

    def block(d):
        s, r = st['docs'][d], S.get(d, {})
        pts = [p for p in tri.get(d, {}).get('points', []) if p.get('result') in LAB][:8]
        ex = N.extra_text(d) if s.get('review', '').startswith('лишний') else {}
        chips = ''.join(f"<span class='chip {LAB[k][1]}'>{LAB[k][0]}: {n}</span>" for k in LAB
                        for n in [sum(1 for p in pts if p['result'] == k)] if n)
        if ex.get('paras_extra'): chips = f"<span class='chip diff'>Лишний текст: {ex['paras_extra']}</span>" + chips
        rows = ''.join(f"<tr><td class='num'>{e(p['num'])}</td><td><span class='chip {LAB[p['result']][1]}'>{LAB[p['result']][0]}</span></td>"
                       f"<td class='pdf'>{e(p.get('code_a_only')) or '—'}</td><td class='word'>{e(p.get('code_b_only')) or '—'}</td>"
                       f"<td>{e(p.get('llm_reason')) or '—'}</td></tr>" for p in pts)
        extra = ''.join(f"<li>{e(x)}</li>" for x in (ex.get('examples') or [])[:6])
        body = (f"<p class='note'><b>Текст в каноне, которого нет в утверждённом PDF:</b></p><ul class='extra'>{extra}</ul>" if extra else '') + \
               (f"<div class='scroll'><table><thead><tr><th>Пункт</th><th>Действие</th><th>Только в PDF</th><th>Только в Word</th><th>Пояснение модели</th></tr></thead><tbody>{rows}</tbody></table></div>" if rows else '') or \
               "<p class='note'>Пар для сравнения нет: сверка по пунктам для этого документа не построена (нет раздела 6, многочастный документ, скан или нет базы Word).</p>"
        pm = f"пункты 6+: {e(r.get('pts_match'))} из {e(r.get('pts_total'))}" if r.get('pts_total') not in (None, '', '0') else 'пункты не сопоставлены'
        return f"<details><summary><span class='code'>{e(d)}</span><span class='ttl'>{e(s.get('title'))}</span><span class='meta'>{pm}</span><span class='chips'>{chips}</span></summary>{body}</details>"

    acc = sum(1 for s in st['docs'].values() if s.get('accepted')); tot = len(st['docs'])
    secs = [('Расхождения, лишний текст, оформление', 'Решение команды качества', g2,
             'Сборка здесь не мешает: правки Word против утверждённого PDF, лишний текст (старая редакция, текст протокола) или особенности оформления.'),
            ('Сложные случаи сборки', 'Дорабатывается в коде', g1,
             'Часть различий создаёт наша сборка, документы дорабатываются. Среди показанных пар есть и настоящие расхождения.'),
            ('Нет базы Word или скан', 'Ручное решение', g3, 'Канон из Word собрать нельзя: нет исходного Word-файла или эталон отсканирован.')]
    intro = (f"<h1>Остаток канона БНД</h1><p class='lead'>Состояние на {datetime.date.today():%d.%m.%Y}. Принято {acc} из {tot}, ниже — {tot - acc} непринятых.</p>"
             "<p>Документ принят, если в каноне есть весь текст утверждённого PDF и нет текста сверх него. Для непринятых показаны пункты разделов 6 и далее, где тексты расходятся, и лишний текст. "
             "Различие находит код; пояснение даёт корпоративная модель, она ничего не меняет. <b>Проверить</b> — похоже на настоящее расхождение; "
             "<b>Подтвердить</b> — похоже на оформление; <b>Различие (код)</b> — модель не проверяла. В таблицах — слова только в PDF и только в Word.</p>")
    out = "<title>Остаток канона БНД</title>" + intro + ''.join(
        f"<h2>{e(h)}</h2><div class='eyebrow'>{e(k)} · {len(ds)}</div><p class='lead'>{e(n)}</p>" + ''.join(block(d) for d in ds) for h, k, ds, n in secs)
    os.makedirs(R + '/qa', exist_ok=True)
    open(R + '/qa/residual_qa.html', 'w', encoding='utf-8').write(out)
    print(f'{tot - acc} непринятых: {len(g1)}/{len(g2)}/{len(g3)} -> {R}/qa/residual_qa.html')


if __name__ == '__main__': main()
