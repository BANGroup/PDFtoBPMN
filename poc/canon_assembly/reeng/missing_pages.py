"""Недостающие строки эталона по страницам (та же логика, что verify_canon.verify; исходник verify_canon не меняется).
python missing_pages.py <src части> <canon_text.txt> <canon.docx> [источники .docx...]  -> {метка страницы: число missing}"""
import sys, os, inspect, json, collections, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_canon as V

_src = inspect.getsource(V.verify).replace("    return {'lines': len(L),", "    return {'_miss_real': miss_real, 'lines': len(L),")
_ns = dict(V.__dict__); exec(_src, _ns)
verify_ex = _ns['verify']

def by_page(sd, canon_text, canon_docx, sources):
    r = verify_ex(sd, canon_text, canon_docx, sources)
    c = collections.Counter(lab for lab, l in r['_miss_real'])
    return r, c

if __name__ == '__main__':
    sd, ct, cd = sys.argv[1:4]
    srcs = sys.argv[4:] or (glob.glob(sd + '/word/*.docx')[:1] + sorted(glob.glob(sd + '/amendments/**/*.docx', recursive=True)))
    r, c = by_page(sd, ct, cd, srcs)
    print(json.dumps({k: r[k] for k in ('lines', 'missing', 'coverage')}), len(c), 'pages with missing')
    print(sorted(c.items(), key=lambda t: -t[1])[:40])
    if os.environ.get('OUT'): json.dump({str(k): v for k, v in c.items()}, open(os.environ['OUT'], 'w'), ensure_ascii=False)
