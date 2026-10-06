#!/usr/bin/env python3
"""Итоговый статус каждого документа прогона (без пересборки): <run>/status.csv и <run>/status.md. Без ИИ, Word не нужен.

  python3 status_report.py [--run data/canon_reeng/full3] [--no-recheck]

Читает: summary.csv, out/<doc>/{status,verify,plan,check}.json (части — out/<doc>/part_N/), points/<doc>.json (point_fingerprint),
classify/<doc>.json (classify_missing; нет — считается здесь). Статусы:
  ready            сборка прошла проверку (в т. ч. повторы, разорванные колонтитулом эталона — verify_canon);
  ready_core       «годен по сути»: пункты 6+ (без приложений) совпали на 100 %, ненайденных строк класса A/B/U и неверных номеров
                   в разделах >=6 нет (замечания разделов 1-5, надписи схем E и объекты C не мешают — они перечислены);
                   приложения (формы) сверяются только по числу: приложений в эталоне столько же, сколько в Word
                   (решение human 03.10.2026), строки внутри приложений не мешают;
  not_ready        есть класс: наша ошибка / расхождение документа / двуязычный метод / прочее;
  scan_skipped     битый текстовый слой эталона (>30 % строк контента: латиница-мусор или смесь кириллицы с латиницей в слове;
                   либо content_start_not_found при >10 % мусора) — из оценки исключён;
  base_outdated    база Word не содержит значительной части эталона (>=25 % страниц «страница без штампа не найдена в базе» /
                   «штамп 0, но есть лист замены»; для документов из частей — в большинстве частей);
  multi_part       документ из нескольких частей-эталонов, не готов (оценка по частям — в status.json документа);
  no_base_word, changed_during_run  — как в summary.csv.
Раздел строки эталона — по последнему заголовку верхнего уровня «N ТЕКСТ» (classify_missing.top_section).
"""
import os, sys, re, csv, json, glob, argparse, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
EXCL = ('ИОТ', 'РПП', 'РОТО')
GAP_TYPES = ('страница без штампа не найдена в базе', 'штамп 0, но есть лист замены')
CLASSES = ('наша ошибка', 'расхождение документа', 'двуязычный метод', 'прочее')


def jload(p):
    try: return json.load(open(p, encoding='utf-8'))
    except Exception: return None


def part_dirs(od):
    return sorted(glob.glob(od + '/part_*'), key=lambda x: int(re.search(r'part_(\d+)', x).group(1))) or [od]


# ------------------------------------------------------------ scan_skipped / base_outdated
def _mixed(l):
    ws = [w for w in re.findall(r'\w+', l) if len(w) >= 3]
    bad = sum(1 for w in ws if re.search('[A-Za-z]', w) and re.search('[А-Яа-яЁё]', w))
    return bad >= 2 or bool(re.search(r'[Il1]{3,}|[<>{}|]\w', l))


def garbage_share(od):
    """(доля мусорных строк контента эталона, content_start_found) по всем частям документа."""
    import pagediff as P
    bad = tot = 0; found = True
    for pd in part_dirs(od):
        pl = jload(pd + '/plan.json'); ck = jload(pd + '/check.json')
        if ck: found = found and ck.get('metrics', {}).get('content_start_found', True)
        if not pl or not os.path.exists(pl.get('canon_pdf', '')): continue
        pages = P.canon_pages(pl['canon_pdf'])
        cnt = collections.Counter(k for p in pages for k in {P.key(l) for l in p['lines']})
        head = {k for k, c in cnt.items() if c > 0.3 * len(pages)}
        for p in pages:
            for l in p['lines']:
                if P.key(l) in head or len(P.key(l)) < 12: continue
                tot += 1; bad += bool(P.garbage(l) or _mixed(l))
    return bad / max(tot, 1), found


def gap_share(od):
    """(доля страниц эталона с дефектом «нет базы страницы» по документу, доля частей, где она >=25 %, число частей)."""
    pages = gap = 0; hot = 0; ps = part_dirs(od)
    for pd in ps:
        pl = jload(pd + '/plan.json')
        if not pl: continue
        n = len(pl.get('pages') or []) or 1
        g = sum(1 for x in pl.get('defects', []) if x.get('type') in GAP_TYPES)
        pages += n; gap += g; hot += g >= 0.25 * n
    return gap / max(pages, 1), hot / max(len(ps), 1), len(ps)


