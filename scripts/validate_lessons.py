# -*- coding: utf-8 -*-
"""Validate one lesson-v2 JSON file or every *.lesson.json below a directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lesson_contract import validate_v2  # noqa: E402


def lesson_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.lesson.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    files = lesson_files(args.path)
    if not files:
        print(f"No *.lesson.json files found below {args.path}")
        return 2
    failed = 0
    for path in files:
        try:
            lesson = json.loads(path.read_text(encoding="utf-8-sig"))
            errors = validate_v2(lesson)
        except Exception as exc:  # noqa: BLE001 - CLI should report every file
            errors = [f"cannot read JSON: {exc}"]
        if errors:
            failed += 1
            print(f"FAIL {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            task_count = sum(len(segment.get("tasks") or []) for segment in lesson["segments"])
            print(f"OK   {path} ({task_count} tasks)")
    print(f"Validated {len(files)} lesson(s); failures={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
