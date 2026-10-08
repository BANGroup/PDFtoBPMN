"""Канон целиком из текстового слоя утверждённого PDF (TASK-021, шаг 11.2): для крупных документов, где сборка из Word не годится.

python3 pdf_canon.py --src <каталог src/<doc> (одна часть)> --out <каталог результата> [--doc <doc_num>]
Результат (формат как у pyengine): out/canon.docx, canon_text.txt, verify.json, verify_extra.json, status.json {source:'pdf', ready, ...}.
Word и ИИ не нужны. Конвейер: страницы эталона с начала содержания (как в verify_canon: титул, лист регистрации, оглавление отброшены) ->
pdf_frag.make_fragment (абзацы по геометрии, живая нумерация, таблицы find_tables, закладки PDF_src_p<N>) -> стили заголовков по уровню номера ->
py_numfix (выравнивание нумерации по эталону) -> pynum.dump -> verify_canon.verify -> verify_extra.check.
Двуязычные страницы (РД-Б8.*, РД-М1.031-04): оставлены обе колонки в порядке PDF; английский пункт идёт отдельным абзацем (свой список) сразу за русским
(или после русской колонки страницы — как в PDF). Многочастный документ: части — отдельные процессы (batch_run --engine pdf, split_parts), здесь одна часть.
Сканы и битый слой: доля строк-мусора (pagediff.garbage) > GARBAGE_MAX — документ пропускается (status skipped_garbage).
"""
import sys, os, re, json, time, resource, argparse, traceback, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
import docx
from docx.oxml.ns import qn
import pagediff as P
import reeng_plan as rp
import pdf_frag, pynum, py_numfix, verify_canon, verify_extra, ooxml_check

GARBAGE_MAX = 0.3


def rss_mb(): return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


def start_page(pages):
    """Индекс первой страницы содержания: то же правило, что в verify_canon.verify (титул/регистрация/оглавление раньше)."""
    st = next((i for i, p in enumerate(pages) if any(re.match(r'^\s*1\.?\s+(ЦЕЛЬ|НАЗНАЧЕНИЕ|ОБЩИЕ)', l, re.I) and not re.search(r'\d\s*$', l.strip()) for l in p['lines'])), None)
    if st is None:
        st = next((i for i, p in enumerate(pages) if any(re.match(r'^\s*(1\.?\s+ОБЛАСТЬ|(РАЗДЕЛ|ЧАСТЬ|ГЛАВА)\s+1\b|ОБЩИЕ ПОЛОЖЕНИЯ\s*$)', l, re.I) and not re.search(r'[.…]{3,}|\d\s*$', l.strip()) for l in p['lines'])), 1 if len(pages) > 1 else 0)
    return st


def garbage_share(pages, head, start):
    ls = [l for p in pages[start:] for l in p['lines'] if P.key(l) not in head and len(P.key(l)) >= 6]
    return (sum(1 for l in ls if P.garbage(l)) / len(ls)) if ls else 1.0


def bilingual_pages(pdf, pages_idx):
    """Страницы с двумя колонками (русская слева, английская справа): >=6 строк начинаются в правой половине и >=6 — в левой."""
    import fitz
    d = fitz.open(pdf); n = 0
    for i in pages_idx:
        pg = d[i]; w = pg.rect.width
        xs = [l['x0'] for l in pdf_frag.page_lines(pg)]
        if sum(x > 0.5 * w for x in xs) >= 6 and sum(x < 0.4 * w for x in xs) >= 6: n += 1
    return n


def style_headings(path, pdf):
    """Стили: нумерованный многоуровневый абзац (номер вида 7.2.5), короткий, без точки в конце -> Heading min(уровень, 4); остальное Normal. Затем numfix по эталону."""
    d = docx.Document(path)
    root = d.part.numbering_part.element
    multi = set()
    for n in root.findall(qn('w:num')):
        aid = n.find(qn('w:abstractNumId')).get(qn('w:val'))
        for a in root.findall(qn('w:abstractNum')):
            if a.get(qn('w:abstractNumId')) == aid:
                mt = a.find(qn('w:multiLevelType'))
                if mt is not None and mt.get(qn('w:val')) == 'multilevel': multi.add(n.get(qn('w:numId')))
    nh = 0
    for p in d.paragraphs:
        np_ = p._p.find('.//' + qn('w:numPr'))
        if np_ is None: continue
        if np_.find(qn('w:numId')).get(qn('w:val')) not in multi: continue
        t = p.text.strip(); lvl = int(np_.find(qn('w:ilvl')).get(qn('w:val')))
        if len(t) <= 120 and not t.endswith(('.', ';', ':', ',')):
            p.style = d.styles['Heading %d' % min(lvl + 1, 4)]; nh += 1
    nlog = py_numfix.run(d, pdf)
    d.save(path)
    return nh, [{k: v for k, v in x.items() if k not in ('detail', 'unmatched_list')} for x in nlog]


