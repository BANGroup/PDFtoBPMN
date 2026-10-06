"""Пакет для вычитки командой качества: исходники + итог по 5 документам, index.html, zip.

python build_qa_package.py   -> output/canon_qa_2026-10-01/<пакет>/ и <пакет>.zip
"""
import os, re, json, shutil, zipfile, html
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '../../..'))
CORPUS = os.path.join(ROOT, 'data/bnd_corpus/documents/СМК')
NAME = 'Канон_БНД_вычитка_2026-10-01'
OUT = os.path.join(ROOT, 'output/canon_qa_2026-10-01')
PKG = os.path.join(OUT, NAME)

# Цифры — из VERIFIED.md (проверка независимым скриптом), замечания — подтверждены по файлам.
DOCS = [
    {'doc': 'ДП-Б1.024-06', 'path': 'B1/ДП-Б1.024-06', 'lines': 2302, 'num': '88 / 88', 'note_lines': '',
     'remarks': [
         ('fix', 'Исправить при вычитке. В итоге заголовок раздела 9 начинается с лишней буквы: «Щ9 ПРИЕМ-СДАЧА ТОРГОВОГО '
                 'ОБОРУДОВАНИЯ». В утверждённом PDF её нет. Источник — лист замены изм. 1 («Листы для замены_8DA2B6D5.docx»): '
                 'там перед номером стоит строчная «щ», которую стиль заголовка показывает прописной. Алгоритм переносит '
                 'текст листа замены как есть и ничего не исправляет сам.'),
         ('see', 'Схема размещения оборудования (стр. 28 PDF). Надписи на схеме («подогреватель», перечень бортов VQ-BLH, '
                 'VQ-BLI…) в Word — текстовые фигуры, в PDF — часть рисунка. Сверять глазами по рисунку.'),
         ('info', 'Справочно: в листе замены изм. 1 есть лишний разрыв страницы, похожий на отдельную «стр. 26». Алгоритм '
                  'его не использовал: стр. 26 эталона совпадает с исходным Word.'),
     ]},
    {'doc': 'РГ-184-06', 'path': 'V4/РГ-184-06', 'lines': 672, 'num': '78 / 78',
     'note_lines': '11 строк отличаются только цифрой: в текстовом слое PDF надстрочный номер сноски слит с текстом '
                   '(«Экономия фонда заработной платы3»), в Word номер стоит надстрочным знаком.',
     'remarks': [
         ('see', 'Таблица со сносками (стр. 25 PDF). Проверить, что номера сносок 1–4 стоят у тех же слов, что в PDF.'),
         ('ok', 'Дефектов, искажающих смысл, не найдено.'),
     ]},
    {'doc': 'КД-РД-В5.058-04', 'path': 'V5/КД-РД-В5.058-04', 'lines': 2488, 'num': '228 / 228',
     'note_lines': '15 строк из них — текст бланка графика работы. В Word бланк вставлен картинками EMF '
                   '(image4, image10–image13); текст извлечён из картинок напрямую, без распознавания.',
     'remarks': [
         ('see', 'Бланк графика работы (стр. 72–73 PDF) в Word — картинка. Сверять глазами; править его как текст нельзя.'),
         ('ok', 'Дефектов, искажающих смысл, не найдено.'),
     ]},
    {'doc': 'КД-РД-Б1.041-04', 'path': 'B1/КД-РД-Б1.041-04', 'lines': 2895, 'num': '148 / 148', 'note_lines': '',
     'remarks': [
         ('info', 'Исходный Word в старом формате .doc; Word пересохранил его в .docx без изменения содержимого.'),
         ('info', 'Справочно: в листах замены изм. 13 есть стр. 36, которой нет в перечне страниц протокола изм. 13. '
                  'На итог не влияет: в эталоне стр. 36 — версия изм. 17.'),
         ('info', 'Справочно: в листах замены изм. 23 лишний разрыв страницы, похожий на «стр. 60». Не использован.'),
         ('info', 'У 7 абзацев номер набран вручную текстом, а не автонумерацией. Так он набран и в исходном Word или листах замены.'),
         ('ok', 'Дефектов, искажающих смысл, не найдено.'),
     ]},
    {'doc': 'КД-ДП-Б1.011-04', 'path': 'B1/КД-ДП-Б1.011-04', 'lines': 2669, 'num': '212 / 212',
     'note_lines': '7 строк из них — образец МСО 298 (приложение 11, рис. 11.1–11.2): встроенный объект и картинка EMF '
                   'в исходном «РПБ.doc», в итоге они есть.',
     'remarks': [
         ('doc', 'Оформление эталона: стр. 18 PDF — версия изм. 27 (дата введения изменения 25.03.2025, приказ №КП-53/25, '
                 'новый п. 6.12 «Вице-президент по управлению тарифами и загрузкой…»), но штампа «Изменение № 27» на '
                 'странице нет. Смысл не искажён, итог соответствует PDF.'),
         ('see', 'Образец МСО 298 (стр. 99 PDF) — встроенный объект. Номер бланка «2982201159700» виден на изображении '
                 '(стр. 118 PDF итога), текстом в файлах он не хранится.'),
         ('info', 'Исходный Word в старом формате .doc; Word пересохранил его в .docx без изменения содержимого.'),
         ('info', 'Справочно: в 20 разделах листов замены (изм. 3, 7, 10, 27, 36, 37) нет номера страницы в колонтитуле или '
                  'он повторяется. Страница определена по дословному совпадению строк с эталоном.'),
         ('info', 'У 9 абзацев номер набран вручную текстом, а не автонумерацией. Так он набран и в исходном Word или листах замены.'),
     ]},
]

