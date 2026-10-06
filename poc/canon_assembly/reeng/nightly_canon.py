#!/usr/bin/env python3
"""Ночная обработка канона (TASK-021, шаги 7-8, направление C): корпус изменился -> пересобрать только изменившееся -> что нового по сути (пункты 6+).

  python3 nightly_canon.py --init [--from full3]   # создать data/canon_reeng/live/ из полного прогона
  python3 nightly_canon.py --adopt RUN [--docs A,B] [--dry-run]   # взять в live результаты прогона RUN, если они лучше текущих
  python3 nightly_canon.py --accept [--dry-run]                    # отметить «принят»: статус live ready/ready_core (+ для py-сборки — открытие в Word)
  python3 nightly_canon.py --dry-run               # только разница манифеста и состояния live и план действий (Word не нужен, ничего не пишет)
  python3 nightly_canon.py                         # боевой запуск (нужен Word, WSL cron после bnd_sync)

Состояние: data/canon_reeng/live/{state.json, out/<doc> (ссылки на последний прогон документа), points/<doc>.json, snapshot.json, summary.csv, reports/, logs/}.
Пересборка: batch_run.py --run-id nightly_<дата> --docs ... --redo ...; сверка: point_fingerprint.py (FP_RUN=<прогон>, FP_STEP1=/nonexistent).
Без ИИ и без зависимостей (стандартная библиотека). Корпус только читается.
"""
import os, sys, re, csv, json, glob, time, fcntl, shutil, argparse, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
MANIFEST = os.path.join(REPO, 'data/bnd_corpus/manifest.json')
RUNS = os.path.join(REPO, 'data/canon_reeng')
LIVE = os.path.join(RUNS, 'live')
BND_LOCK = os.path.join(REPO, 'data/bnd_sync/logs/.lock')
EXCLUDE = ('ИОТ-', 'РПП', 'РОТО')          # вне объёма (как в batch_run и point_fingerprint)
STABLE_STATUS = ('ready', 'not_ready', 'no_base_word', 'skipped_no_pdf')
MAX_DOCS = 40
MIN_MANIFEST_AGE = 300                       # с
FIRST = 200                                  # знаков заголовка пункта в отчёте


