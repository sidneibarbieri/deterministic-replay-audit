"""Generate reviewer-facing reproducibility metrics."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "exports"
SOURCE_DIRS = (ROOT / "src" / "arenawealth", ROOT / "tests", ROOT / "scripts")
FRONTEND_SOURCE_DIR = ROOT / "frontend" / "src"
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", "archive", "exports"}


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_command(command: list[str], timeout_seconds: int) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return CommandResult(
        command=" ".join(command),
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for directory in SOURCE_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            if EXCLUDED_PARTS.isdisjoint(path.parts):
                files.append(path)
    return sorted(files)


def count_code_lines(path: Path) -> int:
    lines = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#"):
            lines += 1
    return lines


def source_metrics() -> dict[str, int]:
    files = iter_python_files()
    test_files = [path for path in files if "/tests/" in str(path)]
    source_files = [path for path in files if "/tests/" not in str(path)]
    frontend_files = sorted(FRONTEND_SOURCE_DIR.rglob("*")) if FRONTEND_SOURCE_DIR.exists() else []
    frontend_source_files = [
        path for path in frontend_files if path.suffix in {".css", ".ts", ".tsx"}
    ]
    return {
        "python_files": len(files),
        "source_files": len(source_files),
        "test_files": len(test_files),
        "source_lines": sum(count_code_lines(path) for path in source_files),
        "test_lines": sum(count_code_lines(path) for path in test_files),
        "frontend_source_files": len(frontend_source_files),
        "frontend_lines": sum(count_code_lines(path) for path in frontend_source_files),
    }


def build_payload(timeout_seconds: int) -> dict[str, object]:
    commands = [
        run_command([".venv/bin/python", "-m", "ruff", "check", "."], timeout_seconds),
        run_command([".venv/bin/python", "-m", "pytest", "-q"], timeout_seconds),
        run_command(["npm", "--prefix", "frontend", "run", "build"], timeout_seconds),
        run_command(["npm", "--prefix", "frontend", "run", "lint"], timeout_seconds),
        run_command(
            [
                ".venv/bin/python",
                "scripts/moat_compounding_analysis.py",
                "--cash",
                "1500.00",
                "--holdings",
                "tests/fixtures/seed_portfolio_broker.csv",
                "--offline-demo",
            ],
            timeout_seconds,
        ),
        run_command(["git", "status", "--short"], timeout_seconds),
    ]
    return {
        "generated_utc": datetime.now(UTC).isoformat(),
        "repository": ROOT.name,
        "metrics": source_metrics(),
        "commands": [asdict(result) for result in commands],
        "overall_passed": all(result.passed for result in commands[:-1]),
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=int, default=120)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = arguments.output_dir / f"reviewer_metrics_{stamp}.json"
    payload = build_payload(arguments.timeout)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