BADGE = {'fix': ('Исправить', '#b42318'), 'doc': ('Дефект эталона', '#b54708'), 'see': ('Сверить глазами', '#175cd3'),
         'info': ('Справочно', '#667085'), 'ok': ('Итог', '#067647')}


def kind(fn):
    l = fn.lower()
    if l.endswith('.pdf'):
        return 'pdf' if re.match(r'измене', l) else 'other'
    if 'замен' in l or l.startswith('зам '):
        return 'sheets'
    if 'лист' in l and ('изм' in l or 'зимен' in l):
        return 'protocol'
    if l.startswith('изменение'):
        return 'sheets'
    return 'other'


def href(rel):
    return quote(rel.replace(os.sep, '/'))


def a(rel, text):
    return f'<a href="{href(rel)}">{html.escape(text)}</a>'


def copy(src, rel):
    dst = os.path.join(PKG, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return rel


def build_doc(d):
    src = os.path.join(CORPUS, d['path'])
    meta = json.load(open(os.path.join(src, 'document.json'), encoding='utf-8'))
    plan = json.load(open(os.path.join(HERE, d['doc'], 'plan.json'), encoding='utf-8'))
    n = d['doc']
    etalon = [f for f in os.listdir(os.path.join(src, 'files')) if 'талон' in f][0]
    base = os.listdir(os.path.join(src, 'word'))
    r = {'meta': meta, 'pages_total': len(plan['pages']), 'pages_sheets': sum(len(x['pages']) for x in plan['regions'])}
    r['etalon'] = copy(os.path.join(src, 'files', etalon), f'{n}/1_Оригинал_PDF/{etalon}')
    r['base'] = [copy(os.path.join(src, 'word', f), f'{n}/2_Исходный_Word/{f}') for f in sorted(base)
                 if f.lower().endswith(('.doc', '.docx'))]
    r['base_other'] = [copy(os.path.join(src, 'word', f), f'{n}/2_Исходный_Word/{f}') for f in sorted(base)
                       if not f.lower().endswith(('.doc', '.docx'))]
    am = []
    for fd in os.listdir(os.path.join(src, 'amendments')):
        m = re.match(r'(\d{4})-(\d\d)-(\d\d)_изм(\d+)', fd)
        am.append((int(m.group(4)), f'{m.group(3)}.{m.group(2)}.{m.group(1)}', fd))
    r['izm'] = []
    for k, date, fd in sorted(am):
        files = {'protocol': [], 'sheets': [], 'pdf': [], 'other': []}
        for f in sorted(os.listdir(os.path.join(src, 'amendments', fd))):
            files[kind(f)].append(copy(os.path.join(src, 'amendments', fd, f), f'{n}/3_Изменения/изм{k:02d} ({date})/{f}'))
        r['izm'].append((k, date, files))
    r['markup'] = copy(os.path.join(HERE, n, f'{n}_markup.docx'), f'{n}/4_Итог/{n}_исправления.docx')
    r['canon'] = copy(os.path.join(HERE, n, f'{n}_canon.docx'), f'{n}/4_Итог/{n}_чистая.docx')
    r['canon_pdf'] = copy(os.path.join(HERE, n, f'{n}_canon.pdf'), f'{n}/4_Итог/{n}_чистая (PDF для сверки).pdf')
    return r


def izm_html(izm):
    rows = []
    for k, date, f in izm:
        parts = []
        for key, label in (('protocol', 'лист изменения'), ('sheets', 'листы замены'), ('pdf', 'PDF изменения'), ('other', 'прочее')):
            for i, rel in enumerate(f[key]):
                parts.append(a(rel, label if len(f[key]) == 1 else f'{label} {i + 1}'))
        rows.append(f'<li><b>№{k}</b> от {date}: ' + ' · '.join(parts) + '</li>')
    return f'<details><summary>{len(izm)} изменений</summary><ol class="izm">{"".join(rows)}</ol></details>'


def doc_row(d, r):
    m = r['meta']
    rem = ''.join(f'<li><span class="badge" style="background:{BADGE[t][1]}">{BADGE[t][0]}</span> {html.escape(x)}</li>'
                  for t, x in d['remarks'])
    note = f'<div class="small">{html.escape(d["note_lines"])}</div>' if d['note_lines'] else ''
    base = '<br>'.join(a(x, os.path.basename(x)) for x in r['base'])
    base += ''.join(f'<div class="small">также: {a(x, os.path.basename(x))}</div>' for x in r['base_other'])
    return f'''<tr>
<td><b>{html.escape(d["doc"])}</b><div>{html.escape(m["title"])}</div>
<div class="small">{html.escape(m["process_code"])} · {html.escape(m["process_name"])}<br>{html.escape(m["department"])}<br>
<a href="{html.escape(m["web_url"])}">карточка в Lotus</a></div></td>
<td>{a(r["etalon"], "PDF оригинала")}</td>
<td>{base}</td>
<td>{izm_html(r["izm"])}<div class="small">из листов замены взято {r["pages_sheets"]} из {r["pages_total"]} стр. эталона</div></td>
<td class="res">{a(r["markup"], "исправления (Word)")}<br>{a(r["canon"], "чистая (Word)")}<br>
<span class="small">{a(r["canon_pdf"], "чистая — PDF для сверки")}</span></td>
<td><div>Текст эталона в итоге: <b>100 %</b> ({d["lines"]} строк)</div>{note}
<div>Номер + текст пункта = эталон: <b>{d["num"]}</b></div><div>Дубли абзацев: <b>0</b></div>
<ul class="rem">{rem}</ul></td>
</tr>'''


GENERAL = '''
<h2>Как вычитывать</h2>
<ol>
<li><b>Эталон</b> — «PDF оригинала»: утверждённая версия документа со всеми изменениями. С ним и сверяем.</li>
<li><b>«Чистая (Word)»</b> — итог сборки. По тексту она должна совпадать с PDF оригинала: те же пункты, номера, таблицы и приложения.</li>
<li><b>«Исправления (Word)»</b> — тот же итог в режиме рецензирования относительно исходного Word. Видно всё, что изменения
добавили и удалили за всё время. Удобно проверять, что каждая правка подкреплена листом изменения.</li>
<li><b>«Чистая — PDF для сверки»</b> — печать итогового Word, чтобы листать рядом с оригиналом.</li>
</ol>
<p><b>Что проверять:</b> текст и номера пунктов, таблицы, приложения, ссылки между пунктами.<br>
<b>Что не проверять:</b> разбивку на страницы, колонтитулы, штампы «Изменение №», лист регистрации изменений, реквизиты титульного листа.
Они не входили в задачу сборки.</p>

<h2>Как устроена сборка — простыми словами</h2>
<p><b>Почему это нужно.</b> При изменении документа Word целиком не переделывают. Готовят два файла: <i>лист изменения</i>
(протокол: что на что меняем и какие страницы заменить) и <i>листы замены</i> (новые версии отдельных страниц). Утверждённый
PDF собирают вручную: из прежнего PDF убирают старые страницы и вставляют новые. В итоге актуальный текст есть только в PDF,
а Word устаревает. Мы восстанавливаем Word, который совпадает с PDF. Это машиночитаемая версия документа; дальше с ней можно
работать в режиме «исправления / чистая», как юристы с договорами.</p>
<ol>
<li><b>Читаем эталон постранично.</b> На каждой странице есть «Стр. N из M», а на изменённой ещё и штамп «Изменение № K».
Поэтому для каждой страницы точно известно, какая версия действует: без штампа — исходный Word, со штампом K — лист замены изменения K.</li>
<li><b>Находим эти страницы в листах замены.</b> В файле листов замены каждая страница — отдельный раздел Word с колонтитулом
«Стр. N». Сверяются три источника: перечень страниц в протоколе, колонтитулы листов и штампы в эталоне. Если колонтитула нет
или он повторяется (пустые разделы, страница, разрезанная на два раздела), страница определяется по содержимому: какая
страница эталона дословно содержит строки раздела. Сопоставления «по похожести» нет.</li>
<li><b>Находим место в исходном Word.</b> Подряд идущие изменённые страницы образуют участок. Его границы в исходном Word
определяются по последним строкам предыдущей неизменённой страницы и первым строкам следующей — точным совпадением текста.</li>
<li><b>Заменяем.</b> Участок исходного Word вырезается. На его место сам Microsoft Word (через автоматизацию) вставляет страницы
из листов замены со всем оформлением: стилями, таблицами, рисунками. Файлы старого формата .doc Word сначала пересохраняет в .docx.</li>
<li><b>Восстанавливаем нумерацию.</b> Номера пунктов в Word ставит автонумерация, и после вставки кусков из разных файлов счёт
сбивается. Номер каждого пункта сравнивается с эталоном; где он расходится, списку задаётся правильная точка отсчёта.
Нумерация остаётся живой: если добавить пункт, Word перенумерует сам. Номера, которые в источниках набраны вручную текстом, не трогаются.</li>
<li><b>Строим исправления.</b> Встроенным сравнением Word («Рецензирование → Сравнить») получаем версию «исходный Word → итог» с отмеченными правками.</li>
<li><b>Проверяем отдельной программой</b>, не той, что собирала:
<ul><li>каждая строка текста эталона ищется в итоговом Word дословно, без учёта пробелов и знаков препинания, вместе с номерами пунктов;</li>
<li>номера пунктов сравниваются с эталоном;</li>
<li>ищутся задвоенные абзацы;</li>
<li>текст внутри картинок-форм (EMF) и встроенных объектов извлекается прямо из файла, без распознавания.</li></ul>
Каждое замечание в таблице подтверждено цитатой из конкретного файла. Ложные срабатывания автоматической проверки разобраны вручную и в таблицу не попали.</li>
</ol>
<p><b>Главный принцип — ничего не додумывать.</b> Если источники расходятся между собой, это выносится в замечания, а не
исправляется молча. Поэтому, например, лишняя буква из листа замены ДП-Б1.024-06 осталась в итоге и отмечена «Исправить».</p>

<h2>Общие замечания ко всем документам</h2>
<ul>
<li><b>Страницы Word не совпадают со страницами PDF.</b> Word верстает сам, поэтому сверять нужно по пунктам, а не по номерам страниц.</li>
<li><b>В «исправлениях» видны пустые абзацы и разрывы разделов</b> на стыках вставок. Они сохраняют колонтитулы исходного Word и на текст не влияют.</li>
<li><b>Рисунки-формы и встроенные объекты</b> (бланки, образцы документов) перенесены как есть. Текст внутри них виден, но правится не как обычный текст.</li>
<li><b>Оглавление и номера страниц в нём</b> могут отличаться от PDF, пока не обновлены поля. Если Word предложит обновить поля, можно согласиться.</li>
<li><b>Отметки «Справочно»</b> — технические огрехи файлов листов замены и протоколов: пустые разделы, страницы без номера,
листы вне перечня протокола. Алгоритм их обработал, на итоговый текст они не влияют.</li>
</ul>

<h2>Как вернуть замечания</h2>
<p>Удобнее всего таблицей: <i>документ · файл (чистая / исправления) · пункт · что в итоге · что в PDF оригинала · комментарий</i>.</p>
'''

CSS = '''body{font:14px/1.45 "Segoe UI",Arial,sans-serif;margin:24px;color:#1d2939;max-width:1500px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 8px;border-bottom:1px solid #eaecf0;padding-bottom:4px}
table{border-collapse:collapse;width:100%;table-layout:fixed;min-width:1100px}th,td{border:1px solid #d0d5dd;padding:8px;vertical-align:top;text-align:left;overflow-wrap:anywhere}
th{background:#f2f4f7;font-weight:600}.small{font-size:12px;color:#667085;margin-top:4px}
.res a{font-weight:600}.badge{color:#fff;border-radius:4px;padding:1px 6px;font-size:11px;white-space:nowrap}
ul.rem{padding-left:16px;margin:8px 0 0}ul.rem li{margin-bottom:6px}ol.izm{padding-left:22px;margin:6px 0;font-size:12px}
summary{cursor:pointer;color:#175cd3}.flow{background:#f9fafb;border:1px solid #eaecf0;padding:8px 12px;border-radius:6px}'''


def main():
    if os.path.exists(PKG):
        shutil.rmtree(PKG)
    os.makedirs(PKG)
    rows = ''.join(doc_row(d, build_doc(d)) for d in DOCS)
    page = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Канон БНД — вычитка</title><style>{CSS}</style></head><body>
<h1>Восстановление Word по утверждённым PDF — пакет для вычитки</h1>
<div class="small">5 документов СМК · сборка и проверка 30.09–01.10.2026 · ссылки открывают файлы из этой же папки (архив нужно распаковать)</div>
<p class="flow"><b>Цепочка:</b> исходный Word + изменения (лист изменения и листы замены) → итог: «исправления» и «чистая».
Эталон для сверки — PDF оригинала.</p>
<table><colgroup><col style="width:17%"><col style="width:7%"><col style="width:11%"><col style="width:13%"><col style="width:10%"><col style="width:42%"></colgroup>
<tr><th>Документ</th><th>Оригинал</th><th>Исходный Word</th><th>Изменения</th><th>Итог</th><th>Проверка и замечания по документу</th></tr>
{rows}</table>
{GENERAL}
</body></html>'''
    open(os.path.join(PKG, 'index.html'), 'w', encoding='utf-8').write(page)
    zp = os.path.join(OUT, NAME + '.zip')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for dp, _, fs in os.walk(PKG):
            for f in sorted(fs):
                p = os.path.join(dp, f)
                z.write(p, os.path.relpath(p, OUT))
    print(PKG, sum(len(fs) for _, _, fs in os.walk(PKG)), 'files;', zp, round(os.path.getsize(zp) / 2**20, 1), 'MB')


if __name__ == '__main__':
    main()
