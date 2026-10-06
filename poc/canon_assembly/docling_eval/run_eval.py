"""Оценка Docling как основы записи документа. Только чтение корпуса.

python run_eval.py docx|pdf|cover <tag> [--out DIR]   (tag = версия docling; python = venv нужной версии)
Результаты: <out>/json_<tag>/*.json (DoclingDocument), <out>/res_<tag>/*.json (метрики).
"""
import sys, os, re, json, time, glob, zipfile, difflib, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
ROOT = '/home/budnik_an/Obligations/data/bnd_corpus/documents/'
SCR = '/tmp/claude-1000/-home-budnik-an-Obligations/ad94d5b3-6c33-4112-9797-7bbad830b1b4/scratchpad/eval_out'
import assemble as A
import body as B

C = ROOT + 'СМК/_unclassified/КД-РГ-174-05/'
M = ROOT + 'СУБП/M1/РД-М1.029-07/'
INPUTS = {   # name: (docx, pdf|None, pilot)
    'KD-RG-174-05': (C + 'word/Регламент, р5, в8_C32601FA.docx', glob.glob(C + 'files/*Эталон*.pdf')[0], True),
    'RD-M1.029-07': (M + 'word/РД-М1-029-07.docx', glob.glob(M + 'files/*Эталон*.pdf')[0], True),
    'x_visio_B1.034-01': (ROOT + 'СМК/B1/КД-ДП-Б1.034-01/word/проект 1408.docx', None, False),
    'x_visio_RG-201-03': (ROOT + 'СМК/_unclassified/КД-РГ-201-03/word/КД-РГ-201 Доступы в7_03303126.docx', None, False),
    'x_txbx_B1.004-06': (ROOT + 'СМК/B1/ДП-Б1.004-06/word/ДП-Б1_ADF8B06F.004-06 версия 1.docx', None, False),
    'x_excel_M1.027-06': (ROOT + 'СУБП/M1/ДП-М1.027-06/word/ДП-М1_66C8A538.027-6.docx', None, False),
}
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
      'v': 'urn:schemas-microsoft-com:vml'}
NUMRE = re.compile(r'^\s*\d+(\.\d+)+\.?(\s|$)')


def all_layers():
    from docling_core.types.doc import ContentLayer
    return set(ContentLayer)


def items(doc, furniture=False):
    """(label, text, item) по порядку; таблицы — отдельным элементом."""
    kw = {'included_content_layers': all_layers()} if furniture else {}
    for it, _ in doc.iterate_items(with_groups=False, **kw):
        yield it


def item_texts(doc, furniture=False):
    out = []
    for it in items(doc, furniture):
        lab = str(getattr(it.label, 'value', it.label))
        if lab == 'table':
            cells = getattr(it.data, 'table_cells', [])
            out.append(('table', [c.text for c in sorted(cells, key=lambda c: (c.start_row_offset_idx, c.start_col_offset_idx))]))
        elif lab == 'picture':
            out.append(('picture', [c.resolve(doc).text for c in it.captions]))
        else:
            out.append((lab, getattr(it, 'text', '') or ''))
    return out


def flat_texts(doc, furniture=False):
    r = []
    for lab, t in item_texts(doc, furniture):
        if isinstance(t, list):
            r += [x for x in t if x and x.strip()]
        elif t.strip():
            r.append(t)
    return r


