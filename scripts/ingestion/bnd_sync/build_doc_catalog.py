#!/usr/bin/env python3
"""Build doc-catalog.json from BND (dflib.nsf).

Uses DocumentByNumberForAll view:
- Without documents=true: all entries (Document + DocumentAdds), top-level = main docs
- With documents=true: only DocumentAdds with full fields (ProcessIndex, Type, etc.)
"""

import argparse
import glob as _glob_mod
import hashlib
import json
import os
import re
import shutil
import sys
import time as _time_mod
from datetime import datetime, timedelta, timezone

import httpx

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
except ImportError:
    pass

KEEP_BASE = os.getenv("DOMINO_DB02_URL", os.getenv("DOMINO_BASE_URL_DB02", "https://domino-db02.utair.ru"))
KEEP_PORT = os.getenv("DOMINO_KEEP_PORT", "8880")
KEEP_URL = f"{KEEP_BASE}:{KEEP_PORT}"
DOMINO_WEB = KEEP_BASE

DOMINO_USER = os.getenv("DOMINO_USER_LOGIN", "")
DOMINO_PASS = os.getenv("DOMINO_PASSWORD", "")

DATA_SOURCE = os.getenv("DFLIB_DATA_SOURCE", "dflibreader")
DB_REPLICA_ID = os.getenv("DFLIB_REPLICA_ID", "C52575BB00318DA6")
NOTES_SERVER = os.getenv("DFLIB_NOTES_SERVER", "domino-db02")
VIEW_DOCS = "%28DocumentByNumberForAll%29"
VIEW_PDF_READ = "v_ImagesForDocRead"

# Каталог читает портал todo (bind mount webBI/) — контракт, см. .cursor/rules/60_todo_portal.mdc
WEBBI_DIR = os.getenv("BND_WEBBI_DIR", "/home/budnik_an/todo/webBI")
OUTPUT = os.path.join(WEBBI_DIR, "doc-catalog.json")
STATE_FILE = os.path.join(WEBBI_DIR, "doc-catalog.state.json")

# Пороговое количество дней, после которого --auto переключается на full
INCREMENTAL_MAX_AGE_DAYS = 7

EXCLUDE_PREFIXES = ["ДВС-"]
EXCLUDE_EXACT = ["2тест-2025"]

# ИОТ — Инструкции по охране труда (система СУОТ, процесс В7).
# В источнике у них пустой ProcessIndex — без override ушли бы в _unclassified.
# По правилам АК относятся к СУОТ / В7 (не отдельная массовая категория СМК).
IOT_PROCESS_CODE = "V7"
IOT_PREFIX = "ИОТ-"

# Documents whose PDFs live in external Domino databases (ImageLink in dflib).
# Format: doc_num → {unid, filename, ds} where ds is the dataSource for the proxy.
EXTERNAL_PDF = {
    "КД-РД-В6.025-03": {  # РОТО / MCM
        # Мастер-PDF лежит в came (domino-db01), но KEEP-scope came потерял привязку
        # к серверу-носителю и отдаёт 302 «query a different server» (см. переписку
        # с админом). Пока scope не починят, кнопка PDF ведёт на актуальный PDF из
        # ПОСЛЕДНЕГО изменения в dflib (db02, достижим штатно).
        # Исходный came-файл (для отката после фикса scope):
        #   unid=F18FA042BDE7629A4525879F003C8FC2, ds=came, "РОТО (iss 3 rev 4).pdf"
        # Текущий указатель — изм 4.0 (2026-03-25), вложение «РОТО-pdf» в dflib:
        "unid": "8B6FE7CAE281D82245258DB8002631EC",
        "filename": "РОТО (актуальная редакция, изм. 4).pdf",
        "ds": "dflib",
        "exclude_word_unids": {"E305FC751CDCF44445258D4500231056"},  # ImageLink: БАЗА ДАННЫХ MCM
    },
}

MANUAL_OVERRIDES = {
    "КД-РГ-053-06": "B6", "КД-РГ-093-04": "B6", "КД-СТ-122-07": "B6",
    "РГ-004-05": "B6", "СТ-155-04": "B6",
    "РД-В5.024-03": "V5",
    "СТ-097-09": "V2",
    "ДП-М1.025-06": "M1",
    "КД-РГ-215-02": "B1", "КД-РГ-225-01": "B1",
    "КД-РИ-Б1.075-06": "B1",
    "КД-РД-В5.058-04": "V5",
    "КД-СТ-171-01": "V4",
    "ДП-М1.020-06": "M1",
    "КД-РГ-204-01": "B7",
    "ДП-М1.047-01": "M1",
    "КД-РГ-126-04": "M1",
}

CYRILLIC_TO_LATIN = {"М": "M", "Б": "B", "В": "V"}

_ORDER_HEAD_RE = re.compile(r"^(приказ\b|об\s+утв)", re.I)


