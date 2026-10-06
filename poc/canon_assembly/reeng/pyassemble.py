"""Сборка канона без Word (пилот TASK-021, шаг 9): вставка frag_*.docx в метки base_marked.docx на lxml + docxcompose.

Аналог шага assemble word_run.ps1: для каждой вставки {marker, frags} фрагменты по порядку встают перед абзацем-меткой, абзац-метка убирается
(если это единственный абзац после таблицы в конце тела — очищается). Стили (по имени), нумерация (новые abstractNum/num с новыми id),
картинки/OLE/embeddings/rels, сноски переносит docxcompose; sectPr фрагмента не переносится (как в InsertFile: свойства раздела — у базы).
python3 pyassemble.py <base_marked.docx> <plan.json> <каталог фрагментов> <out.docx>
"""
import sys, os, re, json, copy
import docx
from docx.oxml.ns import qn
from docxcompose.composer import Composer
from docxcompose.utils import xpath


class PyComposer(Composer):
    """Composer без глобальных пересчётов, ломающих структуру: закладки (id start/end пересчитывались независимо — пары сбивались),
    секции (фрагмент — один раздел). Уникальность docPr/закладок восстанавливается точечно в конце сборки."""
    def add_styles(self, doc, element):
        # docxcompose сливает abstractNum вставляемого списка с абзацным стилем базы (anum_id_mapping): счётчики идут насквозь через главы/фрагменты.
        # InsertFile в Word ведёт каждый вставленный список отдельно -> записи, добавленные стилевой веткой, отбрасываем.
        before = set(self.anum_id_mapping)
        super().add_styles(doc, element)
        for k in set(self.anum_id_mapping) - before: del self.anum_id_mapping[k]

    def add_numberings(self, doc, element):
        """docxcompose.add_numberings, исправленная: у элемента с несколькими numId (таблица, абзацы разных списков) все они получали ОДИН новый numId/abstractNum
        (next_num_id не увеличивался в цикле) — списки сливались. Здесь каждый исходный numId/abstractNum получает свой новый id."""
        import random
        from docxcompose.utils import NS
        num_ids = {n.val for n in xpath(element, './/w:numId')}
        if not num_ids: return
        next_num_id, next_anum_id = self._next_numbering_ids()
        src = doc.part.numbering_part
        for num_id in sorted(num_ids):
            if num_id in self.num_id_mapping: continue
            res = src.element.xpath('.//w:num[@w:numId="%s"]' % num_id)
            if not res: continue
            num_element = copy.deepcopy(res[0]); num_element.numId = next_num_id
            self.num_id_mapping[num_id] = next_num_id; next_num_id += 1
            anum_id = num_element.xpath('./w:abstractNumId')[0]
            if anum_id.val not in self.anum_id_mapping:
                r2 = src.element.xpath('.//w:abstractNum[@w:abstractNumId="%s"]' % anum_id.val)
                if not r2: continue
                anum_element = copy.deepcopy(r2[0]); self.anum_id_mapping[anum_id.val] = next_anum_id
                anum_id.val = next_anum_id
                anum_element.set('{%s}abstractNumId' % NS['w'], str(next_anum_id)); next_anum_id += 1
                nsid = anum_element.find('.//w:nsid', NS)
                if nsid is not None: nsid.set('{%s}val' % NS['w'], '{0:08X}'.format(int(10 ** 8 * random.random())))
                self._insert_abstract_num(anum_element)
            else: anum_id.val = self.anum_id_mapping[anum_id.val]
            self._insert_num(num_element)
        for ref in xpath(element, './/w:numId'): ref.val = self.num_id_mapping.get(ref.val, ref.val)

    def renumber_bookmarks(self): pass
    def renumber_docpr_ids(self): pass
    def renumber_nvpicpr_ids(self): pass
    def fix_section_types(self, doc): pass
    def fix_header_and_footers(self, doc): pass


def marker_paragraph(body, marker):
    for el in body.iterchildren(qn('w:p')):
        if ''.join(t.text or '' for t in el.iter(qn('w:t'))).strip() == marker: return el
    return None


