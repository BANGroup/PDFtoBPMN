"""Конвейер без Word (пилот TASK-021, шаг 9): plan (reeng_plan, Word не нужен) -> pyassemble -> py_numfix -> pynum.dump -> verify_canon.

python3 pyengine.py --src <каталог src/<doc>> --out <каталог результата> --work <рабочий каталог> [--doc <doc_num>]
Результат: out/canon.docx, canon_text.txt, verify.json, status.json {stage_seconds, ru_maxrss_mb, ready, ...}. Word не запускается: в reeng_plan подменяется
ensure_dumps (выгрузки ListString листов замены считает pynum). Подключается в batch_run.py флагом --engine py (run_py_engine).
"""
import sys, os, re, json, glob, time, shutil, resource, argparse, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
import reeng_plan as rp
import pagediff as PD
import pynum, pyassemble, py_numfix, verify_canon
import docx, wordrun


def _no_word(*a, **k): raise RuntimeError('Word запрещён в py-движке (нет .docx-конверсии базы/листа рядом с .doc?)')
wordrun.run = _no_word
import pdf_frag
_mk = pdf_frag.make_fragment
def _mk_safe(*a, **k):
    st = _mk(*a, **k)
    if not st.get('bookmarks'): st['bookmarks'] = ['(без закладки)']   # reeng_plan.plan_doc берёт bookmarks[0]: пустой фрагмент PDF-страниц не должен ронять план
    return st
pdf_frag.make_fragment = _mk_safe


def py_ensure_dumps(slug, workdir, files):
    os.makedirs(os.path.join(workdir, 'sd'), exist_ok=True)
    for f in files:
        dp = rp.dump_path_for(workdir, f)
        if not os.path.exists(dp): pynum.dump(f, dp)


SKIP_BASE = re.compile('пояснит|приказ|ЭСЗ', re.I)


def ensure_docx_siblings(sd):
    """.doc листов изменений, баз и глав -> <f>x из кэша doc2docx (Word не запускается). -> список .doc без конвертации (кроме приказов/пояснительных/ЭСЗ в word/)."""
    import doc2docx
    miss = []
    for f in glob.glob(sd + '/**/*', recursive=True):
        if not f.lower().endswith('.doc') or '/files/' in f or '/__parts/' in f: continue
        if os.path.exists(f + 'x') and os.path.getsize(f + 'x') > 0: continue
        c = doc2docx.cached(f)
        if c: shutil.copy(c, f + 'x')
        elif '/amendments/' in f or not SKIP_BASE.search(re.sub(r'\bк\s+приказ\w*', '', os.path.basename(f), flags=re.I)): miss.append(f)
    return miss


def rss_mb(): return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


