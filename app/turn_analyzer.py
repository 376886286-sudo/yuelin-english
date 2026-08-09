# -*- coding: utf-8 -*-
"""Structured student-turn analysis with deterministic safety guards."""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher

from . import llm

logger = logging.getLogger(__name__)

USER_ACTS = {"answer", "question", "repeat", "help_request", "off_topic", "unclear", "skip"}
SEMANTIC_RESULTS = {"valid", "invalid", "not_applicable"}


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in (text or ""))


def _language(text: str) -> str:
    has_zh = _has_chinese(text)
    has_en = bool(re.search(r"[A-Za-z]", text or ""))
    if has_zh and has_en:
        return "mixed"
    return "zh" if has_zh else "en"


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", (text or "").lower()))


def _looks_help(text: str) -> bool:
    low = (text or "").lower()
    return any(
        token in low
        for token in (
            "i don't know",
            "i do not know",
            "how to say",
            "help me",
            "can't answer",
            "cannot answer",
            "不会说",
            "不知道怎么",
            "怎么说",
            "帮帮我",
            "没听懂",
            "没听清",
        )
    )


def _looks_skip(text: str) -> bool:
    low = (text or "").lower().strip()
    return low in {"skip", "next", "pass"} or any(x in low for x in ("跳过", "下一个", "不想做"))


def _looks_question(text: str) -> bool:
    raw = (text or "").strip()
    low = raw.lower()
    if "?" in raw or "？" in raw:
        return True
    if re.match(r"^(what|why|how|where|who|when|which|can|could|do|does|did|is|are|am|will|would)\b", low):
        return True
    return any(x in raw for x in ("什么意思", "为什么", "是什么", "能不能", "可以吗", "怎么用"))


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalized(left), _normalized(right)).ratio()


