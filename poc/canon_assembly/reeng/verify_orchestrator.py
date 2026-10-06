"""Независимая проверка канона (orchestrator) — эталон для verify_canon.py; кодом сборки не используется.

Строки контента эталона (с раздела 1, без колонтитулов >30 % страниц, штампов, «Стр. N», битого слоя)
ищутся точным вхождением key() в выгрузке канона из Word (<doc>_canon_text.txt: idx, kind, ListString,
text, pos) — с номером, без номера, без цифр. Дубли: абзацы >60 знаков, которых в каноне больше, чем
в эталоне. Номера: строки эталона «7.2.5 Текст» должны быть в «ListString + текст». Живая нумерация:
numId != 0; numId=0 с номером в начале должен дословно встречаться в источниках. Текст EMF/WMF/OLE —
отдельно (UTF-16/cp1251, по key).

python3 verify_orchestrator.py <src_doc_dir> <canon_text.txt> <canon.docx> [источники.docx ...]
"""
import sys, os, glob, collections, re, zipfile, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pagediff as P
import blobtext as BT   # текст встроенных объектов без декодирования картинок целиком (OOM 05.10)

_TOC_LEAD = re.compile(r'[.…]{3,}\s*\d{1,3}\s*$|^\s*\d+(\.\d+)*\.?\s+\S.*[.…]{8,}')
_TOC_HEAD = re.compile(r'^(содержание|оглавление)\s*$', re.I)
_HEADING = re.compile(r'^\d+(\.\d+)*\.?\s+\S')


def body_paras(paras):
    """Только тело канона: без строк оглавления (точки-заполнители + номер страницы), блока «Содержание»
    (до первого заголовка «1 …», за которым идёт содержательный абзац, а не ≥5 заголовков подряд) и
    повторных списков заголовков (≥5 коротких «N текст» подряд с возрастающими номерами, без абзацев между)."""
    def txt(i): return (paras[i][0] + ' ' + paras[i][1]).strip()
    def num(i): return tuple(int(x) for x in re.findall(r'\d+', txt(i).split()[0]))
    def hl(i):
        t = txt(i)
        return bool(_HEADING.match(t)) and bool(len(t) <= 150 and not re.search(r'[.;:,]\s*$', t) or _TOC_LEAD.search(t))
    ne = [i for i, p in enumerate(paras) if (p[0] + p[1]).strip()]   # непустые абзацы
    drop = {i for i in ne if _TOC_LEAD.search(txt(i))}
    # начало тела: первый заголовок «1 …», за которым идёт содержательный абзац (а не ≥5 заголовков подряд)
    b = next((j for j, i in enumerate(ne) if re.match(r'^\s*1\.?\s+\S', txt(i)) and not all(hl(k) for k in ne[j + 1:j + 5])), None)
    s = next((j for j, i in enumerate(ne[:b]) if _TOC_HEAD.match(paras[i][1].strip())), None)   # блок «Содержание»
    if s is not None:
        # конец блока — первая строка, повторяющая строку этого же блока (оглавление кончилось, пошли те же заголовки в теле;
        # нужно для документов с разделами «РАЗДЕЛ 1 …», где первый «1 …» стоит глубоко в теле)
        def norm(i): return re.sub(r'[\d\W_]+$', '', re.sub(r'[.…]{3,}.*$', '', txt(i))).lower().replace('ё', 'е').strip()
        seen, end = set(), None
        for j in range(s + 1, b if b is not None else len(ne)):
            k = norm(ne[j])
            if len(k) < 4 or _TOC_HEAD.match(paras[ne[j]][1].strip()): continue
            if k in seen: end = j; break
            seen.add(k)
        b = end if end is not None else b
        if b is not None: drop.update(ne[s:b])
    if b is not None:
        j = 0   # повторные списки заголовков — только до начала тела (в приложениях нумерованные короткие строки — это содержимое)
        while j < b:
            e = j
            while e < b and hl(ne[e]) and (e == j or num(ne[e]) > num(ne[e - 1])): e += 1
            if e - j >= 5: drop.update(ne[j:e])
            j = max(e, j + 1)
    return [p for i, p in enumerate(paras) if i not in drop]


def join_heading(lines):
    """Заголовок эталона, разбитый PDF на короткие ПРОПИСНЫЕ обрывки («7.2 ПОРЯДОК» / «ОБНОВЛЕНИЯ» / …),
    проверяется целиком: короткие обрывки (<12 знаков) иначе пропускаются, а хвост находится в чужом месте."""
    out, i = [], 0
    while i < len(lines):
        l, j = lines[i], i + 1
        if re.match(r'^\s*\d+(\.\d+)*\.?\s+\S', l) and len(P.key(l)) < 12 and not re.search('[а-яa-z]', l):
            while j < len(lines) and j - i <= 6 and lines[j].strip() and not re.search('[а-яa-z]', lines[j]) \
                    and not re.match(r'^\s*\d+(\.\d+)*\.?\s', lines[j]) and not re.search(r'Стр', lines[j]):
                l += ' ' + lines[j].strip(); j += 1
        out.append(l); i = j
    return out


