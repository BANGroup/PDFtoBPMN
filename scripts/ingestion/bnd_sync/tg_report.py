#!/usr/bin/env python3
"""Единый формат уведомлений в Telegram для всех cron-отчётов проекта.

Цель — единообразие: какой бы скрипт ни слал отчёт (перебилд каталогов БНД/РПП,
ежедневная загрузка КК, обновление SFV, снапшот UTE-Stock), сообщение имеет одну
и ту же структуру:

    [AI research portal] <иконка> <Заголовок>
    🔗 <Название дашборда>: <url>            (0..N строк)

    🕒 Старт ЧЧ:ММ · Финиш ЧЧ:ММ · <длит> (UTC+5)

    Результат: <вердикт одной-двумя строками>

    Объёмы:
      • <строка свода по объёмам>
      • …

    Ошибки: нет
      (либо)
    Ошибки (N):
      • <строка ошибки>

    Примечания:                              (необязательный блок)
      • <строка, штатные отклонения, не ошибки>

Модуль не имеет внешних зависимостей и доступен как host-крону
(`python3 tools/<script>.py`), так и backend-контейнеру (`./tools:/app/tools:ro`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Проект работает в часовом поясе UTC+5 (Asia/Yekaterinburg). Фиксируем явно,
# чтобы отчёт не зависел от tz хоста/контейнера (в Docker обычно UTC).
TZ = timezone(timedelta(hours=5))
TZ_LABEL = "UTC+5"
APP_TAG = "[AI research portal]"
TG_LIMIT = 4090  # запас под лимит Telegram 4096

_ICONS = {"ok": "✅", "warn": "⚠️", "error": "❌", "skip": "⏭️"}


def status_icon(status: str) -> str:
    return _ICONS.get(status, "❔")


def hhmm(dt: datetime) -> str:
    """Время как ЧЧ:ММ в UTC+5. Naive datetime трактуется как локальное хоста."""
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(TZ).strftime("%H:%M")


def humanize_duration(sec: float) -> str:
    sec = int(round(sec or 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}ч {m}м {s}с"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return str(n)


def fmt_delta(delta) -> str:
    """Знаковая дельта: 'Δ +5' / 'Δ −3' / 'Δ 0'."""
    try:
        d = int(delta)
    except Exception:
        return str(delta)
    if d == 0:
        return "Δ 0"
    sign = "+" if d > 0 else "−"
    return f"Δ {sign}{abs(d)}"


def _as_lines(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(v) for v in value if str(v).strip()]


def build_report(
    *,
    title: str,
    status: str,
    started: datetime,
    finished: datetime,
    dashboards: list[tuple[str, str]] | None = None,
    result: str | list[str] | None = None,
    volumes: str | list[str] | None = None,
    errors: list[str] | None = None,
    notes: str | list[str] | None = None,
    max_len: int = TG_LIMIT,
) -> str:
    """Собирает единый текст отчёта.

    Аргументы:
        title      — заголовок (без тега портала и иконки, их добавим сами).
        status     — 'ok' | 'warn' | 'error' | 'skip' (определяет иконку).
        started/finished — datetime начала/конца (для строки времени и длительности).
        dashboards — список (название, url) ссылок на связанные дашборды.
        result     — общий результат, строка или список строк.
        volumes    — свод по объёмам (список строк, выводится буллитами).
        errors     — список ошибок; пусто/None → «Ошибки: нет».
        notes      — примечания (штатные отклонения, не ошибки).
    """
    icon = status_icon(status)
    lines: list[str] = [f"{APP_TAG} {icon} {title}"]

    for name, url in (dashboards or []):
        lines.append(f"🔗 {name}: {url}")

    lines.append("")
    dur = humanize_duration((finished - started).total_seconds())
    lines.append(f"🕒 Старт {hhmm(started)} · Финиш {hhmm(finished)} · {dur} ({TZ_LABEL})")

    result_lines = _as_lines(result)
    if result_lines:
        lines.append("")
        if len(result_lines) == 1:
            lines.append(f"Результат: {result_lines[0]}")
        else:
            lines.append("Результат:")
            lines.extend(f"  {r}" for r in result_lines)

    volume_lines = _as_lines(volumes)
    if volume_lines:
        lines.append("")
        lines.append("Объёмы:")
        lines.extend(f"  • {v}" for v in volume_lines)

    lines.append("")
    err_lines = _as_lines(errors)
    if err_lines:
        lines.append(f"Ошибки ({len(err_lines)}):")
        lines.extend(f"  • {e}" for e in err_lines)
    else:
        lines.append("Ошибки: нет")

    note_lines = _as_lines(notes)
    if note_lines:
        lines.append("")
        lines.append("Примечания:")
        lines.extend(f"  • {n}" for n in note_lines)

    text = "\n".join(lines).rstrip()
    return text[:max_len]
