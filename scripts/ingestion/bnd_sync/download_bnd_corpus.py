#!/usr/bin/env python3
"""Скачивание файлов БНД (+ РОТО, + РПП) в локальное зеркало для RAG.

Зачем:
    Вкладки «Документы»/РПП-навигатор хранят только ССЫЛКИ на файлы в Lotus и
    тянут содержимое через backend-прокси по клику. Это правильно для сотен
    пользователей, но не годится для офлайн-индексации RAG. Этот скрипт делает
    структурированное зеркало САМИХ файлов (PDF + Word), синхронно с ночным
    перебилдом каталогов.

Источники:
    $BND_WEBBI_DIR/doc-catalog.json        — БНД (dflib). Спец-документ РОТО
                                     (КД-РД-В6.025-03) лежит во внешней базе
                                     came (db01) — качаем по ds=came.
    $BND_WEBBI_DIR/doc-catalog.state.json  — fingerprints БНД для инкрементальной докачки.
    $BND_WEBBI_DIR/rpp-catalog.json        — РПП (отдельная база rppnew, ~535 PDF).
    (BND_WEBBI_DIR по умолчанию /home/budnik_an/todo/webBI — каталоги портала.)

Структура зеркала (навигация RAG: система → процесс/часть → документ):
    data/bnd_corpus/
    ├── manifest.json              — самодостаточный индекс для RAG-агента
    ├── .download-state.json       — служебное состояние (fingerprints, пути)
    └── documents/
        ├── <Система СМК>/<Процесс>/<DocNum>/   ← БНД
        │   ├── document.json
        │   ├── files/<name>.pdf
        │   ├── word/<name>.docx
        │   └── amendments/<YYYY-MM-DD>_изм<N>/
        ├── РПП/<Часть>/<Название_unid>/        ← РПП
        │   ├── document.json
        │   └── files/<name>.pdf
        └── _archive/<DocNum>/                  ← отменённые (перенесены, не удалены)

Инкрементальность:
    Документ перекачивается, если изменился его fingerprint, либо если
    ожидаемый файл отсутствует на диске. Иначе запись переносится из прошлого
    состояния. Документы, исчезнувшие из источников, переезжают в _archive/.
    Полная перекачка: --full.

Запуск:
    python3 scripts/ingestion/bnd_sync/download_bnd_corpus.py            # инкремент (БНД + РПП)
    python3 scripts/ingestion/bnd_sync/download_bnd_corpus.py --full     # перекачать всё
    python3 scripts/ingestion/bnd_sync/download_bnd_corpus.py --limit 5  # смок-тест
    python3 scripts/ingestion/bnd_sync/download_bnd_corpus.py --skip-rpp # только БНД

Exit-коды:
    0 — успех (возможны единичные ошибки файлов, см. CORPUS REPORT)
    1 — фатальная ошибка (нет каталога / auth провален)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

_THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _THIS_DIR.parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

# ── окружение / пути ────────────────────────────────────────────────────
DB02_URL = os.getenv("DOMINO_DB02_URL", os.getenv("DOMINO_BASE_URL_DB02", "https://domino-db02.utair.ru"))
DB01_URL = os.getenv("DOMINO_DB01_URL", os.getenv("DOMINO_BASE_URL_DB01", "https://domino-db01.utair.ru"))
KEEP_PORT = os.getenv("DOMINO_KEEP_PORT", "8880")
DOMINO_USER = os.getenv("DOMINO_USER_LOGIN", "")
DOMINO_PASS = os.getenv("DOMINO_PASSWORD", "")

DEFAULT_DS = os.getenv("DFLIB_DATA_SOURCE", "dflibreader")
# dataSource → базовый URL KEEP-сервера. Ключа "dflib" нет намеренно (так вёл себя
# прогон в todo): единственный файл с ds=dflib — мастер-PDF РОТО — идёт в external_files.
DS_SERVER_MAP = {
    DEFAULT_DS: DB02_URL,
    "rppnew": DB02_URL,
    "came":   DB01_URL,
    "employeesreader": DB01_URL,
}

WEBBI_DIR = Path(os.getenv("BND_WEBBI_DIR", "/home/budnik_an/todo/webBI"))
CATALOG_PATH = WEBBI_DIR / "doc-catalog.json"
STATE_PATH = WEBBI_DIR / "doc-catalog.state.json"
RPP_CATALOG_PATH = WEBBI_DIR / "rpp-catalog.json"
# Раскладка всегда <PROJECT_ROOT>/data/bnd_corpus: пути в manifest/state
# относительны PROJECT_ROOT и начинаются с data/bnd_corpus/.
CORPUS_ROOT = Path(os.getenv("BND_CORPUS_ROOT", str(REPO_ROOT / "data" / "bnd_corpus")))
PROJECT_ROOT = CORPUS_ROOT.parents[1]
DOCS_DIR = CORPUS_ROOT / "documents"
ARCHIVE_DIR = DOCS_DIR / "_archive"
DL_STATE_PATH = CORPUS_ROOT / ".download-state.json"
MANIFEST_PATH = CORPUS_ROOT / "manifest.json"
QUARANTINE_DIR = REPO_ROOT / "data" / "bnd_sync" / "quarantine" / datetime.now().strftime("%Y%m%d")

HTTP_TIMEOUT = 180
DOC_TIMEOUT = 90  # запрос метаданных /document: крупные карточки KEEP отдаёт ~40с
PROGRESS_EVERY = 25
RPP_SYSTEM = "РПП"

# Внешние базы, которые из cron-хоста могут быть недоступны (редирект KEEP на
# персональный сервер пользователя, как у почты/came). Их сбой не считаем
# жёсткой ошибкой — документ помечается external с причиной.
SOFT_DS = {"came", "employeesreader"}
SOFT_REASON = "внешняя база недоступна через KEEP с cron-хоста (редирект на персональный сервер)"

# Карточка существует (HTTP 200), но вложения нет ($FILES пуст). Это штатная
# ситуация для структурных записей РПП (разделы/узлы дерева без файла), поэтому
# считаем её отдельной категорией, а НЕ ошибкой загрузки.
NO_ATTACHMENT = "__no_attachment__"

# Словари расшифровок — кладём прямо в manifest, чтобы RAG-агент мог
# ориентироваться без доступа к нашему коду/дашборду.
SYSTEM_NAMES = {
    "СМК":  "Система менеджмента качества",
    "СУОТ": "Система управления охраной труда",
    "СУАБ": "Система управления авиационной безопасностью",
    "СУБП": "Система управления безопасностью полётов",
    "СЭМ":  "Система экологического менеджмента",
    "РПП":  "Руководство по производству полётов (отдельная база rppnew)",
}

# Имена процессов — авторитетные ProcessName из Domino (dflib), сверены по
# фактическим карточкам каталога. На случай новых кодов в навигации всё равно
# используется process_name самого документа как fallback.
PROCESS_NAMES = {
    "M1": "Анализ и оценка",
    "M2": "Планирование качества",
    "V1": "Управление авиационной безопасностью",
    "V2": "Управление безопасностью полётов",
    "V3": "Сервис ВС в аэропортах",
    "V4": "Менеджмент персонала",
    "V5": "Инфраструктура",
    "V6": "Поддержание лётной годности, организация ТО ВС",
    "V7": "Управление охраной труда",
    "V8": "Экологический менеджмент",
    "B1": "Организация перевозки на самолётах",
    "B5": "Взаимодействие с потребителями",
    "B6": "Планирование и бюджетирование",
    "B7": "Закупки",
    "B8": "Управление полётами",
    # IOT — устаревший бакет (до 2026-07): ИОТ теперь в V7 (СУОТ)
    "_unclassified": "Без привязки к процессу СМК (ProcessIndex пуст)",
}

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(component: str, fallback: str = "_") -> str:
    """Безопасное имя для файловой системы. Кириллицу сохраняем."""
    s = (component or "").strip().strip(".")
    s = _ILLEGAL.sub("_", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s[:180]
    return s or fallback


def _short_fp(*parts: str) -> str:
    raw = "|".join(p or "" for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kind_for(name: str) -> str:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext == "pdf":
        return "pdf"
    if ext in ("doc", "docx", "rtf", "odt"):
        return "word"
    return "other"


def _zip_member_name(info: zipfile.ZipInfo) -> str:
    """Имя элемента архива. Windows-zip без UTF-8 флага хранит имена в CP866."""
    if info.flag_bits & 0x800:  # бит UTF-8
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp866")
    except Exception:
        return info.filename


def extract_zip(content: bytes, out_dir: Path) -> list[tuple[Path, bytes]]:
    """Распаковать zip из памяти в out_dir. Возвращает [(abs_path, data)].

    Сохраняет вложенную структуру (Часть N/...), чинит кириллицу, отсеивает
    каталоги и временные файлы Word (~$...). Имена компонентов санитизируем.
    Пустой/битый архив → [] (вызывающий оставит сам .zip как обычный файл).
    """
    out: list[tuple[Path, bytes]] = []
    try:
        zf = zipfile.ZipFile(io_bytes(content))
    except Exception:
        return out
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = _zip_member_name(info)
            base = os.path.basename(name.replace("\\", "/"))
            low = base.lower()
            if (not base or base.startswith("~$")  # lock-файлы Word
                    or low in ("thumbs.db", "desktop.ini")  # системный мусор Windows
                    or low.endswith(".tmp")):
                continue
            parts = [sanitize(p) for p in name.replace("\\", "/").split("/")
                     if p not in ("", ".", "..")]
            if not parts:
                continue
            try:
                data = zf.read(info)
            except Exception:
                continue
            out.append((out_dir.joinpath(*parts), data))
    return out


def io_bytes(b: bytes):
    import io
    return io.BytesIO(b)


# ── KEEP API (мультисервер: db01/db02, токен на сервер) ─────────────────
def _auth(client: httpx.Client, keep_url: str) -> str:
    r = client.post(f"{keep_url}/api/v1/auth",
                    json={"username": DOMINO_USER, "password": DOMINO_PASS},
                    timeout=15)
    r.raise_for_status()
    return r.json().get("bearer", "")


def fetch_attachment(client: httpx.Client, token_cache: dict, ds: str,
                     unid: str) -> tuple[str, bytes] | None:
    """Возвращает (filename, content) первого вложения image-документа unid.

    Логика идентична backend-прокси: document → $FILES[0] → attachments,
    но dataSource и сервер выбираются по ds (dflib/came/rppnew).
    """
    keep_base = DS_SERVER_MAP.get(ds)
    if not keep_base:
        return None
    keep_url = f"{keep_base}:{KEEP_PORT}"

    # Сетевые таймауты/сбросы — транзиентные: ретраим, а не роняем весь прогон.
    # Любая неустранимая ошибка → None (главный цикл засчитает мягкий fail и пойдёт дальше).
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            token = token_cache.get(keep_url)
            if not token:
                token = _auth(client, keep_url)
                if not token:
                    return None
                token_cache[keep_url] = token

            headers = {"Authorization": f"Bearer {token}"}
            # Крупные карточки (напр. РД-В6.026-02 — PDF 74 МБ) KEEP отдаёт
            # медленно: метаданные /document готовятся ~40с. Жёсткие 30с давали
            # ложный ReadTimeout и роняли документ в fail. Поднимаем до DOC_TIMEOUT.
            doc_r = client.get(f"{keep_url}/api/v1/document/{unid}?dataSource={ds}",
                               headers=headers, timeout=DOC_TIMEOUT)
            if doc_r.status_code == 401:
                token_cache.pop(keep_url, None)  # токен протух — переавторизуемся
                continue
            if doc_r.status_code != 200:
                return None
            files = doc_r.json().get("$FILES", [])
            if not files:
                return NO_ATTACHMENT  # карточка без вложения — структурная запись, не ошибка
            fname = files[0]
            # KEEP двойного декодирует path-сегмент: на втором слое "+" трактуется
            # как пробел (form-decoding) → 404 для имён со знаком "+". Спасает только
            # двойное кодирование "+": quote() даёт %2B, заменяем на %252B → 200.
            enc = urllib.parse.quote(fname).replace("%2B", "%252B")
            file_r = client.get(f"{keep_url}/api/v1/attachments/{unid}/{enc}?dataSource={ds}",
                                headers=headers, timeout=HTTP_TIMEOUT)
            if file_r.status_code == 401:
                token_cache.pop(keep_url, None)
                continue
            if file_r.status_code != 200:
                return None
            return fname, file_r.content
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_exc = e
            time.sleep(2 * (attempt + 1))  # 2с, 4с — короткий backoff
            continue
        except Exception:
            return None
    if last_exc is not None:
        print(f"  WARN: {ds}/{unid[:8]} — сетевой сбой после ретраев: {type(last_exc).__name__}")
    return None


# ── нормализация источников в единый «unit» ─────────────────────────────
def _doc_dir_bnd(entry: dict, process_code: str) -> Path:
    system = sanitize(entry.get("doc_sm") or "без_системы")
    proc = sanitize(process_code or "_unclassified")
    num = sanitize(entry.get("num") or "noname")
    return DOCS_DIR / system / proc / num


def make_bnd_units(catalog: dict, fingerprints: dict) -> list[dict]:
    """БНД из doc-catalog.json → список units. РОТО (ds=came) теперь качаем."""
    units: list[dict] = []
    for proc_code, items in catalog.items():
        if not isinstance(items, list):
            continue
        for entry in items:
            if not isinstance(entry, dict) or not entry.get("num"):
                continue
            num = entry["num"]
            local: list[dict] = []
            external: list[dict] = []

            def _add(unid, kind, scope, subdir, name, ds, amd=None, ami=None):
                if not unid:
                    return
                ds = ds or DEFAULT_DS
                if ds not in DS_SERVER_MAP:
                    external.append({"name": name, "source_unid": unid, "ds": ds, "scope": scope})
                    return
                local.append({"unid": unid, "kind": kind, "scope": scope, "subdir": subdir,
                              "catalog_name": name, "ds": ds, "amend_date": amd, "amend_izm": ami})

            for f in entry.get("files", []) or []:
                fname = f.get("name", "") or ""
                # "База данных: …" — это Notes-doclink на отдельную базу (напр. РПП),
                # а не вложение. Скачать из dflib нельзя (403), да и не нужно: контент
                # этой базы качается своим источником (rppnew). Пропускаем как ссылку.
                if fname.strip().lower().startswith("база данных"):
                    continue
                _add(f.get("url"), "pdf", "current", "files", fname, f.get("ds"))
            for w in entry.get("word_files", []) or []:
                _add(w.get("unid"), "word", "current", "word", w.get("name", ""), w.get("ds"))
            for a in entry.get("amendments", []) or []:
                a_date = (a.get("date") or "").strip() or "nodate"
                izm = a.get("izm", "")
                izm_str = sanitize(str(izm), "0") if izm not in ("", None) else "0"
                sub = f"amendments/{sanitize(a_date)}_изм{izm_str}"
                for pf in a.get("pdf_files", []) or []:
                    _add(pf.get("url"), "pdf", "amendment", sub, pf.get("name", ""), pf.get("ds"), a_date, izm)
                for wf in a.get("word_files", []) or []:
                    _add(wf.get("unid"), "word", "amendment", sub, wf.get("name", ""), wf.get("ds"), a_date, izm)

            ddir = _doc_dir_bnd(entry, proc_code)
            units.append({
                "source": "bnd",
                "key": num,
                "num": num,
                "title": entry.get("title", ""),
                "type": entry.get("type", ""),
                "doc_sm": entry.get("doc_sm", ""),
                "process_code": proc_code,
                "process_name": entry.get("process_name", ""),
                "department": entry.get("department", ""),
                "date": entry.get("date", ""),
                "changes": entry.get("changes", 0),
                "web_url": entry.get("web_url", ""),
                "notes_url": entry.get("notes_url", ""),
                "dir": ddir,
                "fingerprint": fingerprints.get(num, ""),
                "local_files": local,
                "external_files": external,
            })
    return units


def make_rpp_units(rpp_catalog: dict) -> list[dict]:
    """РПП из rpp-catalog.json → список units (база rppnew, ds=rppnew).

    Структура каталога: {<Часть>: [ {unid, part, chapter, name, pdf:{unid,filename}} ]}.
    Каждый элемент = один PDF. Группируем по «части» (process-уровень).
    """
    units: list[dict] = []
    for part, items in rpp_catalog.items():
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            pdf = it.get("pdf") or {}
            unid = pdf.get("unid") or it.get("unid")
            if not unid:
                continue
            fname = pdf.get("filename") or it.get("attachment_name") or it.get("name") or ""
            title = it.get("name") or it.get("chapter") or part
            key = f"РПП::{unid}"
            ddir = DOCS_DIR / RPP_SYSTEM / sanitize(part) / (sanitize(title)[:80] + "_" + unid[:6])
            units.append({
                "source": "rpp",
                "key": key,
                "num": title,
                "title": title,
                "type": "РПП",
                "doc_sm": RPP_SYSTEM,
                "process_code": part,
                "process_name": part,
                "department": "",
                "date": "",
                "changes": 0,
                "web_url": "",
                "notes_url": "",
                "dir": ddir,
                "fingerprint": _short_fp(unid, fname, it.get("chapter", "")),
                "local_files": [{"unid": unid, "kind": "pdf", "scope": "current",
                                 "subdir": "files", "catalog_name": fname or title,
                                 "ds": "rppnew", "amend_date": None, "amend_izm": None}],
                "external_files": [],
            })
    return units


# ── состояние ───────────────────────────────────────────────────────────
def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  WARN: не прочитать {path.name}: {e}")
        return default


def save_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ── раскладка файлов на диске ───────────────────────────────────────────
def quarantine(path: Path) -> int:
    """Переносит устаревший файл/папку зеркала в карантин (удаляет только human)."""
    try:
        dst = QUARANTINE_DIR / path.relative_to(PROJECT_ROOT)
        if dst.exists():
            dst = dst.with_name(f"{dst.name}.{int(time.time())}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dst))
        return 1
    except Exception as e:
        print(f"  WARN: карантин {path}: {e}")
        return 0


def relocate_doc_dir(prev: dict, new_rel: str) -> tuple[int, int]:
    """Документ сменил систему/процесс: переносит папку и правит пути в prev, чтобы
    файлы не перекачивались. Если новая папка уже есть — старая уходит в карантин.
    Возвращает (перенесено, в карантин)."""
    old_rel = prev["dir"]
    src, dst = PROJECT_ROOT / old_rel, PROJECT_ROOT / new_rel
    if not src.exists():
        return 0, 0
    if dst.exists():
        return 0, quarantine(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    for f in prev.get("files", []):
        if f["path"].startswith(old_rel + "/"):
            f["path"] = new_rel + f["path"][len(old_rel):]
    print(f"  Перенесён: {old_rel} → {new_rel}")
    return 1, 0


def pick_target(subdir: Path, safe_name: str, unid: str, taken: set[str]) -> Path:
    """Путь файла вложения. Повторная закачка пишет поверх файла с тем же именем;
    суффикс _<unid8> перед расширением — только если имя занято другим вложением
    этого документа (taken — пути относительно PROJECT_ROOT)."""
    target = subdir / safe_name
    if str(target.relative_to(PROJECT_ROOT)) in taken:
        p = Path(safe_name)
        target = subdir / f"{p.stem}_{unid[:8]}{p.suffix}"
    return target


def find_orphans() -> list[Path]:
    """Файлы зеркала, которых нет в manifest: старые дубли, папки после переклассификации,
    *.bloated. _archive/ (отменённые документы) — не сироты."""
    manifest = load_json(MANIFEST_PATH, {})
    docs = manifest.get("documents", [])
    known = {f["path"] for d in docs for f in d.get("files", [])}
    known_dirs = {d["dir"] for d in docs}
    out = sorted(CORPUS_ROOT.glob("*.bloated"))
    for p in sorted(DOCS_DIR.rglob("*")):
        if not p.is_file() or ARCHIVE_DIR in p.parents:
            continue
        rel = p.relative_to(PROJECT_ROOT)
        if p.name == "document.json":
            if str(rel.parent) not in known_dirs:
                out.append(p)
        elif str(rel) not in known:
            out.append(p)
    return out


def quarantine_orphans(apply: bool) -> int:
    if not MANIFEST_PATH.exists():
        print("ERROR: нет manifest.json — сначала обычный прогон")
        return 1
    orphans = find_orphans()
    size = sum(p.stat().st_size for p in orphans)
    print(f"Сирот: {len(orphans)} файлов, {size / 1024 ** 3:.2f} ГБ")
    for p in orphans[:20]:
        print(f"  {p.relative_to(PROJECT_ROOT)}")
    if not apply:
        return 0
    moved = sum(quarantine(p) for p in orphans)
    for d in sorted((p for p in DOCS_DIR.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if ARCHIVE_DIR not in d.parents and d != ARCHIVE_DIR and not any(d.iterdir()):
            d.rmdir()
    print(f"В карантин: {moved} → {QUARANTINE_DIR}")
    return 0


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".part")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Скачивание файлов БНД+РОТО+РПП в data/bnd_corpus/ (RAG-зеркало).")
    ap.add_argument("--full", action="store_true", help="Перекачать все файлы, игнорируя fingerprints.")
    ap.add_argument("--limit", type=int, default=0, help="Обработать только N документов (смок-тест).")
    ap.add_argument("--dry-run", action="store_true", help="Не качать и не писать — только план.")
    ap.add_argument("--skip-rpp", action="store_true", help="Не трогать РПП (только БНД).")
    ap.add_argument("--report-orphans", action="store_true",
                    help="Показать файлы на диске, которых нет в manifest, и выйти.")
    ap.add_argument("--quarantine-orphans", action="store_true",
                    help="Перенести такие файлы в data/bnd_sync/quarantine/<дата>/ и выйти.")
    args = ap.parse_args()
    if args.report_orphans or args.quarantine_orphans:
        return quarantine_orphans(apply=args.quarantine_orphans)

    if not CATALOG_PATH.exists():
        print(f"ERROR: нет каталога {CATALOG_PATH} — сначала build_doc_catalog.py")
        return 1
    catalog = load_json(CATALOG_PATH, {})
    if not isinstance(catalog, dict) or not catalog:
        print("ERROR: каталог БНД пуст или неверного формата")
        return 1

    build_state = load_json(STATE_PATH, {})
    fingerprints = build_state.get("fingerprints", {}) if isinstance(build_state, dict) else {}

    units = make_bnd_units(catalog, fingerprints)
    bnd_count = len(units)
    rpp_count = 0
    if not args.skip_rpp and RPP_CATALOG_PATH.exists():
        rpp_catalog = load_json(RPP_CATALOG_PATH, {})
        if isinstance(rpp_catalog, dict) and rpp_catalog:
            rpp_units = make_rpp_units(rpp_catalog)
            rpp_count = len(rpp_units)
            units.extend(rpp_units)

    # Защита от раздутого state-файла: если >100 МБ (накопленные дубли),
    # не пытаемся грузить — стартуем с чистого листа.
    dl_state: dict = {}
    if DL_STATE_PATH.exists():
        _state_sz = DL_STATE_PATH.stat().st_size
        if _state_sz > 100 * 1024 * 1024:
            print(f"  WARN: state-файл раздут ({_state_sz / 1024 / 1024:.0f} МБ) — перегружаем с нуля")
            # Бэкапим на всякий случай
            try:
                import shutil as _sh
                _sh.move(str(DL_STATE_PATH), str(DL_STATE_PATH) + ".bloated")
            except Exception:
                pass
        else:
            dl_state = load_json(DL_STATE_PATH, {})
    if not isinstance(dl_state, dict):
        dl_state = {}
    docs_state: dict = dl_state.get("docs", {}) if isinstance(dl_state.get("docs"), dict) else {}

    current_keys = {u["key"] for u in units}
    if args.limit:
        units = units[:args.limit]
        print(f"--limit {args.limit}: обрабатываем {len(units)} документов")

    print(f"Источники: БНД={bnd_count}, РПП={rpp_count} · всего units={len(current_keys)} · к обработке={len(units)}")
    print(f"Режим: {'FULL' if args.full else 'incremental'}{' · DRY-RUN' if args.dry_run else ''}")

    # ── архивирование исчезнувших документов ────────────────────────────
    archived = 0
    if not args.limit and not args.dry_run:
        removed = [k for k in docs_state.keys() if k not in current_keys]
        for key in removed:
            old_dir = docs_state[key].get("dir")
            if old_dir:
                src = PROJECT_ROOT / old_dir
                if src.exists():
                    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                    dst = ARCHIVE_DIR / sanitize(key)
                    if dst.exists():
                        shutil.rmtree(dst, ignore_errors=True)
                    try:
                        shutil.move(str(src), str(dst))
                        archived += 1
                    except Exception as e:
                        print(f"  WARN: архивирование {key}: {e}")
            docs_state.pop(key, None)
        if archived:
            print(f"Архивировано исчезнувших документов: {archived}")

    if not args.dry_run and (not DOMINO_USER or not DOMINO_PASS):
        print("ERROR: задайте DOMINO_USER_LOGIN и DOMINO_PASSWORD")
        return 1

    downloaded = skipped = failed = 0
    no_attachment = 0  # карточки без вложения ($FILES пуст) — структурные записи РПП
    bytes_total = 0
    docs_with_files = 0
    external_skipped = 0
    external_unreachable = 0
    relocated = quarantined = 0
    manifest_docs: list[dict] = []

    client = None
    token_cache: dict = {}
    if not args.dry_run:
        client = httpx.Client(verify=False)

    t0 = time.monotonic()
    for idx, u in enumerate(units, 1):
        key = u["key"]
        ddir = u["dir"]
        rel_dir = str(ddir.relative_to(PROJECT_ROOT))
        external_skipped += len(u["external_files"])

        cur_fp = u["fingerprint"]
        prev = docs_state.get(key, {})
        prev_fp = prev.get("fingerprint", None)
        if not args.dry_run and prev.get("dir") and prev["dir"] != rel_dir:
            moved, quar = relocate_doc_dir(prev, rel_dir)
            relocated += moved
            quarantined += quar
        # Один source_unid может давать несколько файлов на диске (zip → разделы),
        # поэтому группируем в список, а не в один entry.
        prev_files: dict[str, list[dict]] = {}
        for f in prev.get("files", []):
            prev_files.setdefault(f["source_unid"], []).append(f)

        doc_changed = args.full or (prev_fp != cur_fp) or (not prev)

        manifest_files: list[dict] = []
        runtime_external: list[dict] = list(u["external_files"])
        doc_has_file = False
        stale_paths: list[str] = []  # прежние файлы перекачанных вложений
        doc_failed = False

        processed_unids: set[str] = set()
        for lf in u["local_files"]:
            unid = lf["unid"]
            # Дедуп: один и тот же Domino-документ (unid) может быть указан
            # несколько раз в каталоге (основной файл + поправки). Раньше это
            # приводило к экспоненциальному росту state — prev_entries для
            # одного unid extend'ились N раз за прогон. Обрабатываем первый.
            if unid in processed_unids:
                continue
            processed_unids.add(unid)
            prev_entries = prev_files.get(unid, [])
            all_on_disk = bool(prev_entries) and all(
                (PROJECT_ROOT / pe["path"]).exists() for pe in prev_entries)

            if not doc_changed and all_on_disk:
                manifest_files.extend(prev_entries)
                doc_has_file = True
                skipped += 1
                continue

            if args.dry_run:
                downloaded += 1
                doc_has_file = True
                continue

            res = fetch_attachment(client, token_cache, lf["ds"], unid)
            if res is NO_ATTACHMENT:
                # карточка есть, но файла нет — структурная запись (напр. раздел РПП).
                # Не ошибка загрузки, отдельный счётчик.
                no_attachment += 1
                stale_paths.extend(pe["path"] for pe in prev_entries)
                continue
            if res is None:
                if lf["ds"] in SOFT_DS:
                    runtime_external.append({
                        "name": lf["catalog_name"], "source_unid": unid,
                        "ds": lf["ds"], "scope": lf["scope"], "reason": SOFT_REASON,
                    })
                    external_unreachable += 1
                else:
                    failed += 1
                    doc_failed = True
                    if all_on_disk:  # сбой сети — прежняя версия остаётся в manifest
                        manifest_files.extend(prev_entries)
                        doc_has_file = True
                continue
            fname, content = res
            stale_paths.extend(pe["path"] for pe in prev_entries)
            safe_name = sanitize(fname, f"{unid[:8]}.bin")
            target_subdir = ddir / lf["subdir"]
            target_subdir.mkdir(parents=True, exist_ok=True)
            taken = {mf["path"] for mf in manifest_files} | {
                pe["path"] for other, pes in prev_files.items() if other != unid for pe in pes}
            target = pick_target(target_subdir, safe_name, unid, taken)

            # ── ZIP-вложение: распаковываем в <subdir>/<имя>_разделы/ и в манифест
            #    кладём сами разделы, а не архив (RAG индексирует файлы напрямую).
            if safe_name.lower().endswith(".zip"):
                extract_root = target_subdir / (Path(safe_name).stem + "_разделы")
                members = extract_zip(content, extract_root)
                if members:
                    if extract_root.exists():
                        shutil.rmtree(extract_root, ignore_errors=True)
                    wrote = 0
                    for mpath, mdata in members:
                        try:
                            mpath.parent.mkdir(parents=True, exist_ok=True)
                            mpath.write_bytes(mdata)
                        except Exception as e:
                            print(f"  WARN: запись раздела {mpath.name}: {e}")
                            continue
                        msize = len(mdata)
                        bytes_total += msize
                        wrote += 1
                        manifest_files.append({
                            "path": str(mpath.relative_to(PROJECT_ROOT)),
                            "filename": mpath.name,
                            "kind": _kind_for(mpath.name),
                            "scope": lf["scope"],
                            "amendment_date": lf["amend_date"],
                            "amendment_izm": lf["amend_izm"],
                            "catalog_name": lf["catalog_name"],
                            "from_archive": safe_name,
                            "ds": lf["ds"],
                            "source_unid": unid,
                            "sha256": hashlib.sha256(mdata).hexdigest(),
                            "size": msize,
                        })
                    if wrote:
                        downloaded += wrote
                        doc_has_file = True
                        continue  # сам .zip не сохраняем — только распакованное
                # битый/пустой архив → откатываемся на сохранение .zip как файла

            try:
                write_atomic(target, content)
            except Exception as e:
                print(f"  WARN: запись {target.name}: {e}")
                failed += 1
                doc_failed = True
                if all_on_disk:
                    manifest_files.extend(prev_entries)
                    doc_has_file = True
                continue
            sha = hashlib.sha256(content).hexdigest()
            size = len(content)
            bytes_total += size
            downloaded += 1
            doc_has_file = True
            manifest_files.append({
                "path": str(target.relative_to(PROJECT_ROOT)),
                "filename": safe_name,
                "kind": lf["kind"],
                "scope": lf["scope"],
                "amendment_date": lf["amend_date"],
                "amendment_izm": lf["amend_izm"],
                "catalog_name": lf["catalog_name"],
                "ds": lf["ds"],
                "source_unid": unid,
                "sha256": sha,
                "size": size,
            })

        final_paths = {mf["path"] for mf in manifest_files}
        for sp in dict.fromkeys(stale_paths):
            if sp not in final_paths and (PROJECT_ROOT / sp).is_file():
                quarantined += quarantine(PROJECT_ROOT / sp)

        if doc_has_file:
            docs_with_files += 1

        doc_meta = {
            "doc_num": u["num"],
            "source": u["source"],
            "title": u["title"],
            "type": u["type"],
            "doc_sm": u["doc_sm"],
            "process_code": u["process_code"],
            "process_name": u["process_name"],
            "department": u["department"],
            "date": u["date"],
            "changes": u["changes"],
            "web_url": u["web_url"],
            "notes_url": u["notes_url"],
            "files": manifest_files,
            "external_files": runtime_external,
            "fingerprint": cur_fp,
            "synced_at": _now_iso(),
        }
        if not args.dry_run and (doc_has_file or runtime_external):
            ddir.mkdir(parents=True, exist_ok=True)
            save_json_atomic(ddir / "document.json", doc_meta)

        if not args.dry_run:
            # При сбое оставляем прежний fingerprint — следующий прогон повторит закачку.
            state_fp = prev_fp if doc_failed else cur_fp
            docs_state[key] = {"fingerprint": state_fp, "dir": rel_dir, "files": manifest_files}

        manifest_docs.append({
            "doc_num": u["num"],
            "source": u["source"],
            "title": u["title"],
            "type": u["type"],
            "doc_sm": u["doc_sm"],
            "process_code": u["process_code"],
            "process_name": u["process_name"],
            "date": u["date"],
            "dir": rel_dir,
            "files": manifest_files,
            "external_files": runtime_external,
        })

        if idx % PROGRESS_EVERY == 0:
            print(f"  ... {idx}/{len(units)} (скачано {downloaded}, пропущено {skipped}, "
                  f"ошибок {failed}, без файла {no_attachment})")

    if client is not None:
        client.close()

    elapsed = time.monotonic() - t0

    # ── manifest + state ────────────────────────────────────────────────
    manifest_file_count = sum(len(d["files"]) for d in manifest_docs)
    manifest_bytes = sum(f.get("size", 0) or 0 for d in manifest_docs for f in d["files"])
    if not args.dry_run and not args.limit:
        navigation: dict = {}
        for d in manifest_docs:
            sysk = d.get("doc_sm") or "без_системы"
            prock = d.get("process_code") or "_unclassified"
            node = navigation.setdefault(sysk, {
                "name": SYSTEM_NAMES.get(sysk, ""),
                "documents_total": 0,
                "processes": {},
            })
            pnode = node["processes"].setdefault(prock, {
                "name": PROCESS_NAMES.get(prock, "") or d.get("process_name", ""),
                "documents": [],
            })
            pnode["documents"].append(d["doc_num"])
            node["documents_total"] += 1

        manifest = {
            "generated_at": _now_iso(),
            "source": "Domino: dflib (БНД) + came (РОТО) + rppnew (РПП), через KEEP API",
            "project_root": str(PROJECT_ROOT),
            "root": str(CORPUS_ROOT.relative_to(PROJECT_ROOT)),
            "usage": {
                "purpose": "Офлайн-зеркало нормативных документов Utair (БНД + РОТО + РПП) для построения RAG.",
                "how_to_consume": [
                    "Каждая запись documents[] — один документ; documents[].files[] — его физические файлы (PDF/Word).",
                    "Поле path относительно project_root; абсолютный путь = project_root + '/' + path.",
                    "Для индексации чанкуйте каждый файл, в метаданные чанка кладите doc_num, title, doc_sm, process_code, source, scope, date.",
                    "source: 'bnd' — Базовая нормативная документация (dflib); 'rpp' — Руководство по производству полётов (rppnew).",
                    "doc_sm — система менеджмента (для РПП = 'РПП'); process_code — процесс СМК или часть РПП.",
                    "scope='current' — действующая версия; 'amendment' — файл изменения (amendment_date/izm).",
                    "kind='pdf' — рендер; 'word' — исходник (обычно чище извлекается текст); 'other' — прочий формат.",
                    "from_archive — файл получен распаковкой zip-вложения (напр. РОТО): индексируйте сам файл, а не архив. Несколько файлов с одним source_unid = разделы одного архива.",
                    "external_files[] — файлы во внешних базах, которые НЕ скачаны; доступны по source_unid через backend-прокси.",
                    "sha256 — дедупликация и контроль изменений между прогонами.",
                ],
                "navigation_hint": "Дерево navigation: система → процесс/часть → список doc_num.",
            },
            "dictionaries": {
                "systems": SYSTEM_NAMES,
                "processes": PROCESS_NAMES,
                "sources": {"bnd": "Базовая нормативная документация (dflib)",
                            "rpp": "Руководство по производству полётов (rppnew)"},
                "file_kinds": {"pdf": "PDF (рендер для чтения)", "word": "Word (.doc/.docx, исходник)",
                               "other": "прочий формат (распакован из архива)"},
                "scopes": {"current": "действующая версия", "amendment": "файл изменения"},
            },
            "stats": {
                "documents": len(manifest_docs),
                "documents_bnd": bnd_count,
                "documents_rpp": rpp_count,
                "documents_with_files": docs_with_files,
                "files": manifest_file_count,
                "bytes": manifest_bytes,
                "external_files_skipped": external_skipped,
                "external_unreachable": external_unreachable,
                "no_attachment": no_attachment,
            },
            "navigation": navigation,
            "documents": manifest_docs,
        }
        save_json_atomic(MANIFEST_PATH, manifest)

        dl_state_new = {
            "_meta": {
                "generated_at": _now_iso(),
                "mode": "full" if args.full else "incremental",
                "downloaded": downloaded, "skipped": skipped,
                "failed": failed, "no_attachment": no_attachment, "archived": archived,
                "relocated": relocated, "quarantined": quarantined,
            },
            "docs": docs_state,
        }
        save_json_atomic(DL_STATE_PATH, dl_state_new)

    print(f"\nГотово за {elapsed:.1f}s")
    print("=== CORPUS REPORT ===")
    print(f"mode: {'full' if args.full else 'incremental'}")
    print(f"docs_total: {len(current_keys)}")
    print(f"docs_bnd: {bnd_count}")
    print(f"docs_rpp: {rpp_count}")
    print(f"docs_with_files: {docs_with_files}")
    print(f"downloaded: {downloaded}")
    print(f"skipped: {skipped}")
    print(f"failed: {failed}")
    print(f"no_attachment: {no_attachment}")
    print(f"archived: {archived}")
    print(f"relocated: {relocated}")
    print(f"quarantined: {quarantined}")
    print(f"external_skipped: {external_skipped}")
    print(f"external_unreachable: {external_unreachable}")
    print(f"manifest_files: {manifest_file_count}")
    print(f"bytes: {bytes_total}")
    print(f"mb: {bytes_total / 1024 / 1024:.1f}")
    print(f"manifest_mb: {manifest_bytes / 1024 / 1024:.1f}")
    print(f"elapsed_sec: {elapsed:.1f}")
    print("=== END CORPUS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
