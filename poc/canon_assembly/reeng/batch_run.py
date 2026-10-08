"""Пакетный детерминированный прогон реинжиниринга Word-канона по корпусу БНД (без ИИ).

python3 batch_run.py --run-id <id> [--limit N] [--docs A,B] [--retry-failed] [--redo A,B]

Объём: исключены документы с префиксом doc_num из EXCLUDE_PREFIXES (ИОТ-; решение human 02.10.2026). В снимке они остаются,
но в полный прогон не входят; явно названные в --docs обрабатываются (регрессия).
Многочастные документы (несколько эталонов в files/): каждая часть собирается отдельным воркером (src/<doc>/__parts/pN, out/<doc>/part_N),
статус документа = ready, если готовы все части. Word из файлов-глав: главы склеиваются (Word InsertFile) в word/__главы.docx.

Результаты: data/canon_reeng/<run_id>/{snapshot.json, src/, out/<doc>/, summary.csv, progress.json, run.log}.
Каждый документ обрабатывается отдельным процессом-воркером (таймаут 40 мин), из копии входа со сверкой sha256.
--limit N: первые N ещё не обработанных документов в порядке прогона. Повтор с тем же run_id пропускает
завершённые (ready/not_ready/failed/changed_during_run); --retry-failed повторяет failed и changed_during_run.
--redo A,B: переобработать указанные документы независимо от статуса.
"""
import sys, os, re, json, csv, glob, time, shutil, hashlib, argparse, subprocess, traceback, io, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
MANIFEST = os.path.join(REPO, 'data/bnd_corpus/manifest.json')
RUNS = os.path.join(REPO, 'data/canon_reeng')
WIN_TEMP = '/mnt/c/Users/Budnik_AN/AppData/Local/Temp/canon_reeng'
DOC_TIMEOUT = 40 * 60
MIN_FREE_GB = 20
EXCLUDE_PREFIXES = ('ИОТ-',)
COLS = ['doc_num', 'title', 'process', 'group', 'ref_pages', 'changes', 'status', 'fail_stage', 'error', 'coverage', 'missing',
        'missing_in_objects', 'numbered', 'numbered_bad', 'duplicates', 'frozen_numbers', 'live_numbering',
        'chain_flags', 'parts', 'warnings', 'seconds', 'pdf_pages']
sys.path.insert(0, HERE)
import pagediff as PD