def verify(doc_dir, canon_text, canon_docx, sources):
    rows = [l.split('\t') for l in open(canon_text, encoding='utf-8', errors='replace').read().split('\n')]
    paras = [(r[2].strip(), r[3]) for r in rows if len(r) >= 4]
    body = body_paras(paras)   # поиск строк эталона — только в теле (без оглавления)
    full = P.key(' '.join(n + ' ' + t for n, t in body)); plain = P.key(' '.join(t for n, t in body))
    pdfs = [x for x in glob.glob(doc_dir + '/files/*.pdf') if re.search('[Ээ]тал', x)] or glob.glob(doc_dir + '/files/*.pdf')
    pages = P.canon_pages(pdfs[0])
    cnt = collections.Counter(k for p in pages for k in {P.key(l) for l in p['lines']})
    head = {k for k, c in cnt.items() if c > 0.3 * len(pages)}
    start = next((i for i, p in enumerate(pages) if any(re.match(r'^\s*1\.?\s+(ЦЕЛЬ|НАЗНАЧЕНИЕ|ОБЩИЕ)', l, re.I)
                  and not re.search(r'\d\s*$', l.strip()) for l in p['lines'])), None)
    if start is None:   # нет «1 Цель/Назначение/Общие»: «1 Область применения», «РАЗДЕЛ/ЧАСТЬ 1», «Общие положения» не из оглавления; иначе без титула
        start = next((i for i, p in enumerate(pages) if any(re.match(r'^\s*(1\.?\s+ОБЛАСТЬ|(РАЗДЕЛ|ЧАСТЬ|ГЛАВА)\s+1\b|ОБЩИЕ ПОЛОЖЕНИЯ\s*$)', l, re.I)
                      and not re.search(r'[.…]{3,}|\d\s*$', l.strip()) for l in p['lines'])), 1 if len(pages) > 1 else 0)
    L = [(p['label'], l, P.key(P.LIST_MARK.sub('', l))) for p in pages[start:] for l in join_heading(p['lines'])
         if P.key(l) not in head and len(P.key(l)) >= 12 and not P.garbage(l)
         and not re.search(r'Стр\.?\s*/?\s*(page)?\s*\d', l) and not re.search(r'[.…]{5,}\s*\d{1,3}\s*$', l)
         and not re.match(r'(Дата введения|Дата замены листа|Основание|Изменение\s*(/\s*Revision)?\s*№)', l.strip(), re.I)]
    nodig = re.sub(r'\d', '', plain)
    miss = [(lab, l, k) for lab, l, k in L if k not in full and k not in plain and re.sub(r'\d', '', k) not in nodig]
    hf = P.hf_key(sources); miss = [(lab, l, k) for lab, l, k in miss if not (len(k) >= 12 and k in hf)]   # колонтитул источника — не контент
    obj_key = P.key(' '.join(r for f in sources if f.endswith('.docx') for r in BT.docx_object_runs(f)))
    def in_obj(line):
        k = P.key(P.LIST_MARK.sub('', line)); k2 = P.key(re.sub(r'^\s*\d+(\.\d+)*\.?\s*', '', line))
        return (len(k) >= 12 and k in obj_key) or (len(k2) >= 12 and k2 in obj_key)
    miss_obj = [(lab, l) for lab, l, k in miss if in_obj(l)]
    miss_real = [(lab, l) for lab, l, k in miss if not in_obj(l)]
    ck = collections.Counter(P.key(t) for n, t in paras if len(P.key(t)) > 60)
    pdfk = P.key(' '.join(' '.join(p['lines']) for p in pages))
    over = {k: c for k, c in ck.items() if c > 1 and pdfk.count(k) < c}   # больше, чем в эталоне
    b0 = sources[0] if sources else ''
    bkey = P.key(P.docx_text(b0)) if b0.endswith('.docx') else ''
    # допустимо: колонтитул/ячейка эталона разорвали абзац — в каноне не больше, чем в базе Word, а начало и конец абзаца в эталоне встречаются не реже
    ok_dup = {k for k, c in over.items() if bkey and c <= bkey.count(k) and pdfk.count(k[:30]) >= c and pdfk.count(k[-30:]) >= c}
    dup = [k for k in over if k not in ok_dup]
    nums = [(lab, l) for lab, l, k in L if re.match(r'^\s*\d+(\.\d+)+\.?\s+\S', l)]
    num_bad = [(lab, l) for lab, l in nums if P.key(l) not in full]
    x = zipfile.ZipFile(canon_docx).read('word/document.xml').decode()
    live = len(re.findall(r'<w:numId w:val="(?!0")\d+"', x))
    src = P.key(' '.join(P.docx_text(f) for f in sources if f.endswith('.docx')))
    z0 = [''.join(re.findall(r'<w:t[^>]*>([^<]*)', p)) for p in re.findall(r'<w:p[ >].*?</w:p>', x, re.S) if '<w:numId w:val="0"/>' in p]
    frozen = [t for t in z0 if re.match(r'\s*\d+(\.\d+)+', t) and P.key(t) not in src]
    return {'lines': len(L), 'missing': len(miss_real), 'missing_in_objects': len(miss_obj),
            'numbered': len(nums), 'numbered_bad': len(num_bad), 'duplicates': len(dup), 'duplicates_explained': len(ok_dup),
            'live_numbering': live, 'frozen_numbers': len(frozen),
            'examples_missing': [f'стр.{lab}: {l[:100]}' for lab, l in miss_real[:10]],
            'examples_numbered_bad': [f'стр.{lab}: {l[:100]}' for lab, l in num_bad[:10]]}


if __name__ == '__main__':
    a = sys.argv[1:]
    print(json.dumps(verify(a[0], a[1], a[2], a[3:]), ensure_ascii=False, indent=1))
