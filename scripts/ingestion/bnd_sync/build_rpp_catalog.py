#!/usr/bin/env python3
"""Build rpp-catalog.json from РПП database (rppnew).

Fetches all documents from the AllRPP view and organizes them
by Part → Chapter with PDF attachment info for download via proxy.
"""

import glob as _glob_mod
import json
import os
import shutil
import sys
import time as _time_mod

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

DOMINO_USER = os.getenv("DOMINO_USER_LOGIN", "")
DOMINO_PASS = os.getenv("DOMINO_PASSWORD", "")

DATA_SOURCE = "rppnew"
VIEW = "AllRPP"

# Каталог читает портал todo (bind mount webBI/) — контракт, см. .cursor/rules/60_todo_portal.mdc
OUTPUT = os.path.join(os.getenv("BND_WEBBI_DIR", "/home/budnik_an/todo/webBI"), "rpp-catalog.json")

PART_ORDER = [
    "Титульный лист",
    "Уведомления",
    "Часть A",
    "Часть B",
    "Часть C",
    "Часть D",
    "MEL",
    "Эксплуатационная документация",
]


def auth():
    r = httpx.post(
        f"{KEEP_URL}/api/v1/auth",
        json={"username": DOMINO_USER, "password": DOMINO_PASS},
        verify=False, timeout=15,
    )
    r.raise_for_status()
    token = r.json().get("bearer", "")
    if not token:
        print("ERROR: auth failed", file=sys.stderr)
        sys.exit(1)
    return {"Authorization": f"Bearer {token}"}


def main():
    print(f"Authenticating to {KEEP_URL} ...")
    headers = auth()

    print(f"Fetching {VIEW} from {DATA_SOURCE} ...")
    r = httpx.get(
        f"{KEEP_URL}/api/v1/lists/{VIEW}?dataSource={DATA_SOURCE}&documents=true&richTextAs=none",
        headers=headers, verify=False, timeout=60,
    )
    r.raise_for_status()
    raw = r.json()
    print(f"  Total entries: {len(raw)}")

    catalog = {}
    no_files = 0

    for entry in raw:
        meta = entry.get("@meta", {})
        unid = meta.get("unid", "")
        if not unid:
            continue

        form = entry.get("Form", "")
        part = entry.get("Part", "").strip()
        chapter = entry.get("Сhapter", "").strip()  # Cyrillic С
        name = entry.get("Name", "").strip()
        sort_num = entry.get("SortNum", 0)
        sort_num_1 = entry.get("SortNum_1", 0)
        files = entry.get("$FILES", [])
        ac_type = entry.get("ACType", "").strip() if form == "DocB" else ""
        status = entry.get("Status", "").strip()
        attachment_name = entry.get("sAttachmentName", "").strip()

        if not part:
            continue

        pdf_file = None
        if files:
            pdf_file = {
                "unid": unid,
                "filename": files[0],
                "size": None,
            }
        else:
            no_files += 1

        doc = {
            "unid": unid,
            "form": form,
            "part": part,
            "chapter": chapter,
            "name": name,
            "ac_type": ac_type,
            "sort_num": sort_num,
            "sort_num_1": sort_num_1,
            "attachment_name": attachment_name,
            "pdf": pdf_file,
        }

        catalog.setdefault(part, []).append(doc)

    # Sort parts by predefined order
    ordered = {}
    for p in PART_ORDER:
        if p in catalog:
            docs = catalog[p]
            docs.sort(key=lambda d: (
                d["ac_type"] or "",
                d["sort_num"] if isinstance(d["sort_num"], (int, float)) else 0,
                d["sort_num_1"] if isinstance(d["sort_num_1"], (int, float)) else 0,
                d["chapter"],
            ))
            ordered[p] = docs

    # Any parts not in PART_ORDER
    for p in catalog:
        if p not in ordered:
            ordered[p] = catalog[p]

    total_docs = sum(len(v) for v in ordered.values())
    total_with_pdf = sum(1 for docs in ordered.values() for d in docs if d["pdf"])

    print(f"\nResult:")
    print(f"  Parts: {len(ordered)}")
    print(f"  Documents: {total_docs}")
    print(f"  With PDF: {total_with_pdf}")
    print(f"  Without PDF: {no_files}")
    print()

    for part, docs in ordered.items():
        ac_types = set(d["ac_type"] for d in docs if d["ac_type"])
        ac_str = f" (ВС: {', '.join(sorted(ac_types))})" if ac_types else ""
        with_pdf = sum(1 for d in docs if d["pdf"])
        print(f"  {part}: {len(docs)} docs, {with_pdf} with PDF{ac_str}")

    # ── Sanity-check полноты каталога РПП ────────────────────────────────
    # Защита от тихой деградации Domino: при падении >10% не переписываем JSON
    # и выходим с exit=2. Метрики выводим блоком SANITY REPORT — оркестратор
    # парсит и кладёт в Telegram-отчёт.
    prev_catalog: dict = {}
    prev_count = 0
    if os.path.exists(OUTPUT):
        try:
            with open(OUTPUT, encoding="utf-8") as _f:
                prev_catalog = json.load(_f)
            prev_count = sum(len(v) for v in prev_catalog.values())
        except Exception as _e:
            print(f"  WARN: не удалось прочитать предыдущий {OUTPUT}: {_e}")

    new_count = total_docs
    delta = new_count - prev_count

    if prev_count > 0 and new_count < prev_count * 0.9:
        reason = (f"Каталог РПП упал >10%: было {prev_count}, стало {new_count} "
                  f"(delta {delta:+d}), проверьте источник Domino rppnew")
        print(f"\n❌ {reason}")
        print("=== SANITY REPORT ===")
        print(f"prev_count: {prev_count}")
        print(f"new_count: {new_count}")
        print(f"delta: {delta:+d}")
        print(f"warnings: ['{reason}']")
        print("status: failed_drop_>10%")
        print("=== END SANITY ===")
        sys.exit(2)

    # Бэкап + ротация (3 последних .bak.*)
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

    with open(OUTPUT + ".tmp", "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=1)
    os.replace(OUTPUT + ".tmp", OUTPUT)
    print(f"\nSaved to {OUTPUT}")

    # SANITY REPORT (парсится оркестратором)
    prev_parts = len(prev_catalog) if prev_catalog else 0
    print()
    print("=== SANITY REPORT ===")
    print(f"prev_count: {prev_count}")
    print(f"new_count: {new_count}")
    print(f"delta: {delta:+d}")
    print(f"warnings: нет")
    print(f"rpp_parts: {len(ordered)}")
    print(f"rpp_prev_parts: {prev_parts}")
    print(f"rpp_documents: {total_docs}")
    print(f"rpp_with_pdf: {total_with_pdf}")
    print(f"rpp_without_pdf: {no_files}")
    print("=== END SANITY ===")


if __name__ == "__main__":
    main()