def now(): return time.strftime('%Y-%m-%d %H:%M:%S')
def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
def slug_of(doc): return 'b' + hashlib.md5(doc.encode()).hexdigest()[:8]
def doc_out(rd, doc): return os.path.join(rd, 'out', doc)
def jdump(o, p):
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f: json.dump(o, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


# ---------------------------------------------------------------- воркер (один документ)
def clean_win(slug):
    shutil.rmtree(os.path.join(WIN_TEMP, slug), ignore_errors=True)
    for f in glob.glob(os.path.join(WIN_TEMP, slug + '_*')):
        try: os.remove(f)
        except OSError: pass


def kill_word(slug):
    """Гасит только свои WINWORD: PID из pid-файлов этого документа."""
    for pf in glob.glob(os.path.join(WIN_TEMP, slug + '_*.pid')):
        try: pids = open(pf, encoding='utf-8-sig').read().strip().split(',')
        except OSError: continue
        for pid in pids:
            if pid.strip().isdigit():
                subprocess.run(['powershell.exe', '-NoProfile', '-Command', f"Get-Process -Id {pid.strip()} -ErrorAction SilentlyContinue | Where-Object {{ $_.ProcessName -eq 'WINWORD' }} | Stop-Process -Force"], capture_output=True)   # только WINWORD: номер процесса мог достаться другой программе (validator 06.10)


def dedupe_docpr(path):
    """reeng_plan.merge_head/merge_tail копирует прогоны листа вместе с рисунками: wp:docPr/@id повторяется -> Word: «Файл поврежден».
    Дубликаты получают новые id (первое вхождение сохраняется). Возвращает число переименованных."""
    import zipfile, re
    zin = zipfile.ZipFile(path); x = zin.read('word/document.xml').decode('utf-8')
    ids = [int(i) for i in re.findall(r'<wp:docPr id="(\d+)"', x)]
    seen, nxt, n = set(), max(ids or [0]) + 1000, [0]
    def sub(m):
        i = int(m.group(1))
        if i not in seen: seen.add(i); return m.group(0)
        nid = nxt + n[0]; n[0] += 1; seen.add(nid)
        return f'<wp:docPr id="{nid}"'
    y = re.sub(r'<wp:docPr id="(\d+)"', sub, x)
    if not n[0]: return 0
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zo:
        for it in zin.infolist(): zo.writestr(it, y.encode('utf-8') if it.filename == 'word/document.xml' else zin.read(it.filename))
    zin.close(); os.replace(tmp, path)
    return n[0]


class Stage(Exception):
    def __init__(self, stage, msg): super().__init__(msg); self.stage = stage


def chapter_map(root, need_subdir=True):
    """Файлы-главы под root (имя начинается с номера главы: «2.10 ...», «19-1-140 ...»): {номер(tuple): путь}. .docx предпочтительнее .doc."""
    out = {}
    for f in sorted(glob.glob(root + '/**/*', recursive=True)):
        rel = os.path.relpath(f, root); m = re.match(r'^(\d+(?:[.-]\d+)*)\s', os.path.basename(f))
        if (os.sep in rel or not need_subdir) and m and f.lower().endswith(('.doc', '.docx')):
            k = tuple(int(x) for x in re.split(r'[.-]', m.group(1)))
            if k not in out or f.lower().endswith('.docx'): out[k] = f
    return out


def chapter_files(sd):
    """Главы документа из файлов: база (word/) с заменой главами из изменений по номеру (изм N+1 поверх изм N). -> [(номер, путь)] по порядку номеров; пусто, если это не документ из глав."""
    m = chapter_map(sd + '/word')
    if len(m) < 5: return []
    for adir in sorted(glob.glob(sd + '/amendments/*'), key=lambda d: float((re.search(r'изм([\d.]+)', d) or [0, 0])[1] or 0)):
        m.update(chapter_map(adir))
    return sorted(m.items())


SEVENZ = '/mnt/c/Program Files/7-Zip/7z.exe'
ARCH_EXT = ('.7z', '.zip', '.rar')
WORD_EXT = ('.doc', '.docx')


def unpack_archives(sd):
    """Нет Word в word/, но есть архив(ы): распаковать 7-Zip (Windows) в sd/word/__7z (рабочая копия; вложенные архивы — ещё 2 уровня).
    Если в итоге ровно одна Word-база (не глава) — копия в word/ верхнего уровня. -> (число Word-файлов, ошибка или '')."""
    wd = sd + '/word'; out = wd + '/__7z'
    top = lambda: [f for f in glob.glob(wd + '/*') if f.lower().endswith(WORD_EXT)]
    if top(): return 0, ''
    archs = sorted(f for f in glob.glob(wd + '/*') if f.lower().endswith(ARCH_EXT))
    if not archs: return 0, ''
    if not os.path.isdir(out):
        if not os.path.exists(SEVENZ): return 0, '7-Zip не найден: ' + SEVENZ
        try:
            w = lambda x: subprocess.run(['wslpath', '-w', x], capture_output=True, text=True).stdout.strip()
            level = [(f, out) for f in archs]
            for depth in range(3):
                nxt = []
                for f, dst in level:
                    os.makedirs(dst, exist_ok=True)
                    r = subprocess.run([SEVENZ, 'x', '-y', '-aoa', '-o' + w(dst), w(f)], capture_output=True, text=True, errors='replace')
                    if r.returncode != 0: raise RuntimeError(f'7z код {r.returncode} ({os.path.basename(f)}): {(r.stdout + r.stderr)[-200:]}')
                    nxt += [(g, g + '_x') for g in glob.glob(dst + '/**/*', recursive=True) if g.lower().endswith(ARCH_EXT)]
                level = nxt
                if not level: break
            else:
                raise RuntimeError('вложенность архивов глубже 3')
        except Exception as e:
            shutil.rmtree(out, ignore_errors=True); return 0, f'{type(e).__name__}: {e}'[:400]
    files = [f for f in glob.glob(out + '/**/*', recursive=True) if f.lower().endswith(WORD_EXT) and re.match(r'[^~]', os.path.basename(f))]
    if not files: return 0, 'в архиве нет файлов Word'
    if len(chapter_map(wd)) < 5 and len(files) == 1: shutil.copy(files[0], wd + '/' + os.path.basename(files[0]))
    return len(files), ''


def doc_timeout(sd):
    """40 мин на документ; многочастный — 40 мин на часть; из файлов-глав (сотни страниц, дампы Word) — 3 ч."""
    unpack_archives(sd)
    n = len(PD.ref_pdfs(sd))
    return 3 * 3600 if chapter_files(sd) else DOC_TIMEOUT * (1 + (n if n > 1 else 0))


def part_label(name):
    """Номер части в имени файла («Часть 3», «часть 2.1», «ч. 6»); None, если номера нет или их перечень («части 1, 2, 3», «ч. 2... 6»)."""
    m = re.search(r'(?:[Чч]асти|[Чч]асть|[Чч]\.)\s*(\d+(?:\.\d+)?)(?!\s*[,.]+\s*\d)(?!\d)', name)
    return m.group(1) if m else None


def split_parts(sd, refs):
    """Части многочастного документа: эталон (PDF) <-> базовый Word <-> листы замены.
    Сопоставление: argmax числа строк эталона части, точно (key) входящих в текст файла; при равенстве/нуле — номер части в имени
    (Часть N). Лист при равенстве между частями идёт во все равные (редакции одного документа), без совпадений — не используется (warning).
    Часть без базы -> reason (статус part_unmatched). Создаёт sd/__parts/pN/{files,word,amendments}. -> [{id,pdf,base,sheets,reason,warnings}]"""
    import pagediff as P
    shutil.rmtree(os.path.join(sd, '__parts'), ignore_errors=True)
    parts = []
    def lk(f):
        m = re.search(r'(\d+)(?:\.(\d+))?', part_label(os.path.basename(f)) or '9999')
        return (int(m.group(1)), int(m.group(2) or 0), os.path.basename(f))
    for i, pdf in enumerate(sorted(refs, key=lk), 1):
        pages = P.canon_pages(pdf)
        cnt = {}
        for pg in pages:
            for k in {P.key(l) for l in pg['lines']}: cnt[k] = cnt.get(k, 0) + 1
        head = {k for k, c in cnt.items() if c > 0.3 * len(pages)}
        keys = {P.key(l) for pg in pages for l in pg['lines'] if len(P.key(l)) >= 12 and P.key(l) not in head and not P.garbage(l)}
        parts.append({'id': i, 'pdf': pdf, 'keys': keys, 'label': part_label(os.path.basename(pdf)), 'base': None, 'sheets': [], 'reason': '', 'warnings': []})
    cache = {}
    def scores(f):
        if f not in cache:
            t = P.key(P.docx_text(f)); cache[f] = [sum(1 for k in pt['keys'] if k in t) for pt in parts]
        return cache[f]
    def assign(f):
        sc = scores(f); mx = max(sc); win = [i for i, x in enumerate(sc) if x == mx] if mx > 0 else []
        lab = part_label(os.path.basename(f)); cand = [i for i, pt in enumerate(parts) if lab and pt['label'] == lab]
        if lab and len(cand) == 1:   # номер части в имени однозначно указывает эталон
            return cand, ('' if win == cand else f'номер части в имени ({lab}) ≠ argmax по тексту {[x + 1 for x in win]}')
        if lab and not cand and any(pt['label'] for pt in parts):
            return [], f'у части {lab} нет эталона'
        if len(win) == 1:
            return win, ('имя указывает на другую часть' if cand and cand != win else '')
        if len(win) > 1:
            c = [i for i in cand if i in win]
            return (c, '') if len(c) == 1 else (win, 'равенство по тексту')
        return (cand, 'по имени') if len(cand) == 1 else ([], 'нет совпадений')
    skip_base = re.compile('пояснит|приказ|ЭСЗ', re.I)
    bases = [f for f in sorted(glob.glob(sd + '/word/*.docx')) if not skip_base.search(re.sub(r'\bк\s+приказ\w*', '', os.path.basename(f), flags=re.I))]
    for f in bases:
        a, why = assign(f)
        if len(bases) == 1:   # единственная база на все части (редакции одного документа): сопоставлять нечего
            a, why = list(range(len(parts))), 'единственная база на все части (редакции)' + (', эталоны без совпадений по тексту' if not any(scores(f)) else '')
        elif len(a) > 1: a, why = [], 'база не сопоставлена однозначно: ' + why
        for i in a:
            if not parts[i]['base'] or os.path.getsize(f) > os.path.getsize(parts[i]['base']): parts[i]['base'] = f
        if why: parts[0]['warnings'].append(f'база {os.path.basename(f)}: {why}')
        if not a: parts[0]['warnings'].append(f'база {os.path.basename(f)} не использована')
    for adir in sorted(glob.glob(sd + '/amendments/*')):
        files = sorted(glob.glob(adir + '/*.docx'))
        for f in files:
            kind = P.classify(f)
            if kind == 'changelog':
                for pt in parts: pt.setdefault('copy', []).append(f)
            elif kind == 'sheets':
                a, why = assign(f)
                bs = {parts[i]['base'] for i in a if parts[i]['base']}
                a = sorted(set(a) | {i for i, pt in enumerate(parts) if pt['base'] in bs})   # части с общей базой — редакции одного документа: лист нужен всем (изм1 входит в эталон №2)
                for i in a: parts[i].setdefault('copy', []).append(f); parts[i]['sheets'].append(f)
                if not a: parts[0]['warnings'].append(f'лист {os.path.relpath(f, sd)} не сопоставлен части ({why})')
                elif why: parts[0]['warnings'].append(f'лист {os.path.relpath(f, sd)}: {why}')
    for i, pt in enumerate(parts):   # «лист» с большим числом строк эталона части, чем у базы, — полная новая редакция части: он и есть база
        if pt['base'] and pt['sheets']:
            top = max(pt['sheets'], key=lambda f: scores(f)[i])
            if scores(top)[i] > scores(pt['base'])[i]:
                pt['warnings'].append(f"часть {pt['id']}: файл изменения {os.path.basename(top)} (строк эталона {scores(top)[i]}) полнее базы {os.path.basename(pt['base'])} ({scores(pt['base'])[i]}) — взят как база")
                pt['base'] = top; pt['sheets'] = [f for f in pt['sheets'] if f != top]
                pt['copy'] = [f for f in pt.get('copy', []) if f != top]
    for pt in parts:
        pd_ = os.path.join(sd, '__parts', f"p{pt['id']}")
        os.makedirs(pd_ + '/files'); os.makedirs(pd_ + '/word')
        shutil.copy2(pt['pdf'], pd_ + '/files/')
        if pt['base']: shutil.copy2(pt['base'], pd_ + '/word/')
        else: pt['reason'] = 'базовый Word части не сопоставлен однозначно (argmax строк эталона части / номер части в имени)'
        for f in pt.get('copy', []):
            t = os.path.join(pd_, os.path.relpath(f, sd)); os.makedirs(os.path.dirname(t), exist_ok=True); shutil.copy2(f, t)
        del pt['keys']
    return parts


def run_part(run_id, doc, pid, od):
    """Воркер части в отдельном процессе (таймаут как у документа). -> {status, verify, ref_pages, changes, chain_flags, error}"""
    pod = os.path.join(od, f'part_{pid}'); os.makedirs(pod, exist_ok=True); sl = slug_of(f'{doc}#{pid}')
    cmd = [sys.executable, os.path.abspath(__file__), '--worker', '--run-id', run_id, '--docs', doc, '--part', str(pid)]
    t0 = time.time()
    with open(os.path.join(pod, 'log'), 'w', encoding='utf-8') as lf:
        try: subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=DOC_TIMEOUT); to = False
        except subprocess.TimeoutExpired: to = True
    kill_word(sl); clean_win(sl)
    def rj(n):
        p = os.path.join(pod, n)
        return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None
    ws = rj('worker_result.json') or rj('worker_state.json') or {'stage': 'start', 'error': 'воркер части без результата, см. log'}
    if to: ws['failed'] = True; ws['error'] = f'таймаут {DOC_TIMEOUT // 60} мин на этапе {ws.get("stage")}'
    for f in ('worker_state.json', 'worker_result.json'):
        try: os.remove(os.path.join(pod, f))
        except OSError: pass
    r = {k: ws[k] for k in ('ref_pages', 'changes', 'verify', 'chain_flags', 'error', 'pdf_pages') if k in ws}
    r['seconds'] = round(time.time() - t0)
    if ws.get('status_override'): r['status'] = ws['status_override']
    elif ws.get('failed'): r['status'] = 'failed'; r['error'] = f"@{ws.get('stage')}: {ws.get('error', '')}"
    else: r['status'] = 'ready' if ws.get('ready') else 'not_ready'
    r['reason'] = ''
    return r


