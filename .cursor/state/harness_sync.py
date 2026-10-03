"""Синхронизация обвязки Cursor → Claude Code и Codex (TASK-020, D-042; D-046).

Источник истины — `.cursor/`: тексты ролей `.cursor/agents/*.md`, навыки `.cursor/skills/*`,
команды `.cursor/commands/*.md`, модели ролей `.cursor/state/harness_models.json`.
Из них собираются:
- Claude Code: `.claude/agents/*.md` и симлинки `.claude/skills/*`;
- Codex: `.codex/agents/*.toml`, копии навыков `.agents/skills/*`, навыки
  `.agents/skills/source-command-<имя>` из команд (в Codex нет команд), `.codex/hooks.json`;
поле `model` в карточках Cursor берётся из той же таблицы.

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
CUR_COMMANDS = ROOT / ".cursor/commands"
CX_AGENTS = ROOT / ".codex/agents"
CX_SKILLS = ROOT / ".agents/skills"
CX_HOOKS = ROOT / ".codex/hooks.json"
MODELS = ROOT / ".cursor/state/harness_models.json"


def codex_card(role: str, description: str, body: str) -> str:
    """Карточка субагента Codex: модель не задаётся — работает модель сессии Codex."""
    note = (f"<!-- Сгенерировано из .cursor/agents/{role}.md (harness_sync.py). Не править вручную. -->\n"
            "> Среда: Codex, модель — модель текущей сессии Codex. В журнал пиши `--model <id этой модели>`. "
            "Модели в тексте ниже относятся к Cursor.\n")
    text = note + body
    if "'''" in text or '"' in description:
        raise SystemExit(f"{role}: ''' в тексте или \" в описании — карточку не собрать в TOML")
    return f'name = "{role}"\ndescription = "{description}"\ndeveloper_instructions = \'\'\'\n{text}\'\'\'\n'


def command_skill(path: Path) -> str:
    """Команда Cursor → навык Codex (тот же текст, обёртка навыка)."""
    head, body = split_card(path.read_text(encoding="utf-8"))
    name = f"source-command-{path.stem}"
    return (f'---\nname: "{name}"\ndescription: "{field(head, "description")}"\n---\n\n# {name}\n\n'
            f"Use this skill when the user asks to run the migrated source command `{path.stem}`.\n\n"
            "## Command Template\n\n" + body.lstrip("\n"))


def codex_hooks() -> str:
    """Тот же сторож, что у Cursor и Claude Code; путь абсолютный — Codex запускает хуки из cwd сессии."""
    cmd = f'python3 "{ROOT / ".cursor/hooks/safety_guard.py"}" --codex'
    hooks = {"hooks": {"PreToolUse": [{"matcher": "Bash|apply_patch|Edit|Write",
                                       "hooks": [{"type": "command", "command": cmd, "timeout": 30}]}]}}
    return json.dumps(hooks, ensure_ascii=False, indent=2) + "\n"


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
        files[CX_AGENTS / f"{role}.toml"] = codex_card(role, field(head, "description"), body)
    links = {CL_SKILLS / d.name: os.path.relpath(d, CL_SKILLS) for d in CUR_SKILLS.iterdir() if d.is_dir()}
    # Codex: навыки — копии (не симлинки), команды — навыки source-command-<имя>
    for d in (d for d in CUR_SKILLS.iterdir() if d.is_dir()):
        for f in (f for f in d.rglob("*") if f.is_file()):
            files[CX_SKILLS / f.relative_to(CUR_SKILLS)] = f.read_text(encoding="utf-8")
    for c in sorted(CUR_COMMANDS.glob("*.md")):
        files[CX_SKILLS / f"source-command-{c.stem}" / "SKILL.md"] = command_skill(c)
    files[CX_HOOKS] = codex_hooks()
    return files, links


def extras(files: dict[Path, str]) -> list[Path]:
    """Сгенерированные места, где лежит то, чего нет в источнике."""
    out = [p for p in CL_AGENTS.glob("*.md") if p not in files] if CL_AGENTS.exists() else []
    out += [p for p in CX_AGENTS.glob("*.toml") if p not in files] if CX_AGENTS.exists() else []
    out += [p for p in CX_SKILLS.rglob("*") if p.is_file() and p not in files] if CX_SKILLS.exists() else []
    return out


def main(check: bool) -> int:
    files, links = plan()
    drift = [p for p, t in files.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
    drift += [p for p, t in links.items() if not p.is_symlink() or os.readlink(p) != t]
    extra = extras(files)
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
        print(f"лишний файл (нет в источнике .cursor/), удалите вручную: {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
