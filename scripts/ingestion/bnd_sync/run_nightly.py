#!/usr/bin/env python3
"""Ежедневный перебилд каталогов БНД (doc-catalog.json) + РПП (rpp-catalog.json)
и RAG-зеркала файлов (data/bnd_corpus/).

Логика:
    1. Загружаем .env (DOMINO/MATTERMOST ключи) — subprocess наследует env.
    2. Запускаем build_doc_catalog.py, парсим его SANITY REPORT.
    3. Запускаем download_bnd_corpus.py, парсим CORPUS REPORT.
    4. Запускаем build_rpp_catalog.py, парсим SANITY REPORT.
    5. Отправляем единое сообщение личными сообщениями от бота ДВК в Mattermost
       (получатели — BND_REPORT_MM_USERS).

Каталоги пишутся в BND_WEBBI_DIR (портал todo), зеркало — в Obligations/data/bnd_corpus.

Запуск:
    Ручной:   python3 scripts/ingestion/bnd_sync/run_nightly.py
    Cron:     0 1 * * * /home/budnik_an/Obligations/scripts/ingestion/bnd_sync/cron_nightly.sh

Exit-коды:
    0 — оба скрипта успешны
    1 — хотя бы один build упал (см. блок Лог в отчёте)
    2 — другой инстанс уже работает (lock занят) — обрабатывается wrapper'ом
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # для import tg_report
from tg_report import build_report, fmt_delta, fmt_int  # noqa: E402

# ── пути ──────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).resolve().parent
REPO_ROOT      = SCRIPT_DIR.parents[2]
LOG_DIR        = REPO_ROOT / "data" / "bnd_sync" / "logs"

BUILD_DOC_SCRIPT = SCRIPT_DIR / "build_doc_catalog.py"
BUILD_RPP_SCRIPT = SCRIPT_DIR / "build_rpp_catalog.py"
CORPUS_SCRIPT    = SCRIPT_DIR / "download_bnd_corpus.py"

# Один build может занимать до 7 минут (БНД с PDF/Word per-card).
BUILD_TIMEOUT_SEC = 30 * 60
# Первая полная загрузка зеркала может тянуть ~2000 PDF + ~3000 Word.
CORPUS_TIMEOUT_SEC = 60 * 60


# ── вспомогательное ────────────────────────────────────────────────────
def _load_dotenv() -> None:
    """Подгружаем .env в os.environ, чтобы subprocess унаследовал ключи.

    build_doc_catalog.py читает env на import-time (модульный scope), поэтому
    при запуске через subprocess важно, чтобы переменные уже были в env
    родителя — что нам и нужно для cron.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env", override=False)
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_local(dt: datetime) -> str:
    """Локальное время (Europe/Moscow это +5 для нашего проекта) без TZ-суффикса."""
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def _humanize_duration(sec: float) -> str:
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}ч {m}м {s}с"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"


