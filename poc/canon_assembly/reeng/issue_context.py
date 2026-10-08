"""Контекст проблем документа для разборщика поштучных правок (TASK-021, шаг 11.1).

python3 issue_context.py <doc> [--limit N]

По live/out/<doc> (у многочастного — по частям) печатает: ненайденные строки эталона (стр. PDF + по 3 соседние строки PDF до/после, класс classify),
неверные номера, лишние абзацы канона (verify_extra), дубли, замороженные номера — и для каждой проблемы ближайшие абзацы канона (± 3) с точным
текстом и ListString (из них копируется "anchor"). Внизу — sha файлов документа для поля files_sha патча.
"""
import os, sys, re, json, inspect, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
import pagediff as P
import verify_canon as V
import pdf_lines as PL
import patch_ops as PO

# та же логика, что verify_canon.verify (исходник не меняется, приём как в missing_pages): вернуть полные списки, а не 10 примеров
_src = inspect.getsource(V.verify).replace("    return {'lines': len(L),", "    return {'_miss_real': miss_real, '_num_bad': num_bad, '_dup': dup, '_frozen': frozen, 'lines': len(L),")
_ns = dict(V.__dict__); exec(_src, _ns)
verify_full = _ns['verify']


def canon_rows(ct):
    rows = [l.split('\t') for l in open(ct, encoding='utf-8', errors='replace').read().split('\n')]
    return [(r[2].strip(), r[3].strip(), r[1]) for r in rows if len(r) >= 4 and r[1] in ('T', '-')]


NUM = re.compile(r'^\s*(\d{1,3}(?:\.\d{1,3})*\.?|[а-яa-z]\)|\d{1,2}\)|[-–‒—•·▪])\s+')


def pkey(line): return P.key(NUM.sub('', line, count=1))


def show_canon(rows, keys):
    """Индексы (до 3) абзацев канона, содержащих (или содержащихся в) первый подошедший ключ из keys; короткие ключи (< 12 знаков) не ищутся.
    Несколько совпадений — обычно оглавление и тело: смотрите все."""
    for k in keys:
        if len(k) < 12: continue
        hit = [i for i, (n, t, _) in enumerate(rows) if len(P.key(t)) >= 12 and (k[:40] in P.key(t) or P.key(t)[:40] in k)]
        if hit: return hit[:3]
    return None


def print_neighbors(rows, hits, width=3):
    for i in hits:
        print('      ---')
        _neighbors(rows, i, width)


def _neighbors(rows, i, width=3):
    for j in range(max(0, i - width), min(len(rows), i + width + 1)):
        n, t, kind = rows[j]
        print(f'      {"=>" if j == i else "  "} [{j}]{"T" if kind == "T" else " "} {n + " " if n else ""}{t[:300]}')


def pdf_flow(ref_pdf):
    return [(p['label'], p['n'], l) for p in P.canon_pages(ref_pdf) for l in p['lines']]


def pdf_context(flow, lab, line, w=3):
    for i, (lb, n, l) in enumerate(flow):
        if lb == lab and l == line:
            return n, flow[max(0, i - w):i], flow[i + 1:i + 1 + w]
    return None, [], []


def unit_report(doc, label, od, sd, limit):
    import verify_extra
    ct, cd = os.path.join(od, 'canon_text.txt'), os.path.join(od, 'canon.docx')
    srcs = PO.srcs_of(od, sd); ref = PO.ref_pdf_of(od, sd)
    v = verify_full(sd, ct, cd, srcs)
    rows = canon_rows(ct); flow = pdf_flow(ref)
    print(f'\n######## {doc} {label or ""}  эталон: {os.path.basename(ref)}')
    print('verify:', {k: v[k] for k in PO.VKEYS})
    cls = {}
    try:
        for it in PL.classify(v['_miss_real'], sd): cls[(it['label'], it['text'])] = it['cls']
    except Exception as e: print('classify не выполнен:', type(e).__name__, e)
    print(f'\n--- A. Ненайденные строки эталона: {len(v["_miss_real"])} (показано {min(limit, len(v["_miss_real"]))})')
    for lab, l in v['_miss_real'][:limit]:
        n, before, after = pdf_context(flow, lab, l)
        print(f'  * стр. {lab} (лист PDF {n}) класс {cls.get((lab, l), "?")}: {l}')
        for _, _, x in before: print(f'        PDF до   : {x}')
        for _, _, x in after: print(f'        PDF после: {x}')
        near = show_canon(rows, [pkey(x) for _, _, x in reversed(before)])
        if near is None: near = show_canon(rows, [pkey(x) for _, _, x in after])
        print('      ближайшие абзацы канона (по соседней строке PDF):' if near is not None else '      соседние строки PDF в каноне не найдены')
        if near is not None: print_neighbors(rows, near)
    print(f'\n--- B. Неверные номера: {len(v["_num_bad"])}')
    for lab, l in v['_num_bad'][:limit]:
        print(f'  * стр. {lab}: ожидается «{l}»')
        near = show_canon(rows, [pkey(l)])
        if near is not None: print_neighbors(rows, near)
        else: print('      текст пункта в каноне не найден')
    print(f'\n--- C. Лишние абзацы канона (verify_extra)')
    try:
        ex = verify_extra.check(sd, ct, srcs, ref)
        print(f'  paras_extra={ex["paras_extra"]} paras_repeat={ex["paras_repeat"]}')
        for tag, items in (('нет в PDF', ex['_items']), ('повтор', ex['_repeat'])):
            for c, n, t in items[:limit]:
                print(f'  * [{tag} {(1 - c) if tag == "нет в PDF" else c:.0%}] {n} {t[:300]}')
                near = show_canon(rows, [P.key(t)])
                if near is not None: print_neighbors(rows, near)
    except Exception as e: print('verify_extra не выполнен:', type(e).__name__, e)
    print(f'\n--- D. Дубли: {len(v["_dup"])}; замороженные номера: {len(v["_frozen"])}')
    for t in v['_frozen'][:limit]: print('  * заморожен:', t[:200])
    for k in v['_dup'][:limit]: print('  * дубль (key):', k[:120])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('doc'); ap.add_argument('--limit', type=int, default=40)
    a = ap.parse_args()
    units = PO.unit_dirs(a.doc)
    if not units: print('нет live/out/' + a.doc); return 1
    for label, od, sd in units: unit_report(a.doc, label, od, sd, a.limit)
    print(f'\n=== files_sha для патча: python3 patch_ops.py --sha {a.doc}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