def xml_audit(path):
    """Своим разбором XML: надписи (txbxContent) по классам, VML textpath, vsdx, xlsx, картинки."""
    from lxml import etree
    z = zipfile.ZipFile(path)
    root = etree.fromstring(z.read('word/document.xml'))
    W = '{%s}' % NS['w']
    groups = {'wps_choice': [], 'vml_fallback': [], 'vml_or_plain': []}
    for tb in root.iter(W + 'txbxContent'):
        anc = [a.tag.split('}')[1] for a in tb.iterancestors()]
        g = 'vml_fallback' if 'Fallback' in anc else 'wps_choice' if 'Choice' in anc else 'vml_or_plain'
        for p in tb.iter(W + 'p'):
            t = ''.join(x.text or '' for x in p.iter(W + 't')).strip()
            if t: groups[g].append(t)
    tp = [e.get('string') for e in root.iter('{%s}textpath' % NS['v']) if e.get('string')]
    names = z.namelist()
    vs, xl = {}, {}
    for n in names:
        if n.startswith('word/embeddings/') and n.endswith('.vsdx'):
            try:
                zz = zipfile.ZipFile(__import__('io').BytesIO(z.read(n)))
                txt = []
                for pn in zz.namelist():
                    if pn.startswith('visio/pages/page') and pn.endswith('.xml'):
                        r = etree.fromstring(zz.read(pn))
                        for e in r.iter('{*}Text'):
                            s = ' '.join(''.join(e.itertext()).split())
                            if s: txt.append(s)
                vs[n] = txt
            except Exception as e:
                vs[n] = ['ERR ' + repr(e)]
        if n.startswith('word/embeddings/') and n.endswith('.xlsx'):
            try:
                zz = zipfile.ZipFile(__import__('io').BytesIO(z.read(n)))
                s = []
                if 'xl/sharedStrings.xml' in zz.namelist():
                    r = etree.fromstring(zz.read('xl/sharedStrings.xml'))
                    s = [' '.join(''.join(si.itertext()).split()) for si in r.iter('{*}si')]
                xl[n] = [x for x in s if x]
            except Exception as e:
                xl[n] = ['ERR ' + repr(e)]
    media = [n for n in names if n.startswith('word/media/')]
    numpr = len(root.findall('.//' + W + 'numPr'))
    return dict(groups=groups, textpath=tp, vsdx=vs, xlsx=xl, media=media, ole_bin=[n for n in names if n.endswith('.bin') and 'embeddings' in n],
                vsd=[n for n in names if n.endswith('.vsd')], n_numPr=numpr,
                n_vml_shape=len(list(root.iter('{%s}shape' % NS['v']))), n_drawing=len(list(root.iter(W + 'drawing'))),
                n_pict=len(list(root.iter(W + 'pict'))), n_object=len(list(root.iter(W + 'object'))))


def share(texts, hay, minlen=5):
    """доля различных текстов (норм., >=2 слов или >=5 знаков), найденных подстрокой в hay."""
    seen, ok, tot = set(), 0, 0
    for t in texts:
        n = A.norm(t)
        if n in seen or not (len(n.split()) >= 2 or len(n) >= minlen): continue
        seen.add(n); tot += 1
        if (' ' + n + ' ') in hay: ok += 1
    return dict(found=ok, total=tot, share=round(ok / tot, 3) if tot else None)