def now(): return time.strftime('%Y-%m-%d %H:%M:%S')
def jload(p): return json.load(open(p, encoding='utf-8'))
def jdump(o, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f: json.dump(o, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
def log(m): print(f'[{now()}] {m}', flush=True)


# ---------------------------------------------------------------- манифест -> объём
def in_scope(d):
    return (d.get('source') == 'bnd' and not d['doc_num'].startswith(EXCLUDE)
            and any(f['kind'] == 'pdf' and f['scope'] == 'current' for f in d['files']))


def files_of(d):
    """{путь относительно папки документа: (sha256, kind, scope)}."""
    return {os.path.relpath(f['path'], d['dir']): (f['sha256'], f['kind'], f['scope']) for f in d['files']}


def read_manifest():
    m = jload(MANIFEST)
    allm, scope = {}, {}
    for d in m['documents']:
        allm.setdefault(d['doc_num'], d)
        if in_scope(d): scope.setdefault(d['doc_num'], d)
    return m, allm, scope


# ---------------------------------------------------------------- состояние
def pts_of(o):
    """Пункты из points/<doc>.json: {номер: [fp эталона, fp канона, начало, статус]}."""
    return {r['num']: [r.get('pdf'), r.get('word'), (r.get('head') or '')[:FIRST], r['status']] for r in o.get('points', [])}


def pct_of(pts):
    body = [v for k, v in pts.items() if not k.startswith('прил.')]
    ok = sum(1 for v in body if v[3].startswith('совпадает'))
    return (len(body), ok)


def link_live(doc, run):
    for sub in ('out', 'src'):   # src — копия исходных файлов прогона (нужна classify_missing/status_report --run live)
        dst = os.path.join(LIVE, sub, doc)
        if os.path.lexists(dst): os.remove(dst) if os.path.islink(dst) else shutil.rmtree(dst)
        src = os.path.join(RUNS, run, sub, doc)
        if os.path.isdir(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.symlink(os.path.relpath(src, os.path.dirname(dst)), dst)


def init_live(run):
    sn = jload(os.path.join(RUNS, run, 'snapshot.json'))
    rows = {r['doc_num']: r for r in csv.DictReader(open(os.path.join(RUNS, run, 'summary.csv'), encoding='utf-8-sig'), delimiter=';')}
    docs = {}
    for d in sn['documents']:
        r = rows.get(d['doc_num'])
        if not r or d['doc_num'].startswith(EXCLUDE): continue
        pp = os.path.join(RUNS, run, 'points', d['doc_num'] + '.json')
        pj = jload(pp) if os.path.exists(pp) else {}
        if os.path.exists(pp):
            os.makedirs(os.path.join(LIVE, 'points'), exist_ok=True); shutil.copy2(pp, os.path.join(LIVE, 'points', d['doc_num'] + '.json'))
        link_live(d['doc_num'], run)
        docs[d['doc_num']] = {'title': d['title'], 'files': {os.path.relpath(f['path'], d['dir']): [f['sha256'], f['kind'], f['scope']] for f in d['files']},
                              'status': r['status'], 'run': run, 'points': pts_of(pj), 'skip': pj.get('skip', ''),
                              'rebuild': r['status'] == 'changed_during_run'}
    shutil.copy2(os.path.join(RUNS, run, 'snapshot.json'), os.path.join(LIVE, 'snapshot.json'))
    shutil.copy2(os.path.join(RUNS, run, 'summary.csv'), os.path.join(LIVE, 'summary.csv'))
    for sub in ('reports', 'logs'): os.makedirs(os.path.join(LIVE, sub), exist_ok=True)
    st = {'manifest_generated_at': sn['manifest_generated_at'], 'initialized_from': run, 'updated': now(), 'docs': docs}
    jdump(st, os.path.join(LIVE, 'state.json'))
    return st


# ---------------------------------------------------------------- разница
def label(rel, scope, kind):
    if scope == 'amendment':
        parts = rel.split(os.sep)
        folder = parts[1] if len(parts) > 2 else ''
        return ('лист изменения' if re.search(r'[Лл]ист', parts[-1]) else 'изменение') + (f' {folder}' if folder else '')
    if scope == 'current' and kind == 'pdf': return 'эталон (PDF)'
    return 'исходный Word/прочее'


def diff_files(old, new):
    """old/new: {rel: [sha, kind, scope]} -> описания. Сравнение по содержимому (sha256): переименование без смены содержимого (суффиксы _XXXXXXXX) не изменение."""
    import collections
    cnt = collections.Counter(v[0] for v in old.values()); cnt.subtract(v[0] for v in new.values())
    out = {}
    for src, sign, op in ((old, 1, 'удалён'), (new, -1, 'добавлен')):
        for rel, v in src.items():
            if cnt[v[0]] * sign > 0:
                cnt[v[0]] -= sign
                out.setdefault((label(rel, v[2], v[1]), op), []).append(os.path.basename(rel))
    res = []
    for (lb, op), names in sorted(out.items()):
        res.append(f"{op} {lb}: {', '.join(names[:3])}{' …(+%d)' % (len(names) - 3) if len(names) > 3 else ''}")
    return res


def compute_plan(state, allm, scope):
    sd = state['docs']
    p = {'new': [], 'changed': [], 'deleted': [], 'left_scope': [], 'retry': [], 'same': 0, 'failed_known': []}
    for doc, d in sorted(scope.items()):
        nf = {k: list(v) for k, v in files_of(d).items()}
        s = sd.get(doc)
        if s is None: p['new'].append((doc, [f'новый документ ({len(nf)} файлов)']))
        else:
            ch = diff_files(s['files'], nf)
            if ch:
                if s['status'] == 'failed' and s.get('failed_key') == files_key(nf): p['failed_known'].append(doc)
                else: p['changed'].append((doc, ch))
            elif s.get('rebuild'): p['retry'].append((doc, ['сборка не завершена в прошлый раз (changed_during_run)']))
            else: p['same'] += 1
    for doc in sorted(sd):
        if doc in scope: continue
        if doc not in allm: p['deleted'].append(doc)
        else: p['left_scope'].append(doc)
    return p


def files_key(nf):
    import hashlib
    return hashlib.sha1(json.dumps(sorted((k, v[0]) for k, v in nf.items())).encode()).hexdigest()


def todo_docs(p): return [d for d, _ in p['new'] + p['changed'] + p['retry']]


def plan_text(p, state, manifest):
    L = [f"Манифест от {manifest['generated_at']}; состояние live — от {state['manifest_generated_at']}.",
         f"Без изменений: {p['same']}; новых: {len(p['new'])}; изменённых: {len(p['changed'])}; повтор незавершённых: {len(p['retry'])}; "
         f"удалено из корпуса: {len(p['deleted'])}; вышло из объёма: {len(p['left_scope'])}; не собрались и файлы те же (пропуск): {len(p['failed_known'])}."]
    for title, items in (('Новые', p['new']), ('Изменённые', p['changed']), ('Повтор', p['retry'])):
        if items:
            L.append(f'\n{title}:')
            for doc, ch in items: L.append(f"  {doc}: " + '; '.join(ch))
    if p['deleted']: L.append('\nУдалены из корпуса: ' + ', '.join(p['deleted']))
    if p['left_scope']: L.append('\nВышли из объёма (нет эталона PDF/сменили тип): ' + ', '.join(p['left_scope']))
    n = len(todo_docs(p))
    L.append(f"\nПлан: пересобрать {n} док." + (f' > {MAX_DOCS}: ТРЕБУЕТСЯ ПОЛНЫЙ ПРОГОН, пересборка не запускается.' if n > MAX_DOCS else ' (batch_run --docs ... --redo ..., затем point_fingerprint).' if n else ' Пересборка не нужна.'))
    return '\n'.join(L)


# ---------------------------------------------------------------- защиты
def bnd_sync_running():
    try:
        fd = os.open(BND_LOCK, os.O_RDONLY)
    except OSError: fd = None
    busy = False
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(fd, fcntl.LOCK_UN)
        except BlockingIOError: busy = True
        finally: os.close(fd)
    if not busy:
        r = subprocess.run(['pgrep', '-f', 'bnd_sync/run_nightly.py'], capture_output=True, text=True)
        busy = any(x.strip() and int(x) != os.getpid() for x in r.stdout.split())
    return busy


def manifest_age(): return time.time() - os.path.getmtime(MANIFEST)


def wait_ready(max_wait):
    t0 = time.time()
    while True:
        busy, age = bnd_sync_running(), manifest_age()
        if not busy and age >= MIN_MANIFEST_AGE: return True
        if time.time() - t0 > max_wait: return False
        log(f'ждём: bnd_sync {"работает" if busy else "завершён"}, манифест {age:.0f} с назад')
        time.sleep(60)


# ---------------------------------------------------------------- отчёт по документу
def doc_report(doc, before, st_after, pts_after, skip_after):
    L = []
    pb = before['points'] if before else {}
    nb, kb = pct_of(pb); na, ka = pct_of(pts_after)
    sb = before['status'] if before else '— (новый)'
    L.append(f"### {doc}" + (f" — {st_after['title']}" if st_after.get('title') else ''))
    L.append(f"- Статус сборки: было {sb} → стало {st_after['status']}.")
    if st_after['status'] in ('failed', 'changed_during_run'):
        L.append(f"- СБОЙ: {st_after.get('error', '')[:300]} Состояние документа не обновлено, результаты прежнего прогона сохранены.")
        return L
    L.append(f"- Пунктов 6+ (без приложений): было {nb} (совпало {kb}) → стало {na} (совпало {ka})." + (f' Сверка пропущена: {skip_after}.' if skip_after else ''))
    changed = [k for k in pts_after if k in pb and pb[k][0] != pts_after[k][0]]
    added = [k for k in pts_after if k not in pb]
    removed = [k for k in pb if k not in pts_after]
    drift = [k for k in pts_after if k in pb and pb[k][0] == pts_after[k][0] and (pb[k][1] != pts_after[k][1] or pb[k][3] != pts_after[k][3])]
    if not before: L.append('- Новый документ: сравнивать не с чем (все пункты новые).')
    if changed:
        L.append(f'- Изменилась суть (отпечаток эталона) в {len(changed)} пунктах:')
        for k in changed[:30]:
            L.append(f"  - п. {k}: было «{pb[k][2][:FIRST]}» → стало «{pts_after[k][2][:FIRST]}»" + (' (начало то же, изменился текст дальше)' if pb[k][2] == pts_after[k][2] else ''))
        if len(changed) > 30: L.append(f'  - … ещё {len(changed) - 30}')
    if before and added: L.append(f"- Новые пункты ({len(added)}): " + '; '.join(f"{k} «{pts_after[k][2][:80]}»" for k in added[:15]) + (' …' if len(added) > 15 else ''))
    if removed: L.append(f"- Удалённые пункты ({len(removed)}): " + '; '.join(f"{k} «{pb[k][2][:80]}»" for k in removed[:15]) + (' …' if len(removed) > 15 else ''))
    if drift: L.append(f"- Эталон тот же, но изменился результат нашей сборки/сверки в {len(drift)} пунктах (не суть документа): " + ', '.join(drift[:20]) + (' …' if len(drift) > 20 else ''))
    if before and not (changed or added or removed or drift): L.append('- По отпечаткам пунктов 6+ ничего не изменилось (правка вне разделов 6+ либо только листы/служебные файлы).')
    return L


# ---------------------------------------------------------------- основной шаг
def run_guarded(cmd, timeout, **kw):
    """subprocess в своей группе процессов; при превышении времени — вся группа (включая воркеров) гасится, ночной запуск продолжается
    (validator 06.10: иначе TimeoutExpired ронял запуск без записи состояния и отчёта, воркер оставался сиротой). -> True, если уложился."""
    import signal
    pr = subprocess.Popen(cmd, start_new_session=True, **kw)
    try:
        pr.wait(timeout=timeout); return True
    except subprocess.TimeoutExpired:
        log(f'ТАЙМ-АУТ {timeout} с: {os.path.basename(cmd[1])} — группа процессов остановлена')
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try: os.killpg(pr.pid, sig)
            except ProcessLookupError: break
            try: pr.wait(timeout=30); break
            except subprocess.TimeoutExpired: continue
        return False


def stop_own_word(since):
    """Свой WINWORD по pid-файлам wordrun, созданным после since (если проверку открытия пришлось прервать). Чужие не трогаются."""
    import wordrun
    for f in glob.glob(os.path.join(wordrun.WIN, 'wo_*.pid')):
        if os.path.getmtime(f) < since: continue
        for pid in open(f, encoding='utf-8-sig', errors='ignore').read().strip().split(','):
            if pid.strip().isdigit(): subprocess.run(['powershell.exe', '-NoProfile', '-Command', f"Get-Process -Id {pid.strip()} -ErrorAction SilentlyContinue | Where-Object {{ $_.ProcessName -eq 'WINWORD' }} | Stop-Process -Force"], capture_output=True)   # только WINWORD: номер процесса мог достаться другой программе (validator 06.10)


def run_rebuild(docs, run_id):
    # шаг 9 (05.10.2026): сборка без Word (py-движок); Word — только проверка открытия готовых (wordopen_check) перед приёмкой
    cmd = [sys.executable, os.path.join(HERE, 'batch_run.py'), '--run-id', run_id, '--engine', os.environ.get('CANON_ENGINE', 'py'),
           '--docs', ','.join(docs), '--redo', ','.join(docs)]
    log('batch_run: ' + ' '.join(cmd[2:3] + cmd[3:5]) + f' ({len(docs)} док.)')
    # внешний предел не меньше внутренних (batch_run.doc_timeout: до 3 ч на документ из глав, 40 мин × (1+частей))
    run_guarded(cmd, len(docs) * 3 * 3600 + 600)
    env = dict(os.environ, FP_RUN=run_id, FP_STEP1='/nonexistent')
    log('point_fingerprint')
    run_guarded([sys.executable, os.path.join(HERE, 'point_fingerprint.py')] + docs, len(docs) * 300 + 600, env=env, stdout=subprocess.DEVNULL)
    rows = list(csv.DictReader(open(os.path.join(RUNS, run_id, 'summary.csv'), encoding='utf-8-sig'), delimiter=';')) if os.path.exists(os.path.join(RUNS, run_id, 'summary.csv')) else []
    ready = [r['doc_num'] for r in rows if r['doc_num'] in docs and r['status'] == 'ready']
    if ready:   # проверка открытия в Word собранных py-движком (правило 1) — один Word, свой PID
        log(f'wordopen_check: {len(ready)} док.')
        units = sum(max(1, len(glob.glob(os.path.join(RUNS, run_id, 'out', d, 'part_*')))) for d in ready)   # многочастный — по части
        t0 = time.time()
        if not run_guarded([sys.executable, os.path.join(HERE, 'wordopen_check.py'), os.path.join(RUNS, run_id)] + ready, units * 900 + 600, stdout=subprocess.DEVNULL):
            stop_own_word(t0)


def pick_run_id(manifest):
    base = 'nightly_' + datetime.date.today().isoformat()
    rid, n = base, 1
    while True:
        sp = os.path.join(RUNS, rid, 'snapshot.json')
        if not os.path.exists(sp) or jload(sp).get('manifest_generated_at') == manifest['generated_at']: return rid
        n += 1; rid = f'{base}_{n}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--init', action='store_true'); ap.add_argument('--from', dest='src', default='full3')
    ap.add_argument('--adopt', metavar='RUN'); ap.add_argument('--docs'); ap.add_argument('--accept', action='store_true')
    ap.add_argument('--dry-run', action='store_true'); ap.add_argument('--wait-max', type=int, default=3 * 3600, help='сколько ждать bnd_sync/свежий манифест, с')
    a = ap.parse_args()
    os.makedirs(os.path.join(LIVE, 'logs'), exist_ok=True)
    if a.init:
        st = init_live(a.src); log(f'live инициализирован из {a.src}: документов {len(st["docs"])}'); return 0
    if a.accept:
        accept(a.dry_run); return 0
    if a.adopt:
        adopt(a.adopt, a.docs.split(',') if a.docs else None, a.dry_run); return 0
    sp = os.path.join(LIVE, 'state.json')
    if not os.path.exists(sp): log('live не инициализирован: python3 nightly_canon.py --init'); return 1
    if not a.dry_run:
        lk = open(os.path.join(LIVE, '.lock'), 'w')
        try: fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: log('уже запущен (live/.lock), выходим'); return 2
        if not wait_ready(a.wait_max): log('bnd_sync не завершился или манифест слишком свежий — выходим'); return 3
    else:
        busy, age = bnd_sync_running(), manifest_age()
        log(f'[dry-run] bnd_sync {"РАБОТАЕТ" if busy else "не работает"}; манифест {age / 60:.0f} мин назад' + (' (боевой запуск подождал бы)' if busy or age < MIN_MANIFEST_AGE else ''))
    state = jload(sp)
    manifest, allm, scope = read_manifest()
    p = compute_plan(state, allm, scope)
    text = plan_text(p, state, manifest)
    if a.dry_run:
        print(text); log('[dry-run] ничего не записано, Word не запускался'); return 0

    date = datetime.date.today().isoformat()
    todo = todo_docs(p)
    R = [f'# Что нового в корпусе: {date}', '', f'Отчёт построен {now()}. Манифест корпуса от {manifest["generated_at"]}, предыдущая обработка — по манифесту от {state["manifest_generated_at"]}.', '',
         '## Что изменилось в корпусе за ночь', '', '```', text, '```', '']
    results, fails = {}, []
    if len(todo) > MAX_DOCS:
        R += ['## Требуется полный прогон', '', f'Изменилось {len(todo)} документов (порог {MAX_DOCS}). Ночная пересборка не запускалась, состояние live не изменено; следующей ночью разница накопится.', '']
        finish(R, date); return 0
    rid = None
    if todo:
        rid = pick_run_id(manifest)
        run_rebuild(todo, rid)
        rows = {r['doc_num']: r for r in csv.DictReader(open(os.path.join(RUNS, rid, 'summary.csv'), encoding='utf-8-sig'), delimiter=';')} if os.path.exists(os.path.join(RUNS, rid, 'summary.csv')) else {}
        chg = {d: ch for d, ch in p['new'] + p['changed'] + p['retry']}
        R += ['## Изменения по документам', '']
        for doc in todo:
            r = rows.get(doc)
            before = state['docs'].get(doc)
            nf = {k: list(v) for k, v in files_of(scope[doc]).items()}
            if r is None:
                if before: before.pop('accepted', None); before.pop('accepted_status', None)   # изменился в Lotus, не пересобран — не «принят» (правило 2)
                R += [f'### {doc}', '- СБОЙ: нет строки в summary.csv прогона (batch_run не дошёл до документа).', '']; fails.append(doc); continue
            stt = {'status': r['status'], 'error': r.get('error', ''), 'title': scope[doc].get('title', '')}
            if r['status'] in ('ready', 'not_ready'):
                pf = os.path.join(RUNS, rid, 'points', doc + '.json')
                pj = jload(pf) if os.path.exists(pf) else {'skip': 'нет результата сверки'}
                pa = pts_of(pj)
                lines = doc_report(doc, before, stt, pa, pj.get('skip', ''))
                link_live(doc, rid)
                if os.path.exists(pf): shutil.copy2(pf, os.path.join(LIVE, 'points', doc + '.json'))
                state['docs'][doc] = {'title': stt['title'], 'files': nf, 'status': r['status'], 'run': rid, 'points': pa, 'skip': pj.get('skip', ''), 'rebuild': False}
            else:
                lines = doc_report(doc, before, stt, {}, '')
                fails.append(doc)
                if before is None: state['docs'][doc] = {'title': stt['title'], 'files': {}, 'status': r['status'], 'run': rid, 'points': {}, 'skip': '', 'rebuild': True}
                elif r['status'] == 'failed': before['status'] = 'failed'; before['failed_key'] = files_key(nf)
                if before is not None: before.pop('accepted', None); before.pop('accepted_status', None)   # правило 2: изменился и не пересобран — не «принят»
            R += lines[:1] + ['- Файлы: ' + '; '.join(chg[doc]) + '.'] + lines[1:]
            R.append('')
    for doc in p['deleted'] + p['left_scope']:
        R += [f"### {doc}", '- ' + ('Удалён из корпуса.' if doc in p['deleted'] else 'Вышел из объёма (нет действующего эталона PDF или иной тип).') + ' Убран из live.', '']
        for sub, nm in (('out', doc), ('points', doc + '.json')):
            pth = os.path.join(LIVE, sub, nm)
            if os.path.islink(pth): os.remove(pth)
            elif os.path.isdir(pth): shutil.rmtree(pth)
            elif os.path.exists(pth): os.remove(pth)
        state['docs'].pop(doc, None)
    if p['failed_known']: R += ['## Не собираются (файлы те же, повтор не запускали)', '', ', '.join(p['failed_known']), '']
    R += ['## Сбои', '', (', '.join(fails) if fails else 'нет'), '']
    state['manifest_generated_at'] = manifest['generated_at']; state['updated'] = now()
    jdump(state, sp)
    if todo:   # статусы live и приёмка пересобранных (правила 1–2): classify по ним, status_report, --accept
        run_guarded([sys.executable, os.path.join(HERE, 'classify_missing.py'), '--run', LIVE, '--docs', ','.join(todo)], len(todo) * 1200 + 600, stdout=subprocess.DEVNULL)
        if not run_guarded([sys.executable, os.path.join(HERE, 'status_report.py'), '--run', LIVE], 3600, stdout=subprocess.DEVNULL):
            R += ['## Приёмка', '', 'Не выполнялась: пересчёт статусов live не уложился во время (status.csv устарел).', '']
        else:
          try:
            wait = accept(False); R += ['## Приёмка', '', f'Ждут проверки открытия в Word: {", ".join(wait) or "нет"}.', '']
          except Exception as e: R += ['## Приёмка', '', f'СБОЙ приёмки: {type(e).__name__}: {e}', '']
    rebuild_summary(state)
    finish(R, date)
    return 0


def rebuild_summary(state):
    """live/summary.csv: актуальные строки summary из прогонов, на которые ссылается live."""
    rows, cols = [], []
    for doc, s in sorted(state['docs'].items()):
        p = os.path.join(RUNS, s['run'], 'summary.csv')
        if not os.path.exists(p): continue
        rd = csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')
        cols += [c for c in rd.fieldnames if c not in cols]   # у прогонов разный набор колонок (pdf_pages с A2)
        rows += [r for r in rd if r['doc_num'] == doc]
    if cols:
        with open(os.path.join(LIVE, 'summary.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, cols, delimiter=';', restval=''); w.writeheader(); w.writerows(rows)


def score(r):
    """Качество сборки по строке summary: меньше — лучше. ready лучше not_ready; дальше — сумма ненайденных строк, неверных номеров и повторов."""
    if not r or r.get('status') not in ('ready', 'not_ready'): return (2, 0)
    n = lambda k: int(r.get(k) or 0) if str(r.get(k) or '0').isdigit() else 0
    return (0 if r['status'] == 'ready' else 1, n('missing') + n('numbered_bad') + n('duplicates'))


def is_py_run(run):
    """Прогон py-движком (сборка без Word): по worker_result/статусу первого документа."""
    p = os.path.join(RUNS, run, 'summary.csv')
    if os.path.basename(run).startswith(('py', 'stepP')): return True
    try: return 'pyengine_seconds' in open(p, encoding='utf-8-sig').readline()
    except OSError: return False


def word_opened():
    """{(run, doc): True/False} по всем <run>/wordopen.json (wordopen_check.py)."""
    out = {}
    for f in glob.glob(os.path.join(RUNS, '*', 'wordopen.json')):
        run = os.path.basename(os.path.dirname(f))
        for doc, r in jload(f).items():   # открылся и номера Word на нашем файле совпали с нашими (правило 1)
            out[(run, doc)] = bool(r.get('opened')) and r.get('num_same') == r.get('num_pairs', r.get('num_same'))
    return out


def accept(dry):
    """Правила готовности (human 05.10.2026): «принят» = статус live ready/ready_core (status_report --run live) и, если документ собран
    py-движком, — открылся в Word. Принятый документ замораживается (adopt его не заменяет). Нужны live/status.csv и wordopen.json."""
    state = jload(os.path.join(LIVE, 'state.json'))
    stat = {r['doc']: r for r in csv.DictReader(open(os.path.join(LIVE, 'status.csv'), encoding='utf-8-sig'), delimiter=';')}
    wo = word_opened(); new, wait = [], []
    for doc, st in sorted(state['docs'].items()):
        if st.get('accepted'): continue
        s_ = stat.get(doc, {}).get('status')
        if s_ not in ('ready', 'ready_core'): continue
        if is_py_run(st['run']) and not wo.get((st['run'], doc)): wait.append(doc); continue
        new.append(doc)
        if not dry: st['accepted'] = datetime.date.today().isoformat(); st['accepted_status'] = s_
    if not dry: state['updated'] = now(); jdump(state, os.path.join(LIVE, 'state.json'))
    tot = sum(1 for s in state['docs'].values() if s.get('accepted'))
    print(f'принято сейчас {len(new)}; всего принятых {tot if not dry else tot + len(new)} из {len(state["docs"])}; ждут проверки открытия в Word {len(wait)}: {", ".join(wait)}')
    return wait


def adopt(run, docs, dry):
    """Документы прогона run (после доработки сборки) -> live, только если результат лучше текущего в live (решение human 04.10.2026:
    готовые не пересобираем, неготовые пересобираем кругами; хуже — не берём). Нужна сверка по пунктам прогона (points/)."""
    state = jload(os.path.join(LIVE, 'state.json'))
    sn = {d['doc_num']: d for d in jload(os.path.join(RUNS, run, 'snapshot.json'))['documents']}
    rows = {r['doc_num']: r for r in csv.DictReader(open(os.path.join(RUNS, run, 'summary.csv'), encoding='utf-8-sig'), delimiter=';')}
    cur = {}
    for doc, st in state['docs'].items():
        p = os.path.join(RUNS, st['run'], 'summary.csv')
        cur.setdefault(st['run'], {r['doc_num']: r for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')} if os.path.exists(p) else {})
    taken, kept = [], []
    for doc in (docs or sorted(rows)):
        r = rows.get(doc)
        if not r or doc.startswith(EXCLUDE) or doc not in sn: continue
        st = state['docs'].get(doc)
        if st and st.get('accepted'): kept.append(f'{doc}: принят {st["accepted"]} — не заменяется'); continue   # правило 2 (05.10.2026)
        old = cur.get(st['run'], {}).get(doc) if st else None
        new_s, old_s = score(r), score(old)
        line = f"{doc}: {old.get('status') if old else '—'} {old_s[1] if old else ''} ({st['run'] if st else '—'}) -> {r['status']} {new_s[1]} ({run})"
        wo = word_opened() if new_s == old_s else {}
        if new_s > old_s or (new_s == old_s and not (st and not wo.get((st['run'], doc), True) and wo.get((run, doc)))):
            kept.append(line); continue   # при равенстве берётся новая версия, только если старая не прошла проверку в Word, а новая прошла
        pf_new = os.path.join(RUNS, run, 'points', doc + '.json')
        ok_new = pct_of(pts_of(jload(pf_new)))[1] if os.path.exists(pf_new) else 0
        if st and r['status'] != 'ready' and ok_new < pct_of(st.get('points', {}))[1]:   # суть важнее суммы строк; ready (правило 1) — по verify
            kept.append(line + f'; пунктов 6+ совпало меньше ({ok_new})'); continue
        taken.append(line)
        if dry: continue
        pf = os.path.join(RUNS, run, 'points', doc + '.json')
        pj = jload(pf) if os.path.exists(pf) else {'skip': 'нет результата сверки'}
        link_live(doc, run)
        if os.path.exists(pf): shutil.copy2(pf, os.path.join(LIVE, 'points', doc + '.json'))
        d = sn[doc]
        state['docs'][doc] = {'title': d['title'], 'files': {os.path.relpath(f['path'], d['dir']): [f['sha256'], f['kind'], f['scope']] for f in d['files']},
                              'status': r['status'], 'run': run, 'points': pts_of(pj), 'skip': pj.get('skip', ''), 'rebuild': False}
    if not dry:
        state['updated'] = now(); jdump(state, os.path.join(LIVE, 'state.json')); rebuild_summary(state)
    print(f'взято {len(taken)}:'); print('\n'.join('  ' + x for x in taken))
    print(f'оставлено как было {len(kept)}:'); print('\n'.join('  ' + x for x in kept))


def finish(R, date):
    body = '\n'.join(x for x in R if x is not None) + '\n'
    os.makedirs(os.path.join(LIVE, 'reports'), exist_ok=True)
    for n in (date + '.md', 'latest.md'):
        with open(os.path.join(LIVE, 'reports', n), 'w', encoding='utf-8') as f: f.write(body)
    log(f'отчёт: live/reports/{date}.md')


if __name__ == '__main__':
    sys.exit(main())