def _fmt_int(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return str(n)


def _fmt_delta(delta) -> str:
    try:
        d = int(delta)
    except Exception:
        return str(delta)
    sign = "+" if d >= 0 else "−"
    return f"Δ {sign}{abs(d)}"


# ── парсер SANITY REPORT ───────────────────────────────────────────────
_SANITY_START = "=== SANITY REPORT ==="
_SANITY_END   = "=== END SANITY ==="


def _parse_sanity(stdout: str, start: str = _SANITY_START, end: str = _SANITY_END) -> dict:
    """Извлекает блок метрик (по умолчанию «=== SANITY REPORT ===») в dict.

    Значения интерпретируются:
      - целые числа → int
      - delta вида +5 / -3 → int
      - списки [a, b] / [] → list (через ast.literal_eval)
      - 'нет' / 'no' → пустой list для warnings
      - остальное → str
    """
    if start not in stdout:
        return {}
    block = stdout.split(start, 1)[1].split(end, 1)[0]
    result: dict = {}
    for raw in block.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # int / signed int
        m = re.fullmatch(r"[+-]?\d+", value)
        if m:
            result[key] = int(value)
            continue
        # list/dict literal
        if (value.startswith("[") and value.endswith("]")) or (
                value.startswith("{") and value.endswith("}")):
            try:
                result[key] = ast.literal_eval(value)
                continue
            except Exception:
                pass
        if value.lower() in {"нет", "no", "none", ""}:
            result[key] = []
            continue
        result[key] = value
    return result


# ── запуск build-скрипта ───────────────────────────────────────────────
def run_build(script: Path, label: str, log_fp,
              extra_args: list[str] | None = None,
              timeout_sec: int = BUILD_TIMEOUT_SEC,
              report_start: str = _SANITY_START,
              report_end: str = _SANITY_END) -> tuple[int, str, dict]:
    """Запускает python3 <script> [extra_args...], возвращает (exit_code, log_text, sanity_metrics).

    log_text — объединённый stdout+stderr (для записи в лог-файл и хвоста при ошибке).
    report_start/report_end — маркеры блока метрик (по умолчанию SANITY REPORT;
    для загрузчика зеркала — CORPUS REPORT).
    """
    cmd = [sys.executable, str(script)] + list(extra_args or [])
    print(f"[{_now_iso()}] >>> {label}: {' '.join(str(c) for c in cmd[1:])}", flush=True)
    log_fp.write(f"[{_now_iso()}] >>> {label}: {' '.join(str(c) for c in cmd[1:])}\n")
    log_fp.flush()
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=os.environ.copy(),
        )
        elapsed = time.monotonic() - t0
        combined = (proc.stdout or "") + ("\n--- STDERR ---\n" + proc.stderr if proc.stderr else "")
        log_fp.write(combined + "\n")
        log_fp.write(f"[{_now_iso()}] <<< {label}: exit={proc.returncode} за {elapsed:.1f}s\n\n")
        log_fp.flush()
        sanity = _parse_sanity(proc.stdout or "", report_start, report_end)
        sanity["_elapsed_sec"] = elapsed
        sanity["_exit_code"] = proc.returncode
        print(f"[{_now_iso()}] <<< {label}: exit={proc.returncode} за {elapsed:.1f}s, "
              f"метрик в SANITY={len(sanity)-2}", flush=True)
        return proc.returncode, combined, sanity
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        msg = f"TIMEOUT: {script.name} > {timeout_sec}s ({elapsed:.0f}s)"
        log_fp.write(msg + "\n")
        log_fp.flush()
        return 124, msg, {"_elapsed_sec": elapsed, "_exit_code": 124, "_error": msg}
    except Exception as e:
        elapsed = time.monotonic() - t0
        msg = f"EXCEPTION при запуске {script.name}: {e!r}"
        log_fp.write(msg + "\n")
        log_fp.flush()
        return 1, msg, {"_elapsed_sec": elapsed, "_exit_code": 1, "_error": msg}


# ── формирование отчёта (единый формат tg_report) ────────────────
# Дашборды, к которым относится этот отчёт.
DASHBOARDS = [
    ("Карта процессов СМК (БНД)", "https://10.96.96.47:8050/qms/qms-process-map"),
    ("Навигатор РПП", "https://10.96.96.47:8050/qms/rpp-navigator"),
]


def _err_reason(s: dict) -> str:
    """Короткая причина сбоя билда из warnings/_error."""
    warns = s.get("warnings") or []
    if isinstance(warns, list) and warns:
        return str(warns[0])[:160]
    err = (s.get("_error") or "").splitlines()
    return err[0][:160] if err else ""


def _bnd_volumes(s: dict) -> list[str]:
    mode = s.get("mode", "")
    mode_suffix = f", {mode}" if mode else ""
    out = [
        f"БНД: {fmt_int(s.get('new_count','?'))} документов "
        f"({fmt_delta(s.get('delta', 0))}{mode_suffix}) · "
        f"{s.get('bnd_visible_processes','?')} видимых процессов · "
        f"{s.get('bnd_unclassified','?')} _unclassified",
        f"вложения БНД: {fmt_int(s.get('pdf_files_total','?'))} PDF · "
        f"{fmt_int(s.get('word_files_main','?'))} Word (осн.) + "
        f"{fmt_int(s.get('word_files_amend','?'))} Word (изм.) · "
        f"{fmt_int(s.get('amendments_total','?'))} изменений",
    ]
    return out


