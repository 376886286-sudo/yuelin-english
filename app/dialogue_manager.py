# -*- coding: utf-8 -*-
"""Conversation orchestration and deterministic state transitions."""

from __future__ import annotations

import copy
import re
import time
from difflib import SequenceMatcher

from . import lesson_engine, scoring, turn_analyzer


def _timestamp_ms() -> int:
    return int(time.time() * 1000)


def _append_event(session: dict, role: str, text: str, **extra) -> dict:
    event = {
        "turn_id": session.get("next_turn_id", 1),
        "role": role,
        "text": text,
        "timestamp": _timestamp_ms(),
        **extra,
    }
    session.setdefault("history", []).append(event)
    session["next_turn_id"] = event["turn_id"] + 1
    return event


def public_session(session: dict) -> dict:
    public = copy.deepcopy({k: v for k, v in session.items() if not k.startswith("_")})
    public["exchanges"] = copy.deepcopy(public.get("history", []))
    return public


def new_session(lesson: dict, session_id: str, started: str) -> tuple[dict, str]:
    session = {
        "id": session_id,
        "course_id": lesson.get("id"),
        "started": started,
        "history": [],
        "next_turn_id": 1,
        "degraded_count": 0,
        **lesson_engine.initial_state(lesson),
    }
    opening = (session.get("pending") or {}).get("prompt") or "Hello! Let's start our English practice."
    pending = session.get("pending") or {}
    _append_event(
        session,
        "ai",
        opening,
        segment_idx=pending.get("segment_idx", 0),
        activity_id=pending.get("id"),
    )
    return session, opening


def analyze(session: dict, student_text: str) -> dict:
    pending = session.get("pending") or {}
    return turn_analyzer.analyze_turn(pending, student_text, session.get("history", []))


def _hint_for(target: str) -> str:
    words = (target or "").split()
    if not words:
        return "Try using one short English sentence."
    if len(words) == 1:
        return f"It starts with '{words[0][0]}...'."
    prefix = " ".join(words[: min(3, len(words))])
    return f"You can start with: {prefix}..."


def _repeat_feedback(pronunciation: dict) -> str:
    score = pronunciation.get("score") or pronunciation.get("accuracy") or 0
    weak = pronunciation.get("weak_words") or pronunciation.get("weak") or []
    if weak:
        return f"Good try! Listen to '{weak[0]}' and read the sentence once more."
    if score:
        return "Good try! Let's read it once more, a little more smoothly."
    return "Good try! Let's read it once more."


def _segment_results(session: dict, segment_code: str) -> list[dict]:
    return [
        result
        for result in session.get("activity_results", {}).values()
        if result.get("segment_code") == segment_code
    ]


