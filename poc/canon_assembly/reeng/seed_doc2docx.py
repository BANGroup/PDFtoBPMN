"""Наполняет кэш doc2docx готовыми конверсиями Word, лежащими рядом с .doc в прошлых прогонах (<f>.docx / <f>x), без запуска Word.
python3 seed_doc2docx.py [каталог src ...]   (по умолчанию data/canon_reeng/*/src)"""
import sys, os, glob, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doc2docx
dirs = sys.argv[1:] or glob.glob(os.path.join(doc2docx.REPO, 'data/canon_reeng/*/src'))
os.makedirs(doc2docx.CACHE, exist_ok=True); n = 0
for d in dirs:
    for f in glob.glob(d + '/**/*.doc', recursive=True):
        if doc2docx.cached(f): continue
        for sib in (f + 'x', os.path.splitext(f)[0] + '.docx'):
            if os.path.exists(sib) and os.path.getsize(sib) > 0:
                shutil.copy(sib, os.path.join(doc2docx.CACHE, doc2docx.sha1(f) + '.docx')); n += 1; break
print('добавлено в кэш:', n)