def run_part_py(run_id, doc, pid, od, sd):
    """Часть многочастного документа py-движком в отдельном процессе (RLIMIT_AS наследуется от worker_py, batch_run.py:287). -> как run_part."""
    pod = os.path.join(od, f'part_{pid}'); os.makedirs(pod, exist_ok=True); t0 = time.time()
    psd = os.path.join(sd, '__parts', f'p{pid}')
    cmd = [sys.executable, os.path.join(HERE, 'pyengine.py'), '--src', psd, '--out', pod, '--work', os.path.join(os.path.dirname(od), '..', 'work_py', doc, f'p{pid}'), '--doc', doc]
    with open(os.path.join(pod, 'log'), 'w', encoding='utf-8') as lf:
        try: subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=DOC_TIMEOUT)
        except subprocess.TimeoutExpired: pass
    sp = os.path.join(pod, 'status.json')
    ws = json.load(open(sp, encoding='utf-8')) if os.path.exists(sp) else {'error': 'нет status.json, см. log', 'ready': False}
    r = {k: ws[k] for k in ('verify', 'error', 'patches') if k in ws}
    r['seconds'] = round(time.time() - t0); r['ru_maxrss_mb'] = ws.get('ru_maxrss_mb')
    r['status'] = 'failed' if ws.get('error') else ('ready' if ws.get('ready') else 'not_ready')
    r['reason'] = ''
    return r


