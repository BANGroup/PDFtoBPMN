#!/usr/bin/env python3
"""Block only directly observable destructive actions.

This hook intentionally does not infer agent roles, inspect workflow state, or
scan arbitrary source text. It protects secret files and destructive Git/file
commands at execution time.

Граница: ловятся прямые команды, а не намеренный обход. Не разбираются
`bash -c` / `sh -c`, подстановки `$(...)` и обратные кавычки, `eval`,
`xargs`, `find -delete`, `python -c`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hook_io import emit, run  # noqa: E402
from shell_parse import ASSIGNMENT_RE, mask_quoted, split_segments, strip_heredocs  # noqa: E402


EDIT_TOOLS = {"applypatch", "write", "strreplace", "editnotebook", "delete"}
SAFE_ENV_NAMES = {".env.example", ".env.sample", ".env.template"}
DISPLAY_COMMANDS = {"echo", "printf", "write-host", "write-output"}
WRAPPERS = {"command", "sudo"}
ENV_VALUE_FLAGS = {"-u", "--unset"}
_REDIRECT_RE = re.compile(r"(?:^|[^<>&])(?:\d*|&)>>?\|?\s*(\S+)")
# Запрещена правка конфигурации, а не чтение.
# `git config user.name` печатает значение, `git config user.name Example` — пишет,
# поэтому запись видна по мутирующему флагу либо по второму позиционному аргументу.
GIT_CONFIG_WRITE_FLAGS = {
    "--add",
    "--replace-all",
    "--unset",
    "--unset-all",
    "--remove-section",
    "--rename-section",
    "--edit",
    "-e",
}
# Эти опции забирают следующий токен, и он не является позиционным аргументом.
GIT_CONFIG_VALUE_OPTS = {"--file", "-f", "--blob", "--type", "-t", "--default"}


def _allow() -> None:
    emit({"permission": "allow"})


def _deny(reason: str) -> None:
    emit({"permission": "deny", "user_message": reason, "agent_message": reason})


def _tool_name(payload: dict[str, Any]) -> str:
    for key in ("tool_name", "toolName", "name"):
        value = payload.get(key)
        if isinstance(value, str):
            return value.lower()
    return ""


def _tool_input(payload: dict[str, Any]) -> Any:
    for key in ("tool_input", "toolInput", "arguments", "params", "input"):
        if key in payload:
            return payload[key]
    return {}


def _command(payload: dict[str, Any]) -> str:
    value = _tool_input(payload)
    if isinstance(value, dict):
        for key in ("command", "cmd"):
            command = value.get(key)
            if isinstance(command, str):
                return command
    top_level = payload.get("command")
    return top_level if isinstance(top_level, str) else ""


def _patch_text(payload: dict[str, Any]) -> str:
    value = _tool_input(payload)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("patch", "content", "text"):
            text = value.get(key)
            if isinstance(text, str):
                return text
    return ""


def _normalize_path(raw: str) -> str:
    value = raw.strip().strip("\"'").replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.lower()


def _patch_paths(text: str) -> list[str]:
    paths: list[str] = []
    for line in text.splitlines():
        for marker in (
            "*** Update File: ",
            "*** Add File: ",
            "*** Delete File: ",
        ):
            if line.startswith(marker):
                paths.append(_normalize_path(line[len(marker) :]))
                break
    return paths


def _edit_paths(payload: dict[str, Any], tool_name: str) -> list[str]:
    if tool_name == "applypatch":
        return _patch_paths(_patch_text(payload))
    value = _tool_input(payload)
    if not isinstance(value, dict):
        return []
    for key in ("path", "file_path", "filePath", "target_notebook"):
        path = value.get(key)
        if isinstance(path, str) and path.strip():
            return [_normalize_path(path)]
    return []


def _is_secret_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name in SAFE_ENV_NAMES:
        return False
    return (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith((".pem", ".key"))
        or name.startswith("credentials")
        or name.startswith("secrets.")
    )


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=os.name != "nt")
    except ValueError:
        return segment.split()


def _strip_wrappers(tokens: list[str]) -> list[str]:
    result = list(tokens)
    while result:
        while result and ASSIGNMENT_RE.match(result[0]):
            result.pop(0)
        if not result:
            break
        executable = os.path.basename(result[0]).lower()
        if executable in WRAPPERS:
            result.pop(0)
            while result and result[0].startswith("-"):
                result.pop(0)
            continue
        if executable == "env":
            result.pop(0)
            while result and (
                result[0].startswith("-") or ASSIGNMENT_RE.match(result[0])
            ):
                flag = result.pop(0)
                base = flag.split("=", 1)[0]
                if (
                    base in ENV_VALUE_FLAGS
                    and "=" not in flag
                    and result
                    and not result[0].startswith("-")
                ):
                    result.pop(0)
            continue
        break
    return result


def _flag_letters(args: list[str]) -> set[str]:
    letters: set[str] = set()
    for arg in args:
        if arg.startswith("-") and not arg.startswith("--"):
            letters.update(arg[1:].lower())
    return letters


def _destructive_file_command(tokens: list[str]) -> bool:
    if not tokens:
        return False
    executable = os.path.basename(tokens[0]).lower()
    args = [arg.lower() for arg in tokens[1:]]
    letters = _flag_letters(args)
    if executable == "rm":
        return "r" in letters and "f" in letters
    if executable in {"remove-item", "remove-item.exe"}:
        return any(arg in {"-recurse", "-r"} for arg in args)
    if executable in {"del", "del.exe", "erase", "erase.exe"}:
        return any(arg in {"/s", "/q"} for arg in args)
    if executable in {"rd", "rd.exe", "rmdir", "rmdir.exe"}:
        return "/s" in args
    return False


def _destructive_git_command(tokens: list[str]) -> bool:
    if not tokens or os.path.basename(tokens[0]).lower() not in {"git", "git.exe"}:
        return False
    args = _strip_git_globals([arg.lower() for arg in tokens[1:]])
    if not args:
        return False
    command = args[0]
    rest = args[1:]
    if command == "push":
        return any(
            arg in {"-f", "--force", "--force-with-lease", "--delete"}
            for arg in rest
        )
    if command == "reset":
        return "--hard" in rest
    if command == "clean":
        return "f" in _flag_letters(rest) or "--force" in rest
    if command == "stash":
        return bool(rest and rest[0] in {"drop", "clear"})
    if command == "commit":
        return "--amend" in rest
    if command == "rebase":
        return "-i" in rest or "--interactive" in rest
    if command == "branch":
        return "-d" in rest
    if command in {"filter-branch"}:
        return True
    if command == "reflog":
        return bool(rest and rest[0] == "expire")
    if command == "gc":
        return any(arg.startswith("--prune") for arg in rest)
    if command == "config":
        return _writing_git_config(rest)
    if command == "checkout":
        return _discarding_checkout(rest)
    if command == "restore":
        return _discarding_restore(rest)
    return False


def _discarding_checkout(rest: list[str]) -> bool:
    """Сброс рабочей копии: -- <пути>, `.`, -f/--force, <ref> -- <пути>."""
    if "--force" in rest or "-f" in rest:
        return True
    if any(
        arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:]
        for arg in rest
    ):
        return True
    return "--" in rest or "." in rest


def _discarding_restore(rest: list[str]) -> bool:
    """Сброс рабочей копии. `--staged` без `--worktree` трогает только индекс."""
    if "--worktree" in rest:
        return True
    if "--staged" in rest:
        return False
    return bool(rest)


def _strip_git_globals(args: list[str]) -> list[str]:
    """Снимает глобальные опции git до подкоманды. Аргументы уже в нижнем регистре."""
    rest = list(args)
    while rest:
        arg = rest[0]
        if (
            arg in {"--no-pager", "-p"}
            or arg.startswith("--git-dir=")
            or arg.startswith("--work-tree=")
        ):
            rest.pop(0)
            continue
        if arg in {"-c", "--git-dir", "--work-tree"}:
            rest.pop(0)
            if rest:
                rest.pop(0)
            continue
        break
    return rest


def _secret_redirect(segment: str) -> str | None:
    """Редирект записи по маске сегмента; цель — из исходной строки по тем же позициям."""
    masked = mask_quoted(segment)
    for match in _REDIRECT_RE.finditer(masked):
        path = _normalize_path(segment[match.start(1) : match.end(1)])
        if _is_secret_path(path):
            return path
    return None


def _tee_secret(tokens: list[str]) -> str | None:
    if not tokens or os.path.basename(tokens[0]).lower() != "tee":
        return None
    for arg in tokens[1:]:
        if arg.startswith("-"):
            continue
        path = _normalize_path(arg)
        if _is_secret_path(path):
            return path
    return None


def _writing_git_config(rest: list[str]) -> bool:
    positional = 0
    skip_next = False
    for arg in rest:
        if skip_next:
            skip_next = False
            continue
        if arg in GIT_CONFIG_WRITE_FLAGS:
            return True
        if arg in GIT_CONFIG_VALUE_OPTS:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        positional += 1
    return positional >= 2


def _deny_secret(path: str) -> None:
    _deny(f"Остановлено: попытка изменить файл с секретами ({path}).")


def _handle_shell(payload: dict[str, Any]) -> None:
    command = strip_heredocs(_command(payload))
    # До split_segments: `|` в `>|` для разбора сегментов — оператор пайпа.
    secret = _secret_redirect(command)
    if secret:
        _deny_secret(secret)
        return
    for segment in split_segments(command):
        raw_tokens = _tokens(segment)
        if not raw_tokens:
            continue
        tokens = _strip_wrappers(raw_tokens)
        secret = _tee_secret(tokens)
        if secret:
            _deny_secret(secret)
            return
        if not tokens:
            continue
        first = os.path.basename(tokens[0]).lower()
        if first in DISPLAY_COMMANDS:
            continue
        if _destructive_git_command(tokens):
            _deny("Остановлено: прямая разрушительная Git-команда.")
            return
        if _destructive_file_command(tokens):
            _deny("Остановлено: прямая рекурсивная команда удаления файлов.")
            return
    _allow()


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    tool_name = _tool_name(payload)
    if tool_name == "shell":
        _handle_shell(payload)
        return
    if tool_name in EDIT_TOOLS:
        secret_paths = [
            path for path in _edit_paths(payload, tool_name) if _is_secret_path(path)
        ]
        if secret_paths:
            _deny(
                "Остановлено: попытка изменить файл с секретами "
                f"({', '.join(secret_paths)})."
            )
            return
    _allow()


if __name__ == "__main__":
    run(main, "safety_guard")
