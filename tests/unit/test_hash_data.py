from pathlib import Path

from scripts import hash_data


def test_verify_fails_when_advisor_run_is_missing_from_manifest(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path
    static_input = root / "paper" / "data" / "static.json"
    advisor_run = root / "paper" / "data" / "advisor_runs" / "provider" / "run.json"
    manifest = root / "paper" / "data" / "DATA_HASHES.txt"
    static_input.parent.mkdir(parents=True)
    advisor_run.parent.mkdir(parents=True)
    static_input.write_text('{"ok": true}\n', encoding="utf-8")
    advisor_run.write_text('{"status": "collected"}\n', encoding="utf-8")

    monkeypatch.setattr(hash_data, "ROOT", root)
    monkeypatch.setattr(hash_data, "MANIFEST", manifest)
    monkeypatch.setattr(hash_data, "STATIC_INPUTS", ("paper/data/static.json",))
    monkeypatch.setattr(hash_data, "ADVISOR_RUNS", root / "paper" / "data" / "advisor_runs")

    manifest.write_text(
        f"{hash_data.sha256(static_input)}  paper/data/static.json\n",
        encoding="utf-8",
    )

    assert hash_data.verify() == 1

    hash_data.write_manifest()

    assert hash_data.verify() == 0