def is_base_outdated(od):
    share, hot, nparts = gap_share(od)
    if nparts == 1: return False
    own = 0; pages = 0   # только «страница без штампа не найдена в базе»
    for pd in part_dirs(od):
        pl = jload(pd + '/plan.json') or {}
        pages += len(pl.get('pages') or []); own += sum(1 for x in pl.get('defects', []) if x.get('type') == GAP_TYPES[0])
    return (own / max(pages, 1) >= 0.25) or (nparts >= 5 and share >= 0.25 and hot > 0.5)


# ------------------------------------------------------------ повторное решение по повторам (verify_canon)
def recheck_dups(run, doc):
    """verify_canon заново (повторы, разорванные колонтитулом эталона, теперь допустимы). -> dict verify или None (источник .doc без .docx)."""
    import verify_canon as V
    od = os.path.join(run, 'out', doc); pl = jload(od + '/plan.json')
    b = pl['base_src']
    if b.lower().endswith('.doc'): b = b + 'x' if os.path.exists(b + 'x') else None
    if not b: return None
    srcs = [b] + sorted(glob.glob(os.path.join(run, 'src', doc, 'amendments/**/*.docx'), recursive=True))
    return V.verify(os.path.join(run, 'src', doc), od + '/canon_text.txt', od + '/canon.docx', srcs)


def _cap_mem():
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (int(float(os.environ.get('CLASSIFY_MEM_GB', '5')) * 2**30),) * 2)


def _job(a):
    kind, run, doc = a
    try:
        import classify_missing as C
        if kind == 'scan': return a, garbage_share(os.path.join(run, 'out', doc))
        if kind == 'cls': return a, C.classify_doc(doc, run)
        if kind == 'dup': return a, recheck_dups(run, doc)
    except Exception as e: return a, {'error': f'{type(e).__name__}: {e}'}


