"""Scan issue-52 scope for Kyushu-related contamination."""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCAN_PATHS = (
    ROOT / "web",
    ROOT / "trips" / "awaji-naruto-tokushima-kobe-2026",
    ROOT / "docs" / "trips" / "awaji-2026",
)

FORBIDDEN = (
    "九州",
    "熊本",
    "阿蘇",
    "高千穗",
    "kyushu_",
    "/ai_kyushu/",
    "ai_kyushu",
    "六天導覽",
    "6日互動排程",
)

ALLOWED_REFERENCE_FILE = Path("docs/trips/awaji-2026/reference-analysis.md")
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__"}


def iter_text_files(path: Path):
    if not path.exists():
        return
    for file in path.rglob("*"):
        if not file.is_file():
            continue
        if any(part in SKIP_DIRS for part in file.relative_to(path).parts):
            continue
        if file.suffix.lower() not in {
            ".md",
            ".txt",
            ".json",
            ".py",
            ".sh",
            ".yml",
            ".yaml",
            ".toml",
            ".html",
            ".css",
            ".js",
            ".tsx",
            ".ts",
            ".cpp",
        }:
            continue
        yield file


def scan() -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    patterns = [re.compile(re.escape(pattern), re.IGNORECASE) for pattern in FORBIDDEN]
    for root in SCAN_PATHS:
        for file in iter_text_files(root):
            relative_file = file.relative_to(ROOT)
            if relative_file == ALLOWED_REFERENCE_FILE:
                continue
            lines = file.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines, start=1):
                for pattern in patterns:
                    if pattern.search(line):
                        findings.append((relative_file, index, line.strip()))
                        break
    return findings


def main() -> None:
    findings = scan()
    if not findings:
        print("No contamination found for issue-52 scope.")
        raise SystemExit(0)
    print("Found disallowed scope strings:")
    for file, line, text in findings:
        print(f"- {file}:{line}: {text}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