def stage_docx(tag, out):
    from docling.document_converter import DocumentConverter
    os.makedirs(f'{out}/json_{tag}', exist_ok=True); os.makedirs(f'{out}/res_{tag}', exist_ok=True)
    conv = DocumentConverter()
    for name, (dx, _, pilot) in INPUTS.items():
        res = dict(name=name, docx=os.path.basename(dx), size=os.path.getsize(dx))
        t0 = time.time()
        try:
            doc = conv.convert(dx).document
        except Exception as e:
            res['error'] = repr(e)[:500]; json.dump(res, open(f'{out}/res_{tag}/{name}.docx.json', 'w'), ensure_ascii=False, indent=1); continue
        res['time_s'] = round(time.time() - t0, 2)
        doc.save_as_json(f'{out}/json_{tag}/{name}.docx.json')
        it = item_texts(doc)
        c = collections.Counter(l for l, _ in it)
        res['labels'] = dict(c)
        res['tables'] = [dict(rows=t.data.num_rows, cols=t.data.num_cols, cells=len(t.data.table_cells)) for t in doc.tables]
        res['n_tables'] = len(doc.tables); res['n_table_cells'] = sum(x['cells'] for x in res['tables'])
        res['pictures'] = dict(n=len(doc.pictures), with_image=sum(1 for p in doc.pictures if p.image is not None),
                               with_caption=sum(1 for p in doc.pictures if p.captions))
        lis = [i for i in items(doc) if str(i.label.value) == 'list_item']
        res['list_markers'] = dict(n=len(lis), with_marker=sum(1 for i in lis if getattr(i, 'marker', '')), enumerated=sum(1 for i in lis if getattr(i, 'enumerated', False)),
                                   sample=[getattr(i, 'marker', '') for i in lis[:8]])
        flat = flat_texts(doc, True)
        hay = ' ' + A.norm(' '.join(flat)) + ' '
        # порядок/полнота против assemble.docx_pages
        ours = [t for pg in A.docx_pages(dx) for t in pg]
        on = [A.norm(t) for t in ours]; on = [x for x in on if x]
        dn = [A.norm(t) for t in flat]; dn = [x for x in dn if x]
        dset = set(dn)
        res['para'] = dict(ours=len(on), docling=len(dn), ours_exact_in_docling=round(sum(x in dset for x in on) / max(len(on), 1), 3),
                           ours_substring_in_docling=round(sum((' ' + x + ' ') in hay for x in on) / max(len(on), 1), 3))
        sm = difflib.SequenceMatcher(None, on, dn, autojunk=False) if len(on) * len(dn) < 4e7 else None
        res['para']['order_match'] = round(sum(b.size for b in sm.get_matching_blocks()) / max(len(on), 1), 3) if sm else 'skipped_big'
        # номера пунктов
        ours_num = [t for t in ours if NUMRE.match(t)]
        dl_num = [t for t in flat if NUMRE.match(t)]
        onum = set(NUMRE.match(t).group(0).strip() for t in ours_num); dnum = set(NUMRE.match(t).group(0).strip() for t in dl_num)
        res['numbers'] = dict(ours_typed_number_paras=len(ours_num), docling_number_paras=len(dl_num), typed_numbers_found_in_docling=round(len(onum & dnum) / max(len(onum), 1), 3),
                              sample_docling=dl_num[:5])
        # XML-аудит
        au = xml_audit(dx)
        g = au['groups']
        res['xml'] = dict(n_numPr=au['n_numPr'], n_vml_shape=au['n_vml_shape'], n_drawing=au['n_drawing'], n_pict=au['n_pict'], n_object=au['n_object'],
                          media=len(au['media']), media_ext=dict(collections.Counter(os.path.splitext(m)[1].lower() for m in au['media'])), vsdx=len(au['vsdx']), vsd=len(au['vsd']), xlsx=len(au['xlsx']), ole_bin=len(au['ole_bin']),
                          txbx_paras={k: len(v) for k, v in g.items()}, textpath=len(au['textpath']))
        res['txbx_in_docling'] = {k: share(v, hay) for k, v in g.items()}
        res['txbx_in_docling']['all_wps+vml_only'] = share(g['wps_choice'] + g['vml_or_plain'], hay)
        res['textpath_in_docling'] = share(au['textpath'], hay, 3)
        vt = [t for v in au['vsdx'].values() for t in v]; res['vsdx_text_in_docling'] = share(vt, hay, 3); res['vsdx_text_n'] = len(vt)
        xt = [t for v in au['xlsx'].values() for t in v]; res['xlsx_text_in_docling'] = share(xt, hay, 3); res['xlsx_text_n'] = len(xt)
        res['md_chars'] = len(doc.export_to_markdown())
        json.dump(res, open(f'{out}/res_{tag}/{name}.docx.json', 'w'), ensure_ascii=False, indent=1)
        print(name, res['time_s'], res['labels'], res['para'], flush=True)