def run_doc(sd, od, wd, doc=None):
    doc = doc or os.path.basename(os.path.normpath(sd))
    os.makedirs(od, exist_ok=True); shutil.rmtree(wd, ignore_errors=True); os.makedirs(wd)
    st = {'doc': doc, 'engine': 'py', 'stage_seconds': {}, 'warnings': []}
    T = [time.time()]
    def lap(name):
        now = time.time(); st['stage_seconds'][name] = round(now - T[0], 2); T[0] = now
    try:
        rp.ensure_dumps = py_ensure_dumps
        import batch_run as br, doc2docx, pychapters
        miss = ensure_docx_siblings(sd)
        if miss: raise RuntimeError('нет конвертации .doc (кэш doc2docx пуст, Word не запускается): ' + '; '.join(os.path.relpath(m, sd) for m in miss)[:400])
        ch = br.chapter_files(sd)
        if ch:
            fl = [f if f.lower().endswith('.docx') else f + 'x' for _, f in ch]
            miss = [f for f in fl if not os.path.exists(f)]
            if miss: st['warnings'].append('глав без docx: %d' % len(miss))
            r = pychapters.concat([f for f in fl if os.path.exists(f)], os.path.join(sd, 'word', '__главы.docx'))
            st['chapters'] = r; lap('chapters')
        pl = rp.plan_doc(sd, 'py', wd); lap('plan')
        json.dump(pl, open(os.path.join(od, 'plan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        if pl.get('fatal'): raise RuntimeError(pl['fatal'][-300:])
        ref_pdf = pl['canon_pdf']
        d, lg = pyassemble.assemble(os.path.join(wd, 'base_marked.docx'), pl, wd, os.path.join(wd, 'canon_raw.docx')); lap('assemble')
        st['assemble'] = lg
        if lg['marker_not_found']: st['warnings'].append('marker not found: ' + ','.join(lg['marker_not_found']))
        if lg['frag_errors']: st['warnings'].append('frag errors: %d' % len(lg['frag_errors']))
        nlog = py_numfix.run(d, ref_pdf)
        d.save(os.path.join(od, 'canon.docx')); lap('numfix')
        import ooxml_check
        st['ooxml_problems'] = ooxml_check.check(os.path.join(od, 'canon.docx'))
        if st['ooxml_problems']: st['warnings'].append('ooxml: ' + '; '.join(st['ooxml_problems'])[:300])
        st['numfix'] = [{k: v for k, v in x.items() if k not in ('detail', 'unmatched_list')} for x in nlog]
        pynum.dump(os.path.join(od, 'canon.docx'), os.path.join(od, 'canon_text.txt')); lap('dump')
        srcs = [os.path.join(wd, 'base_orig.docx')] + sorted(glob.glob(sd + '/amendments/**/*.docx', recursive=True))
        v = verify_canon.verify(sd, os.path.join(od, 'canon_text.txt'), os.path.join(od, 'canon.docx'), srcs); lap('verify')
        json.dump(v, open(os.path.join(od, 'verify.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        if v['missing'] > 0 and os.environ.get('A2_PDF_LINES', '1') == '1':   # A2 PDF-строки (круг 2): строки класса B (нет ни в одном Word) -> из текстового слоя PDF, закладка PDF_src_*
            import pdf_lines
            try: pr = pdf_lines.patch_canon(sd, od, ref_pdf, srcs)
            except Exception as e:   # вставка из PDF не должна ронять сборку (ПР-073-15: нет numbering part)
                st['warnings'].append(f'pdf_lines пропущен: {type(e).__name__}: {e}'[:300]); pr = {'inserted': 0, 'items': []}
            st['pdf_lines'] = {'inserted': pr['inserted'], 'classes': {c: sum(1 for i in pr['items'] if i['cls'] == c) for c in {i['cls'] for i in pr['items']}}}
            if pr.get('verify'): v = json.load(open(os.path.join(od, 'verify.json'), encoding='utf-8'))
            if pr.get('ooxml_problems'): st['warnings'].append('ooxml после pdf_lines: ' + '; '.join(pr['ooxml_problems'])[:300])
            lap('pdf_lines')
        if os.environ.get('A2_PDF_WORDS', '1') == '1':   # A2 PDF-слова (круг 3): абзац канона отличается от абзаца эталона 1–3 словами -> слова из PDF, закладка PDF_src_p*_w*
            import pdf_words
            keep = {f: open(os.path.join(od, f), 'rb').read() for f in ('canon.docx', 'canon_text.txt', 'verify.json') if os.path.exists(os.path.join(od, f))}
            def restore(why):   # шаг необязательный: при сбое или ухудшении проверки канон возвращается к состоянию до него (validator 07.10)
                for f, b_ in keep.items(): open(os.path.join(od, f), 'wb').write(b_)
                st['warnings'].append(why[:300]); return json.load(open(os.path.join(od, 'verify.json'), encoding='utf-8'))
            bad = lambda x: x['missing'] + x['numbered_bad'] + x['duplicates'] + x['frozen_numbers']
            try:
                pw = pdf_words.patch_words(sd, od, ref_pdf, srcs)
                st['pdf_words'] = {'replaced': pw['replaced']}
                if pw.get('verify'):
                    v2 = json.load(open(os.path.join(od, 'verify.json'), encoding='utf-8'))
                    if bad(v2) > bad(v): v = restore(f'pdf_words откатан: проверка ухудшилась ({bad(v)} -> {bad(v2)})'); st['pdf_words'] = {'replaced': 0, 'rolled_back': pw['replaced']}
                    else: v = v2
                if pw.get('ooxml_problems'): st['warnings'].append('ooxml после pdf_words: ' + '; '.join(pw['ooxml_problems'])[:300])
            except Exception as e:   # ПР-073-15: нет numbering part — как у pdf_lines
                v = restore(f'pdf_words пропущен: {type(e).__name__}: {e}')
            lap('pdf_words')
        # ВЫКЛЮЧЕНО по умолчанию (orchestrator 08.10): дописывание «осиротевших» номеров в конец тела подгоняет verify под эталон,
        # а строка оказывается не на своём месте (КД-РД-Б7.006-02: 18 подписей схем в конце документа). Подписи схем — класс C.
        if v['numbered_bad'] and os.environ.get('A2_PDF_NUM', '0') == '1':
            import pdf_lines
            keep = {f: open(os.path.join(od, f), 'rb').read() for f in ('canon.docx', 'canon_text.txt', 'verify.json') if os.path.exists(os.path.join(od, f))}
            def restore_num(why):
                for f, b_ in keep.items(): open(os.path.join(od, f), 'wb').write(b_)
                st['warnings'].append(why[:300]); return json.load(open(os.path.join(od, 'verify.json'), encoding='utf-8'))
            bad = lambda x: x['missing'] + x['numbered_bad'] + x['duplicates'] + x['frozen_numbers']
            try:
                d2 = docx.Document(os.path.join(od, 'canon.docx'))
                n_orph = pdf_lines.append_orphan_numbers(d2, ref_pdf, os.path.join(od, 'canon_text.txt'))
                st['pdf_num'] = {'appended': n_orph}
                if n_orph:
                    d2.save(os.path.join(od, 'canon.docx'))
                    pynum.dump(os.path.join(od, 'canon.docx'), os.path.join(od, 'canon_text.txt'))
                    v2 = verify_canon.verify(sd, os.path.join(od, 'canon_text.txt'), os.path.join(od, 'canon.docx'), srcs)
                    json.dump(v2, open(os.path.join(od, 'verify.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
                    if bad(v2) >= bad(v): v = restore_num(f'pdf_num откатан: проверка не улучшилась ({bad(v)} -> {bad(v2)})'); st['pdf_num'] = {'appended': 0, 'rolled_back': n_orph}
                    else: v = v2
            except Exception as e:
                v = restore_num(f'pdf_num пропущен: {type(e).__name__}: {e}')
            lap('pdf_num')
        st['verify'] = {k: v[k] for k in ('lines', 'missing', 'numbered', 'numbered_bad', 'duplicates', 'frozen_numbers', 'live_numbering', 'coverage')}
        st['ready'] = v['lines'] > 0 and v['missing'] == 0 and v['numbered_bad'] == 0 and v['duplicates'] == 0 and v['frozen_numbers'] == 0
        st['error'] = ''
    except Exception:
        st['error'] = traceback.format_exc()[-800:]; st['ready'] = False
    st['seconds'] = round(sum(st['stage_seconds'].values()), 2); st['ru_maxrss_mb'] = rss_mb()
    json.dump(st, open(os.path.join(od, 'status.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return st


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True); ap.add_argument('--out', required=True); ap.add_argument('--work', required=True); ap.add_argument('--doc')
    a = ap.parse_args()
    s = run_doc(a.src, a.out, a.work, a.doc)
    print(json.dumps({k: s.get(k) for k in ('doc', 'ready', 'seconds', 'ru_maxrss_mb', 'stage_seconds', 'verify', 'error', 'warnings')}, ensure_ascii=False))