def worker_py(run_id, doc):
    """--engine py: сборка без Word (pyengine). Многочастные документы — части отдельными процессами (split_parts как в Word-пути),
    главы-файлы склеиваются внутри pyengine (pychapters). Результат в формате worker_result.json."""
    import pyengine, resource
    g = min(int(os.environ.get('PY_RLIMIT_GB', '5')), 8); resource.setrlimit(resource.RLIMIT_AS, (g << 30, g << 30))   # предел памяти процесса
    rd = os.path.join(RUNS, run_id); od = doc_out(rd, doc); sd = os.path.join(rd, 'src', doc); os.makedirs(od, exist_ok=True)
    st = {'doc_num': doc, 'stage': 'start', 'warnings': []}
    try:
        refs = PD.ref_pdfs(sd)
        if not refs: raise RuntimeError('в files/ нет действующего PDF-эталона')
        if len(refs) > 1:
            miss = pyengine.ensure_docx_siblings(sd)
            if miss: raise RuntimeError('нет конвертации .doc (кэш doc2docx пуст, Word не запускается): ' + '; '.join(os.path.relpath(m, sd) for m in miss)[:400])
            ps = split_parts(sd, refs); st['parts_info'] = []
            for pt in ps:
                info = {'id': pt['id'], 'pdf': os.path.basename(pt['pdf']), 'base': os.path.basename(pt['base']) if pt['base'] else None, 'sheets': len(pt['sheets']), 'status': None, 'reason': pt['reason']}
                if pt['reason']: info['status'] = 'part_unmatched'
                else: info.update(run_part_py(run_id, doc, pt['id'], od, sd))
                st['parts_info'].append(info)
            st['warnings'] += [w for pt in ps for w in pt['warnings']]
            v = {k: sum((i.get('verify') or {}).get(k, 0) for i in st['parts_info']) for k in ('lines', 'missing', 'numbered', 'numbered_bad', 'duplicates', 'live_numbering', 'frozen_numbers')}
            v['coverage'] = 1 - v['missing'] / max(v['lines'], 1)
            st['verify'] = v; st['parts'] = [f"{i['id']}:{i['status']}" for i in st['parts_info']]
            pp = [i.get('patches') or {} for i in st['parts_info']]
            st['patches'] = {'applied': sum(x.get('applied', 0) for x in pp), 'skipped': sum(x.get('skipped', 0) for x in pp), 'stale': any(x.get('stale') for x in pp)}
            sts = [i['status'] for i in st['parts_info']]
            st['ready'] = all(x == 'ready' for x in sts)
            if not st['ready']:
                if 'part_unmatched' in sts: st['status_override'] = 'part_unmatched'
                elif 'failed' in sts: st['status_override'] = 'part_failed'
            st['error'] = '; '.join(f"ч{i['id']}: {i['reason'] or i.get('error') or ''}" for i in st['parts_info'] if i['status'] not in ('ready', 'not_ready'))[:400]
            st['pyengine_seconds'] = sum(i.get('seconds') or 0 for i in st['parts_info'])
            st['ru_maxrss_mb'] = max([i.get('ru_maxrss_mb') or 0 for i in st['parts_info']] or [0])
        else:
            s = pyengine.run_doc(sd, od, os.path.join(rd, 'work_py', doc), doc)
            st.update(warnings=s.get('warnings', []), ready=s.get('ready'), verify=s.get('verify'), error=s.get('error', ''), failed=bool(s.get('error')), pyengine_seconds=s.get('seconds'), ru_maxrss_mb=s.get('ru_maxrss_mb'), patches=s.get('patches'), chapters=s.get('chapters'))
        st['stage'] = 'done'
    except Exception:
        st['error'] = traceback.format_exc()[-600:]; st['failed'] = True
    jdump(st, os.path.join(od, 'worker_result.json'))
    return 0


def run_part_pdf(run_id, doc, pid, od, sd):
    """Часть многочастного документа PDF-движком (pdf_canon.py) в отдельном процессе. -> как run_part_py."""
    pod = os.path.join(od, f'part_{pid}'); os.makedirs(pod, exist_ok=True); t0 = time.time()
    cmd = [sys.executable, os.path.join(HERE, 'pdf_canon.py'), '--src', os.path.join(sd, '__parts', f'p{pid}'), '--out', pod, '--doc', doc]
    with open(os.path.join(pod, 'log'), 'w', encoding='utf-8') as lf:
        try: subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=DOC_TIMEOUT)
        except subprocess.TimeoutExpired: pass
    sp = os.path.join(pod, 'status.json')
    ws = json.load(open(sp, encoding='utf-8')) if os.path.exists(sp) else {'error': 'нет status.json, см. log', 'ready': False}
    r = {k: ws[k] for k in ('verify', 'error', 'paras_extra', 'garbage_share', 'pdf_pages', 'canon_docx_mb') if k in ws}
    r['seconds'] = round(time.time() - t0); r['ru_maxrss_mb'] = ws.get('ru_maxrss_mb')
    r['status'] = 'skipped_garbage' if ws.get('skipped') else 'failed' if ws.get('error') else ('ready' if ws.get('ready') else 'not_ready')
    r['reason'] = ''
    return r


