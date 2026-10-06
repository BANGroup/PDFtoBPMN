"""Текстовый индекс Word-источников: ListString (по выгрузке Word), текст EMF/WMF (UTF-16/cp1251 строки), OLE-объекты."""
import re, zipfile, os, io
from lxml import etree
from pagediff import key, W

RUN = re.compile(r'[А-Яа-яЁёA-Za-z0-9 ,.:;()\-–/№%«»"\'@+*=<>?!]{3,}')


def _runs(data):
    out = []
    for off in (0, 1):
        try: out += RUN.findall(data[off:].decode('utf-16le', errors='ignore'))
        except Exception: pass
    try: out += RUN.findall(data.decode('cp1251', errors='ignore'))
    except Exception: pass
    return out


def _ole_runs(data, depth=0):
    out = []
    try:
        import olefile
        if olefile.isOleFile(data):
            ole = olefile.OleFileIO(io.BytesIO(data))
            for st in ole.listdir():
                try: b = ole.openstream(st).read()
                except Exception: continue
                out += _stream_runs(b, depth)
            return out
    except Exception: pass
    return _stream_runs(data, depth)


def _stream_runs(b, depth):
    out = []
    if b[:2] == b'PK' and depth < 3:
        try:
            z = zipfile.ZipFile(io.BytesIO(b))
            for n in z.namelist():
                if n.endswith('.xml'):
                    x = z.read(n).decode('utf-8', errors='ignore')
                    out += re.findall(r'<(?:w:t|t)[^>]*>([^<]+)</', x)
                elif n.endswith('.bin'): out += _ole_runs(z.read(n), depth + 1)
            return out
        except Exception: pass
    if b[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' and depth < 3: return _ole_runs(b, depth + 1)
    return _runs(b)


def media_text(docx):
    """Строки текста внутри картинок EMF/WMF и встроенных OLE-объектов пакета docx (в порядке файлов)."""
    z = zipfile.ZipFile(docx); out = []
    for n in sorted(z.namelist()):
        low = n.lower()
        if low.startswith('word/media/') and low.endswith(('.emf', '.wmf')): out += _runs(z.read(n))
        elif low.startswith('word/embeddings/'): out += _ole_runs(z.read(n))
    seen, res = set(), []
    for r in out:
        r = r.strip(); k = key(r)
        if len(k) < 5 or r in ('Times New Roman', 'Arial') or k in seen: continue
        if not re.search(r'[А-Яа-яA-Za-z]{3}', r): continue
        seen.add(k); res.append(r)
    return res


def media_key(docx):
    return ''.join(key(r) for r in media_text(docx))
