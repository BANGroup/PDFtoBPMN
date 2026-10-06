"""Склейка файлов-глав в один docx без Word (аналог op 'concat' в word_run.ps1): главы по порядку, между главами разрыв раздела (следующая страница).
Стили/нумерация/картинки/OLE переносит docxcompose (PyComposer из pyassemble). Свойства раздела берутся у первой главы; sectPr остальных глав не переносятся (как InsertFile).
python3 pychapters.py out.docx ch1.docx ch2.docx ..."""
import sys, os, copy
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pyassemble import PyComposer, fix_ids


def section_break_para(body):
    """Абзац с разрывом раздела (nextPage) по свойствам последнего раздела тела (без ссылок на колонтитулы)."""
    sp = body.find(qn('w:sectPr'))
    sp = copy.deepcopy(sp) if sp is not None else OxmlElement('w:sectPr')
    for r in list(sp):
        if r.tag in (qn('w:headerReference'), qn('w:footerReference'), qn('w:titlePg')): sp.remove(r)
    ty = sp.find(qn('w:type'))
    if ty is None: ty = OxmlElement('w:type'); sp.insert(0, ty)
    ty.set(qn('w:val'), 'nextPage')
    p = OxmlElement('w:p'); ppr = OxmlElement('w:pPr'); ppr.append(sp); p.append(ppr)
    return p


def concat(files, out):
    """-> {'chapters': n, 'errors': [...]}"""
    d = None; errs = []; n = 0
    for f in files:
        try: fd = docx.Document(f)
        except Exception as e: errs.append(f'{os.path.basename(f)}: {type(e).__name__}: {e}'[:200]); continue
        if d is None: d = fd; comp = PyComposer(d); comp.restart_numbering = False; n = 1; continue
        body = d.element.body
        idx = body.index(body.find(qn('w:sectPr'))) if body.find(qn('w:sectPr')) is not None else len(body)
        body.insert(idx, section_break_para(body))
        try: comp.insert(idx + 1, fd, remove_property_fields=False); n += 1
        except Exception as e: errs.append(f'{os.path.basename(f)}: {type(e).__name__}: {e}'[:200])
    if d is None: raise RuntimeError('нет ни одной главы')
    fix_ids(d); d.save(out)
    return {'chapters': n, 'errors': errs}


if __name__ == '__main__':
    print(concat(sys.argv[2:], sys.argv[1]))
