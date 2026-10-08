"""Лишний текст в каноне — обратная проверка к verify_canon (TASK-021, правило 1, дополнение human 08.10.2026).

verify_canon проверяет полноту: каждая строка эталона есть в каноне. Лишнего не видит: старая редакция пункта рядом с новой
(правила, сохраняющие элементы базы), текст протокола изменений, служебные коды полей проходили как ready
(КД-ДП-В4.036-01 — раздел 7.2 дважды; РД-Б1.042-06 — «29 добавить п.8.6.8.2 … со следующим текстом»).

Абзац тела канона вне таблицы (body_paras, с первого заголовка «1 …»; надписи S и сноски F не проверяются) лишний, если в утверждённом
PDF есть меньше половины его словесных троек (три слова подряд, слова — по pagediff.key). Источник «есть»: текст PDF без
колонтитулов и «Стр. N», плюс текст объектов и колонтитулов Word-источников. Устойчиво к переносам, разрывам страниц,
порядку ячеек таблицы и правке 1–2 слов (это работа сверки пунктов); ловит вставленные куски текста. Ячейки таблиц: доля слов, найденных в PDF (порядок не учитывается), повторы в таблицах не считаются.
  python3 verify_extra.py <src_doc_dir> <canon_text.txt> [источники.docx ...]   -> JSON
"""
import sys, os, re, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pagediff as P, verify_canon as V, blobtext as BT

MIN_WORDS = 8      # короче — не проверяется (заголовки, ячейки)
COVER = 0.5        # доля троек, найденных в PDF, ниже которой абзац лишний


def words(t):
    t = re.sub(r'[\x00-\x08\x0b-\x1f\u00ad\u200b-\u200f\u2060-\u2064\ufeff]', '', t)   # мягкий перенос (\x1f у Word, U+00AD), невидимые знаки
    return [w for w in (P.key(x) for x in re.split(r'[\s\-–—/|]+', t)) if w]


def pdf_words(t):
    """Слова текстового слоя PDF: цепочки одиночных букв (разрядка при выключке по ширине: «т е х н и ч е с к и е») склеиваются."""
    out, run = [], []
    for w in words(t):
        if len(w) == 1 and not w.isdigit(): run.append(w); continue
        if len(run) >= 3: out.append(''.join(run))
        else: out += run
        run = []; out.append(w)
    out += [''.join(run)] if len(run) >= 3 else run
    return out


def formula_like(ws):
    """Формула Word (OMML): больше половины «слов» — одиночные знаки или короткие обозначения с цифрами."""
    return sum(1 for w in ws if len(w) <= 2 or re.fullmatch(r'[a-z]\d*|\d+', w)) > 0.5 * len(ws)


def trigrams(ws):
    return {tuple(ws[i:i + 3]) for i in range(len(ws) - 2)}


def check(doc_dir, canon_text, sources=(), ref_pdf=None):
    rows = [l.split('\t') for l in open(canon_text, encoding='utf-8', errors='replace').read().split('\n')]
    paras = [(r[2].strip(), r[3]) for r in rows if len(r) >= 4 and r[1] in ('T', '-')]
    kinds = [r[1] for r in rows if len(r) >= 4 and r[1] in ('T', '-')]
    intable = {id(p): k == 'T' for p, k in zip(paras, kinds)}
    body = V.body_paras(paras)
    b0 = next((i for i, (n, t) in enumerate(body) if re.match(r'^\s*1\.?\s*\S', (n + ' ' + t).strip()) and len(P.key(t)) >= 3), 0)
    pages = P.canon_pages(ref_pdf or P.ref_pdfs(doc_dir)[0])   # часть многочастного документа — свой эталон (plan.json canon_pdf)
    cnt = collections.Counter(k for p in pages for k in {P.key(l) for l in p['lines']})
    head = {k for k, c in cnt.items() if c > 0.3 * len(pages)}
    flow = [l for p in pages for l in p['lines'] if P.key(l) not in head and not re.search(r'Стр\.?\s*/?\s*(page)?\s*\d', l)]
    fw = pdf_words(' '.join(flow))
    allw = pdf_words(' '.join(l for p in pages for l in p['lines']))   # с колонтитулами: фраза, повторённая на многих листах (ДП-В4.005-07), — не колонтитул для наличия
    pdf_cnt = collections.Counter(tuple(fw[i:i + 3]) for i in range(len(fw) - 2))
    ref = set(pdf_cnt) | {tuple(allw[i:i + 3]) for i in range(len(allw) - 2)}
    other = ' '.join(r for f in sources if str(f).endswith('.docx') for r in BT.docx_object_runs(f))
    ref |= trigrams(words(other))
    paras_b = [(n, t, words(t), intable.get(id(pp), False)) for pp in body[b0:] for n, t in [pp]]
    fwset = set(fw) | set(allw) | set(words(other)) | set(words(' '.join(flow)))
    can_cnt = collections.Counter(g for _, _, ws, tb in paras_b if not tb for g in (tuple(ws[i:i + 3]) for i in range(len(ws) - 2)))
    out, rep = [], []
    for n, t, ws, tb in paras_b:
        if len(ws) < MIN_WORDS or formula_like(ws): continue
        if tb:   # ячейка таблицы: порядок чтения PDF другой — только наличие слов, без повторов
            cov = sum(1 for w in ws if w in fwset) / len(ws)
            if cov < COVER: out.append((round(cov, 2), n, t))
            continue
        tg = trigrams(ws)
        cov = sum(1 for g in tg if g in ref) / len(tg)
        wcov = sum(1 for w in ws if w in fwset) / len(ws)
        if cov < COVER and wcov < 0.8: out.append((round(cov, 2), n, t)); continue   # тройки рвутся на разрядке/вёрстке — тогда нужны и чужие слова
        # повтор сверх эталона: тройки абзаца в каноне встречаются чаще, чем в PDF (старая редакция рядом с новой)
        over = sum(1 for g in tg if g in pdf_cnt and can_cnt[g] > pdf_cnt[g]) / len(tg)
        if over >= COVER: rep.append((round(over, 2), n, t))
    return {'_items': out, '_repeat': rep, 'paras_extra': len(out), 'paras_repeat': len(rep), 'words_extra': sum(len(words(t)) for _, _, t in out + rep),
            'examples': [f'[нет в PDF {1 - c:.0%}] {n} {t[:140]}'.strip() for c, n, t in out[:8]]
                        + [f'[повтор {c:.0%}] {n} {t[:140]}'.strip() for c, n, t in rep[:8]]}


if __name__ == '__main__':
    a = sys.argv[1:]
    print(json.dumps(check(a[0], a[1], a[2:]), ensure_ascii=False, indent=1))
