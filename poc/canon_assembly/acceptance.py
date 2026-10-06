"""Карточка приёмки записи документа (TASK-021, шаг 5): полнота по страницам эталона, учёт страниц, цепочка изменений,
нумерация пунктов, доли источников, графика."""
import os, re, sys, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assemble as A
import body as B
import apply_ops as AO

K = 4
THR = 0.98
REG_KEY = re.compile(r'лист регистрации внесения изменений|регистрации изменений|номера листов', re.I)


def block_units(b, use_old=False):
    """Строки блока для потока слов (номера в начале строк потом снимает strip_num)."""
    if b['type'] in ('paragraph', 'list_item'):
        t = b['replaced_word_text'] if (use_old and b.get('replaced_word_text')) else b['text']
        return [t]
    if b['type'] == 'table':
        return [p for c in b['cells'] for p in c['text'].split('\n')]
    if b['type'] == 'figure':
        return list(b.get('text_fragments', []))
    if b['type'] == 'visio':
        return [s['text'] for s in b.get('shapes', [])]
    if b['type'] == 'excel':
        return [c['text'] for s in b.get('sheets', []) for c in s['cells']]
    return []


def units_of(rec, use_old=False, meta=False):
    out = []
    for n in rec['body']:
        if n.get('heading'): out.append(n['heading'])
        for b in n['blocks']: out += block_units(b, use_old)
    for a in rec['appendices']:
        if a.get('heading'): out.append(a['heading'])
        for b in a['blocks']: out += block_units(b, use_old)
    if meta:
        for ms in rec['meta_sections']:
            for b in ms['blocks']: out += block_units(b, use_old)
    return out


def words_of(units):
    return A.norm(' '.join(B.strip_num(u) for u in units)).split()


def sh(words, k=K):
    return {' '.join(words[i:i + k]) for i in range(len(words) - k + 1)}


def coverage_flags(words, have, k=K):
    n = len(words)
    cov = [False] * n
    for i in range(n - k + 1):
        if ' '.join(words[i:i + k]) in have:
            for j in range(i, i + k): cov[j] = True
    return cov


def runs(flags):
    res, i = [], 0
    while i < len(flags):
        if not flags[i]:
            j = i
            while j < len(flags) and not flags[j]: j += 1
            res.append((i, j)); i = j
        else:
            i += 1
    return res