def is_approval_order(desc: str) -> bool:
    """True if description is the approval order itself (НЕ приложение к приказу).

    Отбрасываем: 'Приказ ...', 'Об утверждении ..., приказ ...'.
    Сохраняем:   'пр к приказу', 'приложение к приказу', 'Изменение №...', 'Лист изм...'.
    """
    s = (desc or "").strip().lower()
    if not s:
        return False
    return bool(_ORDER_HEAD_RE.match(s))


def normalize_process(code: str) -> str:
    if not code:
        return ""
    code = code.strip()
    if "." in code:
        code = code.split(".")[0]
    for cyr, lat in CYRILLIC_TO_LATIN.items():
        code = code.replace(cyr, lat)
    return code


def get_token() -> str:
    r = httpx.post(f"{KEEP_URL}/api/v1/auth",
                   json={"username": DOMINO_USER, "password": DOMINO_PASS},
                   verify=False, timeout=15)
    return r.json().get("bearer", "")


def fetch_view(token: str, view: str, count: int = 10000, documents: bool = False) -> list[dict]:
    params = f"dataSource={DATA_SOURCE}&count={count}"
    if documents:
        params += "&documents=true"
    r = httpx.get(f"{KEEP_URL}/api/v1/lists/{view}?{params}",
                  headers={"Authorization": f"Bearer {token}"},
                  verify=False, timeout=180)
    r.raise_for_status()
    return r.json()


def build_web_url(doc_unid: str) -> str:
    return f"{DOMINO_WEB}/dflib.nsf/0/{doc_unid}?OpenDocument"


def build_notes_url(doc_unid: str) -> str:
    return f"Notes://{NOTES_SERVER}/{DB_REPLICA_ID}//{doc_unid}"


# ── Incremental state ────────────────────────────────────────────────
def load_state() -> dict:
    """Читает state.json с fingerprints. Возвращает {} если файла нет."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  WARN: не удалось прочитать {STATE_FILE}: {e}")
        return {}


def save_state(state: dict) -> None:
    """Атомарная запись state через .tmp + os.replace."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def build_fingerprint(num: str, main_doc: dict, amendment_docs: list[dict]) -> str:
    """Стабильный sha256-хеш по UNID + @meta.lastmodified.

    KEEP API возвращает @meta.lastmodified для Document и DocumentAdds (проверено).
    Хеш ловит:
      - изменения main-карточки (правки полей, замена документа)
      - добавление/удаление/правки amendments
    Может НЕ поймать: изменение Word/PDF-вложений без правки родительской карточки.
    Этот зазор покрывается еженедельным full-перебилдом (--auto).
    """
    parts: list[str] = [num, main_doc.get("unid", ""), main_doc.get("_lastmodified", "")]
    for a in sorted(amendment_docs, key=lambda x: x.get("unid", "")):
        parts.append(a.get("unid", ""))
        parts.append(a.get("_lastmodified", ""))
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def should_full_rebuild(state: dict, max_age_days: int = INCREMENTAL_MAX_AGE_DAYS) -> bool:
    """Auto-режим: full если state пуст или последний full старше max_age_days."""
    if not state or not state.get("fingerprints"):
        return True
    last_full = state.get("_meta", {}).get("last_full_load_at")
    if not last_full:
        return True
    try:
        last = datetime.fromisoformat(last_full.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last) > timedelta(days=max_age_days)
    except Exception:
        return True


