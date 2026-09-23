"""
Тест: ночная сборка корпуса БНД (scripts/ingestion/bnd_sync) — раскладка файлов и отчёт.
Запустить: pytest tests/test_bnd_sync.py -v
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ingestion" / "bnd_sync"))

import download_bnd_corpus as corpus  # noqa: E402
import run_nightly  # noqa: E402


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(corpus, "QUARANTINE_DIR", tmp_path / "data" / "bnd_sync" / "quarantine" / "d")
    return tmp_path


def test_pick_target_keeps_name_on_redownload(root):
    """Повторная закачка того же вложения: имя без суффикса, номер документа не портится."""
    subdir = root / "data/bnd_corpus/documents/СЭМ/V5/РИ-В5.072-01/files"
    name = "РИ-В5.072-01 (эталон для ознакомления).pdf"
    (subdir).mkdir(parents=True)
    (subdir / name).write_bytes(b"old")
    assert corpus.pick_target(subdir, name, "F9386D6B0000", taken=set()) == subdir / name


def test_pick_target_suffix_before_extension_on_collision(root):
    """Имя занято другим вложением документа → суффикс перед последним расширением."""
    subdir = root / "data/bnd_corpus/documents/СМК/M1/РД-М1.032-08/word"
    name = "РД-М1.032-08 Лист.docx"
    taken = {str((subdir / name).relative_to(root))}
    target = corpus.pick_target(subdir, name, "ABCDEF1234", taken)
    assert target.name == "РД-М1.032-08 Лист_ABCDEF12.docx"


def test_relocate_doc_dir_moves_and_rewrites_paths(root):
    """Документ сменил процесс: папка переезжает, пути в state указывают на новое место."""
    old_rel = "data/bnd_corpus/documents/СМК/_unclassified/КД-ДП-В4.012-03"
    new_rel = "data/bnd_corpus/documents/СМК/V4/КД-ДП-В4.012-03"
    (root / old_rel / "files").mkdir(parents=True)
    (root / old_rel / "files" / "a.pdf").write_bytes(b"x")
    prev = {"dir": old_rel, "files": [{"path": f"{old_rel}/files/a.pdf"}]}

    assert corpus.relocate_doc_dir(prev, new_rel) == (1, 0)
    assert (root / new_rel / "files" / "a.pdf").exists()
    assert not (root / old_rel).exists()
    assert prev["files"][0]["path"] == f"{new_rel}/files/a.pdf"


def test_relocate_doc_dir_quarantines_when_target_exists(root):
    """Новая папка уже есть → старая уходит в карантин, а не остаётся сиротой."""
    old_rel = "data/bnd_corpus/documents/СМК/_unclassified/X-01"
    new_rel = "data/bnd_corpus/documents/СМК/V4/X-01"
    (root / old_rel).mkdir(parents=True)
    (root / new_rel).mkdir(parents=True)

    assert corpus.relocate_doc_dir({"dir": old_rel, "files": []}, new_rel) == (0, 1)
    assert not (root / old_rel).exists()
    assert (corpus.QUARANTINE_DIR / old_rel).exists()


def test_quarantine_keeps_relative_path(root):
    f = root / "data/bnd_corpus/documents/СЭМ/V5/Y/files/old.pdf"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    assert corpus.quarantine(f) == 1
    assert (corpus.QUARANTINE_DIR / "data/bnd_corpus/documents/СЭМ/V5/Y/files/old.pdf").exists()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Изолированный корпус <tmp>/data/bnd_corpus + каталоги в <tmp>/webBI, без сети."""
    webbi, corpus_root = tmp_path / "webBI", tmp_path / "data" / "bnd_corpus"
    webbi.mkdir()
    for name, value in {
        "CATALOG_PATH": webbi / "doc-catalog.json", "STATE_PATH": webbi / "doc-catalog.state.json",
        "RPP_CATALOG_PATH": webbi / "rpp-catalog.json", "CORPUS_ROOT": corpus_root,
        "PROJECT_ROOT": tmp_path, "DOCS_DIR": corpus_root / "documents",
        "ARCHIVE_DIR": corpus_root / "documents" / "_archive",
        "DL_STATE_PATH": corpus_root / ".download-state.json",
        "MANIFEST_PATH": corpus_root / "manifest.json",
        "QUARANTINE_DIR": tmp_path / "data" / "bnd_sync" / "quarantine" / "d",
        "DOMINO_USER": "u", "DOMINO_PASS": "p",
    }.items():
        monkeypatch.setattr(corpus, name, value)
    monkeypatch.setattr(sys, "argv", ["download_bnd_corpus.py", "--skip-rpp"])
    return tmp_path


def _run(sandbox, monkeypatch, fp: str, fetch):
    import json
    entry = {"num": "РИ-В5.072-01", "title": "t", "doc_sm": "СЭМ",
             "files": [{"url": "UNID0001", "name": "РИ-В5.072-01 (эталон).pdf"}]}
    (sandbox / "webBI" / "doc-catalog.json").write_text(json.dumps({"V5": [entry]}), encoding="utf-8")
    (sandbox / "webBI" / "doc-catalog.state.json").write_text(
        json.dumps({"fingerprints": {"РИ-В5.072-01": fp}}), encoding="utf-8")
    monkeypatch.setattr(corpus, "fetch_attachment", lambda *a, **k: fetch())
    assert corpus.main() == 0
    return (json.loads((sandbox / "data/bnd_corpus/manifest.json").read_text(encoding="utf-8")),
            json.loads((sandbox / "data/bnd_corpus/.download-state.json").read_text(encoding="utf-8")))