def _canon(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", (text or "").lower()))


def _complete_activity(session: dict, lesson: dict, analysis: dict, pronunciation: dict | None) -> tuple[str, str | None]:
    pending = session["pending"]
    activity_id = pending["id"]
    grade = scoring.activity_grade(completed=True, hint_level=pending.get("hint_level", 0))
    session["activity_results"][activity_id] = {
        "activity_id": activity_id,
        "segment_code": pending.get("segment_code"),
        "attempts": pending.get("attempts", 0),
        "hint_level": pending.get("hint_level", 0),
        "completed": True,
        "grade": grade,
        "pronunciation": pronunciation,
    }
    old_segment_code = pending.get("segment_code")
    old_segment_idx = pending.get("segment_idx", 0)
    closing = pending.get("closing_prompt") or ""
    session["activity_pos"] += 1
    next_pending = lesson_engine.next_pending(lesson, session["activity_pos"])
    session["pending"] = next_pending

    segment_finished = not next_pending or next_pending.get("segment_code") != old_segment_code
    segment_grade = None
    if segment_finished:
        segment_grade = scoring.segment_grade(_segment_results(session, old_segment_code))
        if segment_grade:
            session["grades"]["segments"][old_segment_code] = segment_grade

    feedback = (analysis.get("reply") or "Great!").strip()
    if "?" in feedback or "？" in feedback:
        feedback = "Great!"
    comparison = ""
    if segment_finished and closing:
        comparison = closing
    elif segment_finished:
        comparison = lesson_engine.segment_transition(lesson, old_segment_idx)
    elif next_pending:
        comparison = next_pending.get("prompt") or ""
    if comparison:
        similarity = SequenceMatcher(None, _canon(feedback), _canon(comparison)).ratio()
        if similarity >= 0.62:
            feedback = "Great!"
        if _canon(feedback).startswith("great") and _canon(comparison).startswith("great"):
            feedback = ""
    parts = [feedback] if feedback else []
    if segment_finished and closing:
        parts.append(closing)
    if next_pending:
        if segment_finished:
            transition = lesson_engine.segment_transition(lesson, old_segment_idx)
            if transition:
                parts.append(transition)
        parts.append(next_pending.get("prompt") or "Let's continue.")
        session["segment_idx"] = next_pending.get("segment_idx", old_segment_idx)
    else:
        session["done"] = True
        parts.append("Excellent work today! You kept speaking, and that is real progress.")
    return " ".join(part for part in parts if part), segment_grade


def _skip_activity(session: dict, lesson: dict) -> tuple[str, str | None]:
    pending = session["pending"]
    session["activity_results"][pending["id"]] = {
        "activity_id": pending["id"],
        "segment_code": pending.get("segment_code"),
        "attempts": pending.get("attempts", 0),
        "hint_level": pending.get("hint_level", 0),
        "completed": False,
        "grade": "D",
        "skipped": True,
    }
    old_code = pending.get("segment_code")
    session["activity_pos"] += 1
    next_pending = lesson_engine.next_pending(lesson, session["activity_pos"])
    session["pending"] = next_pending
    segment_finished = not next_pending or next_pending.get("segment_code") != old_code
    segment_grade = None
    if segment_finished:
        segment_grade = scoring.segment_grade(_segment_results(session, old_code))
        session["grades"]["segments"][old_code] = segment_grade
    if next_pending:
        session["segment_idx"] = next_pending.get("segment_idx", session.get("segment_idx", 0))
        return f"Okay, we'll move on. {next_pending.get('prompt', '')}", segment_grade
    session["done"] = True
    return "Okay. That's all for today.", segment_grade


def apply_turn(
    session: dict,
    lesson: dict,
    student_text: str,
    analysis: dict,
    *,
    input_mode: str = "typed",
    pronunciation: dict | None = None,
) -> dict:
    """Append chronological events and apply one guarded state transition."""
    pending = session.get("pending")
    if not pending or session.get("done"):
        raise ValueError("session is already complete")

    expected_mode = pending.get("expected_mode", "open_answer")
    user_act = analysis.get("user_act", "unclear")
    student_event = _append_event(
        session,
        "student",
        student_text,
        segment_idx=pending.get("segment_idx", 0),
        activity_id=pending.get("id"),
        intent=user_act,
        language=analysis.get("language", "en"),
        input_mode=input_mode,
    )
    speech_degraded = bool(analysis.get("speech_degraded"))
    if analysis.get("degraded") or speech_degraded:
        session["degraded_count"] = session.get("degraded_count", 0) + 1

    progressed = False
    task_completed = False
    segment_grade = None
    support_level = "none"
    should_score = bool(
        not analysis.get("degraded")
        and not speech_degraded
        and expected_mode == "repeat"
        and user_act == "repeat"
        and input_mode == "audio"
        and pronunciation
    )

    if speech_degraded:
        reply = "I couldn't check that recording clearly. Please read the same sentence once more."
        task_action = "retry"
        pronunciation = None
    elif analysis.get("degraded") and user_act in {"answer", "repeat", "off_topic", "unclear"}:
        reply = f"I heard you. Let's stay here and try once more: {pending.get('prompt', '')}"
        task_action = "stay"
        pronunciation = None
    elif user_act == "question":
        reply = f"{analysis.get('reply') or 'That is a good question.'} Now, let's go back: {pending.get('prompt', '')}"
        task_action = "pause_and_resume"
    elif user_act == "help_request":
        pending["attempts"] = pending.get("attempts", 0) + 1
        pending["hint_level"] = max(1, pending.get("hint_level", 0))
        support_level = "hint"
        reply = f"{analysis.get('reply') or 'No problem.'} {_hint_for(pending.get('target_text', ''))}"
        task_action = "hint"
    elif user_act == "skip":
        reply, segment_grade = _skip_activity(session, lesson)
        progressed = True
        task_action = "advance"
    elif (
        analysis.get("semantic_result") == "valid"
        and (
            (expected_mode == "repeat" and user_act == "repeat")
            or (expected_mode != "repeat" and user_act == "answer")
        )
    ):
        if expected_mode == "repeat" and pronunciation:
            score = pronunciation.get("score") or pronunciation.get("accuracy") or 0
            if score < 85 and pending.get("repeat_attempts", 0) < 1:
                pending["repeat_attempts"] = pending.get("repeat_attempts", 0) + 1
                reply = _repeat_feedback(pronunciation)
                support_level = "demo"
                task_action = "retry"
            else:
                reply, segment_grade = _complete_activity(session, lesson, analysis, pronunciation)
                progressed = task_completed = True
                support_level = "demo" if pending.get("hint_level", 0) >= 2 else "none"
                task_action = "advance"
        else:
            reply, segment_grade = _complete_activity(session, lesson, analysis, pronunciation)
            progressed = task_completed = True
            support_level = "hint" if pending.get("hint_level", 0) == 1 else ("demo" if pending.get("hint_level", 0) >= 2 else "none")
            task_action = "advance"
    else:
        pending["attempts"] = pending.get("attempts", 0) + 1
        if pending["attempts"] >= 2:
            pending["hint_level"] = 2
            pending["expected_mode"] = "repeat"
            reply = f"Let's try together. Repeat after me: {pending.get('target_text', '')}"
            support_level = "demo"
            task_action = "demo"
        else:
            pending["hint_level"] = max(1, pending.get("hint_level", 0))
            reply = f"{analysis.get('reply') or 'Let us try again.'} {_hint_for(pending.get('target_text', ''))}"
            support_level = "hint"
            task_action = "hint"

    if pronunciation:
        student_event["pronunciation"] = pronunciation
        weak = pronunciation.get("weak_words") or []
        for word in weak:
            if word not in session["grades"]["weak"]:
                session["grades"]["weak"].append(word)

    current_pending = session.get("pending") or pending
    ai_event = _append_event(
        session,
        "ai",
        reply,
        segment_idx=current_pending.get("segment_idx", session.get("segment_idx", 0)),
        activity_id=current_pending.get("id"),
    )
    return {
        "session": public_session(session),
        "turn": {
            "user_act": user_act,
            "language": analysis.get("language", "en"),
            "semantic_result": analysis.get("semantic_result", "not_applicable"),
            "expected_mode": expected_mode,
            "progressed": progressed,
            "task_completed": task_completed,
            "should_score": should_score,
            "support_level": support_level,
            "task_action": task_action,
            "degraded": bool(analysis.get("degraded")),
            "speech_degraded": speech_degraded,
        },
        "ai_message": {"text": ai_event["text"], "role": "teacher", "segment": current_pending.get("segment_code", pending.get("segment_code"))},
        "pronunciation": pronunciation if should_score else None,
        "segment_grade": segment_grade,
        "degraded": bool(analysis.get("degraded") or speech_degraded),
    }
