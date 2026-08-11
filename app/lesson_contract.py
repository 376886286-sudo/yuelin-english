# -*- coding: utf-8 -*-
"""Versioned lesson contract shared with the independent lesson project.

The website owns runtime behavior. Lesson repositories own content. They meet
only through this JSON-compatible contract, so neither project imports code or
data from the other at runtime.
"""

from __future__ import annotations

from copy import deepcopy

SCHEMA_VERSION = "2.0"
EXPECTED_ACTIONS = {
    "open_answer",
    "fixed_answer",
    "ask_question",
    "repeat",
    "free_talk",
}


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_v2(lesson: dict) -> list[str]:
    """Return stable, human-readable validation errors for a lesson-v2 file."""
    errors: list[str] = []
    if not isinstance(lesson, dict):
        return ["lesson must be a JSON object"]
    if str(lesson.get("schema_version")) != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    for field in ("id", "title_zh", "title_en", "language_standard"):
        if not _nonempty(lesson.get(field)):
            errors.append(f"{field} is required")
    if not isinstance(lesson.get("unit"), int) or lesson.get("unit", 0) <= 0:
        errors.append("unit must be a positive integer")
    if not isinstance(lesson.get("duration_minutes"), int) or lesson.get("duration_minutes", 0) <= 0:
        errors.append("duration_minutes must be a positive integer")

    segments = lesson.get("segments")
    if not isinstance(segments, list) or len(segments) != 3:
        errors.append("segments must contain exactly three short stages")
        return errors

    segment_codes: set[str] = set()
    task_ids: set[str] = set()
    for segment_idx, segment in enumerate(segments, 1):
        prefix = f"segments[{segment_idx}]"
        if not isinstance(segment, dict):
            errors.append(f"{prefix} must be an object")
            continue
        code = str(segment.get("code") or "").strip()
        if not code or not code.isalpha() or code.upper() != code:
            errors.append(f"{prefix}.code must use unique uppercase letters")
        elif code in segment_codes:
            errors.append(f"{prefix}.code duplicates {code}")
        segment_codes.add(code)
        for field in ("name_zh", "mission", "interest_hook", "transition"):
            if not _nonempty(segment.get(field)):
                errors.append(f"{prefix}.{field} is required")
        if not isinstance(segment.get("duration_minutes"), int) or segment.get("duration_minutes", 0) <= 0:
            errors.append(f"{prefix}.duration_minutes must be positive")

        targets = segment.get("language_targets")
        if not isinstance(targets, dict):
            errors.append(f"{prefix}.language_targets is required")
        else:
            for field in ("active_vocabulary", "sentence_frames", "pronunciation_focus", "grammar_focus"):
                if not isinstance(targets.get(field), list):
                    errors.append(f"{prefix}.language_targets.{field} must be a list")

        tasks = segment.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            errors.append(f"{prefix}.tasks must contain at least one task")
            continue
        for task_idx, task in enumerate(tasks, 1):
            task_prefix = f"{prefix}.tasks[{task_idx}]"
            if not isinstance(task, dict):
                errors.append(f"{task_prefix} must be an object")
                continue
            task_id = str(task.get("id") or "").strip()
            if not task_id:
                errors.append(f"{task_prefix}.id is required")
            elif task_id in task_ids:
                errors.append(f"{task_prefix}.id duplicates {task_id}")
            task_ids.add(task_id)
            for field in ("title", "teacher_prompt"):
                if not _nonempty(task.get(field)):
                    errors.append(f"{task_prefix}.{field} is required")
            action = task.get("expected_action")
            if action not in EXPECTED_ACTIONS:
                errors.append(f"{task_prefix}.expected_action is invalid")
            samples = task.get("sample_answers")
            if not isinstance(samples, list) or not any(_nonempty(value) for value in samples):
                errors.append(f"{task_prefix}.sample_answers needs at least one example")
            if action == "repeat" and not _nonempty(task.get("reference_text")):
                errors.append(f"{task_prefix}.reference_text is required for repeat")
            if action != "repeat" and task.get("reference_text"):
                errors.append(f"{task_prefix}.reference_text is only allowed for repeat")
            if action == "ask_question" and isinstance(samples, list) and not any("?" in str(value) for value in samples):
                errors.append(f"{task_prefix}.ask_question needs a question example")
            rule = task.get("completion_rule")
            if not isinstance(rule, dict) or not _nonempty(rule.get("semantic_goal")):
                errors.append(f"{task_prefix}.completion_rule.semantic_goal is required")
            for field in ("help", "correction"):
                if not isinstance(task.get(field), dict):
                    errors.append(f"{task_prefix}.{field} is required")

        assessment = segment.get("assessment")
        if not isinstance(assessment, dict) or not _nonempty(assessment.get("pass_rule")):
            errors.append(f"{prefix}.assessment.pass_rule is required")
    return errors


def validate_for_import(lesson: dict) -> list[str]:
    """Validate v2 strictly while retaining legacy TXT/DOCX compatibility."""
    if str((lesson or {}).get("schema_version")) == SCHEMA_VERSION:
        return validate_v2(lesson)
    errors = []
    if not _nonempty((lesson or {}).get("title_zh")):
        errors.append("title_zh is required")
    if not isinstance((lesson or {}).get("segments"), list) or not lesson.get("segments"):
        errors.append("segments is required")
    return errors


def normalize_v2(lesson: dict) -> dict:
    """Add legacy display mirrors without changing the v2 source semantics."""
    normalized = deepcopy(lesson)
    normalized["duration"] = f"{normalized.get('duration_minutes', 0)} minutes"
    normalized.setdefault("abilities", normalized.get("learning_outcomes", []))
    normalized.setdefault("rules", normalized.get("teaching_rules", []))
    normalized.setdefault("closing_check", normalized.get("exit_checks", []))
    normalized.setdefault(
        "record_scheme",
        {
            "A": "independent completion",
            "B": "completion after a keyword hint",
            "C": "completion after a model or explicit repeat",
            "D": "not completed or skipped",
        },
    )
    for segment in normalized.get("segments", []):
        targets = segment.get("language_targets") or {}
        segment.setdefault("task", segment.get("mission", ""))
        segment.setdefault(
            "words",
            [*(targets.get("active_vocabulary") or []), *(targets.get("receptive_vocabulary") or [])],
        )
        segment.setdefault("phonics", targets.get("pronunciation_focus") or [])
        segment.setdefault("patterns", targets.get("sentence_frames") or [])
        segment.setdefault("pass_rule", (segment.get("assessment") or {}).get("pass_rule", ""))
    return normalized