def acceptance(ctx, rec, et, results, pairs, amd, etalon_no, dropped, parsed, s, e, main_e, appx_e, entries):
    card = {}
    # ---------- (1) полнота по страницам эталона
    content_words = words_of(units_of(rec))
    content_words_old = words_of(units_of(rec, use_old=True))
    all_words = words_of(units_of(rec, meta=True))
    have, have_old, have_all = sh(content_words), sh(content_words_old), sh(all_words)
    vocab = set(content_words)
    bg = sh(content_words, 2)
    tot2 = hit2 = 0
    sheet_sh = {izm: sh(words_of(t)) for izm, t in ctx.sheet_words.items()}
    unapplied = [(izm, op['n'], set(A.norm(op.get('new') or '').split()))
                 for izm, op, r in results if r.status in ('NOT_FOUND', 'SKIPPED', 'NOT_IN_SHEETS') and op.get('new')]
    per_page, tot, hit, hit_old = [], 0, 0, 0
    classes = {}
    reasons = collections.Counter()
    page_lines = collections.defaultdict(list)
    for i, (p, l) in enumerate(et.pl):
        page_lines[p].append(i)
    body_page = min((et.line_page[i] for i in range(et.s, len(et.lines))), default=et.n + 1) if et.s < len(et.lines) else et.n + 1
    for p in range(1, et.n + 1):
        idx = page_lines.get(p, [])
        core = [i for i in idx if i >= et.s]
        pg = et.doc[p - 1]
        n_img, n_dr = len(pg.get_images()), len(pg.get_drawings())
        if not idx:
            if p < body_page:
                classes[p] = ('out_of_content', 'скан (титул/лист регистрации): текстового слоя нет')
            elif n_img or n_dr > 5:
                classes[p] = ('graphics', f'страница без текста: изображений {n_img}, векторных объектов {n_dr}')
            else:
                classes[p] = ('blank', 'пустая страница')
            continue
        if not core:
            if p == 1:
                classes[p] = ('out_of_content', 'титульный лист')
            elif any(REG_KEY.search(et.lines[i]) for i in idx[:6]) or any(REG_KEY.search(et.lines[i]) for i in idx):
                classes[p] = ('out_of_content', 'лист регистрации изменений')
            else:
                classes[p] = ('meta_section', 'предисловие / перечень рассылки / содержание')
            continue
        pw = words_of([et.lines[i] for i in core])
        if len(pw) < 20 and (n_img or n_dr > 5):
            classes[p] = ('graphics', f'слов {len(pw)}, изображений {n_img}, векторных объектов {n_dr}')
            if len(pw) >= K:
                pass
            continue
        psh = sh(pw)
        if not psh:
            classes[p] = ('blank', f'слов {len(pw)}')
            continue
        p2 = sh(pw, 2)
        tot2 += len(p2); hit2 += len(p2 & bg)
        c = len(psh & have); co = len(psh & have_old)
        tot += len(psh); hit += c; hit_old += co
        cov = c / len(psh)
        row = {'page': p, 'coverage': round(cov, 4), 'coverage_without_pdf_substitution': round(co / len(psh), 4), 'shingles': len(psh)}
        if cov >= THR:
            classes[p] = ('text_verified', f'{cov:.1%}')
        else:
            # кластеры непокрытых 4-грамм: слова [a, b) страницы
            bad = [q for q in range(len(pw) - K + 1) if ' '.join(pw[q:q + K]) not in have]
            unc, st = [], None
            for q in bad:
                if st is not None and q <= en:
                    en = q + K
                else:
                    if st is not None: unc.append((st, en))
                    st, en = q, q + K
            if st is not None: unc.append((st, en))
            tw = set()
            try:
                for t in pg.find_tables().tables:
                    for r_ in t.extract():
                        for cell in r_:
                            tw |= set(A.norm(cell or '').split())
            except Exception:
                pass
            cls = collections.Counter()
            sample = []
            for a_, b_ in unc:
                rw = pw[a_:b_]
                if sum(rw[q] + rw[q + 1] in vocab for q in range(len(rw) - 1)) >= 1 and (len(rw) <= 12 or sum(rw[q] + rw[q + 1] in vocab for q in range(len(rw) - 1)) >= 0.08 * len(rw)):
                    k = 'разрыв слова в текстовом слое PDF (вёрстка)'
                elif len(rw) >= 3 and sum(' '.join(rw[q:q + 2]) in bg for q in range(len(rw) - 1)) >= 0.75 * (len(rw) - 1):
                    k = ('таблица: слова есть в записи, порядок ячеек иной' if tw and sum(w in tw for w in rw) >= 0.6 * len(rw)
                         else 'стык блоков: слова и пары слов есть в записи, соседство иное (колонки RU/EN, границы страниц)')
                else:
                    hit_op = next(((iz, n) for iz, n, ws in unapplied if len(rw) >= 3 and sum(w in ws for w in rw) >= 0.5 * len(rw)), None)
                    hit_sh = next((iz for iz, ss in sheet_sh.items() if len(rw) >= 4 and
                                   sum(' '.join(rw[q:q + K]) in ss for q in range(len(rw) - K + 1)) >= 0.6 * (len(rw) - K + 1)), None)
                    if hit_op:
                        k = f'правка не применена (изм{hit_op[0]} #{hit_op[1]})'
                    elif hit_sh:
                        k = f'текст есть в листе замены изм{hit_sh}, но протокол его не адресует (лист не привязан)'
                    elif tw and sum(w in tw for w in rw) >= 0.6 * len(rw):
                        k = 'таблица (порядок/состав ячеек, перенос строк)'
                    elif len(rw) < 8:
                        k = 'локальное расхождение 1–3 слов (редакция/орфография)'
                    elif n_img or n_dr > 20:
                        k = 'страница с рисунком/формой: текст в графике, не разобран'
                    else:
                        k = 'нет в источниках Word (расхождение Word–эталон)'
                cls[k] += len(rw)
                sample.append((len(rw), ' '.join(rw[:14])))
            sample.sort(reverse=True)
            row['reasons'] = dict(cls)
            row['largest_missing'] = sample[0][1] if sample else ''
            classes[p] = ('text_partial', f'{cov:.1%}; ' + ', '.join(f'{k}: {v} сл.' for k, v in cls.most_common(3)))
            for k_, v_ in cls.items(): reasons[k_] += v_
        per_page.append(row)
    # глобально по ядру, как body.py
    core_pdf = words_of(et.lines[et.s:])
    g_all = len(sh(core_pdf) & have) / max(len(sh(core_pdf)), 1)
    g_old = len(sh(core_pdf) & have_old) / max(len(sh(core_pdf)), 1)
    front_pdf = words_of(et.lines[:et.s])
    front_cov = len(sh(front_pdf) & have_all) / max(len(sh(front_pdf)), 1)
    card['completeness'] = {
        'by_pages': round(hit / max(tot, 1), 4), 'by_pages_without_pdf_substitution': round(hit_old / max(tot, 1), 4),
        'global_core_like_body_py': round(g_all, 4), 'global_core_without_pdf_substitution': round(g_old, 4),
        'front_pages_vs_record(meta+body), info': round(front_cov, 4),
        'by_pages_bigrams_order_tolerant, info': round(hit2 / max(tot2, 1), 4),
        'target': THR, 'pages_below_target': [r for r in per_page if r['coverage'] < THR],
        'uncovered_words_by_reason': dict(reasons),
    }
    card['pages'] = {'total': et.n, 'by_class': dict(collections.Counter(v[0] for v in classes.values())),
                     'unaccounted': et.n - len(classes), 'detail': {str(p): list(v) for p, v in sorted(classes.items())}}
    # ---------- (3) цепочка изменений
    chain, gaps = [], []
    HERE = os.path.dirname(os.path.abspath(__file__))
    doc = rec['doc_num']
    N = etalon_no or (max(amd) if amd else 0)
    for k in range(1, N + 1):
        row = {'izm': k}
        if k not in amd:
            row['gap'] = 'нет папки изменения (пустая карточка Lotus)'
            gaps.append({'type': 'chain_missing', 'where': f'изм{k}', 'detail': row['gap']})
            chain.append(row); continue
        date, d = amd[k]
        row['date'] = date
        files = [os.path.basename(f) for f in glob.glob(d + '/*')]
        row['files'] = len(files)
        row['sheets_docx'] = len([f for f in glob.glob(d + '/*.docx') if A.classify(f) == 'sheets'])
        row['changelog_docx'] = len([f for f in glob.glob(d + '/*.docx') if A.classify(f) == 'changelog'])
        opsf = os.path.join(HERE, 'ops', doc, f'izm{k}.json')
        rs = [r for r in results if r[0] == k]
        if not os.path.exists(opsf):
            row['gap'] = 'протокол правок не разобран (нет ops/*.json)' + ('' if row['changelog_docx'] else '; листа изменения нет в карточке')
            gaps.append({'type': 'chain_no_protocol', 'where': f'изм{k}', 'detail': row['gap']})
        else:
            row['ops'] = len(rs)
            row['statuses'] = dict(collections.Counter(r[2].status for r in rs))
            row['via'] = dict(collections.Counter(r[2].via for r in rs if r[2].status == 'APPLIED'))
            bad = [r for r in rs if r[2].status not in ('APPLIED', 'ALREADY_PRESENT')]
            row['not_applied'] = [f'#{r[1]["n"]} {r[2].status}: {r[2].why[:70]}' for r in bad]
            for r in bad:
                gaps.append({'type': 'op_not_applied', 'where': f'изм{k} #{r[1]["n"]}', 'detail': f'{r[2].status}: {r[2].why[:100]} | {r[1]["source_line"][:100]}'})
        chain.append(row)
    extra = sorted(set(amd) - set(range(1, N + 1)))
    if extra:
        gaps.append({'type': 'chain_extra', 'where': f'изм{extra}', 'detail': f'изменения сверх номера эталона {N}'})
    card['chain'] = {'etalon_no': N, 'rows': chain}
    ctx.gaps.extend(gaps)
    # ---------- (4) нумерация
    card['numbering'] = numbering(rec, results)
    # ---------- (5) источники
    src = collections.Counter(); srcw = collections.Counter(); by_izm = collections.Counter()
    for grp in (rec['body'], rec['appendices']):
        for n in grp:
            for b in n['blocks']:
                units = []
                if b['type'] == 'table':
                    for c in b['cells']:
                        src[('cell', c['source'].split(':')[0])] += 1
                        srcw[c['source'].split(':')[0]] += len(A.norm(c['text']).split())
                        if ':' in c['source']: by_izm[c['source']] += 1
                else:
                    cat = b['source'].split(':')[0]
                    src[(b['type'], cat)] += 1
                    srcw[cat] += len(block_units_words(b))
                    if ':' in b['source']: by_izm[b['source']] += 1
    txt_units = collections.Counter()
    for (t, c), v in src.items():
        if t in ('paragraph', 'list_item', 'cell'): txt_units[c] += v
    totu = sum(txt_units.values()) or 1
    card['sources'] = {'text_units_paragraphs_and_cells': dict(txt_units),
                       'share': {k: round(v / totu, 4) for k, v in txt_units.items()},
                       'words': dict(srcw), 'by_amendment': dict(by_izm),
                       'by_type': {f'{t}/{c}': v for (t, c), v in sorted(src.items())}}
    # ---------- проверка абзацев
    vs = collections.Counter()
    for grp in (rec['body'], rec['appendices']):
        for n in grp:
            for b in n['blocks']:
                if b['type'] in ('paragraph', 'list_item'):
                    vs[f'paragraph verified={b["verified"]}'] += 1
                elif b['type'] == 'table':
                    for c in b['cells']:
                        if c['verified'] is not None: vs[f'cell verified={c["verified"]}'] += 1
    card['verification'] = dict(vs)
    card['verification']['pdf_substituted'] = ctx.stat['pdf_substituted']
    card['verification']['pdf_substituted_low_confidence_ratio_lt_0.8'] = ctx.stat['pdf_substituted_low']
    card['verification']['unverified_paragraphs_kept'] = ctx.stat['unverified_kept']
    # ---------- (6) графика
    fig = collections.Counter(); fmts = collections.Counter(); vis = {'count': 0, 'shapes': 0, 'links': 0}
    exc = {'count': 0, 'cells': 0}
    unread = []
    for grp in (rec['body'], rec['appendices'], rec['meta_sections']):
        for n in grp:
            for b in n['blocks']:
                if b['type'] == 'figure':
                    fig['figure'] += 1; fmts[b.get('format', '?')] += 1
                    if not b.get('readable'): unread.append(b.get('file') or b.get('format'))
                elif b['type'] == 'visio':
                    vis['count'] += 1; vis['shapes'] += len(b.get('shapes', [])); vis['links'] += len(b.get('links', []))
                elif b['type'] == 'excel':
                    exc['count'] += 1; exc['cells'] += sum(len(s['cells']) for s in b.get('sheets', []))
    tb = sum(1 for grp in (rec['body'], rec['appendices']) for n in grp for b in n['blocks'] if b['type'] in ('paragraph', 'list_item') and b.get('in_textbox'))
    dl = {}
    for name, ps in parsed.items():
        if name == 'base' or True:
            mine_tables = len(ps.tables)
            mine_gfx = len(ps.gfx)
            dl[name] = {'docling_tables': ps.docling.get('tables'), 'my_tables': mine_tables,
                        'docling_pictures': ps.docling.get('pictures'), 'my_graphics': mine_gfx,
                        'aligned_paragraphs': f'{ps.docling.get("aligned")}/{ps.docling.get("mine_paragraphs")}', 'warn': ps.warn}
    card['graphics'] = {'figures': fig['figure'], 'formats': dict(fmts), 'unreadable_format_files': len(unread),
                        'visio': vis, 'excel': exc, 'textbox_paragraphs': tb, 'other_unparsed': ctx.stat['gfx_other'],
                        'emf_wmf_text_fragments': ctx.stat['fig_text_fragments'], 'emf_bitmap_only': ctx.stat['fig_emf_bitmap'], 'visio_without_vsdx': ctx.stat['visio_unreadable'], 'excel_unreadable': ctx.stat['excel_unreadable'],
                        'docling_crosscheck': dl}
    card['dropped_out_of_content'] = dict(dropped)
    card['counts'] = {'nodes': len(rec['body']), 'appendices': len(rec['appendices']), 'meta_sections': [m['name'] for m in rec['meta_sections']],
                      'history_entries': sum(len(n['history']) for g in (rec['body'], rec['appendices'], rec['meta_sections']) for n in g),
                      'history_unassigned': len(rec['history_unassigned']), 'gaps': len(ctx.gaps)}
    return card