def _rpp_volume(s: dict) -> str:
    docs = s.get("rpp_documents", s.get("new_count", "?"))
    return (f"РПП: {fmt_int(docs)} записей ({fmt_delta(s.get('delta', 0))}) · "
            f"{fmt_int(s.get('rpp_with_pdf','?'))} с PDF")


def _corpus_volume(s: dict) -> str:
    return (f"RAG-зеркало: {fmt_int(s.get('manifest_files','?'))} файлов · "
            f"{s.get('manifest_mb','?')} МБ "
            f"(скачано +{fmt_int(s.get('downloaded','?'))} / {s.get('mb','?')} МБ, "
            f"без изменений {fmt_int(s.get('skipped','?'))})")


def _changes_summary(bnd: dict, rpp: dict, corpus: dict | None) -> str:
    """Что изменилось за прогон. «Изменений нет» — только если нет ни правок и удалений
    карточек, ни скачанных/архивированных файлов, ни сдвига числа документов."""
    if bnd.get("mode") == "full":
        return "полная пересборка БНД"

    def _n(src: dict | None, key: str) -> int:
        v = (src or {}).get(key, 0)
        return v if isinstance(v, int) else 0

    changed, removed = _n(bnd, "changed_docs"), _n(bnd, "removed_docs")
    bnd_delta, rpp_delta = _n(bnd, "delta"), _n(rpp, "delta")
    downloaded, archived = _n(corpus, "downloaded"), _n(corpus, "archived")
    parts = []
    if changed:
        parts.append(f"изменилось документов БНД: {changed}")
    if removed:
        parts.append(f"удалено документов БНД: {removed}")
    if bnd_delta and not removed:
        parts.append(f"БНД {fmt_delta(bnd_delta)}")
    if downloaded:
        parts.append(f"скачано файлов: {fmt_int(downloaded)}")
    if archived:
        parts.append(f"в архив: {archived}")
    if rpp_delta:
        parts.append(f"РПП {fmt_delta(rpp_delta)}")
    return ", ".join(parts) if parts else "изменений нет"


def format_report(bnd: dict, rpp: dict,
                    started_at: datetime, finished_at: datetime,
                    log_path: Path, corpus: dict | None = None) -> str:
    """Готовит финальный текст отчёта в едином формате (tg_report)."""
    bnd_ok = bnd.get("_exit_code") == 0
    rpp_ok = rpp.get("_exit_code") == 0
    corpus_code = corpus.get("_exit_code") if corpus is not None else None
    corpus_ok = corpus_code == 0

    volumes: list[str] = []
    errors: list[str] = []
    notes: list[str] = []

    # ── БНД ──
    if bnd_ok:
        volumes.extend(_bnd_volumes(bnd))
    else:
        r = _err_reason(bnd)
        errors.append(f"БНД: сборка упала (exit={bnd.get('_exit_code','?')})"
                      + (f" — {r}" if r else ""))

    # ── РПП ──
    if rpp_ok:
        volumes.append(_rpp_volume(rpp))
    elif rpp.get("_exit_code") is None:
        notes.append("РПП: сборка пропущена")
    else:
        r = _err_reason(rpp)
        errors.append(f"РПП: сборка упала (exit={rpp.get('_exit_code','?')})"
                      + (f" — {r}" if r else ""))

    # ── RAG-зеркало файлов (data/bnd_corpus/) ──
    if corpus is not None:
        if corpus_ok:
            volumes.append(_corpus_volume(corpus))
            fa = corpus.get("failed", 0)
            if isinstance(fa, int) and fa:
                errors.append(f"RAG-зеркало: {fa} файлов не скачалось")
            q = corpus.get("quarantined", 0)
            if isinstance(q, int) and q:
                notes.append(f"{q} устаревших файлов/папок перенесено в карантин "
                             f"(data/bnd_sync/quarantine/)")
            arch = corpus.get("archived", 0)
            if isinstance(arch, int) and arch:
                notes.append(f"{arch} документ(ов) перемещено в архив "
                             f"(исчезли из каталога, файлы сохранены)")
            na = corpus.get("no_attachment", 0)
            if isinstance(na, int) and na:
                notes.append(f"{na} записей РПП без вложения — узлы структуры "
                             f"руководства, файла нет по построению (норма)")
            unreach = corpus.get("external_unreachable", 0)
            if isinstance(unreach, int) and unreach:
                notes.append(f"{unreach} внешних файлов недоступны с cron-хоста (РОТО/came)")
        elif corpus_code is None:
            notes.append("RAG-зеркало: пропущено (БНД не собрался)")
        else:
            r = _err_reason(corpus)
            errors.append(f"RAG-зеркало: загрузка упала (exit={corpus_code})"
                          + (f" — {r}" if r else ""))

    # ── sanity warnings → примечания ──
    for tag, src in (("БНД", bnd), ("РПП", rpp)):
        w = src.get("warnings")
        if isinstance(w, list) and w:
            for item in w[:4]:
                notes.append(f"sanity {tag}: {item}")

    # ── статус и общий результат ──
    has_sanity_warn = any(n.startswith("sanity") for n in notes)
    if errors:
        status = "error" if (not bnd_ok and not rpp_ok) else "warn"
    elif has_sanity_warn:
        status = "warn"
    else:
        status = "ok"

    if status == "ok":
        result = ("каталоги БНД и РПП собраны, RAG-зеркало синхронизировано, "
                  + _changes_summary(bnd, rpp, corpus))
    elif status == "warn":
        result = "собрано с замечаниями — см. блок «Ошибки»/«Примечания»"
    else:
        result = "сборка не удалась — подробности в логе"

    if errors:
        errors.append(f"лог: {log_path}")

    return build_report(
        title="Перебилд каталогов БНД/РПП",
        status=status,
        started=started_at,
        finished=finished_at,
        dashboards=DASHBOARDS,
        result=result,
        volumes=volumes,
        errors=errors,
        notes=notes,
    )