def worker_pdf(run_id, doc):
    """--engine pdf: канон целиком из текстового слоя PDF-эталона (pdf_canon, шаг 11.2). Части — split_parts, каждая отдельным процессом; Word не нужен."""
    import pdf_canon, resource
    g = min(int(os.environ.get('PY_RLIMIT_GB', '5')), 8); resource.setrlimit(resource.RLIMIT_AS, (g << 30, g << 30))
    rd = os.path.join(RUNS, run_id); od = doc_out(rd, doc); sd = os.path.join(rd, 'src', doc); os.makedirs(od, exist_ok=True)
    st = {'doc_num': doc, 'stage': 'start', 'warnings': [], 'source': 'pdf'}
    try:
        refs = PD.ref_pdfs(sd)
        if not refs: raise RuntimeError('в files/ нет действующего PDF-эталона')
        if len(refs) > 1:
            import pyengine
            pyengine.ensure_docx_siblings(sd)   # split_parts читает базы Word; нет конвертации — часть без базы, для PDF-движка не важно
            ps = split_parts(sd, refs); st['parts_info'] = []
            for pt in ps:
                info = {'id': pt['id'], 'pdf': os.path.basename(pt['pdf']), 'status': None}
                info.update(run_part_pdf(run_id, doc, pt['id'], od, sd)); st['parts_info'].append(info)
            v = {k: sum((i.get('verify') or {}).get(k, 0) for i in st['parts_info']) for k in ('lines', 'missing', 'numbered', 'numbered_bad', 'duplicates', 'live_numbering', 'frozen_numbers')}
            v['coverage'] = 1 - v['missing'] / max(v['lines'], 1)
            st['verify'] = v; st['parts'] = [f"{i['id']}:{i['status']}" for i in st['parts_info']]
            st['paras_extra'] = sum(i.get('paras_extra') or 0 for i in st['parts_info'])
            sts = [i['status'] for i in st['parts_info']]
            st['ready'] = all(x == 'ready' for x in sts)
            if not st['ready'] and 'failed' in sts: st['status_override'] = 'part_failed'
            st['error'] = '; '.join(f"ч{i['id']}: {i.get('error') or i['status']}" for i in st['parts_info'] if i['status'] not in ('ready', 'not_ready'))[:400]
            st['pyengine_seconds'] = sum(i.get('seconds') or 0 for i in st['parts_info'])
            st['ru_maxrss_mb'] = max([i.get('ru_maxrss_mb') or 0 for i in st['parts_info']] or [0])
        else:
            s = pdf_canon.run_doc(sd, od, doc)
            st.update(warnings=s.get('warnings', []), ready=s.get('ready'), verify=s.get('verify'), paras_extra=s.get('paras_extra'), error=s.get('error', ''), failed=bool(s.get('error')),
                      pyengine_seconds=s.get('seconds'), ru_maxrss_mb=s.get('ru_maxrss_mb'), pdf_pages=s.get('pdf_pages'))
            if s.get('skipped'): st['status_override'] = 'skipped_' + s['skipped']
        st['stage'] = 'done'
    except Exception:
        st['error'] = traceback.format_exc()[-600:]; st['failed'] = True
    jdump(st, os.path.join(od, 'worker_result.json'))
    return 0


