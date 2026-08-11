# -*- coding: utf-8 -*-
"""Semantic turn decisions for a child-friendly English tutor.

DeepSeek understands the child's intent and drafts a natural response.  This
module never advances lesson state; deterministic progression stays in
``dialogue_manager`` and ``lesson_engine``.
"""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher

from . import llm

logger = logging.getLogger(__name__)

INTENTS = {
    "answer",
    "question",
    "repeat_attempt",
    "help_request",
    "free_talk",
    "off_topic",
    "unclear",
    "skip",
}
ANSWER_QUALITIES = {"correct", "understandable", "needs_recast", "not_applicable"}
RESPONSE_ACTIONS = {
    "acknowledge",
    "recast_then_continue",
    "answer_then_resume",
    "hint_then_resume",
    "chat_then_resume",
    "redirect_then_resume",
    "clarify",
    "skip",
}


def expected_action(pending: dict) -> str:
    return str(pending.get("expected_action") or pending.get("expected_mode") or "open_answer")


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
            "say it again",
            "不会说",
            "不知道怎么",
            "怎么说",
            "帮帮我",
            "没听懂",
            "没听清",
            "再说一遍",
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
    target = pending.get("reference_text") or pending.get("target_text") or ""

    if expected_action(pending) == "repeat":
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
        "meet": "Meet means to see someone and get to know them. 中文是‘见面、认识’。",
        "worried": "Worried means feeling afraid or uneasy about something. 中文是‘担心的’。",
        "excited": "Excited means feeling very happy and eager about something. 中文是‘兴奋的’。",
        "angry": "Angry means feeling mad or upset. 中文是‘生气的’。",
        "happy": "Happy means feeling good and pleased. 中文是‘开心的’。",
        "under": "Under means below something. 中文是‘在……下面’。",
    }
    return meanings.get(word, "That's a good question. Tell me which word you want to know, and I'll explain it simply.")


def _natural_recast(text: str) -> str:
    raw = (text or "").strip().rstrip(".!?")
    low = raw.lower()
    if re.match(r"^my\s+\w+\s+(under|on|in|behind|near)\b", low):
        words = raw.split()
        return " ".join(words[:2] + ["is"] + words[2:]) + "."
    if re.match(r"^i\s+(happy|sad|worried|excited|angry|tired)\b", low):
        words = raw.split()
        return " ".join([words[0], "am", *words[1:]]) + "."
    if re.match(r"^my name\s+(?!is\b)[a-z]", low):
        return re.sub(r"^my name\s+", "My name is ", raw, flags=re.IGNORECASE) + "."
    return ""


def _rule_decision(pending: dict, student_text: str) -> dict:
    language = _language(student_text)
    base = {
        "language": language,
        "understood": True,
        "task_relevant": False,
        "task_completed": False,
        "answer_quality": "not_applicable",
        "corrected_text": "",
        "resume_task": True,
        "degraded": False,
    }
    if _looks_skip(student_text):
        return {**base, "intent": "skip", "response_action": "skip", "response_text": "Okay, we can move on.", "resume_task": False, "semantic_result": "not_applicable"}
    if _looks_help(student_text):
        return {**base, "intent": "help_request", "response_action": "hint_then_resume", "response_text": "No problem. Let's make it easier together.", "semantic_result": "not_applicable"}
    if _looks_question(student_text):
        return {**base, "intent": "question", "response_action": "answer_then_resume", "response_text": _word_meaning_answer(student_text), "semantic_result": "not_applicable"}
    if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", student_text or ""):
        return {**base, "intent": "unclear", "understood": False, "response_action": "clarify", "response_text": "I didn't quite catch that. Can you say it one more time?", "semantic_result": "invalid"}

    valid = _semantic_valid(pending, student_text)
    if expected_action(pending) == "repeat":
        intent = "repeat_attempt" if valid else "unclear"
    elif valid:
        intent = "answer"
    else:
        explicit_off_topic = any(token in (student_text or "").lower() for token in ("minecraft", "roblox", "youtube", "数学作业", "王者荣耀"))
        intent = "off_topic" if explicit_off_topic else ("free_talk" if len(_normalized(student_text).split()) >= 3 else "unclear")

    corrected = _natural_recast(student_text) if intent == "answer" else ""
    quality = "needs_recast" if corrected else ("correct" if valid else "not_applicable")
    if intent == "answer":
        response = f"Good! A natural way to say it is: {corrected}" if corrected else "Nice! I understood you."
        action = "recast_then_continue" if corrected else "acknowledge"
    elif intent == "repeat_attempt":
        response, action = "Nice try!", "acknowledge"
    elif intent == "free_talk":
        response, action = "That sounds interesting! Let's keep that thought and come back to our question.", "chat_then_resume"
    elif intent == "off_topic":
        response, action = "That sounds fun! Let's finish this little English challenge first.", "redirect_then_resume"
    else:
        response, action = "Let's try it one more time.", "clarify"
    return {
        **base,
        "intent": intent,
        "task_relevant": intent in {"answer", "repeat_attempt"},
        "task_completed": valid and intent in {"answer", "repeat_attempt"},
        "answer_quality": quality,
        "corrected_text": corrected,
        "response_action": action,
        "response_text": response,
        "semantic_result": "valid" if valid else ("not_applicable" if intent in {"free_talk", "off_topic"} else "invalid"),
    }


