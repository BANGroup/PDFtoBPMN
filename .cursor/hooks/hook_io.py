"""Вывод вердикта сторожа, устойчивый к кодировке stdout.

Причина (замер 2026-08-20, W_hook_contour_repair_20260820, замер в проекте cube): причина отказа
печатается по-русски через `json.dumps(ensure_ascii=False)`, и если текстовый
слой stdout не в UTF-8, `sys.stdout.write` падает `UnicodeEncodeError`. Все
сторожа из `hooks.json` объявлены `failClosed`, поэтому упавший deny становится
отказом без текста: агент видит запрет, но не причину, а в журнале следа нет —
код до логирования не доходит. Замер: при `PYTHONIOENCODING=ascii` каждый из
семи preToolUse-сторожей (замер в проекте cube) давал `exit=1` и пустой stdout на пути отказа.

Байты пишем сами: `sys.stdout.buffer` не зависит от кодировки текстового слоя.
Если буфера нет (stdout подменён), отступаем на `ensure_ascii=True` — вердикт
дороже читаемости кириллицы.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable, Dict


def emit(verdict: Dict[str, Any]) -> None:
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        sys.stdout.write(json.dumps(verdict, ensure_ascii=True))
        return
    buffer.write(json.dumps(verdict, ensure_ascii=False).encode("utf-8"))
    buffer.flush()


def run(main: Callable[[], None], guard: str) -> None:
    """Запускает сторожа так, чтобы отказ никогда не был безмолвным.

    При `failClosed` упавший сторож означает запрет без причины: Cursor пишет
    «hook returned no output», агент видит стену и не знает, чем она вызвана.
    Замер 2026-08-20: governance-агент (замер в проекте cube) получил ровно такой отказ на `git status`
    и на обычном поиске. Исключение не подавляется — оно становится текстом
    вердикта, поэтому запрет остаётся запретом, но перестаёт быть немым.
    """
    try:
        main()
    except BaseException:  # noqa: BLE001 — вердикт важнее типа ошибки
        emit({
            "permission": "deny",
            "user_message": (
                f"Сторож {guard} упал, поэтому вызов запрещён (fail-closed). "
                "Это дефект контура, а не решение по вашей команде: "
                f"{traceback.format_exc(limit=4)}"
            ),
            "agent_message": (
                f"Сторож {guard} упал: запрет вызван дефектом контура, а не политикой. "
                "Остановись и доложи человеку, не подбирай варианты команды. "
                f"{traceback.format_exc(limit=4)}"
            ),
        })