def main():
    ap = argparse.ArgumentParser(description="Build doc-catalog.json (БНД, dflib).")
    mode_grp = ap.add_mutually_exclusive_group()
    mode_grp.add_argument("--full", action="store_true",
                          help="Полный перебилд (пере-фетч Word/PDF для всех карточек).")
    mode_grp.add_argument("--incremental", action="store_true",
                          help="Только изменённые DocNum (fallback на full если state пуст).")
    mode_grp.add_argument("--auto", action="store_true",
                          help=f"Auto: incremental, если последний full < {INCREMENTAL_MAX_AGE_DAYS} дней (default).")
    args = ap.parse_args()

    state = load_state()
    if args.full:
        mode = "full"
    elif args.incremental:
        if not state.get("fingerprints"):
            print("WARN: state.json пуст — fallback на full")
            mode = "full"
        else:
            mode = "incremental"
    else:  # default или --auto
        mode = "full" if should_full_rebuild(state) else "incremental"
    print(f"Режим: {mode}")

    if not DOMINO_USER or not DOMINO_PASS:
        print("ERROR: Set DOMINO_USER_LOGIN and DOMINO_PASSWORD")
        sys.exit(1)

    print("Шаг 1: Авторизация...")
    token = get_token()
    if not token:
        print("ERROR: Auth failed")
        sys.exit(1)

    print("Шаг 2a: View entries (все записи)...")
    view_entries = fetch_view(token, VIEW_DOCS, count=5000)
    print(f"  {len(view_entries)} записей")

    print("Шаг 2b: documents=true (изменения с полными полями)...")
    doc_entries = fetch_view(token, VIEW_DOCS, count=5000, documents=True)
    print(f"  {len(doc_entries)} DocumentAdds")

    # Карта: DocNum -> данные основного документа
    # Приоритет: Form=Document из documents=true (точный UNID основной карточки)
    main_docs: dict[str, dict] = {}

    # Сначала из documents=true — Form=Document
    for d in doc_entries:
        if d.get("Form") != "Document":
            continue
        num = d.get("DocNum", "").strip()
        if not num:
            continue
        if any(num.startswith(p) for p in EXCLUDE_PREFIXES) or num in EXCLUDE_EXACT:
            continue
        meta = d.get("@meta", {})
        main_docs[num] = {
            "unid": meta.get("unid", ""),
            "num": num,
            "title": d.get("DocSubject", "").replace("\r\n", " ").replace("\n", " ").strip(),
            "date": d.get("DocDate", ""),
            "date_actual": d.get("DocDateActual", ""),
            "doc_date_intro": d.get("DocDate", ""),
            "doc_sm": (d.get("DocSM", "") or "").strip(),
            "_lastmodified": meta.get("lastmodified", ""),
        }

    # Fallback: view top-level для документов без Form=Document
    for d in view_entries:
        num = d.get("DocNum", "").strip()
        idx = d.get("@index", "")
        if not num or num in main_docs:
            continue
        if any(num.startswith(p) for p in EXCLUDE_PREFIXES) or num in EXCLUDE_EXACT:
            continue
        if "." not in idx:
            main_docs[num] = {
                "unid": d["@unid"],
                "num": num,
                "title": d.get("DocSubject", "").replace("\r\n", " ").replace("\n", " ").strip(),
                "date": d.get("DocDate", ""),
                "date_actual": d.get("DocDateActual", ""),
                "_lastmodified": d.get("@meta", {}).get("lastmodified", ""),
            }

    # Enrich main_docs with ProcessIndex from Form=Document entries
    for d in doc_entries:
        if d.get("Form") != "Document":
            continue
        num = d.get("DocNum", "").strip()
        if num in main_docs and not main_docs[num].get("process_from_doc"):
            pi = d.get("ProcessIndex", "")
            if pi:
                main_docs[num]["process_from_doc"] = normalize_process(pi)

    doc_count = sum(1 for d in doc_entries if d.get("Form") == "Document")
    print(f"  Form=Document: {doc_count}, Form=DocumentAdds: {len(doc_entries) - doc_count}")

    # Обогащаем из DocumentAdds (documents=true) — ProcessIndex, Type, amendments
    adds_by_num: dict[str, list[dict]] = {}
    for d in doc_entries:
        if d.get("Form") != "DocumentAdds":
            continue
        num = d.get("DocNum", "").strip()
        if not num:
            continue
        meta = d.get("@meta", {})
        adds_by_num.setdefault(num, []).append({
            "unid": meta.get("unid", ""),
            "date": d.get("DocDate", ""),
            "izm": d.get("DocNumIzm", ""),
            "process_idx": d.get("ProcessIndex", ""),
            "process_name": d.get("ProcessName", ""),
            "type": d.get("Type", ""),
            "type_idx": d.get("TypeIndex", ""),
            "doc_sm": (d.get("DocSM", "") or "").strip(),
            "executor": d.get("DocExecutorSNM", ""),
            "department": d.get("DocMainDepartmentName", ""),
            "osnov": d.get("DocOsnov", ""),
            "status": d.get("DocStatus", ""),
            "_lastmodified": meta.get("lastmodified", ""),
        })

    # Документы только из изменений (нет в main_docs)
    resolve_parent_count = 0
    for num, amendments in adds_by_num.items():
        if num in main_docs:
            continue
        if any(num.startswith(p) for p in EXCLUDE_PREFIXES) or num in EXCLUDE_EXACT:
            continue
        latest = sorted(amendments, key=lambda x: x["date"])[-1]
        doc_unid = latest["unid"]
        parent_lastmod = ""
        # Resolve parentunid — the real main document UNID
        try:
            r_meta = httpx.get(
                f"{KEEP_URL}/api/v1/document/{doc_unid}?dataSource={DATA_SOURCE}",
                headers={"Authorization": f"Bearer {token}"},
                verify=False, timeout=15,
            )
            if r_meta.status_code == 200:
                meta_obj = r_meta.json().get("@meta", {})
                parent = meta_obj.get("parentunid", "")
                if parent:
                    doc_unid = parent
                    parent_lastmod = meta_obj.get("lastmodified", "")
                    resolve_parent_count += 1
        except Exception:
            pass
        main_docs[num] = {
            "unid": doc_unid,
            "num": num,
            "title": "",
            "date": latest["date"],
            "date_actual": "",
            "_lastmodified": parent_lastmod,
        }
        # Find title from view entries
        for d in view_entries:
            if d.get("DocNum", "").strip() == num:
                title = d.get("DocSubject", "").replace("\r\n", " ").replace("\n", " ").strip()
                if title:
                    main_docs[num]["title"] = title
                    break
    if resolve_parent_count:
        print(f"  Resolved parentunid for {resolve_parent_count} docs without Form=Document")

    # Enrich with ProcessIndex and amendment count
    for num, doc in main_docs.items():
        amendments = adds_by_num.get(num, [])
        doc["changes"] = len(amendments)

        # ProcessIndex from latest amendment
        if amendments:
            latest = sorted(amendments, key=lambda x: x["date"])[-1]
            pi = latest.get("process_idx", "")
            doc["process"] = normalize_process(pi)
            doc["process_name"] = latest.get("process_name", "")
            doc["type"] = latest.get("type", "")
            doc["department"] = latest.get("department", "")
            if not doc.get("doc_sm"):
                doc["doc_sm"] = latest.get("doc_sm", "")

            # Build amendments list (sorted chronologically) with Notes links
            doc["amendments"] = [
                {"date": a["date"], "izm": a["izm"], "unid": a["unid"],
                 "notes_url": build_notes_url(a["unid"])}
                for a in sorted(amendments, key=lambda x: x["date"])
            ]
        else:
            doc["process"] = ""
            doc["process_name"] = ""
            doc["type"] = ""
            doc["department"] = ""
            doc["amendments"] = []

    print(f"  {len(main_docs)} документов (после исключений)")

    # Дедуп версий: в семействе оставляем версию, действующую на сегодня.
    # Семейство = DocNum без хвостового "-NN" (номер редакции). Если действует
    # старая версия, а новая выходит позже (DocDate в будущем) — берём старую.
    # Правило: максимальная дата среди тех, у кого DocDate <= сегодня.
    def _ver_family(n: str) -> str:
        return re.sub(r"-\d+$", "", n)

    def _ver_suffix(n: str) -> int:
        m = re.search(r"-(\d+)$", n)
        return int(m.group(1)) if m else -1

    def _parse_date(n: str):
        ds = (main_docs[n].get("date") or "").strip()[:10]
        try:
            return datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            return None

    today = datetime.now().date()
    fams: dict[str, list[str]] = {}
    for num in main_docs:
        fams.setdefault(_ver_family(num), []).append(num)

    drop_versions: set[str] = set()
    for fam, nums in fams.items():
        if len(nums) < 2:
            continue
        current = [(n, _parse_date(n)) for n in nums]
        effective = [(n, dt) for n, dt in current if dt is not None and dt <= today]
        if effective:
            keep = max(effective, key=lambda x: (x[1], _ver_suffix(x[0])))[0]
        else:
            # никто не действует на сегодня (все будущие/без даты) — оставляем старшую редакцию
            keep = max(nums, key=_ver_suffix)
        for n in nums:
            if n != keep:
                drop_versions.add(n)

    for n in drop_versions:
        main_docs.pop(n, None)
    print(f"  Дедуп версий: убрано {len(drop_versions)} неактуальных "
          f"({', '.join(sorted(drop_versions)) or '—'})")

    # Fallback: ProcessIndex from DocumentByProcess view ($15)
    print("Шаг 2c: Fallback — DocumentByProcess ($15)...")
    VIEW_BY_PROCESS = "%28DocumentByProcess%29"
    bp_entries = fetch_view(token, VIEW_BY_PROCESS, count=10000)
    bp_process: dict[str, str] = {}
    for d in bp_entries:
        num = d.get("DocNum", "").strip()
        p15 = d.get("$15", "")
        if isinstance(p15, list):
            p15 = p15[0] if p15 else ""
        if num and p15 and "не предусмотрен" not in p15.lower():
            m = re.match(r"^([А-ЯA-Z]\d+(?:\.\d+)?)", p15.strip())
            if m:
                bp_process[num] = normalize_process(m.group(1))

    enriched = 0
    for num, doc in main_docs.items():
        if not doc.get("process") and num in bp_process:
            doc["process"] = bp_process[num]
            enriched += 1
    print(f"  Обогащено из $15: {enriched}")

    # ── Incremental: определяем changed/removed на основе fingerprints ───
    new_fingerprints: dict[str, str] = {}
    for num, doc in main_docs.items():
        amends = adds_by_num.get(num, [])
        new_fingerprints[num] = build_fingerprint(num, doc, amends)

    prev_fps = state.get("fingerprints", {}) if isinstance(state, dict) else {}

    if mode == "incremental":
        changed_docs = {num for num, fp in new_fingerprints.items()
                        if prev_fps.get(num) != fp}
        removed_docs = set(prev_fps.keys()) - set(new_fingerprints.keys())
        print(f"Incremental: {len(changed_docs)} изменилось, {len(removed_docs)} удалено "
              f"(всего {len(new_fingerprints)} в источнике)")
    else:
        changed_docs = set(new_fingerprints.keys())
        removed_docs: set[str] = set()
        print(f"Full rebuild: {len(changed_docs)} документов")

    # Загружаем предыдущий каталог: нужен для merge unchanged + для sanity-check
    prev_catalog: dict = {}
    prev_by_num: dict[str, tuple[str, dict]] = {}
    if os.path.exists(OUTPUT):
        try:
            with open(OUTPUT, encoding="utf-8") as _f:
                prev_catalog = json.load(_f)
            for _proc, _items in prev_catalog.items():
                for _it in _items:
                    prev_by_num[_it["num"]] = (_proc, _it)
        except Exception as _e:
            print(f"  WARN: не удалось прочитать предыдущий {OUTPUT}: {_e}")

    if mode == "incremental" and not prev_by_num:
        print("WARN: prev catalog пуст — fallback на full")
        mode = "full"
        changed_docs = set(new_fingerprints.keys())
        removed_docs = set()

    # Шаг 2d: Word (v_ImagesForDoc) + PDF (v_ImagesForDocPrint)
    print("Шаг 2d: Word + PDF файлы (по карточкам)...")
    VIEW_WORD = "v_ImagesForDoc"

    main_unid_set: set[str] = set()
    amend_unid_set: set[str] = set()
    all_card_unids: dict[str, str] = {}
    # Итерируем по main_docs (стабильный порядок dict), но в incremental
    # фильтруем по changed_docs — сохраняет детерминированный порядок ключей
    # в итоговом catalog и идентичность full/incremental на уровне байтов.
    for num, doc in main_docs.items():
        if mode == "incremental" and num not in changed_docs:
            continue
        all_card_unids[doc["unid"]] = num
        main_unid_set.add(doc["unid"])
        for a in doc.get("amendments", []):
            if a.get("unid"):
                all_card_unids[a["unid"]] = num
                amend_unid_set.add(a["unid"])

    word_files_by_card: dict[str, list[dict]] = {}
    pdf_files_by_card: dict[str, list[dict]] = {}
    total_queries = len(all_card_unids)
    fetched = 0
    cards_with_word = 0
    cards_with_pdf = 0

    def _parse_pdf_entries(entries: list[dict]) -> list[dict]:
        pdfs = []
        for pe in entries:
            pe_unid = pe.get("@unid", "")
            if not pe_unid:
                continue
            pe_name = pe.get("$14", pe.get("$12", pe.get("FileName", "")))
            if isinstance(pe_name, list):
                pe_name = pe_name[0] if pe_name else ""
            if not pe_name:
                pe_name = "PDF"
            nl = pe_name.lower()
            if any(skip in nl for skip in ["приказ", "п-", "кп-"]):
                if "часть" not in nl and "эталон" not in nl:
                    continue
            pdfs.append({"name": pe_name, "url": pe_unid})
        return pdfs

    for card_unid, num in all_card_unids.items():
        # Word: v_ImagesForDoc?category=
        try:
            r_w = httpx.get(
                f"{KEEP_URL}/api/v1/lists/{VIEW_WORD}?dataSource={DATA_SOURCE}&category={card_unid}&count=200",
                headers={"Authorization": f"Bearer {token}"},
                verify=False, timeout=15,
            )
            if r_w.status_code == 200:
                entries = r_w.json()
                active = []
                for w in entries:
                    sign = w.get("DocSign") or w.get("$13")
                    if sign != "Действующий":
                        continue
                    desc = w.get("DocSubject") or w.get("$14", "")
                    if isinstance(desc, list):
                        desc = desc[0] if desc else ""
                    if is_approval_order(desc):
                        continue
                    active.append({"unid": w["@unid"], "desc": desc})

                by_base: dict[str, dict] = {}
                for a in active:
                    desc = a["desc"]
                    m = re.match(r"^(.+?)\s*\(версия\s+(\d+)\)\s*$", desc, re.I)
                    if m:
                        base = m.group(1).strip()
                        ver = int(m.group(2))
                    else:
                        base = desc.strip()
                        ver = 0
                    if base not in by_base or ver > by_base[base]["ver"]:
                        by_base[base] = {"unid": a["unid"], "desc": desc, "base": base, "ver": ver}

                deduped = list(by_base.values())
                if deduped:
                    word_files_by_card[card_unid] = [
                        {"unid": d["unid"], "name": d["base"], "notes_url": build_notes_url(d["unid"])}
                        for d in sorted(deduped, key=lambda x: x["base"])
                    ]
                    cards_with_word += 1
        except Exception:
            pass

        # PDF: v_ImagesForDocRead для всех (основные + изменения)
        try:
            r_p = httpx.get(
                f"{KEEP_URL}/api/v1/lists/{VIEW_PDF_READ}?dataSource={DATA_SOURCE}&key={card_unid}",
                headers={"Authorization": f"Bearer {token}"},
                verify=False, timeout=15,
            )
            if r_p.status_code == 200:
                pdfs = _parse_pdf_entries(r_p.json())
                if pdfs:
                    pdf_files_by_card[card_unid] = pdfs
                    cards_with_pdf += 1
        except Exception:
            pass

        fetched += 1
        if fetched % 200 == 0:
            print(f"  ... {fetched}/{total_queries}")

    total_word = sum(len(v) for v in word_files_by_card.values())
    total_pdf = sum(len(v) for v in pdf_files_by_card.values())
    print(f"  {fetched}/{total_queries} карточек проверено")
    print(f"  Word: {cards_with_word} карточек, {total_word} файлов")
    print(f"  PDF:  {cards_with_pdf} карточек, {total_pdf} файлов")

    print("Шаг 3: Сопоставление файлов...")
    matched = 0
    rebuilt_for_match = 0
    for num, doc in main_docs.items():
        if mode == "incremental" and num not in changed_docs:
            continue
        rebuilt_for_match += 1
        doc_unid = doc["unid"]
        doc["files"] = pdf_files_by_card.get(doc_unid, [])
        doc["web_url"] = build_web_url(doc_unid)
        doc["notes_url"] = build_notes_url(doc_unid)

        amend_pdfs: dict[str, list[dict]] = {}
        for a in doc.get("amendments", []):
            a_unid = a.get("unid", "")
            if a_unid and a_unid in pdf_files_by_card:
                amend_pdfs[a_unid] = pdf_files_by_card[a_unid]
        doc["amend_pdfs"] = amend_pdfs

        # Patch external-database PDFs (ImageLink → real file from another Domino DB)
        if num in EXTERNAL_PDF:
            ext = EXTERNAL_PDF[num]
            doc["files"] = [{
                "name": ext["filename"],
                "url": ext["unid"],
                "ds": ext["ds"],
            }]

        if doc["files"]:
            doc["url"] = doc["files"][0]["url"]
            matched += 1
        else:
            doc["url"] = doc["web_url"]

    print(f"  {matched}/{rebuilt_for_match} документов с PDF (rebuilt)")
    if EXTERNAL_PDF:
        patched = [n for n in EXTERNAL_PDF if n in main_docs]
        print(f"  Внешние PDF (ImageLink → реальный файл): {', '.join(patched)}")

    print("Шаг 5: Классификация...")
    catalog: dict[str, list] = {}
    unclassified_count = 0

    for num, doc in main_docs.items():
        if mode == "incremental" and num not in changed_docs:
            continue
        files_list = [
            {"name": f["name"], "url": f["url"], **({"ds": f["ds"]} if f.get("ds") else {})}
            for f in doc.get("files", [])
        ]
        # Word верхнего уровня: главная карточка → если пусто, берём из самого свежего изменения
        excl = EXTERNAL_PDF.get(num, {}).get("exclude_word_unids", set())
        top_word = [w for w in word_files_by_card.get(doc.get("unid", ""), [])
                    if w.get("unid") not in excl]
        if not top_word:
            for a in reversed(doc.get("amendments", [])):
                a_unid = a.get("unid", "")
                cand = [w for w in word_files_by_card.get(a_unid, []) if w.get("unid") not in excl]
                if cand:
                    top_word = cand
                    break
        # doc_sm: значение из источника (DocSM), для ИОТ — принудительно «СУОТ»
        doc_sm_val = doc.get("doc_sm", "")
        if not doc_sm_val and num.startswith(IOT_PREFIX):
            doc_sm_val = "СУОТ"
        entry = {
            "num": doc["num"],
            "title": doc["title"],
            "url": doc.get("url", ""),
            "web_url": doc.get("web_url", ""),
            "notes_url": doc.get("notes_url", ""),
            "files": files_list,
            "date": doc.get("date", ""),
            "changes": doc.get("changes", 0),
            "type": doc.get("type", ""),
            "doc_sm": doc_sm_val,
            "department": doc.get("department", ""),
            "process_name": doc.get("process_name", ""),
            "doc_sm": doc.get("doc_sm", "") or (
                "СУОТ" if num.startswith(IOT_PREFIX) else ""
            ),
            "word_files": top_word,
            "amendments": [
                {"date": a["date"], "izm": a["izm"], "notes_url": a["notes_url"],
                 "word_files": word_files_by_card.get(a.get("unid", ""), []),
                 "pdf_files": doc.get("amend_pdfs", {}).get(a.get("unid", ""), [])}
                for a in doc.get("amendments", [])
            ],
            "auto": False,
        }

        # Priority: ИОТ-префикс > manual override > ProcessIndex from amendments
        #         > ProcessIndex from Document > unclassified
        if num.startswith(IOT_PREFIX):
            proc = IOT_PROCESS_CODE  # V7 · СУОТ
            if not entry.get("process_name"):
                entry["process_name"] = "Управление охраной труда"
        elif num in MANUAL_OVERRIDES:
            proc = MANUAL_OVERRIDES[num]
        elif doc.get("process"):
            proc = doc["process"]
        elif doc.get("process_from_doc"):
            proc = doc["process_from_doc"]
        else:
            proc = "_unclassified"
            entry["auto"] = True
            unclassified_count += 1

        catalog.setdefault(proc, []).append(entry)

    # LLM-классификация удалена для детерминизма ночных перебилдов.
    # Документы без явного ProcessIndex/manual_override остаются в _unclassified
    # и присутствуют в JSON-каталоге (для корректного подсчёта в «Состав БНД»),
    # но в виджете «Документы» дашборда не отображаются (safety-net фильтрует
    # code !== '_unclassified'). Если их нужно классифицировать — добавь явный
    # MANUAL_OVERRIDES выше или попроси владельца БНД заполнить ProcessIndex в
    # Domino-источнике.

    # Incremental: добавляем unchanged-документы из предыдущего каталога.
    # Удалённые (removed_docs) пропускаем; уже пере-собранные (changed) — тоже.
    if mode == "incremental":
        new_changed_nums = set()
        for _proc, _items in catalog.items():
            for _it in _items:
                new_changed_nums.add(_it["num"])
        carried = 0
        for _num, (_proc, _item) in prev_by_num.items():
            if _num in removed_docs or _num in new_changed_nums:
                continue
            if _num not in new_fingerprints:
                # отсутствует в текущем view — на всякий случай не несём
                continue
            catalog.setdefault(_proc, []).append(_item)
            carried += 1
        print(f"  Перенесено unchanged из prev: {carried}")

    for key in catalog:
        catalog[key].sort(key=lambda x: x["num"])

    classified = sum(len(v) for v in catalog.values()) - len(catalog.get("_unclassified", []))
    print(f"  Классифицировано: {classified} (ProcessIndex + overrides)")
    print(f"  Нераспределённых: {unclassified_count}")

    total = sum(len(v) for v in catalog.values())
    with_files = sum(1 for v in catalog.values() for d in v if d.get("files"))
    print(f"\nИтого: {total} документов, {with_files} с файлами")
    for k in sorted(catalog.keys()):
        print(f"  {k:5s} {len(catalog[k]):3d} док.")

    # ── Sanity-check полноты каталога ────────────────────────────────────
    # Защита от тихой деградации Domino: если каталог внезапно «похудел» >10%,
    # старый JSON не перезаписываем, выходим с exit=2. Метрики выводим в
    # структурированном блоке SANITY REPORT, чтобы оркестратор мог их
    # распарсить и отдать в Telegram-отчёт.
    # prev_catalog уже загружен ранее (для incremental-merge); здесь только считаем.
    prev_count = sum(len(v) for v in prev_catalog.values()) if prev_catalog else 0

    new_count = sum(len(v) for v in catalog.values())
    delta = new_count - prev_count
    prev_unc = len(prev_catalog.get("_unclassified", []))
    new_unc = len(catalog.get("_unclassified", []))

    sanity_warnings: list[str] = []

    # 1) Падение количества >10% — критичная ошибка, JSON НЕ переписываем
    if prev_count > 0 and new_count < prev_count * 0.9:
        reason = (f"Каталог упал >10%: было {prev_count}, стало {new_count} "
                  f"(delta {delta:+d}), проверьте источник Domino")
        print(f"\n❌ {reason}")
        print("=== SANITY REPORT ===")
        print(f"prev_count: {prev_count}")
        print(f"new_count: {new_count}")
        print(f"delta: {delta:+d}")
        print(f"warnings: ['{reason}']")
        print("status: failed_drop_>10%")
        print("=== END SANITY ===")
        sys.exit(2)

    # 2) Пустые обязательные поля — warning, не ошибка
    empty_title = empty_type = empty_date = 0
    for _v in catalog.values():
        for _d in _v:
            if not _d.get("title"):
                empty_title += 1
            if not _d.get("type"):
                empty_type += 1
            if not _d.get("date"):
                empty_date += 1
    # Пороги:
    # title/date — должны быть у >95% документов (если нет — реально аномалия источника),
    # type — структурно берётся из amendments, у документов без amendments он пустой;
    # известный baseline ~53% → порог 70%, чтобы ловить только резкое падение качества.
    threshold_strict = max(1, new_count * 0.05) if new_count else 0
    threshold_type = max(1, new_count * 0.70) if new_count else 0
    if empty_title > threshold_strict:
        sanity_warnings.append(f"empty_title={empty_title} ({empty_title/new_count*100:.1f}%)")
    if empty_type > threshold_type:
        sanity_warnings.append(f"empty_type={empty_type} ({empty_type/new_count*100:.1f}%)")
    if empty_date > threshold_strict:
        sanity_warnings.append(f"empty_date={empty_date} ({empty_date/new_count*100:.1f}%)")

    # 3) Дубли DocNum внутри одного процесса
    for _proc, _items in catalog.items():
        _nums = [d["num"] for d in _items]
        _dupes = sorted({n for n in _nums if _nums.count(n) > 1})
        if _dupes:
            sample = ",".join(_dupes[:5])
            sanity_warnings.append(f"dup_in_{_proc}: {sample}")

    # 4) Резкий рост _unclassified
    if prev_unc > 0 and new_unc > prev_unc * 1.5:
        sanity_warnings.append(f"unclassified_growth: {prev_unc}→{new_unc}")

    # 5) Агрегированные метрики
    amendments_total = 0
    word_files_main = 0
    word_files_amend = 0
    pdf_files_main = 0
    pdf_files_amend = 0
    unique_nums: set[str] = set()
    for _v in catalog.values():
        for _d in _v:
            unique_nums.add(_d["num"])
            amendments_total += len(_d.get("amendments", []))
            word_files_main += len(_d.get("word_files", []))
            pdf_files_main += len(_d.get("files", []))
            for _a in _d.get("amendments", []):
                word_files_amend += len(_a.get("word_files", []))
                pdf_files_amend += len(_a.get("pdf_files", []))
    pdf_files_total = pdf_files_main + pdf_files_amend

    # 6) Бэкап + ротация (последние 3 .bak.*)
    if os.path.exists(OUTPUT):
        bak_path = f"{OUTPUT}.bak.{int(_time_mod.time())}"
        try:
            shutil.copy2(OUTPUT, bak_path)
            print(f"  Backup: {os.path.basename(bak_path)}")
        except Exception as _e:
            print(f"  WARN: не удалось создать backup: {_e}")
        backups = sorted(_glob_mod.glob(f"{OUTPUT}.bak.*"))
        for _old in backups[:-3]:
            try:
                os.remove(_old)
                print(f"  Удалён старый backup: {os.path.basename(_old)}")
            except Exception as _e:
                print(f"  WARN: rm {_old}: {_e}")

    # 7) Запись JSON
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT + ".tmp", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    os.replace(OUTPUT + ".tmp", OUTPUT)
    print(f"\nЗаписано: {OUTPUT}")

    # 7b) Запись state.json (fingerprints + meta)
    now_iso = datetime.now(timezone.utc).isoformat()
    new_state: dict = {
        "fingerprints": new_fingerprints,
        "_meta": {
            "generated_at": now_iso,
            "mode": mode,
            "changed_docs": (len(changed_docs) if mode == "incremental"
                             else len(new_fingerprints)),
            "removed_docs": len(removed_docs),
            "rebuilt_cards": len(all_card_unids),
            "last_full_load_at": (now_iso if mode == "full"
                                  else state.get("_meta", {}).get("last_full_load_at", "")),
        },
    }
    try:
        save_state(new_state)
        print(f"State: {os.path.basename(STATE_FILE)} (mode={mode}, "
              f"changed={new_state['_meta']['changed_docs']}, rebuilt_cards={len(all_card_unids)})")
    except Exception as _e:
        print(f"  WARN: не удалось сохранить {STATE_FILE}: {_e}")

    # 8) SANITY REPORT в stdout (парсится оркестратором)
    prev_keys = set(prev_catalog.keys())
    new_keys = set(catalog.keys())
    added_keys = sorted(new_keys - prev_keys)
    removed_keys_list = sorted(prev_keys - new_keys)
    visible_processes = sum(1 for k in catalog if k != "_unclassified")
    print()
    print("=== SANITY REPORT ===")
    print(f"mode: {mode}")
    print(f"changed_docs: {new_state['_meta']['changed_docs']}")
    print(f"removed_docs: {len(removed_docs)}")
    print(f"rebuilt_cards: {len(all_card_unids)}")
    print(f"prev_count: {prev_count}")
    print(f"new_count: {new_count}")
    print(f"delta: {delta:+d}")
    print(f"new_keys: {added_keys if added_keys else '[]'}")
    print(f"removed_keys: {removed_keys_list if removed_keys_list else '[]'}")
    print(f"warnings: {sanity_warnings if sanity_warnings else 'нет'}")
    print(f"bnd_total_unique_docnum: {len(unique_nums)}")
    print(f"bnd_visible_processes: {visible_processes}")
    print(f"bnd_unclassified: {new_unc}")
    print(f"amendments_total: {amendments_total}")
    print(f"word_files_main: {word_files_main}")
    print(f"word_files_amend: {word_files_amend}")
    print(f"pdf_files_total: {pdf_files_total}")
    print("=== END SANITY ===")


if __name__ == "__main__":
    main()