def test_network_failure_retries_next_run(sandbox, monkeypatch):
    """v1 скачан → на v2 сбой (v1 остаётся, fingerprint прежний) → сеть вернулась, v2 скачан."""
    name = "РИ-В5.072-01 (эталон).pdf"
    manifest, state = _run(sandbox, monkeypatch, "fp1", lambda: (name, b"v1"))
    path = manifest["documents"][0]["files"][0]["path"]
    assert manifest["project_root"] == str(sandbox)
    assert path == f"data/bnd_corpus/documents/СЭМ/V5/РИ-В5.072-01/files/{name}"

    manifest, state = _run(sandbox, monkeypatch, "fp2", lambda: None)
    assert manifest["documents"][0]["files"][0]["path"] == path
    assert state["docs"]["РИ-В5.072-01"]["fingerprint"] == "fp1"

    manifest, state = _run(sandbox, monkeypatch, "fp2", lambda: (name, b"v2"))
    assert (sandbox / path).read_bytes() == b"v2"
    assert state["docs"]["РИ-В5.072-01"]["fingerprint"] == "fp2"
    assert sorted(p.name for p in (sandbox / path).parent.iterdir()) == [name]


def test_quarantine_orphans_keeps_manifest_files(sandbox, monkeypatch):
    """Сироты уходят в карантин, файлы manifest и _archive/ остаются, пустые папки убираются."""
    name = "РИ-В5.072-01 (эталон).pdf"
    manifest, _ = _run(sandbox, monkeypatch, "fp1", lambda: (name, b"v1"))
    keep = sandbox / manifest["documents"][0]["files"][0]["path"]
    docs = sandbox / "data/bnd_corpus/documents"
    dup = keep.with_name("РИ-В5_F9386D6B.072-01 (эталон).pdf")
    dup.write_bytes(b"old")
    moved_dir = docs / "СМК/_unclassified/РИ-В5.072-01"
    (moved_dir / "files").mkdir(parents=True)
    (moved_dir / "files/a.pdf").write_bytes(b"x")
    (moved_dir / "document.json").write_text("{}")
    (docs / "_archive/OLD/files").mkdir(parents=True)
    (docs / "_archive/OLD/files/b.pdf").write_bytes(b"x")
    bloated = sandbox / "data/bnd_corpus/manifest.json.bloated"
    bloated.write_bytes(b"x")

    assert sorted(p.name for p in corpus.find_orphans()) == sorted(
        ["manifest.json.bloated", dup.name, "a.pdf", "document.json"])
    assert corpus.quarantine_orphans(apply=True) == 0
    assert keep.exists() and (docs / "_archive/OLD/files/b.pdf").exists()
    assert not dup.exists() and not moved_dir.exists() and not bloated.exists()
    assert corpus.find_orphans() == []


def _ok(**kw):
    return {"_exit_code": 0, **kw}


@pytest.mark.parametrize("bnd,rpp,corp,expected", [
    (_ok(mode="incremental", changed_docs=0, delta=0), _ok(delta=0), _ok(downloaded=0), "изменений нет"),
    (_ok(mode="incremental", changed_docs=31, delta=0), _ok(delta=0), _ok(downloaded=1043),
     "изменилось документов БНД: 31, скачано файлов: 1 043"),
    (_ok(mode="full", changed_docs=358, delta=0), _ok(delta=0), _ok(downloaded=150), "полная пересборка БНД"),
    (_ok(mode="incremental", changed_docs=0, removed_docs=3, delta=-3), _ok(delta=0), _ok(downloaded=0, archived=3),
     "удалено документов БНД: 3, в архив: 3"),
])
def test_changes_summary(bnd, rpp, corp, expected):
    """«Изменений нет» — только когда реально ничего не менялось (было: при Δ 0 числа документов)."""
    assert run_nightly._changes_summary(bnd, rpp, corp) == expected


def test_format_telegram_no_false_no_changes():
    text = run_nightly.format_report(
        _ok(mode="incremental", changed_docs=31, delta=0), _ok(delta=0),
        datetime(2026, 9, 23, 1, 0), datetime(2026, 9, 23, 1, 5), Path("/tmp/x.log"),
        corpus=_ok(downloaded=1043, manifest_files=6747, manifest_mb=9340.0, mb=677.6, skipped=5287),
    )
    assert "изменений нет" not in text
    assert "изменилось документов БНД: 31" in text


def test_send_report_skips_without_config(monkeypatch):
    for k in ("MATTERMOST_URL", "MATTERMOST_TOKEN", "BND_REPORT_MM_USERS"):
        monkeypatch.delenv(k, raising=False)
    assert run_nightly.send_report("x") == (False, "not_configured")


def test_report_recipients_parsing(monkeypatch):
    monkeypatch.setenv("BND_REPORT_MM_USERS", " budnik_an, @lavrova_tv ,bachurina_iv,")
    assert run_nightly._report_recipients() == ["budnik_an", "lavrova_tv", "bachurina_iv"]