def stage_pdf(tag, out, maxp=None):
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    os.makedirs(f'{out}/json_{tag}', exist_ok=True); os.makedirs(f'{out}/res_{tag}', exist_ok=True)
    conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=PdfPipelineOptions(do_ocr=False))})
    for name, (_, pdf, pilot) in INPUTS.items():
        if not pdf: continue
        res = dict(name=name, pdf=os.path.basename(pdf))
        import fitz
        res['pdf_pages'] = fitz.open(pdf).page_count
        t0 = time.time()
        kw = {'page_range': (1, maxp)} if maxp else {}
        try:
            doc = conv.convert(pdf, **kw).document
        except Exception as e:
            res['error'] = repr(e)[:500]; json.dump(res, open(f'{out}/res_{tag}/{name}.pdf.json', 'w'), ensure_ascii=False, indent=1); continue
        res['time_s'] = round(time.time() - t0, 1); res['pages_converted'] = len(doc.pages)
        doc.save_as_json(f'{out}/json_{tag}/{name}.pdf.json')
        allit = list(doc.iterate_items(with_groups=False, included_content_layers=all_layers()))
        c = collections.Counter(str(getattr(i.label, 'value', i.label)) for i, _ in allit)
        res['labels_all_layers'] = dict(c)
        res['layers'] = dict(collections.Counter(str(getattr(i, 'content_layer', '')) for i, _ in allit))
        prov = [i for i, _ in allit if getattr(i, 'prov', None)]
        res['prov'] = dict(items=len(allit), with_prov=len(prov), with_page_and_bbox=sum(1 for i in prov if i.prov[0].page_no and i.prov[0].bbox is not None),
                           sample=[dict(page=i.prov[0].page_no, bbox=[round(x, 1) for x in i.prov[0].bbox.as_tuple()], label=str(i.label.value)) for i in prov[:2]])
        res['tables'] = [dict(page=t.prov[0].page_no if t.prov else None, rows=t.data.num_rows, cols=t.data.num_cols, cells=len(t.data.table_cells)) for t in doc.tables]
        res['n_pictures'] = len(doc.pictures)
        hf = [(i.prov[0].page_no if i.prov else None, i.text[:60]) for i, _ in allit if str(i.label.value) in ('page_header', 'page_footer')]
        res['header_footer_items'] = len(hf); res['header_footer_pages'] = len({p for p, _ in hf}); res['header_footer_sample'] = hf[:4]
        json.dump(res, open(f'{out}/res_{tag}/{name}.pdf.json', 'w'), ensure_ascii=False, indent=1)
        print(name, res['time_s'], res['labels_all_layers'], flush=True)


def load(path):
    from docling_core.types.doc import DoclingDocument
    return DoclingDocument.load_from_json(path)


def grams(lines, k=4):
    return A.shingles(B.words(lines), k)


def cellset(cells):
    return {A.norm(c) for c in cells if A.norm(c)}


