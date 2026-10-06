"""Разбор листов изменения как протокола правок и сверка каждой правки с базой и эталоном.

python3 protocol.py <папка документа>
"""
import sys, re, glob, os, collections
sys.path.insert(0, os.path.dirname(__file__))
from assemble import docx_pages, classify, norm, pdf_pages, shingles

K = 4


def quotes(s):
    """Строки в «ёлочках» верхнего уровня с учётом вложенных кавычек."""
    out, depth, start = [], 0, None
    for i, ch in enumerate(s):
        if ch == '«':
            if depth == 0: start = i + 1
            depth += 1
        elif ch == '»' and depth:
            depth -= 1
            if depth == 0: out.append(s[start:i])
    return out


def kind(line):
    l = line.lower()
    if re.search(r'заменой лист|заменой страниц', l): return 'sheets'
    if 'заменить' in l and len(quotes(line)) >= 2: return 'replace'
    if re.search(r'излож|представить в новой редакции|в редакции', l): return 'restate'
    if re.search(r'исключ|утратившим|удалить', l): return 'delete'
    if re.search(r'дополн|добав|ввести|внести вновь|внести сокращ|внести пункт', l): return 'insert'
    if re.search(r'нумерац', l): return 'renumber'
    return None


def cov(text, sh_target):
    w = norm(text).split()
    if len(w) < K: return 1.0 if ' '.join(w) in ' '.join(sh_target and ['']) else None
    s = shingles(w, K)
    return len(s & sh_target) / len(s)


def contains(text, big):
    t = norm(text)
    return None if len(t.split()) < 2 else (t in big)


def main(ddir):
    base = max([f for f in glob.glob(ddir + '/word/*.docx') if classify(f) == 'sheets'], key=os.path.getsize)
    base_txt = norm(' '.join(t for p in docx_pages(base) for t in p))
    canon = [f for f in glob.glob(ddir + '/files/*.pdf') if re.search('[Ээ]талон', f)][0]
    pdfp = pdf_pages(canon)
    canon_txt = ' '.join(' '.join(p) for p in pdfp)
    canon_sh = shingles(canon_txt.split(), K)
    base_sh = shingles(base_txt.split(), K)
    total = collections.Counter()
    for adir in sorted(glob.glob(ddir + '/amendments/*'), key=lambda p: float(re.search(r'изм([\d.]+)', p).group(1))):
        cl = [f for f in glob.glob(adir + '/*.docx') if classify(f) == 'changelog']
        if not cl:
            print(f'\n## {os.path.basename(adir)}: листа изменения в Word НЕТ'); total['нет листа'] += 1; continue
        lines = [t for p in docx_pages(cl[0]) for t in p]
        body = lines[next((i for i, t in enumerate(lines) if t.lower().startswith('введения')), 0) + 2:]
        print(f'\n## {os.path.basename(adir)} — {len(body)} строк протокола')
        pending = None
        for ln in body:
            k = kind(ln)
            q = quotes(ln)
            if k is None and pending and q:        # продолжение: текст новой редакции на следующей строке
                k = pending
            if k is None:
                continue
            pending = k if (k in ('restate', 'insert') and not q) else None
            if k == 'sheets':
                print(f'   [листы] {ln[:120]}'); continue
            if k == 'replace':
                # пары «A» … на «B»: берём соседние кавычки вокруг «на»
                pairs = []
                parts = re.split(r'(«)', ln)
                qs = quotes(ln)
                for a, b in zip(qs[::2], qs[1::2]) if len(qs) % 2 == 0 else [(qs[-2], qs[-1])]:
                    pairs.append((a, b))
                for a, b in pairs:
                    old_in_base = contains(a, base_txt)
                    new_in_canon = contains(b, canon_txt)
                    old_in_canon = contains(a, canon_txt)
                    st = 'OK' if new_in_canon and (not old_in_canon or a in b) else ('НОВОГО НЕТ В ЭТАЛОНЕ' if new_in_canon is False else 'СТАРОЕ ОСТАЛОСЬ')
                    if old_in_base is False: st += ', старого нет в базе'
                    total[st] += 1
                    print(f'   [заменить] {st}: «{a[:45]}» → «{b[:45]}»')
            elif k in ('restate', 'insert'):
                for x in q:
                    if len(norm(x).split()) < 3: continue
                    c = cov(x, canon_sh)
                    st = 'OK' if c is not None and c >= .9 else f'в эталоне {c:.0%}' if c is not None else '?'
                    total['OK' if st == 'OK' else 'текст не найден' if c is not None and c < .5 else 'частично'] += 1
                    print(f'   [{"изложить" if k=="restate" else "дополнить"}] {st}: «{x[:70]}»')
                if not q and not pending:
                    total['без текста (только в листах замены)'] += 1
                    print(f'   [{k}] БЕЗ ТЕКСТА: {ln[:100]}')
            elif k == 'delete':
                for x in q:
                    if len(norm(x).split()) < 3: continue
                    in_base, in_canon = contains(x, base_txt), contains(x, canon_txt)
                    st = 'OK' if in_canon is False else 'ОСТАЛОСЬ В ЭТАЛОНЕ'
                    if in_base is False: st += ', нет в базе'
                    total[st] += 1
                    print(f'   [исключить] {st}: «{x[:60]}»')
                if not q:
                    total['исключение без текста'] += 1
                    print(f'   [исключить] по ссылке: {ln[:100]}')
            elif k == 'renumber':
                total['перенумерация'] += 1
                print(f'   [нумерация] {ln[:100]}')
    print('\nИТОГ:', dict(total))


if __name__ == '__main__':
    main(sys.argv[1])