def block_units_words(b):
    return [w for u in block_units(b) for w in A.norm(u).split()]


def numbering(rec, results):
    """Нумерация пунктов в разделах: дыры, дубли, нарушение порядка; объяснение правками."""
    explain = collections.defaultdict(list)
    for izm, op, r in results:
        txt = ' '.join(str(x) for x in (op['locator'].get('point'), op['locator'].get('raw'), op['source_line']) if x)
        for m in re.findall(r'\d+(?:\.\d+)*', txt):
            if op['action'] in ('delete', 'renumber', 'insert', 'restate', 'replace'):
                explain[m].append(f'изм{izm} #{op["n"]} {op["action"]}')
    out = {'checked_groups': 0, 'issues': [], 'explained': 0, 'unexplained': 0}
    en_share = sum(1 for n in rec['body'] if n['id'] and n['lang'] == 'en') / max(sum(1 for n in rec['body'] if n['id']), 1)
    bilingual = en_share >= 0.15
    out['bilingual'] = bilingual
    for lg in (('ru', 'en') if bilingual else ('ru',)):
        groups = collections.defaultdict(list)
        for n in rec['body']:
            if n['id'] and (n['lang'] == lg or not bilingual):
                t = tuple(int(x) for x in n['id'].split('.'))
                groups[t[:-1]].append(t[-1])
        for par, nums in groups.items():
            out['checked_groups'] += 1
            seen = set(); prev = None
            for x in nums:
                pid = '.'.join(map(str, par + (x,)))
                if x in seen:
                    out['issues'].append(dict(kind='дубль', lang=lg, id=pid, why=explain.get(pid, [])))
                if prev is not None and x < prev:
                    out['issues'].append(dict(kind='порядок', lang=lg, id=pid, why=explain.get(pid, [])))
                seen.add(x); prev = x
            lo, hi = min(nums), max(nums)
            start = 1 if par else min(lo, 1)
            for x in range(start if par else lo, hi + 1):
                if x not in seen:
                    pid = '.'.join(map(str, par + (x,)))
                    out['issues'].append(dict(kind='дыра', lang=lg, id=pid, why=explain.get(pid, [])))
    for i in out['issues']:
        if i['why']: out['explained'] += 1
        else: out['unexplained'] += 1
    return out


