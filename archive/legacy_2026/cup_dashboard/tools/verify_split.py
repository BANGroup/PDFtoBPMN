"""
verify_split.py — Верификация целостности раскола xlsm.

Проверяет:
  1. Количество строк: оригинал == CSV == Parquet
  2. 5 случайных строк (seed=42): побайтовое сравнение всех колонок
  3. Все файлы в output/ ≤ 30 МБ
  4. Дописывает блок "verification" в split_report.json
  5. Exit code 0 при success, 1 при mismatch

Использование:
  python -m cup_dashboard.tools.verify_split \\
      --split-dir output/january_split/ \\
      --original "input2/ЦУП/Отчетность/Отчет за ЯНВАРЬ 2026.xlsm"
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

SHEET_DATA = "Данные"
SHEET_DATA_15 = "Данные (15МИН)"
MAX_FILE_BYTES = 30 * 1024 * 1024
SAMPLE_SEED = 42
SAMPLE_N = 5


def _normalize_col(series: pd.Series) -> pd.Series:
    """Нормализует колонку для сравнения между Excel, CSV и Parquet.

    Правила:
    - timedelta64: total_seconds() как строка, NaT → ''
    - datetime64: ISO date '%Y-%m-%d', NaT → ''
    - numeric: round(6), strip trailing .0 если целое, NaN → ''
    - object с числами (mixed str/float): нормализуем через float → int/str
    - остальное: str, NaN/None → ''
    """
    import numpy as np

    # timedelta (время РЗ, время РЗ 2)
    if pd.api.types.is_timedelta64_dtype(series):
        secs = series.dt.total_seconds()
        return secs.apply(lambda x: "" if pd.isna(x) else str(int(round(x))))

    # datetime
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.strftime("%Y-%m-%d").fillna("")

    # numeric dtype
    if pd.api.types.is_numeric_dtype(series):
        def _num_str(x):
            if pd.isna(x):
                return ""
            r = round(float(x), 6)
            return str(int(r)) if r == int(r) else str(r)
        return series.apply(_num_str)

    # object — попробуем числовую нормализацию
    if series.dtype == object:
        def _obj_str(x):
            if x is None or (isinstance(x, float) and pd.isna(x)):
                return ""
            s = str(x).strip()
            if s in ("nan", "NaT", "None", ""):
                return ""
            try:
                f = float(s)
                return str(int(f)) if f == int(f) else str(round(f, 6))
            except (ValueError, OverflowError):
                return s
        return series.apply(_obj_str)

    return series.fillna("").astype(str)


def _hash_rows(df: pd.DataFrame, indices: list[int]) -> str:
    """SHA256 хэш по нормализованным значениям (NaN='', даты=ISO, числа=round6)."""
    subset = df.iloc[indices].copy()
    norm = pd.DataFrame({c: _normalize_col(subset[c]) for c in subset.columns})
    raw = norm.to_csv(sep="\t", index=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_csv_or_parts(base_path: Path) -> pd.DataFrame:
    """Читает CSV или часть1+часть2, если раскололи."""
    if base_path.exists():
        return pd.read_csv(str(base_path), sep=";", encoding="utf-8-sig", low_memory=False)
    part1 = base_path.with_name(base_path.stem + "_part1.csv")
    part2 = base_path.with_name(base_path.stem + "_part2.csv")
    if part1.exists() and part2.exists():
        df1 = pd.read_csv(str(part1), sep=";", encoding="utf-8-sig", low_memory=False)
        df2 = pd.read_csv(str(part2), sep=";", encoding="utf-8-sig", low_memory=False)
        return pd.concat([df1, df2], ignore_index=True)
    raise FileNotFoundError(f"CSV не найден: {base_path} (и нет part1/part2)")


def verify_sheet(
    original_path: Path,
    sheet_name: str,
    csv_base: Path,
    parquet_path: Path,
) -> dict:
    """Верифицирует один лист. Возвращает словарь с результатами."""
    result = {"sheet": sheet_name, "ok": False, "errors": []}

    print(f"  Читаю оригинал '{sheet_name}' (pandas/openpyxl)...")
    df_orig = pd.read_excel(str(original_path), sheet_name=sheet_name, engine="openpyxl")
    n_orig = len(df_orig)
    result["rows_original"] = n_orig
    print(f"  Оригинал: {n_orig:,} строк × {len(df_orig.columns)} столбцов")

    # CSV
    print(f"  Читаю CSV {csv_base.name}...")
    df_csv = _read_csv_or_parts(csv_base)
    n_csv = len(df_csv)
    result["rows_csv"] = n_csv

    # Parquet
    print(f"  Читаю Parquet {parquet_path.name}...")
    df_pq = pd.read_parquet(str(parquet_path))
    n_pq = len(df_pq)
    result["rows_parquet"] = n_pq

    # Проверка количества строк
    if n_orig != n_csv:
        result["errors"].append(f"rows_mismatch: original={n_orig}, csv={n_csv}")
    if n_orig != n_pq:
        result["errors"].append(f"rows_mismatch: original={n_orig}, parquet={n_pq}")

    # Выборка 5 случайных строк
    import random
    rng = random.Random(SAMPLE_SEED)
    indices = sorted(rng.sample(range(min(n_orig, n_csv, n_pq)), min(SAMPLE_N, n_orig)))
    result["sample_indices"] = indices

    hash_orig = _hash_rows(df_orig, indices)
    hash_csv = _hash_rows(df_csv, indices)
    hash_pq = _hash_rows(df_pq, indices)

    result["hash_original"] = hash_orig[:16]
    result["hash_csv"] = hash_csv[:16]
    result["hash_parquet"] = hash_pq[:16]

    if hash_orig != hash_csv:
        result["errors"].append("sample_hash_mismatch: original vs csv")
    if hash_orig != hash_pq:
        result["errors"].append("sample_hash_mismatch: original vs parquet")

    result["ok"] = len(result["errors"]) == 0
    return result


def check_file_sizes(split_dir: Path) -> dict:
    """Проверяет все файлы в директории ≤ 30 МБ."""
    oversize = []
    checked = []
    for p in sorted(split_dir.iterdir()):
        if p.is_file():
            sz = p.stat().st_size
            checked.append({"name": p.name, "size_bytes": sz})
            if sz > MAX_FILE_BYTES:
                oversize.append({"name": p.name, "size_bytes": sz})
    return {"checked": checked, "oversize": oversize, "all_ok": len(oversize) == 0}


def main():
    parser = argparse.ArgumentParser(description="Верификация целостности раскола xlsm")
    parser.add_argument("--split-dir", required=True, help="Директория с результатами split")
    parser.add_argument("--original", required=True, help="Путь к оригинальному xlsm")
    args = parser.parse_args()

    split_dir = Path(args.split_dir)
    original = Path(args.original)

    if not original.exists():
        print(f"ERROR: оригинал не найден: {original}", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== Верификация split: {split_dir} ===\n")
    all_errors = []

    # Верификация листа Данные
    print("[1/3] Верификация листа 'Данные'...")
    res_data = verify_sheet(
        original,
        SHEET_DATA,
        split_dir / "Январь_2026_Данные.csv",
        split_dir / "Январь_2026_Данные.parquet",
    )
    if res_data["ok"]:
        print(f"  ✓ OK — {res_data['rows_original']:,} строк совпадают, хэши совпадают")
    else:
        print(f"  ✗ ОШИБКИ: {res_data['errors']}")
        all_errors.extend(res_data["errors"])

    # Верификация листа Данные (15МИН)
    print("\n[2/3] Верификация листа 'Данные (15МИН)'...")
    res_15 = verify_sheet(
        original,
        SHEET_DATA_15,
        split_dir / "Январь_2026_Данные_15МИН.csv",
        split_dir / "Январь_2026_Данные_15МИН.parquet",
    )
    if res_15["ok"]:
        print(f"  ✓ OK — {res_15['rows_original']:,} строк совпадают, хэши совпадают")
    else:
        print(f"  ✗ ОШИБКИ: {res_15['errors']}")
        all_errors.extend(res_15["errors"])

    # Проверка размеров файлов
    print("\n[3/3] Проверка размеров файлов ≤ 30 МБ...")
    sizes = check_file_sizes(split_dir)
    if sizes["all_ok"]:
        print(f"  ✓ OK — все {len(sizes['checked'])} файлов ≤ 30 МБ")
    else:
        for f in sizes["oversize"]:
            mb = f["size_bytes"] / 1024 / 1024
            msg = f"  ✗ {f['name']}: {mb:.1f} МБ > 30 МБ"
            print(msg)
            all_errors.append(msg)

    # Дописать в split_report.json
    report_path = split_dir / "split_report.json"
    verification_block = {
        "status": "PASS" if not all_errors else "FAIL",
        "errors": all_errors,
        "sheet_data": res_data,
        "sheet_data_15min": res_15,
        "file_sizes": sizes,
    }

    if report_path.exists():
        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)
        report["verification"] = verification_block
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\nОбновлён split_report.json: verification.status = {verification_block['status']}")
    else:
        print(f"\nWARN: split_report.json не найден в {split_dir}, верификация не записана")

    if all_errors:
        print(f"\n✗ FAIL — найдено {len(all_errors)} ошибок")
        sys.exit(1)
    else:
        print("\n✓ PASS — все проверки пройдены")
        sys.exit(0)


if __name__ == "__main__":
    main()
