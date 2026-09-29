"""Синхронизация обвязки Cursor → Claude Code (TASK-020, D-042).

Источник истины — `.cursor/`: тексты ролей `.cursor/agents/*.md`, навыки `.cursor/skills/*`,
модели ролей `.cursor/state/harness_models.json`. Из них собираются `.claude/agents/*.md`
и симлинки `.claude/skills/*`; поле `model` в карточках Cursor берётся из той же таблицы.

    python3 .cursor/state/harness_sync.py           # записать
    python3 .cursor/state/harness_sync.py --check   # выход 1, если что-то разошлось
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CUR_AGENTS = ROOT / ".cursor/agents"
CUR_SKILLS = ROOT / ".cursor/skills"
CL_AGENTS = ROOT / ".claude/agents"
CL_SKILLS = ROOT / ".claude/skills"
MODELS = ROOT / ".cursor/state/harness_models.json"


def split_card(text: str) -> tuple[list[str], str]:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise SystemExit("карточка без заголовка --- … ---")
    return m.group(1).split("\n"), text[m.end():]


def field(head: list[str], key: str) -> str:
    return next(l.split(":", 1)[1].strip() for l in head if l.startswith(key + ":"))


def plan() -> tuple[dict[Path, str], dict[Path, str]]:
    """Ожидаемое содержимое файлов и ожидаемые цели симлинков."""
    roles = json.loads(MODELS.read_text(encoding="utf-8"))["roles"]
    files: dict[Path, str] = {}
    cards = {p.stem for p in CUR_AGENTS.glob("*.md")}
    if cards != set(roles):
        raise SystemExit(f"роли в таблице {sorted(roles)} ≠ карточки {sorted(cards)}")
    for role, m in roles.items():
        src = CUR_AGENTS / f"{role}.md"
        head, body = split_card(src.read_text(encoding="utf-8"))
        head = [f"model: {m['cursor']}" if l.startswith("model:") else l for l in head]
        files[src] = "---\n" + "\n".join(head) + "\n---\n" + body
        if m["claude"] is None:  # роль исполняет основной чат Claude Code
            continue
        cl_head = [f"name: {role}", f"description: {field(head, 'description')}", f"model: {m['claude']}"]
        if m.get("claude_tools"):
            cl_head.append(f"tools: {m['claude_tools']}")
        note = (f"<!-- Сгенерировано из .cursor/agents/{role}.md (harness_sync.py). Не править вручную. -->\n"
                f"> Среда: Claude Code, модель `{m['claude_id']}`. В журнал пиши `--model {m['claude_id']}`. "
                "Модели в тексте ниже относятся к Cursor.\n")
        files[CL_AGENTS / f"{role}.md"] = "---\n" + "\n".join(cl_head) + "\n---\n" + note + body
    links = {CL_SKILLS / d.name: os.path.relpath(d, CL_SKILLS) for d in CUR_SKILLS.iterdir() if d.is_dir()}
    return files, links


def main(check: bool) -> int:
    files, links = plan()
    drift = [p for p, t in files.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
    drift += [p for p, t in links.items() if not p.is_symlink() or os.readlink(p) != t]
    extra = [p for p in CL_AGENTS.glob("*.md") if p not in files] if CL_AGENTS.exists() else []
    if check:
        for p in drift + extra:
            print(f"расхождение: {p.relative_to(ROOT)}")
        return 1 if drift or extra else 0
    for p in drift:
        if p in links:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.is_symlink():
                p.unlink()
            p.symlink_to(links[p])
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(files[p], encoding="utf-8")
        print(f"записано: {p.relative_to(ROOT)}")
    for p in extra:
        print(f"лишняя карточка (роль не в таблице), удалите вручную: {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
