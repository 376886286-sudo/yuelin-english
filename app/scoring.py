# -*- coding: utf-8 -*-
"""Task completion grades, deliberately separate from pronunciation scores."""

from __future__ import annotations


def activity_grade(*, completed: bool, hint_level: int = 0, skipped: bool = False) -> str:
    if skipped or not completed:
        return "D"
    if hint_level <= 0:
        return "A"
    if hint_level == 1:
        return "B"
    return "C"


def segment_grade(activity_results: list[dict]) -> str | None:
    if not activity_results:
        return None
    grades = [r.get("grade", "D") for r in activity_results]
    for grade in ("D", "C", "B", "A"):
        if grade in grades:
            return grade
    return "D"