def _system_prompt() -> str:
    return (
        "You are the turn manager for Yuelin, a primary-school English learner. Return strict JSON only. "
        "Classify intent as answer, question, repeat_attempt, help_request, free_talk, off_topic, unclear, or skip. "
        "Return keys: intent, understood, task_relevant, task_completed, answer_quality "
        "(correct/understandable/needs_recast/not_applicable), response_action, response_text, corrected_text, resume_task, language. "
        "Questions, help, free talk, and off-topic talk never complete the pending task. A repeat_attempt is possible only when expected_action is repeat. "
        "Be warm, curious, and concise. For a real answer with a small grammar error, understand the meaning first and use a gentle natural recast; never give a grammar lecture. "
        "Do not ask the next lesson question in response_text because the deterministic lesson engine will add it. "
        "For a child question, answer simply in English and add brief Chinese only when it helps. Keep response_text to at most two short sentences."
    )


def _safe_failure(fallback: dict, reason: str) -> dict:
    return {
        **fallback,
        "intent": "unclear",
        "task_completed": False,
        "semantic_result": "invalid",
        "response_action": "clarify",
        "response_text": "I heard you, but I need one more try to understand. Can you say it again?",
        "degraded": True,
        "degraded_reason": reason,
    }


def analyze_turn(pending: dict, student_text: str, history: list[dict] | None = None) -> dict:
    """Return a validated semantic decision; lesson progression is not mutated."""
    fallback = _rule_decision(pending, student_text)
    if not llm.enabled():
        return {**fallback, "user_act": fallback["intent"], "reply": fallback["response_text"]}

    payload = {
        "pending_task": {
            "activity_id": pending.get("id"),
            "prompt": pending.get("prompt"),
            "expected_action": expected_action(pending),
            "reference_text": pending.get("reference_text") or pending.get("target_text"),
            "assistance_level": pending.get("assistance_level", "none"),
            "attempt_count": pending.get("attempt_count", pending.get("attempts", 0)),
        },
        "recent_history": [
            {"role": "assistant" if e.get("role") == "ai" else "user", "content": e.get("text")}
            for e in (history or [])[-10:]
        ],
        "student_text": student_text,
    }
    try:
        data = llm.chat_json(_system_prompt(), json.dumps(payload, ensure_ascii=False), max_tokens=420, retries=1)
        intent = data.get("intent") if data.get("intent") in INTENTS else fallback["intent"]

        # Deterministic interruption and repeat guards always win.
        if fallback["intent"] in {"question", "help_request", "skip"}:
            intent = fallback["intent"]
        elif expected_action(pending) == "repeat" and fallback["intent"] == "repeat_attempt":
            intent = "repeat_attempt"
        elif expected_action(pending) != "repeat" and intent == "repeat_attempt":
            intent = "answer" if fallback["intent"] == "answer" else fallback["intent"]

        task_completed = bool(data.get("task_completed"))
        if intent not in {"answer", "repeat_attempt"}:
            task_completed = False
        if expected_action(pending) == "repeat" and intent != "repeat_attempt":
            task_completed = False
        if expected_action(pending) != "repeat" and intent == "repeat_attempt":
            task_completed = False

        quality = data.get("answer_quality") if data.get("answer_quality") in ANSWER_QUALITIES else fallback["answer_quality"]
        action = data.get("response_action") if data.get("response_action") in RESPONSE_ACTIONS else fallback["response_action"]
        corrected = str(data.get("corrected_text") or fallback.get("corrected_text") or "").strip()[:180]
        response = str(data.get("response_text") or fallback["response_text"]).strip()[:500]
        semantic = "valid" if task_completed else ("not_applicable" if intent in {"question", "help_request", "free_talk", "off_topic", "skip"} else "invalid")
        decision = {
            "intent": intent,
            "user_act": intent,
            "language": data.get("language") if data.get("language") in {"en", "zh", "mixed"} else fallback["language"],
            "understood": bool(data.get("understood", fallback["understood"])),
            "task_relevant": bool(data.get("task_relevant", fallback["task_relevant"])),
            "task_completed": task_completed,
            "semantic_result": semantic,
            "answer_quality": quality,
            "response_action": action,
            "response_text": response,
            "reply": response,
            "corrected_text": corrected,
            "resume_task": bool(data.get("resume_task", True)),
            "degraded": False,
        }
        return decision
    except Exception as exc:  # noqa: BLE001 - classroom must fail safely
        logger.warning("Turn manager degraded (%s)", type(exc).__name__)
        failed = _safe_failure(fallback, type(exc).__name__)
        return {**failed, "user_act": failed["intent"], "reply": failed["response_text"]}