def worker(run_id, doc, part=None):
    rd = os.path.join(RUNS, run_id); od = doc_out(rd, doc); sd = os.path.join(rd, 'src', doc)
    slug = slug_of(doc)
    if part is not None:
        sd = os.path.join(sd, '__parts', f'p{part}'); od = os.path.join(od, f'part_{part}'); slug = slug_of(f'{doc}#{part}')
        os.makedirs(od, exist_ok=True)
    st = {'doc_num': doc, 'stage': 'start', 'warnings': []}
    def stage(n):
        st['stage'] = n; print(f'[{now()}] stage {n}', flush=True); jdump(st, os.path.join(od, 'worker_state.json'))
    os.environ['REENG_OUT'] = od
    import wordrun as W, reeng_plan as rp, numfix, reeng_check, verify_canon, pagediff as PD
    wd = W.wsl(slug)
    def word(steps, tag, tmo=1500):
        r = W.run(steps, f'{slug}_{tag}', tmo)
        print(r['log'][-600:], r['out'][-200:], r['sec'], flush=True)
        return r
    def need(r, files, stg):
        if 'ERROR' in r['log'] or r['out'].startswith('TIMEOUT') or not all(os.path.exists(os.path.join(wd, f)) for f in files):
            raise Stage(stg, ('Word: ' + (r['log'] or r['out'])[-400:]).strip())
    try:
        clean_win(slug)
        refs = PD.ref_pdfs(sd)
        if not refs:
            st['skip'] = True; raise Stage('plan', 'в files/ нет действующего PDF-эталона')
        if part is None:
            nz, ez = unpack_archives(sd)
            if ez: st['status_override'] = 'base_in_archive'; raise Stage('unpack', 'база в архиве, распаковка не удалась: ' + ez)
            if nz: st['warnings'].append(f'base from 7z: {nz} files')
            chapters = chapter_files(sd)
            multi = len(refs) > 1
            stage('amend_convert')
            am = sorted(f for f in glob.glob(sd + '/amendments/**/*', recursive=True) if f.lower().endswith('.doc') and not os.path.exists(f + 'x'))
            am += [f for _, f in chapters if f.lower().endswith('.doc') and f.startswith(sd + '/word') and not os.path.exists(f + 'x')]
            if multi: am += sorted(f for f in glob.glob(sd + '/word/*') if f.lower().endswith('.doc') and not os.path.exists(f + 'x'))
            if am:   # .doc -> .docx рядом (в рабочей копии src/), иначе plan/check/verify их не видят
                os.makedirs(wd, exist_ok=True); steps = []
                for i, f in enumerate(am):
                    shutil.copy(f, os.path.join(wd, f'amd{i}.doc'))
                    steps.append({'op': 'convert', 'src': W.winpath(f'{slug}/amd{i}.doc'), 'dst': W.winpath(f'{slug}/amd{i}.docx')})
                word(steps, 'amdc', 600 + 60 * len(am))
                ok = 0
                for i, f in enumerate(am):
                    if os.path.exists(os.path.join(wd, f'amd{i}.docx')): shutil.copy(os.path.join(wd, f'amd{i}.docx'), f + 'x'); ok += 1
                    else: st['warnings'].append(f'.doc не сконвертирован: {os.path.relpath(f, sd)}')
                st['warnings'].append(f'.doc -> .docx: {ok}/{len(am)}')
            if chapters:
                stage('chapters')
                os.makedirs(wd, exist_ok=True); fl = []
                for n, (_, f) in enumerate(chapters):
                    g = f if f.lower().endswith('.docx') else f + 'x'
                    if not os.path.exists(g): st['warnings'].append(f'глава пропущена (нет docx): {os.path.relpath(f, sd)}'); continue
                    shutil.copy(g, os.path.join(wd, f'ch{n:03d}.docx')); fl.append(W.winpath(f'{slug}/ch{n:03d}.docx'))
                r = word([{'op': 'concat', 'files': fl, 'out': W.winpath(f'{slug}/chapters.docx')}], 'chap', 600 + 30 * len(fl))
                need(r, ['chapters.docx'], 'chapters')
                if 'WARN insert failed' in r['log']: st['warnings'].append('склейка глав: ' + str(r['log'].count('WARN insert failed')) + ' файлов не вставлено')
                shutil.copy(os.path.join(wd, 'chapters.docx'), os.path.join(sd, 'word', '__главы.docx'))
                st['warnings'].append(f'база = склейка {len(fl)} глав в порядке номеров (глава из изменения заменяет главу с тем же номером)')
            if multi:
                stage('parts')
                ps = split_parts(sd, refs)
                st['parts_info'] = []
                for pt in ps:
                    info = {'id': pt['id'], 'pdf': os.path.basename(pt['pdf']), 'base': os.path.basename(pt['base']) if pt['base'] else None,
                            'sheets': len(pt['sheets']), 'status': None, 'reason': pt['reason']}
                    if pt['reason']: info['status'] = 'part_unmatched'
                    else:
                        wr = run_part(run_id, doc, pt['id'], od)
                        info.update(wr)
                    st['parts_info'].append(info)
                st['warnings'] += [w for pt in ps for w in pt['warnings']]
                for k in ('unassigned',):
                    pass
                v = {k: sum((i.get('verify') or {}).get(k, 0) for i in st['parts_info']) for k in ('lines', 'missing', 'missing_in_objects', 'numbered', 'numbered_bad', 'duplicates', 'live_numbering', 'frozen_numbers')}
                v['coverage'] = 1 - v['missing'] / max(v['lines'], 1)
                st['verify'] = v; st['parts'] = [f"{i['id']}:{i['status']}" for i in st['parts_info']]
                st['ref_pages'] = sum(i.get('ref_pages') or 0 for i in st['parts_info'])
                st['pdf_pages'] = sum(i.get('pdf_pages') or 0 for i in st['parts_info'])
                st['changes'] = max([i.get('changes') or 0 for i in st['parts_info']] or [0])
                st['chain_flags'] = '; '.join(f"ч{i['id']}: {i['chain_flags']}" for i in st['parts_info'] if i.get('chain_flags'))
                sts = [i['status'] for i in st['parts_info']]
                st['ready'] = all(x == 'ready' for x in sts)
                if not st['ready']:
                    if 'part_unmatched' in sts: st['status_override'] = 'part_unmatched'
                    elif 'failed' in sts: st['status_override'] = 'part_failed'
                st['error'] = '; '.join(f"ч{i['id']}: {i['reason'] or i.get('error') or ''}" for i in st['parts_info'] if i['status'] not in ('ready', 'not_ready'))[:400]
                st['stage'] = 'done'
                return 0
        stage('plan')
        try: pl = rp.plan_doc(sd, slug, wd)
        except rp.NoBase as e:
            st['status_override'] = e.status; raise Stage('plan', str(e))
        except IndexError: raise Stage('plan', 'нет эталона files/*.pdf по маске [Ээ]талон или нет Word-базы в word/')
        jdump(pl, os.path.join(od, 'plan.json'))
        if pl.get('fatal'): raise Stage('convert', pl['fatal'][-400:])
        ref_pdf = pl['canon_pdf']
        nd = dedupe_docpr(os.path.join(wd, 'base_marked.docx'))
        if nd: st['warnings'].append(f'docPr id дубликатов переименовано: {nd}')
        stage('assemble')
        r = word([{'op': 'assemble', 'base': W.winpath(f'{slug}/base_marked.docx'), 'out': W.winpath(f'{slug}/canon_raw.docx'), 'inserts': pl['inserts']}], 'asm')
        need(r, ['canon_raw.docx'], 'assemble')
        if 'marker not found' in r['log']: st['warnings'].append('marker not found')
        stage('numfix')
        try: numfix.run(slug, ref_pdf)
        except Exception as e: raise Stage('numfix', f'{type(e).__name__}: {e} @ ' + ' <- '.join(f'{os.path.basename(f.filename)}:{f.lineno}' for f in traceback.extract_tb(e.__traceback__)[::-1][:3]))
        if not os.path.exists(os.path.join(wd, 'canon.docx')): raise Stage('numfix', 'canon.docx не создан')
        stage('dump+pdf')
        r = word([{'op': 'dump', 'src': W.winpath(f'{slug}/canon.docx'), 'out': W.winpath(f'{slug}/canon_dump.txt')},
                  {'op': 'pdf', 'src': W.winpath(f'{slug}/canon.docx'), 'out': W.winpath(f'{slug}/canon.pdf')}], 'fin')
        need(r, ['canon_dump.txt', 'canon.pdf'], 'dump+pdf')
        stage('compare')
        for att in (1, 2):
            r = word([{'op': 'compare', 'orig': W.winpath(f'{slug}/base_orig.docx'), 'revised': W.winpath(f'{slug}/canon.docx'), 'out': W.winpath(f'{slug}/markup.docx')}], 'cmp')
            if 'ERROR' not in r['log'] and not r['out'].startswith('TIMEOUT') and os.path.exists(os.path.join(wd, 'markup.docx')): break
        else: st['warnings'].append('compare failed: ' + r['log'][-150:].strip())
        stage('check')
        try: cm, _ = reeng_check.run(sd, slug)
        except Exception as e: raise Stage('check', f'{type(e).__name__}: {e}')
        if not cm.get('content_start_found', True): st['warnings'].append('content_start_not_found: заголовок «1 ...» в эталоне не найден, check со стр. 4')
        stage('pagediff')
        try:
            PD.BASE_OVERRIDE = os.path.join(wd, 'base_orig.docx')
            with contextlib.redirect_stdout(io.StringIO()): PD.main(sd, os.path.join(od, 'pagediff.json'))
            pdj = json.load(open(os.path.join(od, 'pagediff.json')))
            fl = []
            for c in pdj['chain']:
                for k, n in (('in_protocol_not_in_sheets', 'протокол без листа'), ('in_sheets_not_in_protocol', 'лист без протокола'), ('sheet_pages_not_stamped_in_canon', 'лист без штампа')):
                    if c[k]: fl.append(f"изм{c['izm']} {n}: {','.join(c[k])}")
            bad = [p for p in pdj['pages'] if p['stamp_izm'] != p['expected_izm']]
            if bad: fl.append(f"штамп≠ожидаемому на {len(bad)} стр. PDF")
            st['chain_flags'] = '; '.join(fl)
        except Exception as e:
            st['chain_flags'] = ''; st['warnings'].append(f'pagediff: {type(e).__name__}: {e}')
        stage('verify')
        shutil.copy(os.path.join(wd, 'canon_dump.txt'), os.path.join(od, 'canon_text.txt'))
        srcs = [os.path.join(wd, 'base_orig.docx')] + sorted(glob.glob(sd + '/amendments/**/*.docx', recursive=True))
        try: v = verify_canon.verify(sd, os.path.join(od, 'canon_text.txt'), os.path.join(wd, 'canon.docx'), srcs)
        except Exception as e: raise Stage('verify', f'{type(e).__name__}: {e}')
        v['sources'] = [os.path.relpath(s, rd) if s.startswith(rd) else 'base_orig.docx (из базы корпуса)' for s in srcs]
        jdump(v, os.path.join(od, 'verify.json'))
        stage('collect')
        for f in ('canon.docx', 'markup.docx', 'canon.pdf'):
            if os.path.exists(os.path.join(wd, f)): shutil.copy(os.path.join(wd, f), os.path.join(od, f))
        import fitz
        st.update(ref_pages=fitz.open(ref_pdf).page_count, changes=len(pl.get('izm_info', {})), verify=v, pdf_pages=sum(len(x['labels']) for x in pl.get('pdf_source', [])),
                  ready=(v['lines'] > 0 and v['missing'] == 0 and v['numbered_bad'] == 0 and v['duplicates'] == 0 and v['frozen_numbers'] == 0))
        st['stage'] = 'done'; st['error'] = ''
    except Stage as e:
        st['stage'] = e.stage; st['error'] = str(e); st['failed'] = True
        print('FAIL', e.stage, e, flush=True)
    except Exception:
        st['error'] = traceback.format_exc()[-600:]; st['failed'] = True; print(st['error'], flush=True)
    finally:
        kill_word(slug)
        jdump(st, os.path.join(od, 'worker_result.json'))
    return 0