# ------------------------------------------------------------ статус документа
def judge(doc, row, pts, cls, scan, outdated, dupfix):
    """-> dict(status, class, classes, note, example, поля счётчиков)."""
    r = {'status': row['status'], 'class': '', 'classes': '', 'note': '', 'example': ''}
    if row['status'] != 'not_ready': return r
    if scan and (scan[0] > 0.3 or (not scan[1] and scan[0] > 0.1)):
        r.update(status='scan_skipped', note=f'битых строк эталона {scan[0]:.0%}; заголовок «1 …» найден: {"да" if scan[1] else "нет"}'); return r
    if outdated: r.update(status='base_outdated', note='в базе Word нет значительной части страниц эталона (дефекты плана)'); return r
    if row['parts']: r.update(status='multi_part', note='части: ' + row['parts'][:120]); return r
    if dupfix is not None and not dupfix.get('error') and dupfix['lines'] > 0 and dupfix['missing'] == 0 and dupfix['numbered_bad'] == 0 \
            and dupfix['duplicates'] == 0 and dupfix['frozen_numbers'] == 0:
        r.update(status='ready', note=f"повторов, разорванных колонтитулом/ячейкой эталона: {dupfix['duplicates_explained']} (допустимо)"); return r
    import point_fingerprint as F
    if not cls or cls.get('error') or cls.get('multi_part'): r.update(note='классификация не получена: ' + (cls or {}).get('error', '—')); r['class'] = 'не определён'; return r
    tot, ok, _ = F.summarize(pts) if pts and pts.get('points') else (0, 0, {})
    known = any(m['scope'] != 'не определён' for m in cls['missing'] + cls['numbers'])
    # раздел не определён = до заголовка «1 …» (титул, лист регистрации) — технический; если разделы не определились нигде, считаем осторожно как >=6
    is6_all = (lambda m: m['scope'] == 'суть (>=6)') if known else (lambda m: m['scope'] != '1-5')
    is6 = lambda m: is6_all(m) and m.get('section') != 'П'   # приложения — только по числу (ниже)
    apps = [p for p in (pts or {}).get('points', []) if F.is_app(p)]
    apps_pdf = sum(p['status'] != 'только Word' for p in apps); apps_word = sum(p['status'] != 'только PDF' for p in apps)
    app_lines = sum(1 for m in cls['missing'] if is6_all(m) and m.get('section') == 'П')
    miss6 = [m for m in cls['missing'] if is6(m)]
    c6 = collections.Counter(m['cls'] for m in miss6)
    # подпись рисунка/объекта (текст класса C или E) — не «неверный номер» пункта (КД-РД-Б7.006-02, A3 круг 3)
    nums6 = [n for n in cls['numbers'] if is6(n) and not re.search(r'строка класса [CE]\b', n.get('cls', ''))]
    c15 = collections.Counter(m['cls'] for m in cls['missing'] if not is6_all(m))
    r.update(pts_total=tot, pts_match=ok, A6=c6.get('A', 0), B6=c6.get('B', 0), U6=c6.get('U', 0), C6=c6.get('C', 0), E6=c6.get('E', 0), D6=c6.get('D', 0),
             nums6=len(nums6), apps_pdf=apps_pdf, apps_word=apps_word, app_lines=app_lines, dup_bad=len(cls['duplicates']), dup_ok=len(cls['duplicates_explained']), rest15=sum(c15.values()))
    pts_state = [p for p in (pts or {}).get('points', []) if not p['num'].startswith('прил.')]
    shifted = [p for p in pts_state if p['status'] in ('номер сбит', 'номер сдвинут')]
    blockers = c6.get('A', 0) + c6.get('B', 0) + c6.get('U', 0) + len(nums6) + (apps_pdf != apps_word)
    if tot > 0 and ok == tot and blockers == 0:
        r.update(status='ready_core', note=f'пункты 6+: {ok}/{tot}; приложений эталон/Word: {apps_pdf}/{apps_word} (содержимое не сверяется, строк: {app_lines}); '
                                            f'замечаний в разделах 1-5: {sum(c15.values())}; надписи схем/объекты в 6+: {c6.get("E", 0)}/{c6.get("C", 0)}')
        ex = [m for m in cls['missing'] if not is6_all(m)][:2]
        r['example'] = ' || '.join(f"стр.{m['label'] or m['page']} (раздел {m['section']}), класс {m['cls']}: «{m['text'][:80]}»" for m in ex)
        return r
    cl = []
    if c6.get('A') or nums6 or shifted or cls['duplicates']: cl.append('наша ошибка')
    if c6.get('B'): cl.append('расхождение документа')
    if pts and pts.get('bilingual') and tot > ok: cl.append('двуязычный метод')
    if c6.get('U'): cl.append('источник .doc не прочитан')
    if apps_pdf != apps_word: cl.append('число приложений')
    if not cl: cl.append('прочее')
    r.update(status='not_ready', classes='+'.join(cl), **{'class': cl[0]})
    if cl[0] == 'наша ошибка':
        a = next((m for m in miss6 if m['cls'] == 'A'), None)
        if a: r['example'] = f"стр.{a['label'] or a['page']} (раздел {a['section']}): «{a['text'][:80]}» — есть в {a.get('source')} (изм.{a.get('izm')}), в каноне нет"
        elif nums6: r['example'] = f"номер не тот: {nums6[0]['ref'][:70]}; в каноне: {(nums6[0]['canon'] or [{'num': '?', 'text': ''}])[0]['num']}"
        elif shifted: r['example'] = f"п. {shifted[0]['num']}: {shifted[0]['status']} (в Word № {shifted[0].get('word_num')})"
        elif cls['duplicates']: r['example'] = f"повтор абзаца: «{cls['duplicates'][0]['text'][:70]}», в каноне {cls['duplicates'][0]['canon_count']}, в эталоне {cls['duplicates'][0]['ref_count']}"
    elif cl[0] == 'расхождение документа':
        b = next(m for m in miss6 if m['cls'] == 'B'); nr = b.get('nearest')
        r['example'] = f"стр.{b['label'] or b['page']} (раздел {b['section']}): «{b['text'][:80]}» — ни в одном Word нет" + (f"; рядом в Word: «{nr['text'][:50]}»" if nr else '')
    elif cl[0] == 'число приложений':
        r['example'] = f'приложений в эталоне {apps_pdf}, в Word {apps_word}: ' + ', '.join(f"{p['num']} — {p['status']}" for p in apps if p['status'] in ('только PDF', 'только Word'))[:120]
    else:
        bad = next((p for p in pts_state if p['status'] not in ('совпадает', 'совпадает (порядок иной)')), None)
        r['example'] = (f"двуязычный; п. {bad['num']}: {bad['status']}; PDF «{(bad.get('diff_pdf') or bad['head'])[:60]}»" if bad else '') if cl[0] == 'двуязычный метод' else \
            (f"п. {bad['num']}: {bad['status']}; PDF «{(bad.get('diff_pdf') or bad['head'])[:60]}» / Word «{(bad.get('diff_word') or '')[:60]}»" if bad else '')
    return r


