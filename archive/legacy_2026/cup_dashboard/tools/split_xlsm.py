"""
split_xlsm.py — Раскол монолитного xlsm на части ≤ 30 МБ.

Стратегия (TASK-008, D22):
  1. ZIP-хирургия: починка pivotCacheDefinition refs + удаление calcChain + удаление листов данных
  2. pandas export: два листа данных → CSV (utf-8-sig, sep=;) + Parquet (snappy)
  3. VBA inventory из vbaProject.bin (бинарный поиск строк)
  4. split_report.json — статистика

Использование:
  python -m cup_dashboard.tools.split_xlsm \\
      --input "input2/ЦУП/Отчетность/Отчет за ЯНВАРЬ 2026.xlsm" \\
      --output output/january_split/
"""

import argparse
import json
import re
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

# Имена листов в xlsm (русские)
SHEET_DATA = "Данные"
SHEET_DATA_15 = "Данные (15МИН)"

# xl/worksheets/*.xml записи, которые нужно удалить (листы данных)
DATA_SHEET_PARTS = {"xl/worksheets/sheet9.xml", "xl/worksheets/sheet10.xml"}

# pivotCacheDefinition файлы, чьи refs нужно исправить (3, 4, 5)
PIVOT_REF_MAP = {
    "xl/pivotCache/pivotCacheDefinition3.xml": "'Данные'!$A$1:$BJ$138279",
    "xl/pivotCache/pivotCacheDefinition4.xml": "'Данные'!$A$1:$BF$138279",
    "xl/pivotCache/pivotCacheDefinition5.xml": "'Данные'!$A$1:$BH$138279",
}

# Паттерн для замены раздутого ref (любые границы с 1048576)
BLOAT_REF_RE = re.compile(
    r"(ref=\"[^\"]*!)(\$?[A-Z]+\$?1:\$?[A-Z]+\$?1048576)(\"|'[^']*'!)"
)

MAX_FILE_BYTES = 30 * 1024 * 1024  # 30 МБ


def _fix_pivot_ref(content: bytes, new_ref: str) -> bytes:
    """Заменяет раздутый ref='..!A1:XX1048576' на фактический диапазон."""
    text = content.decode("utf-8")
    # Ищем атрибут ref= в теге worksheetSource
    text = re.sub(
        r'(<worksheetSource[^>]*\bref=")[^"]*(")',
        lambda m: m.group(1) + new_ref + m.group(2),
        text,
    )
    return text.encode("utf-8")


def _remove_calc_chain(zin: zipfile.ZipFile, members: list[str]) -> tuple[list[str], dict[str, bytes]]:
    """Убирает calcChain.xml и его Override из Content_Types."""
    keep = [m for m in members if m != "xl/calcChain.xml"]
    patches: dict[str, bytes] = {}

    if "[Content_Types].xml" in members:
        ct = zin.read("[Content_Types].xml").decode("utf-8")
        ct = re.sub(r'\s*<Override[^>]*calcChain[^>]*/>', "", ct)
        patches["[Content_Types].xml"] = ct.encode("utf-8")

    return keep, patches


def _remove_data_sheets(
    zin: zipfile.ZipFile, members: list[str], patches: dict[str, bytes]
) -> tuple[list[str], dict[str, bytes]]:
    """Удаляет sheet9.xml, sheet10.xml и их регистрации."""
    keep = [m for m in members if m not in DATA_SHEET_PARTS]

    # workbook.xml — убрать <sheet> теги для sheet9 и sheet10
    if "xl/workbook.xml" in members:
        wb = patches.get("xl/workbook.xml", zin.read("xl/workbook.xml")).decode("utf-8")
        for r_id in ("rId9", "rId10"):
            wb = re.sub(rf'\s*<sheet\b[^>]*\br:id="{r_id}"[^/]*/>', "", wb)
        patches["xl/workbook.xml"] = wb.encode("utf-8")

    # workbook.xml.rels — убрать Relationship для sheet9 и sheet10
    rels_path = "xl/_rels/workbook.xml.rels"
    if rels_path in members:
        rels = patches.get(rels_path, zin.read(rels_path)).decode("utf-8")
        rels = re.sub(r'\s*<Relationship\b[^>]*worksheets/sheet(9|10)\.xml[^/]*/>', "", rels)
        patches[rels_path] = rels.encode("utf-8")

    # Content_Types — убрать Override для sheet9 / sheet10
    if "[Content_Types].xml" in members:
        ct = patches.get("[Content_Types].xml", zin.read("[Content_Types].xml")).decode("utf-8")
        for sn in ("sheet9", "sheet10"):
            ct = re.sub(rf'\s*<Override[^>]*worksheets/{sn}\.xml[^/]*/>', "", ct)
        patches["[Content_Types].xml"] = ct.encode("utf-8")

    return keep, patches