def _semantic_valid(pending: dict, text: str) -> bool:
    norm = _normalized(text)
    if not norm or norm in {"hmm", "um", "uh", "i don't know", "i do not know"}:
        return False
    prompt = (pending.get("prompt") or "").lower()
    target = pending.get("target_text") or ""

    if pending.get("expected_mode") == "repeat":
        return _similarity(text, target) >= 0.55
    if "name" in prompt:
        return bool(re.search(r"\b(my name is|i am|i'm)\b", norm)) or (len(norm.split()) <= 3 and norm not in {"good", "fine", "okay"})
    if "feel" in prompt:
        moods = {"good", "great", "fine", "okay", "happy", "sad", "worried", "excited", "angry", "tired", "scared"}
        return bool(moods.intersection(norm.split())) or "feel" in norm
    if "matter" in prompt:
        return len(norm.split()) >= 2
    if "where" in prompt:
        return bool({"in", "on", "under", "behind", "beside", "near", "here", "there"}.intersection(norm.split()))
    if prompt.startswith(("is ", "are ", "do ", "does ", "can ")):
        return bool({"yes", "no", "sure"}.intersection(norm.split()))
    if "nice to meet" in prompt:
        return "meet" in norm or "too" in norm
    if "old" in prompt or "age" in prompt:
        return bool(re.search(r"\b\d+\b", norm) or re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b", norm))
    return len(norm.split()) >= 1


def _word_meaning_answer(text: str) -> str:
    low = (text or "").lower()
    match = re.search(r"(?:what does\s+|['\"]?)([a-z][a-z'-]+)['\"]?\s+(?:mean|是什么意思)", low)
    if not match:
        match = re.search(r"([a-z][a-z'-]+)\s*是什么意思", low)
    word = match.group(1) if match else ""
    meanings = {
        "name": "Name means the word people use to call you, like Yuelin.",
        "worried": "Worried means feeling afraid or uneasy about something.",
        "excited": "Excited means feeling very happy and eager about something.",
        "angry": "Angry means feeling mad or upset.",
        "happy": "Happy means feeling good and pleased.",
    }
    if word in meanings:
        return meanings[word]
    return "That's a good question. I'll help you with it."


def _rule_analysis(pending: dict, student_text: str) -> dict:
    language = _language(student_text)
    if _looks_skip(student_text):
        return {"user_act": "skip", "language": language, "semantic_result": "not_applicable", "reply": "Okay, we can move on.", "degraded": False}
    if _looks_help(student_text):
        return {"user_act": "help_request", "language": language, "semantic_result": "not_applicable", "reply": "No problem. Here's a little hint.", "degraded": False}
    if _looks_question(student_text):
        return {"user_act": "question", "language": language, "semantic_result": "not_applicable", "reply": _word_meaning_answer(student_text), "degraded": False}
    if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", student_text or ""):
        return {"user_act": "unclear", "language": language, "semantic_result": "invalid", "reply": "I didn't catch that yet.", "degraded": False}
    expected = pending.get("expected_mode")
    act = "repeat" if expected == "repeat" else "answer"
    valid = _semantic_valid(pending, student_text)
    return {
        "user_act": act if valid else "unclear",
        "language": language,
        "semantic_result": "valid" if valid else "invalid",
        "reply": "Great!" if valid else "Let's try it one more time.",
        "degraded": False,
    }


def _system_prompt() -> str:
    return (
        "You are the turn analyzer for an elementary-school English tutor. "
        "Classify what the child is doing before writing a reply. Return strict JSON only with keys: "
        "user_act (answer/question/repeat/help_request/off_topic/unclear/skip), "
        "language (en/zh/mixed), semantic_result (valid/invalid/not_applicable), and reply. "
        "A question or help request never completes the pending task. For a valid answer, reply is only a short acknowledgement or gentle correction; do not invent the next lesson prompt. "
        "For a question, answer it simply in at most two short sentences."
    )


def analyze_turn(pending: dict, student_text: str, history: list[dict] | None = None) -> dict:
    """Return validated analysis. Explicit interrupts are guarded by local rules."""
    fallback = _rule_analysis(pending, student_text)
    if not llm.enabled():
        return fallback

    payload = {
        "pending_task": {
            "activity_id": pending.get("id"),
            "prompt": pending.get("prompt"),
            "expected_mode": pending.get("expected_mode"),
            "target_text": pending.get("target_text"),
            "hint_level": pending.get("hint_level", 0),
        },
        "recent_history": [
            {"role": e.get("role"), "text": e.get("text")}
            for e in (history or [])[-6:]
        ],
        "student_text": student_text,
    }
    try:
        data = llm.chat_json(_system_prompt(), json.dumps(payload, ensure_ascii=False), max_tokens=320)
        if not isinstance(data, dict):
            raise ValueError("turn analysis is not an object")
        user_act = data.get("user_act") if data.get("user_act") in USER_ACTS else fallback["user_act"]
        semantic = data.get("semantic_result") if data.get("semantic_result") in SEMANTIC_RESULTS else fallback["semantic_result"]

        # Explicit question/help/skip signals are deterministic safety guards.
        if fallback["user_act"] in {"question", "help_request", "skip"}:
            user_act = fallback["user_act"]
            semantic = fallback["semantic_result"]
        elif pending.get("expected_mode") == "repeat" and fallback["user_act"] == "repeat":
            # A model calling a scripted repetition an "answer" must not bypass
            # the pronunciation branch.
            user_act = "repeat"
            semantic = fallback["semantic_result"]
        reply = str(data.get("reply") or fallback["reply"]).strip()[:500]
        return {
            "user_act": user_act,
            "language": data.get("language") if data.get("language") in {"en", "zh", "mixed"} else fallback["language"],
            "semantic_result": semantic,
            "reply": reply,
            "degraded": False,
        }
    except Exception as exc:  # noqa: BLE001 - fallback must keep the lesson safe
        logger.warning("Turn analyzer degraded (%s)", type(exc).__name__)
        return {**fallback, "degraded": True, "degraded_reason": type(exc).__name__}
