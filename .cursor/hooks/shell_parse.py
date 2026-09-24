"""Разбор shell-команды на сегменты для сторожей.

Общий для `orchestrator_write_guard` и `clickhouse_drop_guard`: оба режут команду
по операторам, чтобы проверять каждый сегмент отдельно, и оба ошибались одинаково.

Резать по сырой строке нельзя: оператор внутри кавычек — это текст, а не
структура. Запись в Agent KG с разбором инцидента отклонялась потому, что её
текст содержал `;`, после чего кусок предложения читался как отдельная команда
и совпадал с запретом (замер 2026-08-17: попытка зафиксировать закрытие находок
была заблокирована сразу двумя сторожами за цитаты `git -c` и `--drop-table`).

Маскировать кавычки перед разбором тоже нельзя: маска прячет и настоящую
команду, если она стоит рядом с безобидной. Поэтому состояние кавычек
отслеживается посимвольно, а содержимое остаётся на месте.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import Iterator, List

OPERATORS = "&|;\n"
SHELL_WRAPPERS = {"bash", "dash", "sh", "zsh"}
COMMAND_PREFIXES = {"command", "nohup", "sudo"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

QUOTED_RE = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def mask_quoted(command: str) -> str:
    """Заменяет содержимое кавычек на X той же длины.

    Аргумент — это данные, а не структура команды: сторож, ищущий свой признак
    по сырой строке, срабатывает на цитату признака внутри аргумента. Замер
    2026-08-20: запись контекста в Agent KG отклонялась как «закрытие workflow»
    ровно потому, что текст флага закрытия был процитирован в `--content`, и
    сообщение об отказе не отличалось от сообщения настоящего гейта.
    """
    return QUOTED_RE.sub(
        lambda m: m.group(0)[0] + "X" * (len(m.group(0)) - 2) + m.group(0)[0],
        command,
    )


def strip_heredocs(command: str) -> str:
    """Убирает тело heredoc, оставляя саму команду.

    Тело heredoc — данные, как и содержимое кавычек, но кавычками оно не
    обёрнуто, поэтому `mask_quoted` его не скрывает. Замер 2026-08-21: создание
    временного скрипта проверок в `/tmp` было отклонено сторожем Superset за
    упоминание пути ядра внутри тела heredoc, то есть за текст сценария, а не
    за обращение к ядру.
    """
    lines = command.splitlines()
    kept: List[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        masked = mask_quoted(line)
        delimiters = [
            line[match.start(2) : match.end(2)]
            for match in HEREDOC_RE.finditer(masked)
        ]
        index += 1
        for delimiter in delimiters:
            while index < len(lines) and lines[index].strip() != delimiter:
                index += 1
            if index < len(lines):
                index += 1
    return "\n".join(kept)


def split_segments(command: str) -> List[str]:
    """Режет команду по `&&`, `||`, `;`, `|` и переводам строк вне кавычек."""
    segments: List[str] = []
    buffer: List[str] = []
    quote: str | None = None
    index = 0
    length = len(command)

    while index < length:
        char = command[index]
        if quote:
            if char == "\\" and quote == '"' and index + 1 < length:
                buffer.append(char)
                buffer.append(command[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            buffer.append(char)
        elif char in "'\"":
            quote = char
            buffer.append(char)
        elif char in OPERATORS:
            segments.append("".join(buffer))
            buffer = []
            while index < length and command[index] in OPERATORS:
                index += 1
            continue
        else:
            buffer.append(char)
        index += 1

    segments.append("".join(buffer))
    return [segment for segment in segments if segment.strip()]


def _command_substitutions(command: str) -> List[str]:
    """Извлекает простые `$()` и backtick-подстановки для отдельной проверки."""
    substitutions: List[str] = []
    index = 0
    while index < len(command):
        if command.startswith("$(", index):
            start = index + 2
            depth = 1
            cursor = start
            while cursor < len(command) and depth:
                if command.startswith("$(", cursor):
                    depth += 1
                    cursor += 2
                    continue
                if command[cursor] == ")":
                    depth -= 1
                    if depth == 0:
                        substitutions.append(command[start:cursor])
                        index = cursor + 1
                        break
                cursor += 1
            else:
                index += 2
            continue
        if command[index] == "`":
            end = command.find("`", index + 1)
            if end != -1:
                substitutions.append(command[index + 1:end])
                index = end + 1
                continue
        index += 1
    return substitutions


def _normalize_invocation(tokens: List[str]) -> List[str]:
    """Убирает env/служебные префиксы, оставляя исполняемую команду и аргументы."""
    remaining = list(tokens)
    while remaining:
        while remaining and ASSIGNMENT_RE.match(remaining[0]):
            remaining.pop(0)
        if not remaining:
            return []
        head = os.path.basename(remaining[0])
        if head == "env":
            remaining.pop(0)
            while remaining and (remaining[0].startswith("-") or ASSIGNMENT_RE.match(remaining[0])):
                remaining.pop(0)
            continue
        if head in COMMAND_PREFIXES:
            remaining.pop(0)
            while remaining and remaining[0].startswith("-"):
                remaining.pop(0)
            continue
        return remaining
    return []


def iter_invocations(command: str) -> Iterator[List[str]]:
    """Возвращает реальные shell-вызовы, игнорируя литералы в аргументах.

    Вложенные команды из `sh -c`, `$()` и backticks проверяются рекурсивно.
    """
    for segment in split_segments(command):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            tokens = []
        invocation = _normalize_invocation(tokens)
        if invocation:
            yield invocation
            head = os.path.basename(invocation[0])
            if head in SHELL_WRAPPERS and "-c" in invocation[1:]:
                command_index = invocation.index("-c") + 1
                if command_index < len(invocation):
                    yield from iter_invocations(invocation[command_index])
        for nested in _command_substitutions(segment):
            yield from iter_invocations(nested)