def pct(x):
    return f'{x:.1%}'


def print_card(doc_num, c, out):
    print('=' * 100)
    print(f'КАРТОЧКА ПРИЁМКИ {doc_num}  ->  {os.path.relpath(out)}')
    print('=' * 100)
    cp = c['completeness']
    print(f'(1) ПОЛНОТА КОНТЕНТА (4-граммы страниц эталона, цель ≥{cp["target"]:.0%})')
    print(f'    по страницам: {pct(cp["by_pages"])}  (без подстановок из PDF: {pct(cp["by_pages_without_pdf_substitution"])})')
    print(f'    глобально по ядру (метрика body.py): {pct(cp["global_core_like_body_py"])}  (без PDF: {pct(cp["global_core_without_pdf_substitution"])});  служебные стр. до раздела 1 vs запись: {pct(cp["front_pages_vs_record(meta+body), info"])} (справочно)')
    print(f'    по 2-граммам (терпимо к порядку блоков, справочно): {pct(cp["by_pages_bigrams_order_tolerant, info"])}')
    print(f'    страниц ниже цели: {len(cp["pages_below_target"])}')
    for r in cp['pages_below_target']:
        rs = ', '.join(f'{k}: {v}' for k, v in sorted(r['reasons'].items(), key=lambda kv: -kv[1]))
        print(f'      стр.{r["page"]:>3}: {pct(r["coverage"])} (без PDF {pct(r["coverage_without_pdf_substitution"])}) | {rs} | «{r["largest_missing"][:70]}»')
    if cp['uncovered_words_by_reason']:
        print('    непокрытые слова по классам причин: ' + '; '.join(f'{k}: {v}' for k, v in sorted(cp['uncovered_words_by_reason'].items(), key=lambda kv: -kv[1])))
    pg = c['pages']
    print(f'(2) УЧЁТ СТРАНИЦ: всего {pg["total"]}; ' + ', '.join(f'{k} {v}' for k, v in sorted(pg['by_class'].items())) + f'; неучтённых {pg["unaccounted"]}')
    for cl in ('out_of_content', 'meta_section', 'graphics', 'blank'):
        ps = [f'{p}({v[1][:40]})' for p, v in pg['detail'].items() if v[0] == cl]
        if ps: print(f'      {cl}: ' + ', '.join(ps))
    N = c['chain']['etalon_no']
    print(f'(3) ЦЕПОЧКА ИЗМЕНЕНИЙ 1…{N}' if N else '(3) ЦЕПОЧКА ИЗМЕНЕНИЙ: эталон без номера, папок изменений нет — изменений нет')
    for r in c['chain']['rows']:
        if 'gap' in r and 'ops' not in r:
            print(f'      изм{r["izm"]} {r.get("date","")}: GAP — {r["gap"]}')
        else:
            print(f'      изм{r["izm"]} {r["date"]}: файлов {r["files"]}, листов замены (docx) {r["sheets_docx"]}, листов изменения {r["changelog_docx"]}; правок {r["ops"]}: {r["statuses"]}; применено через {r["via"]}')
            for x in r['not_applied']: print(f'           не применено {x}')
    nb = c['numbering']
    print(f'(4) НУМЕРАЦИЯ ПУНКТОВ: групп {nb["checked_groups"]}, замечаний {len(nb["issues"])} (объяснены правками {nb["explained"]}, не объяснены {nb["unexplained"]})')
    for i in nb['issues'][:25]:
        print(f'      {i["kind"]:6} {i["lang"]} {i["id"]}  ' + ('объяснено: ' + '; '.join(i['why'][:2]) if i['why'] else 'НЕ ОБЪЯСНЕНО'))
    if len(nb['issues']) > 25: print(f'      … ещё {len(nb["issues"]) - 25}')
    sr = c['sources']
    print('(5) ИСТОЧНИКИ (текстовые единицы: абзацы + ячейки): ' + ', '.join(f'{k} {v} ({pct(sr["share"][k])})' for k, v in sorted(sr['text_units_paragraphs_and_cells'].items(), key=lambda kv: -kv[1])))
    print('    слов: ' + ', '.join(f'{k} {v}' for k, v in sorted(sr['words'].items(), key=lambda kv: -kv[1])))
    print('    по изменениям: ' + ', '.join(f'{k} {v}' for k, v in sorted(sr['by_amendment'].items())))
    print('    сверка: ' + ', '.join(f'{k} {v}' for k, v in sorted(c['verification'].items())))
    g = c['graphics']
    print(f'(6) ГРАФИКА: рисунков {g["figures"]} форматы {g["formats"]}, без читаемого формата (Pillow) {g["unreadable_format_files"]}; '
          f'Visio {g["visio"]["count"]} (фигур {g["visio"]["shapes"]}, связей {g["visio"]["links"]}); Excel {g["excel"]["count"]} (ячеек {g["excel"]["cells"]}); '
          f'абзацев из надписей {g["textbox_paragraphs"]}; текстовых фрагментов из EMF/WMF {g["emf_wmf_text_fragments"]}, EMF-растр без текста {g["emf_bitmap_only"]}; прочих объектов без разбора {g["other_unparsed"]}; Visio без vsdx {g["visio_without_vsdx"]}; Excel не xlsx {g["excel_unreadable"]}')
    for n, d in g['docling_crosscheck'].items():
        print(f'      Docling vs свой разбор [{n[:45]}]: таблиц {d["docling_tables"]}/{d["my_tables"]}, картинок {d["docling_pictures"]}/{d["my_graphics"]}, абзацев сопоставлено {d["aligned_paragraphs"]}' + (f' WARN {d["warn"]}' if d['warn'] else ''))
    print(f'    вне контента (не вошло в запись): {c["dropped_out_of_content"]}')
    print(f'    узлов {c["counts"]["nodes"]}, приложений {c["counts"]["appendices"]}, служебных разделов {c["counts"]["meta_sections"]}, записей истории {c["counts"]["history_entries"]} (без адреса {c["counts"]["history_unassigned"]}), GAP {c["counts"]["gaps"]}')
