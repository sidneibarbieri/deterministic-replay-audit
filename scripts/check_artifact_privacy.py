#!/usr/bin/env python3
"""Fail on high-confidence privacy or secret leaks in the reviewer artifact."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "dist",
    "exports",
    "logs",
    "node_modules",
    "playwright-report",
    "test-results",
    "tmp",
}
SKIP_SUFFIXES = {
    ".DS_Store",
    ".pyc",
    ".sqlite",
    ".sqlite3",
    # Vendored upstream typesetting template files we do not author, which carry
    # upstream maintainer and permissions emails.
    ".cls",
    ".bst",
}
MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    path: Path
    label: str
    line: int | None
    value: str


PRIVATE_FIRST_NAME = "Sid" + "nei"
PRIVATE_LAST_NAME = "Bar" + "bieri"
PRIVATE_HANDLE = (("sid" + "nei") + ("bar" + "bieri")).lower()
PRIVATE_NUMERIC_SENTINELS = (
    "1511" + r"\.18",
    "34" + r"\.47335",
    "201" + r"\.94608",
    "190922" + r"\.43",
    "191112" + r"\.48",
    "16554" + r"\.20",
    "504" + r"\.65",
    "431" + r"\.36",
)

TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "personal name",
        re.compile(
            rf"\b(?:{PRIVATE_FIRST_NAME}|{PRIVATE_LAST_NAME})\b",
            re.IGNORECASE,
        ),
    ),
    ("personal handle", re.compile(PRIVATE_HANDLE, re.IGNORECASE)),
    ("local home path", re.compile("/" + "Users" + r"/[^\"'\s:)]+")),
    (
        "local assistant attachment path",
        re.compile(r"\." + "codex" + "/attachments", re.IGNORECASE),
    ),
    (
        "temporary screenshot path",
        re.compile(("NSIRD_" + "screencaptureui") + "|" + ("Temporary" + "Items")),
    ),
    (
        "private fixture sentinel",
        re.compile(r"\b(?:" + "|".join(PRIVATE_NUMERIC_SENTINELS) + r")\b"),
    ),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
ALLOWED_EMAILS = {"anonymous@example.com", "reviewer@example.com", "user@example.com"}

# paper/main.tex carries the real author block for the non-anonymous build. The
# template "anonymous" option blanks it in the PDF, and package_artifact.sh strips it from
# the published artifact, so author identity is expected in this one file and skipped
# here. Every other file is still scanned for author identity, and main.tex is still
# scanned for keys, local paths, and private sentinels.
SUBMISSION_SOURCE = "paper/main.tex"
AUTHOR_IDENTITY_LABELS = frozenset({"personal name", "personal handle"})


def is_submission_source(path: Path, root: Path) -> bool:
    try:
        return path.relative_to(root).as_posix() == SUBMISSION_SOURCE
    except ValueError:
        return False


def should_skip(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    if any(part in SKIP_DIRS for part in relative.parts):
        return True
    return path.suffix in SKIP_SUFFIXES


def git_tracked_files(root: Path) -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    names = [name for name in result.stdout.decode("utf-8").split("\0") if name]
    return [root / name for name in names]


def files_to_scan(root: Path) -> list[Path]:
    tracked = git_tracked_files(root) if (root / ".git").exists() else None
    candidates = tracked if tracked is not None else [path for path in root.rglob("*")]
    return [
        path
        for path in candidates
        if path.is_file() and not should_skip(path, root) and path.stat().st_size <= MAX_BYTES
    ]


def line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def compact(value: str, limit: int = 96) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def scan_text(path: Path, text: str, allow_author_block: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    for label, pattern in TEXT_PATTERNS:
        if allow_author_block and label in AUTHOR_IDENTITY_LABELS:
            continue
        for match in pattern.finditer(text):
            findings.append(
                Finding(path, label, line_number(text, match.start()), compact(match.group(0)))
            )
    if not allow_author_block:
        for match in EMAIL_PATTERN.finditer(text):
            email = match.group(0).lower()
            if email not in ALLOWED_EMAILS:
                findings.append(
                    Finding(path, "non-anonymous email", line_number(text, match.start()), email)
                )
    return findings


def scan_binary(path: Path, content: bytes) -> list[Finding]:
    findings: list[Finding] = []
    for label, pattern in TEXT_PATTERNS:
        flags = pattern.flags & ~re.UNICODE
        byte_pattern = re.compile(pattern.pattern.encode("utf-8"), flags)
        for match in byte_pattern.finditer(content):
            value = match.group(0).decode("utf-8", errors="replace")
            findings.append(Finding(path, f"{label} in binary", None, compact(value)))
    return findings


def scan_file(path: Path, root: Path) -> list[Finding]:
    content = path.read_bytes()
    allow_author_block = is_submission_source(path, root)
    try:
        return scan_text(path, content.decode("utf-8"), allow_author_block)
    except UnicodeDecodeError:
        return scan_binary(path, content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    findings: list[Finding] = []
    for path in files_to_scan(root):
        findings.extend(scan_file(path, root))
    if findings:
        print("PRIVACY AUDIT FAILED:", file=sys.stderr)
        for finding in findings:
            relative = finding.path.relative_to(root)
            location = f"{relative}:{finding.line}" if finding.line else str(relative)
            print(f"  {location}: {finding.label}: {finding.value}", file=sys.stderr)
        return 1
    print(f"privacy audit OK ({len(files_to_scan(root))} files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
