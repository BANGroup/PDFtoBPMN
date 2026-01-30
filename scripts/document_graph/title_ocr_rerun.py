#!/usr/bin/env python3
"""
Повторный прогон OCR титульных страниц для документов,
где титульная OCR не удалась в полном прогоне.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.document_graph.pdfplumber_extractor import ocr_title_page


def _read_first_lines(path: Path, limit: int = 60) -> List[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    return text.splitlines()[:limit]


def _has_failed_title_ocr(lines: List[str]) -> bool:
    joined = "\n".join(lines)
    if "<!-- Страница 1 (OCR) -->" not in joined:
        return False
    return "OCR не удался" in joined


def _extract_doc_code(dir_name: str) -> Optional[str]:
    if "_" not in dir_name:
        return None
    return dir_name.split("_", 1)[1].strip() or None


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _find_pdf_for_code(input_root: Path, doc_code: str) -> Optional[Path]:
    target = _normalize_name(doc_code)
    for pdf_path in input_root.glob("**/*.pdf"):
        if target and target in _normalize_name(pdf_path.stem):
            return pdf_path
    return None


def collect_failed_titles(results_dir: Path) -> List[Tuple[str, Path]]:
    failed: List[Tuple[str, Path]] = []
    for doc_dir in sorted(results_dir.iterdir()):
        if not doc_dir.is_dir():
            continue
        content_path = doc_dir / "full_content.md"
        if not content_path.exists():
            continue
        lines = _read_first_lines(content_path)
        if _has_failed_title_ocr(lines):
            doc_code = _extract_doc_code(doc_dir.name) or doc_dir.name
            failed.append((doc_code, doc_dir))
    return failed


def wait_health(base_url: str = "http://localhost:8000", timeout: int = 3, retries: int = 10) -> bool:
    for _ in range(retries):
        try:
            resp = requests.get(f"{base_url}/health", timeout=timeout)
            if resp.ok:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Повторный OCR титульных страниц")
    parser.add_argument("--input-root", type=str, required=True,
                        help="Корень, где лежат исходные PDF (input2)")
    parser.add_argument("--results-dir", type=str, required=True,
                        help="Папка с результатами полного прогона (full_run_latest)")
    parser.add_argument("--output-dir", type=str, required=True,
                        help="Папка для результатов повтора титульных OCR")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Таймаут OCR запроса (сек)")
    parser.add_argument("--scale", type=float, default=2.0,
                        help="Масштаб рендера титульной страницы")
    parser.add_argument("--fallback-scale", type=float, default=1.0,
                        help="Fallback масштаб при неудаче")
    parser.add_argument("--prompt-type", type=str, default="default",
                        help="Prompt type для OCR (например: default, ocr_simple)")
    args = parser.parse_args()

    input_root = Path(args.input_root)
    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    failed = collect_failed_titles(results_dir)
    print(f"🔎 Найдено титульных с ошибкой OCR: {len(failed)}")

    report = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "results_dir": str(results_dir),
        "input_root": str(input_root),
        "failed_total": len(failed),
        "items": []
    }

    if not wait_health():
        print("❌ OCR сервис не готов, остановка.")
        return

    for idx, (doc_code, doc_dir) in enumerate(failed, 1):
        pdf_path = _find_pdf_for_code(input_root, doc_code)
        if not pdf_path:
            report["items"].append({
                "doc_code": doc_code,
                "status": "pdf_not_found"
            })
            print(f"[{idx}/{len(failed)}] ❌ PDF не найден: {doc_code}")
            continue

        title_md = ocr_title_page(
            pdf_path,
            timeout=args.timeout,
            scale=args.scale,
            fallback_scale=args.fallback_scale,
            prompt_type=args.prompt_type
        )
        doc_output = output_dir / doc_dir.name
        doc_output.mkdir(parents=True, exist_ok=True)

        status = "ocr_failed"
        if title_md:
            status = "ok"
            (doc_output / "title_ocr.md").write_text(
                title_md, encoding="utf-8", newline="\n"
            )
        (doc_output / "title_ocr_status.json").write_text(
            json.dumps({
                "doc_code": doc_code,
                "pdf_path": str(pdf_path),
                "status": status
            }, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        report["items"].append({
            "doc_code": doc_code,
            "pdf_path": str(pdf_path),
            "status": status
        })
        print(f"[{idx}/{len(failed)}] {doc_code}: {status}")

    (output_dir / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    ok_count = sum(1 for item in report["items"] if item["status"] == "ok")
    print(f"✅ Завершено. Успешных OCR: {ok_count}/{len(failed)}")


if __name__ == "__main__":
    main()