# ---------------------------------------------------------------- главный процесс
def build_snapshot(rd):
    sp = os.path.join(rd, 'snapshot.json')
    if os.path.exists(sp): return json.load(open(sp, encoding='utf-8'))
    m = json.load(open(MANIFEST, encoding='utf-8'))
    docs = []
    for d in m['documents']:
        if d.get('source') != 'bnd': continue
        if not any(f['kind'] == 'pdf' and f['scope'] == 'current' for f in d['files']): continue   # нет действующего эталона PDF
        amd = {os.path.dirname(f['path']) for f in d['files'] if f['scope'] == 'amendment'}
        docs.append({'doc_num': d['doc_num'], 'title': d.get('title', ''), 'process': f"{d.get('process_code', '')} {d.get('process_name', '')}".strip(),
                     'dir': d['dir'], 'excluded': d['doc_num'].startswith(EXCLUDE_PREFIXES), 'changes': len(amd), 'group': 'с изменениями' if amd else 'без изменений',
                     'files': [{'path': f['path'], 'sha256': f['sha256'], 'size': f['size'], 'kind': f['kind'], 'scope': f['scope']} for f in d['files']]})
    snap = {'run_id': os.path.basename(rd), 'created': now(), 'manifest_generated_at': m['generated_at'], 'documents': docs}
    os.makedirs(rd, exist_ok=True); jdump(snap, sp)
    return snap


def copy_input(rd, d):
    """Копия файлов документа в src/<doc_num>/ со сверкой sha256. None или текст расхождения."""
    sd = os.path.join(rd, 'src', d['doc_num'])
    shutil.rmtree(sd, ignore_errors=True)
    for f in d['files']:
        s = os.path.join(REPO, f['path']); t = os.path.join(sd, os.path.relpath(f['path'], d['dir']))
        if not os.path.exists(s): return f"файл удалён: {f['path']}"
        os.makedirs(os.path.dirname(t), exist_ok=True); shutil.copy2(s, t)
        if sha256(t) != f['sha256']: return f"sha256 отличается от снимка: {f['path']}"
    return None


def free_gb(): return shutil.disk_usage('/mnt/c').free / 1e9


def row_of(d, st):
    v = st.get('verify') or {}
    r = {'doc_num': d['doc_num'], 'title': d['title'], 'process': d['process'], 'group': d['group'], 'changes': d['changes'],
         'status': st['status'], 'fail_stage': st.get('fail_stage', ''), 'error': (st.get('error') or '').replace('\n', ' ')[:300],
         'ref_pages': st.get('ref_pages', ''), 'chain_flags': st.get('chain_flags', ''), 'parts': ' | '.join(st.get('parts') or []), 'warnings': '; '.join(st.get('warnings') or []), 'seconds': st.get('seconds', ''), 'pdf_pages': st.get('pdf_pages', '')}
    for k in ('coverage', 'missing', 'missing_in_objects', 'numbered', 'numbered_bad', 'duplicates', 'frozen_numbers', 'live_numbering'):
        r[k] = round(v[k], 4) if k == 'coverage' and k in v else v.get(k, '')
    return r