def stage_cover(tag, out):
    for name, (dx, pdf, pilot) in INPUTS.items():
        if not pdf: continue
        pj = f'{out}/json_{tag}/{name}.pdf.json'; dj = f'{out}/json_{tag}/{name}.docx.json'
        if not (os.path.exists(pj) and os.path.exists(dj)): continue
        res = dict(name=name)
        pd, dd = load(pj), load(dj)
        pres = json.load(open(f'{out}/res_{tag}/{name}.pdf.json'))
        npg = pres.get('pages_converted') or 0
        pages_lim = pres['pdf_pages'] if npg >= pres['pdf_pages'] else npg
        res['pdf_pages_used'] = pages_lim
        # тело эталона по Docling (без furniture) и по нашему pdf_lines (те же страницы)
        d_body = [t for lab, t in item_texts(pd) if not isinstance(t, list) and t.strip()]
        d_tabs = [c for lab, t in item_texts(pd) if isinstance(t, list) and lab == 'table' for c in t]
        d_body_all = flat_texts(pd)  # тело + ячейки таблиц (без furniture)
        d_docx = flat_texts(dd, True)
        ours_pdf = B.pdf_lines(pdf)  # весь документ; для ограниченных страниц ниже отдельно
        if pages_lim < pres['pdf_pages']:
            import fitz, tempfile
            src = fitz.open(pdf); tmp = fitz.open(); tmp.insert_pdf(src, from_page=0, to_page=pages_lim - 1)
            tp = f'{out}/_first{pages_lim}.pdf'; tmp.save(tp); ours_pdf = B.pdf_lines(tp)
        ours_docx = [t for pg in A.docx_pages(dx) for t in pg]
        def rec(pl, wl): 
            p, w = grams(pl), grams(wl)
            return dict(pdf_grams=len(p), recall=round(len(p & w) / max(len(p), 1), 4))
        res['whole'] = {
            'ours_pdf_lines_vs_ours_docx(body.py)': rec(ours_pdf, ours_docx),
            'docling_pdf_body_vs_docling_docx': rec(d_body_all, d_docx),
            'docling_pdf_body_vs_ours_docx': rec(d_body_all, ours_docx),
            'ours_pdf_lines_vs_docling_docx': rec(ours_pdf, d_docx),
        }
        def core(lines):
            _, b, a = B.split_core(lines); return b, a
        pb_o, pa_o = core(ours_pdf); pb_d, pa_d = core(d_body_all)
        wb_o, wa_o = core(ours_docx); wb_d, wa_d = core(d_docx)
        res['core_body'] = {
            'ours(body.py split_core)': rec(pb_o, wb_o),
            'docling(split_core over docling lines)': rec(pb_d, wb_d),
            'docling_pdf_core_vs_ours_docx_core': rec(pb_d, wb_o),
            'ours_pdf_core_vs_docling_docx_core': rec(pb_o, wb_d),
        }
        res['core_appx'] = {'ours': rec(pa_o, wa_o), 'docling': rec(pa_d, wa_d)}
        # что Docling считает колонтитулами: доля 4-грамм furniture в 4-граммах тела
        fur = [t for lab, t in item_texts(pd, True) if lab in ('page_header', 'page_footer') and t]
        res['furniture_lines'] = len(fur)
        res['furniture_grams_in_docx_body'] = rec(fur, ours_docx) if fur else None
        # таблицы: самая большая таблица Word (по ячейкам) и её лучший двойник в PDF и в docx-Docling
        wt = sorted([t for t in dd.tables if t.data.num_rows >= 5], key=lambda t: -len(cellset([c.text for c in t.data.table_cells])))[:3]
        tabres = []
        for t in wt:
            wc = cellset([c.text for c in t.data.table_cells])
            best = None
            for pt in pd.tables:
                pc = cellset([c.text for c in pt.data.table_cells])
                ov = len(wc & pc) / max(len(wc), 1)
                if best is None or ov > best[0]: best = (ov, pt)
            if best:
                bt = best[1]
                tabres.append(dict(word=dict(rows=t.data.num_rows, cols=t.data.num_cols, cells=len(t.data.table_cells), uniq=len(wc)),
                                   pdf_best=dict(page=bt.prov[0].page_no if bt.prov else None, rows=bt.data.num_rows, cols=bt.data.num_cols, cells=len(bt.data.table_cells)),
                                   word_cell_texts_found_in_pdf_table=round(best[0], 3)))
        res['table_pairs'] = tabres
        json.dump(res, open(f'{out}/res_{tag}/{name}.cover.json', 'w'), ensure_ascii=False, indent=1)
        print(name, json.dumps(res['core_body'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    st, tag = sys.argv[1], sys.argv[2]
    out = SCR
    mp = int(sys.argv[3]) if len(sys.argv) > 3 else None
    {'docx': lambda: stage_docx(tag, out), 'pdf': lambda: stage_pdf(tag, out, mp), 'cover': lambda: stage_cover(tag, out)}[st]()