# ── Mattermost: личные сообщения от бота ДВК (профиль Hermes mm, team.utair.io) ──
def _report_recipients() -> list[str]:
    raw = os.getenv("BND_REPORT_MM_USERS", "")
    return [u.strip().lstrip("@") for u in raw.split(",") if u.strip()]


def _log(log_fp, msg: str) -> None:
    if log_fp is not None:
        log_fp.write(f"[{_now_iso()}] {msg}\n")
        log_fp.flush()


def _mm_call(client, method: str, path: str, log_fp, **kw):
    """Запрос к API Mattermost с 3 попытками на сетевые сбои, 429 и 5xx. None — не удалось."""
    import httpx

    for attempt in range(3):
        try:
            r = client.request(method, path, **kw)
            if r.status_code < 300:
                return r.json()
            _log(log_fp, f"⚠️ MM {method} {path} HTTP={r.status_code} body={r.text[:300]}")
            if r.status_code < 500 and r.status_code != 429:
                return None
        except httpx.HTTPError as e:
            _log(log_fp, f"⚠️ MM {method} {path} попытка {attempt + 1}: {e!r}")
        if attempt < 2:
            time.sleep(2 * (attempt + 1))
    return None


def send_report(text: str, log_fp=None) -> tuple[bool, str]:
    """Шлёт text личным сообщением каждому из BND_REPORT_MM_USERS от бота (MATTERMOST_TOKEN).
    Возвращает (доставлено хотя бы одному, описание)."""
    import httpx

    base = os.getenv("MATTERMOST_URL", "").rstrip("/")
    token = os.getenv("MATTERMOST_TOKEN", "").strip()
    users = _report_recipients()
    if not base or not token or not users:
        _log(log_fp, "📭 MM: пропущено — MATTERMOST_URL/MATTERMOST_TOKEN/BND_REPORT_MM_USERS не настроены")
        return False, "not_configured"
    sent = 0
    with httpx.Client(base_url=f"{base}/api/v4", timeout=20,
                      headers={"Authorization": f"Bearer {token}"}) as client:
        bot = _mm_call(client, "GET", "/users/me", log_fp)
        found = _mm_call(client, "POST", "/users/usernames", log_fp, json=users) if bot else None
        if not bot or found is None:
            return False, "mm_unavailable"
        missing = set(users) - {u["username"] for u in found}
        if missing:
            _log(log_fp, f"⚠️ MM: не найдены пользователи {sorted(missing)}")
        for u in found:
            channel = _mm_call(client, "POST", "/channels/direct", log_fp, json=[bot["id"], u["id"]])
            if channel and _mm_call(client, "POST", "/posts", log_fp,
                                    json={"channel_id": channel["id"], "message": text}):
                sent += 1
    _log(log_fp, f"📨 MM: отправлено {sent}/{len(users)} ({len(text)} chars)")
    return sent > 0, f"sent {sent}/{len(users)}"