def read_status(rd, doc):
    p = os.path.join(doc_out(rd, doc), 'status.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def write_summary(rd, order):
    rows, cnt = [], {}
    for d in order:
        st = read_status(rd, d['doc_num'])
        if st: rows.append(row_of(d, st)); cnt[st['status']] = cnt.get(st['status'], 0) + 1
    tmp = os.path.join(rd, 'summary.csv.tmp')
    with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, COLS, delimiter=';'); w.writeheader(); w.writerows(rows)
    os.replace(tmp, os.path.join(rd, 'summary.csv'))
    return cnt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-id', required=True); ap.add_argument('--limit', type=int); ap.add_argument('--docs')
    ap.add_argument('--retry-failed', action='store_true'); ap.add_argument('--redo', help='DOC1,DOC2: переобработать независимо от статуса'); ap.add_argument('--worker', action='store_true'); ap.add_argument('--part', type=int)
    ap.add_argument('--engine', choices=('word', 'py', 'pdf'), default='word', help='py: сборка без Word (pyengine.py, пилот шага 9); pdf: канон из текстового слоя PDF (pdf_canon.py, шаг 11.2)')
    a = ap.parse_args()
    if a.worker and a.engine == 'py' and a.part is None: sys.exit(worker_py(a.run_id, a.docs))
    if a.worker and a.engine == 'pdf' and a.part is None: sys.exit(worker_pdf(a.run_id, a.docs))
    if a.worker: sys.exit(worker(a.run_id, a.docs, a.part))
    rd = os.path.join(RUNS, a.run_id); os.makedirs(os.path.join(rd, 'out'), exist_ok=True)
    snap = build_snapshot(rd)
    full = sorted(snap['documents'], key=lambda d: (d['changes'] > 0, d['changes'], d['doc_num']))   # без изменений, затем по числу изменений
    order = [d for d in full if not d['doc_num'].startswith(EXCLUDE_PREFIXES)]   # вне объёма (ИОТ-): только по явному --docs
    if a.docs:
        want = [x.strip() for x in a.docs.split(',') if x.strip()]
        miss = [x for x in want if x not in {d['doc_num'] for d in full}]
        if miss: sys.exit(f'нет в снимке (нужен source=bnd с действующим PDF): {miss}')
        order = [d for d in full if d['doc_num'] in want]
    logf = open(os.path.join(rd, 'run.log'), 'a', encoding='utf-8')
    def log(m):
        s = f'[{now()}] {m}'; print(s, flush=True); logf.write(s + '\n'); logf.flush()
    redo = {'failed', 'changed_during_run'} if a.retry_failed else set()
    redo_docs = {x.strip() for x in (a.redo or '').split(',') if x.strip()}
    miss = redo_docs - {d['doc_num'] for d in full}
    if miss: sys.exit(f'--redo: нет в снимке: {sorted(miss)}')
    todo = [d for d in order if d['doc_num'] in redo_docs or (read_status(rd, d['doc_num']) or {}).get('status') in (None, *redo)]
    if a.limit: todo = todo[:a.limit]
    log(f"run {a.run_id}: в снимке {len(snap['documents'])}, к обработке {len(todo)} (манифест от {snap['manifest_generated_at']})")
    t0 = time.time(); secs = []
    for n, d in enumerate(todo, 1):
        doc = d['doc_num']; od = doc_out(rd, doc)
        while free_gb() < MIN_FREE_GB:
            log(f'свободно на C: {free_gb():.1f} ГБ < {MIN_FREE_GB} — пауза 60 с')
            time.sleep(60)
            if time.time() - t0 > 6 * 3600 and free_gb() < MIN_FREE_GB: log('СТОП: место на C: не освободилось за 6 ч'); sys.exit(2)
        shutil.rmtree(od, ignore_errors=True); os.makedirs(od)
        ts = time.time(); st = {'doc_num': doc}
        err = copy_input(rd, d)
        if err:
            st.update(status='changed_during_run', error=err)
        else:
            cmd = [sys.executable, os.path.abspath(__file__), '--worker', '--run-id', a.run_id, '--docs', doc] + (['--engine', a.engine] if a.engine != 'word' else [])
            with open(os.path.join(od, 'log'), 'w', encoding='utf-8') as lf:
                try: subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=doc_timeout(os.path.join(rd, 'src', doc))); to = False
                except subprocess.TimeoutExpired: to = True
            kill_word(slug_of(doc))
            def rj(n):
                p = os.path.join(od, n)
                return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None
            ws = rj('worker_result.json')
            if ws is None:
                ws = rj('worker_state.json') or {'stage': 'start'}
                ws['failed'] = True; ws['error'] = 'воркер завершился без результата, см. log'
            if to: ws['failed'] = True; ws['error'] = f'таймаут {DOC_TIMEOUT // 60} мин на этапе {ws.get("stage")}'
            st.update({k: ws[k] for k in ('ref_pages', 'changes', 'verify', 'chain_flags', 'warnings', 'error', 'parts', 'parts_info', 'pdf_pages', 'source', 'paras_extra') if k in ws})
            if ws.get('skip'): st.update(status='skipped_no_pdf', fail_stage='plan')
            elif ws.get('status_override'): st.update(status=ws['status_override'], fail_stage='plan')
            elif ws.get('failed'): st.update(status='failed', fail_stage=ws.get('stage', ''))
            else: st['status'] = 'ready' if ws.get('ready') else 'not_ready'
            for f in ('worker_state.json', 'worker_result.json'):
                try: os.remove(os.path.join(od, f))
                except OSError: pass
        clean_win(slug_of(doc))
        st['seconds'] = round(time.time() - ts); st['finished'] = now()
        jdump(st, os.path.join(od, 'status.json'))
        secs.append(st['seconds'])
        cnt = write_summary(rd, full)
        avg = sum(secs) / len(secs)
        jdump({'run_id': a.run_id, 'done': n, 'total': len(todo), 'counts': cnt, 'avg_sec': round(avg),
               'eta': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + (len(todo) - n) * avg)), 'updated': now()}, os.path.join(rd, 'progress.json'))
        v = st.get('verify') or {}
        log(f"{n}/{len(todo)} {doc} [{d['group']}, изм {d['changes']}] {st['status']}{(' @' + st.get('fail_stage', '')) if st['status'] == 'failed' else ''} "
            f"{st['seconds']}с missing={v.get('missing', '-')} num_bad={v.get('numbered_bad', '-')} dup={v.get('duplicates', '-')} frozen={v.get('frozen_numbers', '-')}"
            + (f" | {st.get('error', '')[:120]}" if st.get('error') else ''))
    log(f'готово. {json.dumps(write_summary(rd, full), ensure_ascii=False)}')


if __name__ == '__main__':
    main()
