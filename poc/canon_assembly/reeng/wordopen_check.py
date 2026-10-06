"""Проверка py-сборки в Word (шаг 9): Word открывает canon.docx без исправлений и сам выгружает абзацы (dump);
сравнение с нашей выгрузкой canon_text.txt: текст по key, ListString нумерованных абзацев.
  python3 wordopen_check.py <run_dir> DOC1 DOC2 ...   -> <run_dir>/wordopen.json"""
import sys, os, json, shutil, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wordrun, pagediff as P


def rows(p):
    out = []
    for l in open(p, encoding='utf-8-sig', errors='replace').read().split('\n'):
        r = l.split('\t')
        if len(r) >= 4 and r[1] in ('T', '-'): out.append((r[2].strip(), P.key(r[3])))
    return out


def main():
    run, docs = sys.argv[1], sys.argv[2:]
    res = {}
    import glob
    units = []   # (имя, каталог out): документ целиком или его части part_N (многочастный: проходит, только если прошли все части)
    for d in docs:
        if os.path.exists(os.path.join(run, 'out', d, 'canon.docx')): units.append((d, os.path.join(run, 'out', d)))
        else: units += [(d + '#' + os.path.basename(pd), pd) for pd in sorted(glob.glob(os.path.join(run, 'out', d, 'part_*'))) if os.path.exists(pd + '/canon.docx')]
    for d, od in units:
        src = os.path.join(od, 'canon.docx'); tag = 'wo_' + str(abs(hash(d)) % 10**8)
        shutil.copy(src, wordrun.wsl(tag + '.docx'))
        r = wordrun.run([{'op': 'dump', 'src': wordrun.winpath(tag + '.docx'), 'out': wordrun.winpath(tag + '.txt')}], tag, 900)
        wt = wordrun.wsl(tag + '.txt')
        if not os.path.exists(wt): res[d] = {'opened': False, 'log': r['log'][-300:]}; print(d, 'НЕ ОТКРЫЛСЯ', r['log'][-200:], flush=True); continue
        a, b = rows(wt), rows(os.path.join(od, 'canon_text.txt'))
        ta, tb = collections.Counter(k for _, k in a if k), collections.Counter(k for _, k in b if k)
        la = [(n, k) for n, k in a if n]; lb = [(n, k) for n, k in b if n]
        # абзацы сопоставляются по порядку (difflib по key всех абзацев), а не словарём по тексту: повторяющиеся и пустые абзацы
        import difflib
        sm = difflib.SequenceMatcher(None, [k for _, k in a], [k for _, k in b], autojunk=False)
        pairs = [(a[i + t], b[j + t]) for i, j, n in sm.get_matching_blocks() for t in range(n)]
        pn = [(x, y) for x, y in pairs if x[0] or y[0]]
        num_ok = sum(1 for x, y in pn if x[0] == y[0]); diff_ex = [(x[0], y[0], x[1][:40]) for x, y in pn if x[0] != y[0]][:5]
        res[d] = {'opened': True, 'sec': r['sec'], 'paras_word': len(a), 'paras_py': len(b), 'text_only_word': sum((ta - tb).values()),
                  'text_only_py': sum((tb - ta).values()), 'numbered_word': len(la), 'numbered_py': len(lb), 'num_same': num_ok, 'num_pairs': len(pn),
                  'num_diff_examples': diff_ex}
        print(d, json.dumps(res[d], ensure_ascii=False), flush=True)
        os.makedirs(os.path.join(run, 'wordopen'), exist_ok=True); shutil.move(wt, os.path.join(run, 'wordopen', d + '.word.txt'))   # выгрузка Word — для разбора
        try: os.remove(wordrun.wsl(tag + '.docx'))
        except OSError: pass
    for d in docs:   # сводная строка многочастного документа
        ps = {k: v for k, v in res.items() if k.startswith(d + '#')}
        if ps and d not in res:
            res[d] = {'opened': all(v['opened'] for v in ps.values()), 'num_same': sum(v.get('num_same', 0) for v in ps.values()),
                      'num_pairs': sum(v.get('num_pairs', 0) for v in ps.values()), 'parts': len(ps)}
    json.dump(res, open(os.path.join(run, 'wordopen.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__': main()
