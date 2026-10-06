"""Отчёт по страницам из PDF: python pdf_report.py <run после> <run до> <doc> [--fast]
По частям: страниц из PDF, закладки в canon.docx, missing/coverage до/после и missing именно на страницах из PDF (verify_canon по страницам)."""
import sys, os, re, json, glob, zipfile, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import missing_pages as MP

def parts_of(run, doc):
    od = os.path.join(run, 'out', doc)
    ps = sorted(glob.glob(od + '/part_*'), key=lambda x: int(re.search(r'part_(\d+)', x).group(1)))
    return [(os.path.basename(p), p, os.path.join(run, 'src', doc, '__parts', 'p' + p.rsplit('_', 1)[1])) for p in ps] or [('', od, os.path.join(run, 'src', doc))]

def srcs_of(sd):
    return sorted(glob.glob(sd + '/word/*.docx'))[:1] + sorted(glob.glob(sd + '/amendments/**/*.docx', recursive=True))

def one(run, od, sd, labels):
    ct, cd = od + '/canon_text.txt', od + '/canon.docx'
    if not os.path.exists(ct): return None
    base = [os.path.join(od, 'base_orig.docx')] if os.path.exists(od + '/base_orig.docx') else []
    r, c = MP.by_page(sd, ct, cd, base + srcs_of(sd) if base else srcs_of(sd))
    return {'lines': r['lines'], 'missing': r['missing'], 'coverage': round(r['coverage'], 4), 'on_pdf_pages': sum(c.get(l, 0) for l in labels)}

def main(run, base, doc):
    out = []
    for name, od, sd in parts_of(run, doc):
        pl = json.load(open(od + '/plan.json')) if os.path.exists(od + '/plan.json') else {}
        labels = [l for s in pl.get('pdf_source', []) for l in s['labels']]
        bk = 0
        if os.path.exists(od + '/canon.docx'):
            bk = len(set(re.findall(r'PDF_src_p\d+', zipfile.ZipFile(od + '/canon.docx').read('word/document.xml').decode())))
        bod = os.path.join(base, 'out', doc, name) if name else os.path.join(base, 'out', doc)
        bsd = os.path.join(base, 'src', doc, '__parts', 'p' + name.split('_')[1]) if name else os.path.join(base, 'src', doc)
        row = {'part': name or '-', 'pdf_pages': len(labels), 'labels': labels[:12], 'bookmarks_in_canon': bk, 'candidates': len(pl.get('pdf_candidates', {})), 'unplaced': pl.get('pdf_unplaced', [])[:12]}
        row['after'] = one(run, od, sd, labels)
        row['before'] = one(base, bod, bsd, labels)
        out.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return out

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