def run_doc(sd, od, doc=None, wd=None):
    doc = doc or os.path.basename(os.path.normpath(sd))
    os.makedirs(od, exist_ok=True)
    st = {'doc': doc, 'engine': 'pdf', 'source': 'pdf', 'stage_seconds': {}, 'warnings': []}
    T = [time.time()]
    def lap(name):
        now = time.time(); st['stage_seconds'][name] = round(now - T[0], 2); T[0] = now
    try:
        refs = P.ref_pdfs(sd)
        if len(refs) != 1: raise RuntimeError(f'ожидался один эталон (часть), найдено {len(refs)}')
        pdf = refs[0]
        pages = P.canon_pages(pdf); head = rp.header_keys(pages); start = start_page(pages)
        st['pdf_pages'] = len(pages); st['start_page'] = start + 1
        gs = garbage_share(pages, head, start); st['garbage_share'] = round(gs, 3)
        if gs > GARBAGE_MAX:
            st['skipped'] = 'garbage'; st['ready'] = False; st['error'] = ''
            st['warnings'].append(f'битый текстовый слой: доля мусорных строк {gs:.2f} > {GARBAGE_MAX} — не берём')
            raise StopIteration
        lap('pages')
        cp = os.path.join(od, 'canon.docx')
        fr = pdf_frag.make_fragment(pdf, list(range(start + 1, len(pages) + 1)), cp, head, restart=True)
        st['fragment'] = {k: (len(v) if isinstance(v, list) else v) for k, v in fr.items() if k != 'bookmarks'}
        st['fragment']['missed_examples'] = fr['missed'][:5]
        if fr['empty_pages']: st['warnings'].append('страниц без текста: %d' % len(fr['empty_pages']))
        lap('fragment')
        st['bilingual_pages'] = bilingual_pages(pdf, range(start, len(pages)))
        nh, nlog = style_headings(cp, pdf); st['headings'] = nh; st['numfix'] = nlog; lap('styles_numfix')
        st['ooxml_problems'] = ooxml_check.check(cp)
        if st['ooxml_problems']: st['warnings'].append('ooxml: ' + '; '.join(st['ooxml_problems'])[:300])
        ct = os.path.join(od, 'canon_text.txt')
        pynum.dump(cp, ct); lap('dump')
        v = verify_canon.verify(sd, ct, cp, [])
        json.dump(v, open(os.path.join(od, 'verify.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1); lap('verify')
        ex = verify_extra.check(sd, ct, [], pdf)
        json.dump(ex, open(os.path.join(od, 'verify_extra.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1); lap('verify_extra')
        st['verify'] = {k: v[k] for k in ('lines', 'missing', 'numbered', 'numbered_bad', 'duplicates', 'frozen_numbers', 'live_numbering', 'coverage')}
        st['paras_extra'] = ex['paras_extra']
        st['ready'] = v['lines'] > 0 and v['missing'] == 0 and v['numbered_bad'] == 0 and v['duplicates'] == 0 and v['frozen_numbers'] == 0 and ex['paras_extra'] == 0
        st['canon_docx_mb'] = round(os.path.getsize(cp) / 1e6, 2)
        st['error'] = ''
    except StopIteration:
        pass
    except Exception:
        st['error'] = traceback.format_exc()[-800:]; st['ready'] = False
    st['seconds'] = round(sum(st['stage_seconds'].values()), 2); st['ru_maxrss_mb'] = rss_mb()
    json.dump(st, open(os.path.join(od, 'status.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return st


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True); ap.add_argument('--out', required=True); ap.add_argument('--doc')
    a = ap.parse_args()
    g = int(os.environ.get('PY_RLIMIT_GB', '5')); resource.setrlimit(resource.RLIMIT_AS, (g << 30, g << 30))
    s = run_doc(a.src, a.out, a.doc)
    print(json.dumps({k: s.get(k) for k in ('doc', 'source', 'ready', 'seconds', 'ru_maxrss_mb', 'stage_seconds', 'verify', 'paras_extra', 'garbage_share', 'error', 'warnings')}, ensure_ascii=False))
