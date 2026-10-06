"""Разовая конвертация .doc -> .docx через Word с постоянным кэшем (шаг 9 TASK-021: сборка без Word, Word — только здесь).

Кэш: data/canon_reeng/_cache/doc2docx/<sha1 содержимого .doc>.docx. Один и тот же файл в Word больше не попадает.
  python3 doc2docx.py [каталог ...]     # по умолчанию data/canon_reeng/live/src: все .doc без .docx-соседа и без кэша
  cached(path) -> путь к .docx из кэша или None (для сборки).
Word: один процесс, пачками по BATCH файлов, тайм-аут на пачку; гасится только свой WINWORD (wordrun).
"""
import os, sys, glob, hashlib, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))
CACHE = os.path.join(REPO, 'data/canon_reeng/_cache/doc2docx')
BATCH = 10


def sha1(p):
    return hashlib.sha1(open(p, 'rb').read()).hexdigest()


def sibling(p):
    for s_ in (p + 'x', os.path.splitext(p)[0] + '.docx'):
        if os.path.exists(s_) and os.path.getsize(s_) > 0: return s_
    return None


def cached(path):
    """Конверсия .doc из кэша; если в кэше нет, но рядом лежит готовая Word-конверсия (<f>.docx / <f>x из прошлых прогонов) — кэшируется копией соседа (без Word)."""
    c = os.path.join(CACHE, sha1(path) + '.docx')
    if os.path.exists(c): return c
    s_ = sibling(path)
    if s_:
        os.makedirs(CACHE, exist_ok=True); shutil.copy(s_, c); return c
    return None


def has_sibling(p):
    return os.path.exists(p + 'x') or os.path.exists(os.path.splitext(p)[0] + '.docx')


def todo(dirs):
    seen, out = set(), []
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, '**', '*.doc'), recursive=True) + glob.glob(os.path.join(d, '**', '*.DOC'), recursive=True)):
            if has_sibling(p): continue
            h = sha1(p)
            if h in seen or os.path.exists(os.path.join(CACHE, h + '.docx')): continue
            seen.add(h); out.append((h, p))
    return out


def convert(items):
    import wordrun
    os.makedirs(CACHE, exist_ok=True); os.makedirs(wordrun.wsl('d2d'), exist_ok=True)
    ok, bad = 0, []
    for i in range(0, len(items), BATCH):
        part = items[i:i + BATCH]
        for h, p in part: shutil.copy(p, wordrun.wsl(f'd2d/{h}.doc'))
        r = wordrun.run([{'op': 'convert', 'src': wordrun.winpath(f'd2d/{h}.doc'), 'dst': wordrun.winpath(f'd2d/{h}.docx')} for h, _ in part],
                        f'd2d_{i // BATCH}', 120 * len(part))
        for h, p in part:
            out = wordrun.wsl(f'd2d/{h}.docx')
            if os.path.exists(out) and os.path.getsize(out) > 0:
                shutil.move(out, os.path.join(CACHE, h + '.docx')); ok += 1
            else: bad.append(p)
            try: os.remove(wordrun.wsl(f'd2d/{h}.doc'))
            except OSError: pass
        print(f'{min(i + BATCH, len(items))}/{len(items)}: готово {ok}, не сконвертировано {len(bad)}' + (' | ' + r['log'].strip()[-200:] if r['out'] == 'TIMEOUT' else ''), flush=True)
    return ok, bad


if __name__ == '__main__':
    dirs = sys.argv[1:] or [os.path.join(REPO, 'data/canon_reeng/live/src')]
    items = todo(dirs)
    print(f'к конвертации {len(items)} файлов .doc (кэш: {CACHE})', flush=True)
    if items:
        ok, bad = convert(items)
        print(f'итог: сконвертировано {ok}, ошибки {len(bad)}'); [print('  НЕ:', b) for b in bad]