def fix_ids(d):
    """Уникальные wp:docPr/@id (дубликаты — новые id) и пары закладок: повторяющиеся id закладок (из разных фрагментов) получают новые вместе со своим End."""
    body = d.element.body
    # wp:docPr/@id уникальны во ВСЕМ пакете (document + header/footer/footnotes): id тела, совпавший с id из колонтитула, Word считает повреждением («Файл поврежден»)
    import re as _re
    seen = set()
    for part in d.part.package.iter_parts():
        if _re.match(r'/word/(header|footer|footnotes|endnotes)', str(part.partname)):
            seen |= set(_re.findall(rb'<wp:docPr[^>]*? id="(\d+)"', part.blob))
    seen = {x.decode() if isinstance(x, bytes) else x for x in seen}
    ids = [int(e.get('id')) for e in xpath(body, './/wp:docPr') if (e.get('id') or '').isdigit()] + [int(x) for x in seen if x.isdigit()]
    nxt = max(ids or [0]) + 1; n = 0
    for e in xpath(body, './/wp:docPr'):
        i = e.get('id')
        if i in seen: e.set('id', str(nxt)); nxt += 1; n += 1; i = str(nxt - 1)
        seen.add(i)
    # закладки: пары start/end сопоставляются по порядку документа (id повторяются между фрагментами); непарные удаляются,
    # каждой паре — уникальный id; повторяющиеся имена получают суффикс (Word: «Файл поврежден» при непарных id)
    W = qn; open_ = {}; pairs = []; lone_ends = []
    for el in body.iter(W('w:bookmarkStart'), W('w:bookmarkEnd')):
        i = el.get(W('w:id'))
        if el.tag == W('w:bookmarkStart'): open_.setdefault(i, []).append(el)
        elif open_.get(i): pairs.append((open_[i].pop(0), el))
        else: lone_ends.append(el)
    for el in lone_ends + [x for v in open_.values() for x in v]:
        el.getparent().remove(el)
    names = set()
    for k, (st_, en_) in enumerate(pairs):
        st_.set(W('w:id'), str(k)); en_.set(W('w:id'), str(k))
        nm = st_.get(W('w:name'))
        if nm in names:
            j = 1
            while f'{nm}_{j}' in names: j += 1
            st_.set(W('w:name'), f'{nm}_{j}'); nm = f'{nm}_{j}'
        names.add(nm)
    d._bm_removed = len(lone_ends) + sum(len(v) for v in open_.values())
    return n


def assemble(base_marked, plan, fragdir, out):
    d = docx.Document(base_marked)
    comp = PyComposer(d); comp.restart_numbering = False
    body = d.element.body
    log = {'inserted': 0, 'markers': 0, 'marker_not_found': [], 'marker_kept': 0, 'frag_errors': []}
    for ins in plan['inserts']:
        mp = marker_paragraph(body, ins['marker'])
        if mp is None: log['marker_not_found'].append(ins['marker']); continue
        log['markers'] += 1
        for fr in ins['frags']:
            fp = os.path.join(fragdir, re.split(r'[\\/]', fr)[-1])
            try:
                fd = docx.Document(fp)
                comp.insert(body.index(mp), fd, remove_property_fields=False)
                log['inserted'] += 1
            except Exception as e:
                log['frag_errors'].append(f'{os.path.basename(fp)}: {type(e).__name__}: {e}'[:200])
        nxt = mp.getnext(); prv = mp.getprevious()
        if prv is not None and prv.tag == qn('w:tbl') and (nxt is None or nxt.tag == qn('w:sectPr')):   # после таблицы в конце тела нужен абзац: очищаем текст метки
            for t in mp.iter(qn('w:t')): t.text = ''
            log['marker_kept'] += 1
        else: body.remove(mp)
    log['docpr_renamed'] = fix_ids(d)
    d.save(out)
    return d, log


if __name__ == '__main__':
    plan = json.load(open(sys.argv[2]))
    _, lg = assemble(sys.argv[1], plan, sys.argv[3], sys.argv[4]); print(lg)
