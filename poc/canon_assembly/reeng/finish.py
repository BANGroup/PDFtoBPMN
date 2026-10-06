"""Собрать результаты документа в reeng/<doc>/ : <doc>_canon.docx/.pdf, _markup.docx, _canon_text.txt. python finish.py <doc> <slug>"""
import sys, os, shutil, wordrun as W
doc, slug = sys.argv[1], sys.argv[2]
here = os.path.dirname(os.path.abspath(__file__)); od = os.path.join(here, doc)
for src, dst in (('canon.docx', '_canon.docx'), ('canon.pdf', '_canon.pdf'), ('markup.docx', '_markup.docx'), ('canon_dump.txt', '_canon_text.txt')):
    p = W.wsl(f'{slug}/{src}')
    if os.path.exists(p): shutil.copy(p, os.path.join(od, doc + dst)); print('copied', doc + dst, os.path.getsize(p))
