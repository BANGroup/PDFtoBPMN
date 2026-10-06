"""Текст встроенных объектов Word (word/media, word/embeddings, вложенные zip/OLE) — без декодирования двоичных данных целиком.

Раньше (classify_missing._blob_text, verify_canon, verify_orchestrator) каждый объект декодировался целиком трижды
(UTF-16 с двух смещений и cp1251), рекурсивно на каждом уровне вложения, и склеивался в одну строку: 381 МБ картинок
давали 5–16 ГБ памяти и OOM в WSL (05.10.2026). Теперь:
  - растровые картинки (PNG, JPEG, GIF, BMP, TIFF) пропускаются: текста в них нет;
  - zip (Office Open XML внутри OLE-пакетов, .xlsx, .vsdx) — текст XML-частей, двоичные части рекурсивно;
  - OLE (.bin, .xls, .vsd, .doc) — потоки рекурсивно, сам контейнер не сканируется (его байты = потоки);
  - EMF/WMF — разбор по записям: текст только из записей вывода текста (EMF: EXTTEXTOUTA/W, SMALLTEXTOUT, комментарии
    EMF+ — участки UTF-16; WMF: TEXTOUT, EXTTEXTOUT в cp1251); растровые записи внутри рисунка не читаются;
  - прочее (потоки OLE и т. п.) — участки, похожие на текст: UTF-16LE (от 3 знаков) и cp1251 (от 4 знаков).
Память пропорциональна тексту, а не размеру файла.
Результат для сверки — P.key(...) склейки: key оставляет только буквы и цифры, поэтому разделители между участками не важны.
"""
import io, re, zipfile, html, struct

RASTER = (b'\x89PNG', b'\xff\xd8\xff', b'GIF8', b'BM', b'II*\x00', b'MM\x00*')
U16 = re.compile(rb'(?:[\x20-\x7e]\x00|[\x01-\x5f]\x04){3,}')      # UTF-16LE: ASCII или кириллица U+0401..U+045F
B8 = re.compile(rb'[\x20-\x7e\xa8\xb8\xc0-\xff]{4,}')               # cp1251: ASCII + Ё/ё + А..я


def xml_text(b):
    return html.unescape(re.sub(r'<[^>]+>', ' ', b.decode('utf-8', 'ignore')))


def raw_runs(b):
    """Участки текста в двоичных данных (EMF/WMF, потоки OLE)."""
    out = [m.decode('utf-16-le', 'ignore') for m in U16.findall(b)]
    out += [m.decode('cp1251', 'ignore') for m in B8.findall(b)]
    return out


def emf_runs(b):
    """Текст рисунка EMF по записям (MS-EMF 2.3.5): 83/84 EXTTEXTOUTA/W, 108 SMALLTEXTOUT, 70 COMMENT (EMF+ DrawString — UTF-16)."""
    out, i, n = [], 0, len(b)
    while i + 8 <= n:
        t, sz = struct.unpack_from('<II', b, i)
        if sz < 8 or i + sz > n: break
        try:
            if t in (83, 84) and sz >= 76:
                nch, off = struct.unpack_from('<II', b, i + 44)
                raw = b[i + off:i + off + nch * (2 if t == 84 else 1)]
                out.append(raw.decode('utf-16-le' if t == 84 else 'cp1251', 'ignore'))
            elif t == 108 and sz >= 36:
                nch, opt = struct.unpack_from('<II', b, i + 16)
                o = i + 36 + (0 if opt & 0x100 else 16)
                out.append(b[o:o + nch].decode('cp1251', 'ignore') if opt & 0x200 else b[o:o + 2 * nch].decode('utf-16-le', 'ignore'))
            elif t == 70: out += [m.decode('utf-16-le', 'ignore') for m in U16.findall(b, i + 8, i + sz)]
        except struct.error: pass
        if t == 14: break   # EMR_EOF
        i += sz
    return out


def wmf_runs(b):
    """Текст рисунка WMF по записям (MS-WMF): 0x0521 TEXTOUT, 0x0A32 EXTTEXTOUT (8-битный текст, cp1251)."""
    out, i = [], 22 if b.startswith(b'\xd7\xcd\xc6\x9a') else 0
    if i + 18 > len(b): return out
    i += struct.unpack_from('<H', b, i + 2)[0] * 2   # размер заголовка в словах
    n = len(b)
    while i + 6 <= n:
        sz, fn = struct.unpack_from('<IH', b, i); sz *= 2
        if sz < 6 or i + sz > n: break
        try:
            if fn == 0x0521:
                c = struct.unpack_from('<H', b, i + 6)[0]; out.append(b[i + 8:i + 8 + c].decode('cp1251', 'ignore'))
            elif fn == 0x0A32:
                c, opt = struct.unpack_from('<HH', b, i + 10)
                o = i + 14 + (8 if opt & 0x6 else 0); out.append(b[o:o + c].decode('cp1251', 'ignore'))
        except struct.error: pass
        if fn == 0: break
        i += sz
    return out


def blob_runs(b, depth=0):
    """Список строк текста двоичного объекта (рекурсивно по zip/OLE, не глубже 4 уровней)."""
    if b.startswith(RASTER): return []
    if b[:4] == b'\x01\x00\x00\x00' and b[40:44] == b' EMF': return emf_runs(b)
    if b[:4] == b'\xd7\xcd\xc6\x9a' or b[:4] in (b'\x01\x00\x09\x00', b'\x02\x00\x09\x00'): return wmf_runs(b)
    if b[:2] == b'\x1f\x8b' and depth <= 3:   # .emz/.wmz
        import gzip
        try: return blob_runs(gzip.decompress(b), depth + 1)
        except Exception: return []
    try:
        if depth <= 3 and b[:2] == b'PK' and zipfile.is_zipfile(io.BytesIO(b)):
            out = []
            z = zipfile.ZipFile(io.BytesIO(b))
            for n in z.namelist():
                d = z.read(n)
                out += [xml_text(d)] if n.lower().endswith(('.xml', '.rels')) else blob_runs(d, depth + 1)
            return out
        if depth <= 3 and b[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            import olefile
            o = olefile.OleFileIO(b)
            out = []
            for st in o.listdir(streams=True, storages=False): out += blob_runs(o.openstream(st).read(), depth + 1)
            return out
    except Exception: pass
    return raw_runs(b)


def docx_object_runs(path, charts=False):
    """Текст всех встроенных объектов одного .docx (и, если charts, XML диаграмм/схем/рисунков Word)."""
    out = []
    try: z = zipfile.ZipFile(path)
    except Exception: return out
    for n in z.namelist():
        if n.startswith(('word/media/', 'word/embeddings/')): out += blob_runs(z.read(n))
        elif charts and re.match(r'word/(diagrams|charts|drawings)/[^/]+\.xml$', n): out.append(xml_text(z.read(n)))
    return out