def write_md(run, out, rows):
    st = collections.Counter(r['status'] for r in out)
    cl = collections.Counter(r['class'] for r in out if r['status'] == 'not_ready')
    L = [f'# Статус документов прогона {os.path.basename(run)}', '',
         'Статус пересчитан по готовым результатам (сборка не запускалась, ИИ и Word не использовались). Разделы 1–5 технические, суть — разделы 6 и далее.', '',
         '## Сколько документов в каждом статусе', '', '| Статус | Документов | Что значит |', '|---|---|---|']
    meaning = {'ready': 'канон полностью соответствует эталону по проверке', 'ready_core': 'годен по сути: пункты 6+ совпали на 100 %, расхождения только в разделах 1–5, надписях схем, объектах и внутри приложений (приложения — только по числу)',
               'not_ready': 'есть расхождения в разделах 6+ (классы ниже)', 'scan_skipped': 'эталон — скан/битый текстовый слой, из оценки исключён',
               'base_outdated': 'база Word не содержит значительной части эталона (РОНО и т. п.)', 'multi_part': 'документ из нескольких частей-эталонов, не готов',
               'no_base_word': 'в папке нет Word-базы', 'changed_during_run': 'файлы корпуса изменились во время прогона', 'failed': 'сбой сборки'}
    for k in ('ready', 'ready_core', 'not_ready', 'scan_skipped', 'base_outdated', 'multi_part', 'no_base_word', 'changed_during_run', 'failed'):
        if st.get(k): L.append(f'| {k} | {st[k]} | {meaning.get(k, "")} |')
    L += [f'| **всего** | **{len(out)}** | |', '']
    ch = [r for r in out if r['status'] != r['build_status']]
    L += [f'Изменилось против сборки (summary.csv): {len(ch)} док. — ' + '; '.join(f"{r['doc']}: {r['build_status']} → {r['status']}" for r in ch[:8]) + ('…' if len(ch) > 8 else ''), '']
    L += ['## not_ready по классам', '', 'Класс — по главной причине в разделах 6+ (документ может быть в нескольких, главным берётся первый): '
          '**наша ошибка** — строка есть в Word, но в канон не встала / номер не тот / номер сбит / повтор; **расхождение документа** — строки нет ни в одном Word-файле документа '
          '(Word в Lotus расходится с утверждённым PDF); **двуязычный метод** — пункты 6+ расходятся только из-за разбора двух колонок эталона (метод сверки); **прочее** — пункты расходятся, ненайденных строк нет (таблицы, схемы).', '',
          '| Класс | Документов |', '|---|---|'] + [f'| {c} | {cl.get(c, 0)} |' for c in CLASSES + ('источник .doc не прочитан', 'не определён') if cl.get(c)] + ['']
    allc = collections.Counter(x for r in out if r['status'] == 'not_ready' for x in r['classes'].split('+'))
    L += ['Документ может иметь несколько причин; по всем причинам: ' + ', '.join(f'{k} — {v}' for k, v in allc.most_common()) + '.', '']
    for c in CLASSES + ('источник .doc не прочитан', 'не определён'):
        ds = [r for r in out if r['status'] == 'not_ready' and r['class'] == c]
        if not ds: continue
        L += [f'### {c} ({len(ds)})', '']
        for r in sorted(ds, key=lambda r: (-int(r.get('A6') or 0) - int(r.get('B6') or 0), r['doc']))[:15]:
            pc = f" {r['pts_match']}/{r['pts_total']} пунктов 6+;" if r.get('pts_total') else ''
            L.append(f"- **{r['doc']}** — {r['title'][:60]};{pc} A/B в 6+: {r.get('A6', 0)}/{r.get('B6', 0)}. {r['example']}")
        if len(ds) > 15: L.append(f'- … и ещё {len(ds) - 15} (полный список — status.csv)')
        L.append('')
    for k, t in (('ready_core', 'Годны по сути (ready_core)'), ('scan_skipped', 'Пропущены как сканы'), ('base_outdated', 'База устарела')):
        ds = [r for r in out if r['status'] == k]
        if ds:
            L += [f'## {t}: {len(ds)}', ''] + [f"- **{r['doc']}** — {r['title'][:60]}: {r['note']}" + (f". Замечание 1–5: {r['example']}" if k == 'ready_core' and r['example'] else '') for r in ds[:40]] + ['']
    open(os.path.join(run, 'status.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default=os.path.join(REPO, 'data/canon_reeng/full3')); ap.add_argument('--no-recheck', action='store_true')
    a = ap.parse_args(); run = os.path.abspath(a.run)
    os.environ.setdefault('FP_RUN', os.path.basename(run)); os.environ.setdefault('FP_STEP1', '/nonexistent')
    rows = list(csv.DictReader(open(os.path.join(run, 'summary.csv'), encoding='utf-8-sig'), delimiter=';'))
    rows = [r for r in rows if not r['doc_num'].startswith(EXCL)]
    nr = [r for r in rows if r['status'] == 'not_ready']
    jobs = [('scan', run, r['doc_num']) for r in nr]
    cdir = os.path.join(run, 'classify'); cls = {}
    for r in nr:
        c = jload(f"{cdir}/{r['doc_num']}.json")
        if c is not None: cls[r['doc_num']] = c
        # нет результата classify_missing -> «классификация не получена»; отчёт сам классификацию НЕ запускает
        # (раньше запускал в 6 процессах без предела памяти — OOM и перезагрузка WSL 05.10)
    if not a.no_recheck:
        for r in nr:
            v = jload(f"{run}/out/{r['doc_num']}/verify.json")
            if v and not r['parts'] and v['duplicates'] > 0 and v['lines'] > 0 and v['missing'] == 0 and v['numbered_bad'] == 0 and v['frozen_numbers'] == 0:
                jobs.append(('dup', run, r['doc_num']))
    scan, dupfix = {}, {}
    import multiprocessing as mp   # spawn, 2 процесса, предел памяти на процесс (как classify_missing)
    with mp.get_context('spawn').Pool(2, initializer=_cap_mem, maxtasksperchild=20) as pool:
        for (kind, _, doc), res in pool.imap_unordered(_job, jobs):
            if kind == 'scan': scan[doc] = res if isinstance(res, tuple) else None
            elif kind == 'cls': cls[doc] = res
            else: dupfix[doc] = res
    out = []
    for r in rows:
        d = r['doc_num']; od = os.path.join(run, 'out', d)
        pts = jload(f'{run}/points/{d}.json')
        j = judge(d, r, pts, cls.get(d), scan.get(d), r['status'] == 'not_ready' and is_base_outdated(od), dupfix.get(d))
        out.append({'doc': d, 'title': r['title'], 'group': r['group'], 'build_status': r['status'], 'status': j['status'], 'class': j['class'], 'classes': j['classes'],
                    'pts_total': j.get('pts_total', ''), 'pts_match': j.get('pts_match', ''), 'A6': j.get('A6', ''), 'B6': j.get('B6', ''), 'U6': j.get('U6', ''),
                    'C6': j.get('C6', ''), 'E6': j.get('E6', ''), 'nums6': j.get('nums6', ''), 'dup_bad': j.get('dup_bad', ''), 'dup_ok': j.get('dup_ok', ''),
                    'rest15': j.get('rest15', ''), 'note': j['note'], 'example': j['example']})
    with open(os.path.join(run, 'status.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, list(out[0]), delimiter=';'); w.writeheader(); w.writerows(out)
    write_md(run, out, rows)
    print(dict(collections.Counter(r['status'] for r in out)), '->', run + '/status.csv, status.md')


if __name__ == '__main__':
    main()