def build_report_xlsm(input_path: Path, output_path: Path) -> int:
    """ZIP-хирургия: оптимизация + удаление листов данных → Отчёт.xlsm."""
    with zipfile.ZipFile(input_path, "r") as zin:
        members = zin.namelist()

        keep, patches = _remove_calc_chain(zin, members)
        keep, patches = _remove_data_sheets(zin, keep, patches)

        # Исправляем pivotCacheDefinition refs
        for pcd_path, new_ref in PIVOT_REF_MAP.items():
            if pcd_path in keep:
                orig = patches.get(pcd_path, zin.read(pcd_path))
                patches[pcd_path] = _fix_pivot_ref(orig, new_ref)

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            for name in keep:
                data = patches.get(name, zin.read(name))
                zout.writestr(name, data)

    return output_path.stat().st_size


def _sanitize_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Конвертирует object-колонки со смешанными типами в str, чтобы pyarrow не падал."""
    import pyarrow as pa

    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            try:
                pa.array(df[col], from_pandas=True)
            except (pa.lib.ArrowInvalid, pa.lib.ArrowTypeError):
                df[col] = df[col].astype(str).where(df[col].notna(), None)
    return df


def export_sheet_to_files(
    input_path: Path, sheet_name: str, base_name: str, out_dir: Path
) -> dict:
    """Читает лист через pandas → CSV (utf-8-sig) + Parquet. Если CSV > 30МБ — split."""
    print(f"  Читаю лист '{sheet_name}' (pandas/openpyxl, может занять 5-10 мин)...")
    df = pd.read_excel(str(input_path), sheet_name=sheet_name, engine="openpyxl")
    rows = len(df)
    print(f"  Прочитано {rows:,} строк × {len(df.columns)} столбцов")

    result = {"rows": rows, "files": []}

    # Parquet (с sanitize для смешанных типов)
    pq_path = out_dir / f"{base_name}.parquet"
    _sanitize_for_parquet(df).to_parquet(str(pq_path), compression="snappy", index=False)
    result["files"].append({"name": pq_path.name, "size_bytes": pq_path.stat().st_size, "kind": "data_parquet"})

    # CSV
    csv_path = out_dir / f"{base_name}.csv"
    df.to_csv(str(csv_path), sep=";", encoding="utf-8-sig", index=False)
    csv_size = csv_path.stat().st_size

    if csv_size > MAX_FILE_BYTES:
        csv_path.unlink()
        n = len(df)
        half = n // 2
        for i, (slc, sfx) in enumerate([(slice(0, half), "part1"), (slice(half, None), "part2")]):
            p = out_dir / f"{base_name}_{sfx}.csv"
            df.iloc[slc].to_csv(str(p), sep=";", encoding="utf-8-sig", index=False)
            result["files"].append({"name": p.name, "size_bytes": p.stat().st_size, "kind": "data_csv_part"})
    else:
        result["files"].append({"name": csv_path.name, "size_bytes": csv_size, "kind": "data_csv"})

    return result


def extract_vba_inventory(input_path: Path, out_dir: Path) -> int:
    """Извлекает vbaProject.bin и строит текстовый инвентарь."""
    vba_size = 0
    with zipfile.ZipFile(input_path, "r") as z:
        if "xl/vbaProject.bin" not in z.namelist():
            (out_dir / "VBA_INVENTORY.md").write_text(
                "# VBA Inventory\n\n⚠ vbaProject.bin не найден в архиве.\n", encoding="utf-8"
            )
            return 0
        raw = z.read("xl/vbaProject.bin")
        vba_size = len(raw)

    # Извлекаем ASCII-строки ≥ 4 символов (VBA хранит имена в UTF-16LE и ASCII)
    ascii_strs: list[str] = re.findall(rb"[ -~]{4,}", raw)
    utf16_strs: list[str] = []
    try:
        text16 = raw.decode("utf-16-le", errors="ignore")
        utf16_strs = re.findall(r"[\x20-\x7e\u0400-\u04ff]{4,}", text16)
    except UnicodeDecodeError as e:
        import sys as _sys
        print(f"WARN: UTF-16LE decode failed for vbaProject.bin: {e}", file=_sys.stderr)

    all_strs = [s.decode("ascii", errors="ignore") if isinstance(s, bytes) else s
                for s in ascii_strs] + utf16_strs

    subs = sorted({s for s in all_strs if re.search(r"\b(Sub|Function)\b", s)})
    sheet_refs = sorted({s for s in all_strs if re.search(r'Sheets\s*\(', s)})
    range_refs = sorted({s for s in all_strs if re.search(r'\bFor\b.*\bRow\b|\bRange\b', s)})

    lines = [
        "# VBA Inventory",
        "",
        f"**Размер vbaProject.bin:** {vba_size:,} байт",
        "",
        "> Бинарный VBA не реинженерим — это инвентарь по A8 (VBA → doc_only).",
        "",
        "## Sub / Function (найдено по сигнатурам)",
        "",
    ]
    if subs:
        lines += [f"- `{s[:120]}`" for s in subs[:50]]
    else:
        lines += ["_Сигнатуры Sub/Function не найдены (сжатый байткод)._"]

    lines += ["", "## Sheet References (`Sheets(...)`)", ""]
    if sheet_refs:
        lines += [f"- `{s[:120]}`" for s in sheet_refs[:30]]
    else:
        lines += ["_Не найдено._"]

    lines += ["", "## Range/Row References (потенциальная бизнес-логика)", ""]
    if range_refs:
        lines += [f"- `{s[:120]}`" for s in range_refs[:30]]
        lines += [
            "",
            "⚠ Найдены ссылки на Range/Row. Возможна бизнес-логика в VBA.",
            "**Требуется ревизия (см. R2 в TASK-008.md)** до удаления листов данных из xlsm.",
        ]
    else:
        lines += ["_Не найдено._"]

    lines += [
        "",
        "## Статус",
        "",
        "- **doc_only** (A8): VBA задокументирован, не реинженерится.",
        "- Pivot-refresh без листов данных не работает (offline cache — плановое поведение).",
    ]

    (out_dir / "VBA_INVENTORY.md").write_text("\n".join(lines), encoding="utf-8")
    return vba_size


def main():
    parser = argparse.ArgumentParser(description="Раскол xlsm-монолита на части ≤ 30 МБ")
    parser.add_argument("--input", required=True, help="Путь к исходному .xlsm файлу")
    parser.add_argument("--output", default="output/january_split/", help="Выходная директория")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Файл не найден: {input_path}")

    input_size = input_path.stat().st_size
    print(f"Входной файл: {input_path.name} ({input_size / 1024 / 1024:.1f} МБ)")

    report = {
        "input_file": input_path.name,
        "input_size_bytes": input_size,
        "output_files": [],
        "all_under_30mb": True,
        "rows_data": None,
        "rows_data_15min": None,
        "vba_size_bytes": 0,
        "vba_status": "doc_only",
    }

    # Шаг 1: Отчётный xlsm (ZIP-хирургия)
    report_xlsm = out_dir / "Январь_2026_Отчёт.xlsm"
    print("\n[1/4] Собираю Январь_2026_Отчёт.xlsm (ZIP-хирургия)...")
    xlsm_size = build_report_xlsm(input_path, report_xlsm)
    print(f"  → {report_xlsm.name}: {xlsm_size / 1024 / 1024:.1f} МБ")
    report["output_files"].append({"name": report_xlsm.name, "size_bytes": xlsm_size, "kind": "report"})

    # Шаг 2: Экспорт листа "Данные"
    print(f"\n[2/4] Экспортирую лист '{SHEET_DATA}'...")
    res_data = export_sheet_to_files(input_path, SHEET_DATA, "Январь_2026_Данные", out_dir)
    report["rows_data"] = res_data["rows"]
    report["output_files"].extend(res_data["files"])

    # Шаг 3: Экспорт листа "Данные (15МИН)"
    print(f"\n[3/4] Экспортирую лист '{SHEET_DATA_15}'...")
    res_15 = export_sheet_to_files(input_path, SHEET_DATA_15, "Январь_2026_Данные_15МИН", out_dir)
    report["rows_data_15min"] = res_15["rows"]
    report["output_files"].extend(res_15["files"])

    # Шаг 4: VBA инвентарь
    print("\n[4/4] Извлекаю VBA инвентарь...")
    vba_size = extract_vba_inventory(input_path, out_dir)
    report["vba_size_bytes"] = vba_size
    inv_path = out_dir / "VBA_INVENTORY.md"
    report["output_files"].append({"name": inv_path.name, "size_bytes": inv_path.stat().st_size, "kind": "vba_inventory"})
    print(f"  → VBA_INVENTORY.md ({vba_size:,} байт vbaProject.bin)")

    # Проверка ≤ 30 МБ
    for f in report["output_files"]:
        if f.get("size_bytes", 0) > MAX_FILE_BYTES:
            report["all_under_30mb"] = False
            print(f"  ⚠ {f['name']} = {f['size_bytes'] / 1024 / 1024:.1f} МБ > 30 МБ")

    # Сохранить отчёт
    report_path = out_dir / "split_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(f"\nГотово. Отчёт: {report_path}")
    print(f"all_under_30mb: {report['all_under_30mb']}")
    for f in report["output_files"]:
        mb = f.get("size_bytes", 0) / 1024 / 1024
        rows_info = f"  {f.get('rows', ''):>7}" if "rows" in f else ""
        print(f"  {f['name']:<45} {mb:6.1f} МБ{rows_info}")


if __name__ == "__main__":
    main()
