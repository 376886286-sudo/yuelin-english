# -*- coding: utf-8 -*-
"""Deterministic lesson activities and pending-task state.

The course file is authored as alternating A/B dialogue lines.  This module
turns those lines into explicit student activities.  It never calls an LLM and
is the only source of truth for which task is currently pending.
"""

from __future__ import annotations

from copy import deepcopy


def _dialogue(segment: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in segment.get("dialogue", []) or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append((str(item[0]).upper(), str(item[1]).strip()))
    return out


def infer_expected_action(prompt: str) -> str:
    """Infer the server-owned teaching action from the teacher prompt."""
    low = (prompt or "").strip().lower()
    if low.startswith(("repeat ", "repeat after me", "listen and repeat")):
        return "repeat"
    if low.startswith(("is ", "are ", "do ", "does ", "can ", "could ", "would ")):
        return "fixed_answer"
    return "open_answer"


def infer_expected_mode(prompt: str) -> str:
    """Backward-compatible alias for older course clients."""
    return infer_expected_action(prompt)


def build_activities(lesson: dict) -> list[dict]:
    """Compile course dialogue and optional review pack into ordered tasks."""
    activities: list[dict] = []
    segments = lesson.get("segments", []) or []
    for segment_idx, segment in enumerate(segments):
        entries = _dialogue(segment)
        b_positions = [i for i, (role, _) in enumerate(entries) if role == "B"]
        if not b_positions:
            continue

        code = segment.get("code", "") or f"SEG{segment_idx + 1}"
        for activity_idx, b_pos in enumerate(b_positions):
            prompt = ""
            lower_bound = b_positions[activity_idx - 1] + 1 if activity_idx else 0
            for pos in range(b_pos - 1, lower_bound - 1, -1):
                if entries[pos][0] == "A":
                    prompt = entries[pos][1]
                    break
            if not prompt:
                prompt = segment.get("task", "") or "Please answer the teacher."

            trailing = ""
            if activity_idx == len(b_positions) - 1:
                for role, text in entries[b_pos + 1 :]:
                    if role == "A":
                        trailing = text
                        break

            target = entries[b_pos][1]
            action = infer_expected_action(prompt)
            activities.append(
                {
                    "id": f"{code}_Q{activity_idx + 1}",
                    "segment_idx": segment_idx,
                    "segment_code": code,
                    "segment_name": segment.get("name_zh", "") or code,
                    "activity_idx": activity_idx,
                    "prompt": prompt,
                    "expected_action": action,
                    "reference_text": target if action == "repeat" else None,
                    "expected_mode": action,
                    "target_text": target,
                    "expected_intent": "answer",
                    "closing_prompt": trailing,
                }
            )

    review_idx = len(segments)
    for idx, item in enumerate(lesson.get("review_errors", []) or []):
        target = (item.get("drill") or item.get("text") or "").strip()
        if not target:
            continue
        activities.append(
            {
                "id": f"REVIEW_Q{idx + 1}",
                "segment_idx": review_idx,
                "segment_code": "REVIEW",
                "segment_name": "往期易错点",
                "activity_idx": idx,
                "prompt": f"Listen and repeat: {target}",
                "expected_action": "repeat",
                "reference_text": target,
                "expected_mode": "repeat",
                "target_text": target,
                "expected_intent": "repeat_attempt",
                "closing_prompt": "",
            }
        )
    return activities


def make_pending(activity: dict | None) -> dict | None:
    if not activity:
        return None
    action = activity.get("expected_action") or activity.get("expected_mode") or "open_answer"
    target = activity.get("target_text") or ""
    return {
        **deepcopy(activity),
        "expected_action": action,
        "reference_text": activity.get("reference_text") or (target if action == "repeat" else None),
        # Compatibility mirrors for the previous frontend/API contract.
        "expected_mode": action,
        "attempts": 0,
        "attempt_count": 0,
        "hint_level": 0,
        "assistance_level": "none",
        "repeat_attempts": 0,
        "completed": False,
    }


def initial_state(lesson: dict) -> dict:
    activities = build_activities(lesson)
    first = activities[0] if activities else None
    return {
        "activity_pos": 0,
        "task_idx": 0,
        "segment_idx": first.get("segment_idx", 0) if first else 0,
        "pending": make_pending(first),
        "suspended_task": None,
        "coaching_notes": [],
        "activity_results": {},
        "grades": {"segments": {}, "weak": []},
        "done": not bool(first),
    }


def activity_at(lesson: dict, position: int) -> dict | None:
    activities = build_activities(lesson)
    if 0 <= position < len(activities):
        return activities[position]
    return None


def next_pending(lesson: dict, position: int) -> dict | None:
    return make_pending(activity_at(lesson, position))


def segment_transition(lesson: dict, segment_idx: int) -> str:
    segments = lesson.get("segments", []) or []
    if 0 <= segment_idx < len(segments):
        return (segments[segment_idx].get("transition") or "").strip()
    return ""
