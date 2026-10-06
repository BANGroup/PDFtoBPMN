"""Индекс эталона: физические строки содержательных страниц + поток key; поиск абзаца по тексту и номера перед ним."""
import re, bisect
NUMONLY = re.compile(r'(\d{1,3}(\.\d{1,3}){0,5}[.)]?|[а-яa-z]\))')
from pagediff import key, canon_pages
import reeng_plan as rp


def norm(s): return re.sub(r'[\s­]+', '', (s or '')).rstrip('.')


def pat_for(lt):
    """lvlText (%1.%2 …) -> (regex, [уровни])."""
    rx, lv = '', []
    for p in re.split(r'(%\d)', lt):
        m = re.fullmatch(r'%(\d)', p)
        if m: rx += r'([0-9]+|[A-Za-zА-Яа-я]{1,3})'; lv.append(int(m.group(1)) - 1)
        else: rx += re.escape(p).replace(r'\ ', r'\s*')
    return re.compile(r'^\s*' + rx + r'\s*'), lv


class RefIndex:
    def __init__(self, pdf):
        self.pages = canon_pages(pdf)
        head = rp.header_keys(self.pages)
        self.start = next((i for i, p in enumerate(self.pages) if any(rp.CONTENT_HEAD.match(l) for l in p['lines'])), 0)
        self.head_line = next((l for l in self.pages[self.start]['lines'] if rp.CONTENT_HEAD.match(l)), '')
        self.lines = [(i, l.strip()) for i in range(self.start, len(self.pages)) for l in rp.usable_lines(self.pages[i], head)]
        self.keys = [key(t) for _, t in self.lines]
        self.off, o = [], 0
        for k in self.keys: self.off.append(o); o += len(k)
        self.S = ''.join(self.keys)

    def locate(self, kt, frm):
        """Позиция начала абзаца (key kt) в потоке эталона после frm -> (pos, L) | None."""
        for n in (min(len(kt), 48), min(len(kt), 24)):
            if n < 4: return None
            pos = self.S.find(kt[:n], frm)
            if pos >= 0 and pos - frm <= 200000: return pos, bisect.bisect_right(self.off, pos) - 1
        return None

    def number_before(self, pos, L, kt, rx):
        """Номер перед текстом абзаца по шаблону lvlText: -> (match, raw, L0) | None; typed=True если текст начинается с набранного номера."""
        for L0 in (L, L - 1, L - 2):
            if L0 < 0: continue
            raw = ' '.join(t for _, t in self.lines[L0:L + 1])
            m = rx.match(raw)
            if not m: continue
            kr = key(raw[m.end():])
            if kr and kt.startswith(kr): return m, raw, L0
        return None

    def typed_at_line_start(self, pos, L):
        return self.off[L] == pos