# ── main ───────────────────────────────────────────────────────────────
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Ночная сборка каталогов БНД/РПП и RAG-зеркала.")
    ap.add_argument("--no-notify", action="store_true",
                    help="Не отправлять отчёт (текст всё равно пишется в лог).")
    args = ap.parse_args()
    _load_dotenv()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_fp = log_path.open("w", encoding="utf-8")

    started_at = datetime.now()
    print(f"[{_now_iso()}] === catalog_daily_rebuild · старт ===", flush=True)
    log_fp.write(f"[{_now_iso()}] === catalog_daily_rebuild · старт ===\n")
    log_fp.write(f"  python:   {sys.executable}\n")
    log_fp.write(f"  cwd:      {REPO_ROOT}\n")
    log_fp.write(f"  webBI:    {os.getenv('BND_WEBBI_DIR', '/home/budnik_an/todo/webBI')}\n")
    log_fp.write(f"  MM users: {', '.join(_report_recipients()) or '-'}\n\n")
    log_fp.flush()

    # БНД поддерживает --auto: incremental, если последний full < 7 дней;
    # иначе full. Cron получает быстрый прогон ~30 с в обычные дни,
    # full safety раз в неделю.
    bnd_code, _, bnd_metrics = run_build(
        BUILD_DOC_SCRIPT, "BUILD doc-catalog (БНД)", log_fp,
        extra_args=["--auto"],
    )

    # RAG-зеркало файлов: качаем только если БНД-каталог собрался успешно
    # (иначе doc-catalog.json мог не обновиться — нет смысла синхронизировать).
    corpus_metrics: dict | None = None
    if bnd_code == 0:
        _, _, corpus_metrics = run_build(
            CORPUS_SCRIPT, "DOWNLOAD bnd-corpus (RAG-зеркало)", log_fp,
            timeout_sec=CORPUS_TIMEOUT_SEC,
            report_start="=== CORPUS REPORT ===",
            report_end="=== END CORPUS ===",
        )
    else:
        log_fp.write(f"[{_now_iso()}] RAG-зеркало пропущено: БНД exit={bnd_code}\n")
        log_fp.flush()

    rpp_code, _, rpp_metrics = run_build(BUILD_RPP_SCRIPT, "BUILD rpp-catalog (РПП)", log_fp)

    finished_at = datetime.now()
    total_dur = _humanize_duration((finished_at - started_at).total_seconds())
    print(f"[{_now_iso()}] === финиш: bnd={bnd_code} rpp={rpp_code} за {total_dur} ===", flush=True)
    log_fp.write(f"\n[{_now_iso()}] === финиш: bnd={bnd_code} rpp={rpp_code} за {total_dur} ===\n")

    # Сборка отчёта
    try:
        tg_text = format_report(bnd_metrics, rpp_metrics, started_at, finished_at,
                                  log_path, corpus=corpus_metrics)
        log_fp.write(f"\n--- REPORT TEXT ({len(tg_text)} chars) ---\n{tg_text}\n--- END REPORT ---\n")
        log_fp.flush()
        if not args.no_notify:
            ok, info = send_report(tg_text, log_fp=log_fp)
            if not ok:
                print(f"[{_now_iso()}] ⚠️ Отчёт не отправлен: {info}", flush=True)
    except Exception as e:
        log_fp.write(f"[{_now_iso()}] ⚠️ Ошибка формирования отчёта: {e!r}\n")
        log_fp.flush()
        print(f"[{_now_iso()}] ⚠️ Ошибка формирования отчёта: {e!r}", flush=True)

    log_fp.close()
    return 0 if (bnd_code == 0 and rpp_code == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
