"""Сборка автономной страницы «Архитектура процессов СМК» (один HTML, всё встроено).

Запуск: venv/bin/python poc/process_arch_view/build.py [путь_выхода]
По умолчанию пишет output/process_arch_view/qms-process-architecture.html.
"""
import base64
import datetime
import html
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import data  # noqa: E402

out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output/process_arch_view/qms-process-architecture.html"


def js(name):
    t = (HERE / "vendor" / name).read_text(encoding="utf-8")
    assert "</script" not in t.lower(), name
    return t


def to_docx(src):
    """Word-версия отчёта через pandoc (gfm → docx), base64 для встраивания."""
    res = subprocess.run(["pandoc", "-f", "gfm", "-t", "docx", str(src), "-o", "-"],
                         check=True, capture_output=True)
    return base64.b64encode(res.stdout).decode("ascii")


md_blocks, docx = [], {}
for r in data.REPORTS:
    t = (ROOT / r["src"]).read_text(encoding="utf-8")
    assert "</script" not in t.lower(), r["src"]
    md_blocks.append(f'<script type="text/markdown" id="md-{r["id"]}">{t}</script>')
    docx[r["id"]] = to_docx(ROOT / r["src"])

payload = {
    "rk": data.RK, "mx": data.MX, "tg": data.TG, "links": data.LINKS,
    "fixes": data.FIXES,
    "reports": [{k: r[k] for k in ("id", "t", "d", "src")} for r in data.REPORTS],
    "docx": docx,
}
ids = {r[0] for r in data.RK} | {r[0] for r in data.MX} | {r[0] for r in data.TG}
bad = [l for l in data.LINKS if l[0] not in ids or l[1] not in ids]
assert not bad, bad

page = (HERE / "template.html").read_text(encoding="utf-8")
subs = {
    "__D3__": js("d3.min.js"),
    "__D3SANKEY__": js("d3-sankey.min.js"),
    "__MARKED__": js("marked.min.js"),
    "__MDBLOCKS__": "\n".join(md_blocks),
    "__DATA__": json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"),
    "__DATE__": html.escape(datetime.date.today().strftime("%d.%m.%Y")),
}
for key in subs:
    assert page.count(key) == 1, key
# одна проходка: вставленный код библиотек не участвует в последующих заменах
page = re.sub("|".join(map(re.escape, subs)), lambda m: subs[m.group(0)], page)

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(page, encoding="utf-8")
print(out, len(page.encode()), "bytes")
