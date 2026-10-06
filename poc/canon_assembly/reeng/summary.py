"""Свод: defects_documents.* (дефекты самих документов, каждая запись — с проверенной цитатой) и defects_assembly.* (сборка)."""
import json, os, csv, collections, zipfile, re
import fitz
from lxml import etree
from pagediff import key, W
REPO = '/home/budnik_an/Obligations/'
here = os.path.dirname(os.path.abspath(__file__))
TEMP = '/mnt/c/Users/Budnik_AN/AppData/Local/Temp/canon_reeng/'
SLUG = {'ДП-Б1.024-06': 'd024', 'РГ-184-06': 'd184', 'КД-РД-В5.058-04': 'd058', 'КД-РД-Б1.041-04': 'd041', 'КД-ДП-Б1.011-04': 'd011'}
_cache = {}


def filekey(path, doc):
    if path in _cache: return _cache[path]
    full = os.path.join(REPO, path)
    if path.lower().endswith('.pdf'):
        k = key(' '.join(pg.get_text() for pg in fitz.open(full)))
    else:
        if path.lower().endswith('.doc'): full = TEMP + SLUG[doc] + '/base_orig.docx'   # .doc -> копия, сохранённая Word
        z = zipfile.ZipFile(full); out = []
        for part in ('word/document.xml', 'word/footnotes.xml', 'word/endnotes.xml'):
            if part in z.namelist():
                out.append(''.join(t.text or '' for t in etree.fromstring(z.read(part)).iter(W + 't')))
        k = key(' '.join(out))
    _cache[path] = k
    return k


def verified(x):
    q = x.get('quote') or []
    if not q or not x.get('verified_by'): return False
    for e in q:
        if not e.get('text') or key(e['text']) not in filekey(e['file'], x['doc']): return False
    return True


docs, asm, table = [], [], []
for d in sorted(os.listdir(here)):
    f = os.path.join(here, d, 'check.json')
    if not os.path.exists(f): continue
    c = json.load(open(f)); m = c['metrics']
    for x in c['defects']:
        x = dict(x); x['result_files'] = [f'poc/canon_assembly/reeng/{d}/{d}_canon.docx', f'poc/canon_assembly/reeng/{d}/{d}_markup.docx', f'poc/canon_assembly/reeng/{d}/{d}_canon.pdf', f'poc/canon_assembly/reeng/{d}/{d}_canon_text.txt']
        if x.get('cat') == 'doc':
            if verified(x): docs.append(x)
            else: x['cat'] = 'asm'; x['cause'] += ' [цитата не подтверждена файлом корпуса]'; asm.append(x)
        else: asm.append(x)
    sd = collections.Counter(x['severity'] for x in docs if x['doc'] == d)
    sa = collections.Counter(x['severity'] for x in asm if x['doc'] == d)
    nm = m.get('numbering', {})
    table.append({'doc': d, 'pages': m['pages_total'], 'regions': f"{m['regions_ok']}/{m['regions']}", 'pct': m['pct_lines'], 'pct2': m['pct_lines_with_number_only_diff'],
                  'num': f"{nm.get('equal_to_ref')}/{nm.get('numbered_paragraphs')}", 'dup': m.get('duplicates'), 'extra': m.get('canon_paragraphs_not_in_ref'), 'scheme': m.get('scheme_text_in_word_graphic_in_pdf'),
                  'dd': (sd['смысл'], sd['граф'], sd['косметика']), 'da': (sa['смысл'], sa['граф'], sa['косметика'])})
for name, rows, cols in (('defects_documents', docs, ['doc', 'type', 'severity', 'where', 'what', 'quote', 'files', 'level', 'cause']),
                         ('defects_assembly', asm, ['doc', 'type', 'severity', 'where', 'what', 'cause', 'sources', 'files', 'result_files'])):
    json.dump(rows, open(os.path.join(here, name + '.json'), 'w'), ensure_ascii=False, indent=1)
    with open(os.path.join(here, name + '.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';'); w.writerow(cols)
        for x in rows: w.writerow([json.dumps(x.get(k), ensure_ascii=False) if isinstance(x.get(k), (list, dict)) else x.get(k, '') for k in cols])
json.dump(table, open(os.path.join(here, 'summary.json'), 'w'), ensure_ascii=False, indent=1)
expl = []
for d in sorted(os.listdir(here)):
    f = os.path.join(here, d, 'check.json')
    if os.path.exists(f):
        for x in json.load(open(f)).get('explained', []): expl.append({'doc': d, **x})
json.dump(expl, open(os.path.join(here, 'explained.json'), 'w'), ensure_ascii=False, indent=1)
print(f"{'doc':18}{'стр.':>5}{'рег.':>7}{'%строк':>8}{'нум.':>8}{'дубли':>6}{'вне эт.':>8}{'схемы':>6}   док.см/гр/кос   сборка см/гр/кос")
for t in table:
    print(f"{t['doc']:18}{t['pages']:>5}{t['regions']:>7}{t['pct']:>8}{t['num']:>8}{t['dup']:>6}{t['extra']:>8}{t['scheme']:>6}   {str(t['dd']):>13}   {str(t['da']):>14}")
