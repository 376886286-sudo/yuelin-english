# -*- coding: utf-8 -*-
"""DeepSeek V4 Flash client and non-realtime learning summaries.

Realtime classroom turns always use non-thinking mode.  Slower tasks such as
session summaries may opt into thinking mode through ``chat_reasoning``.
"""

from __future__ import annotations

import json
import os

import httpx

from . import parser

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
# Kept as a public compatibility constant; requests use model_name() so values
# loaded from .env after module import are still honoured.
MODEL = DEFAULT_MODEL


def _key() -> str:
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


def model_name() -> str:
    return (os.getenv("DEEPSEEK_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def enabled() -> bool:
    return bool(_key())


def _completion(
    system: str,
    user: str,
    *,
    thinking: str,
    max_tokens: int,
    temperature: float,
    response_format: dict | None = None,
) -> str:
    body = {
        "model": model_name(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "thinking": {"type": thinking},
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        body["response_format"] = response_format
    resp = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    content = ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content")
    content = str(content or "").strip()
    if not content:
        raise ValueError("DeepSeek returned empty content")
    return content


def chat_fast(system: str, user: str, max_tokens: int = 1200, temperature: float = 0.55) -> str:
    """Low-latency classroom call: V4 Flash with thinking disabled."""
    return _completion(
        system,
        user,
        thinking="disabled",
        max_tokens=max_tokens,
        temperature=temperature,
    )


def chat_reasoning(system: str, user: str, max_tokens: int = 1200, temperature: float = 0.35) -> str:
    """Non-realtime call for summaries, validation, and review planning."""
    return _completion(
        system,
        user,
        thinking="enabled",
        max_tokens=max_tokens,
        temperature=temperature,
    )


def _decode_json(content: str) -> dict:
    if content.startswith("```"):
        content = content.strip("`").removeprefix("json").strip()
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("DeepSeek JSON output must be an object")
    return data


def chat_json(system: str, user: str, max_tokens: int = 600, retries: int = 1) -> dict:
    """V4 Flash JSON Output with one retry for empty or invalid content."""
    last_error: Exception | None = None
    for _ in range(max(0, retries) + 1):
        try:
            content = _completion(
                system,
                user,
                thinking="disabled",
                max_tokens=max_tokens,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return _decode_json(content)
        except (ValueError, json.JSONDecodeError, httpx.HTTPError) as exc:
            last_error = exc
    raise last_error or ValueError("DeepSeek JSON output failed")


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in (text or ""))


def translate_zh(text: str) -> str:
    """English to child-friendly Chinese for the translation button."""
    if not enabled() or not text:
        return ""
    system = (
        "你是儿童英语学习助手。把英文翻译成简单、口语化的中文，适合 8-10 岁孩子看懂。"
        "只输出译文，不要解释、不要加引号。"
    )
    try:
        return chat_fast(system, text, max_tokens=200, temperature=0.2)
    except Exception:
        return ""


def parse_lesson(filename: str, raw: bytes) -> dict:
    """Parse lesson files through the local deterministic parser."""
    lesson = parser.parse_lesson_file(filename, raw)
    if lesson.get("source_type") == "image" and enabled():
        # Reserved for a future vision-capable lesson parser.
        pass
    return lesson


def generate_record(
    lesson: dict,
    exchanges: list,
    grades: dict,
    activity_results: dict | None = None,
    coaching_notes: list[dict] | None = None,
) -> dict:
    """Generate an evidence-based session record without inventing errors."""
    seg_names = [s.get("name_zh", s.get("code", "")) for s in lesson.get("segments", [])]
    student_lines = [e["text"] for e in exchanges if e.get("role") == "student"]
    weak_lines = [
        e["text"]
        for e in exchanges
        if e.get("role") == "student"
        and any(w.get("label") == "weak" for w in (e.get("pronunciation", {}) or {}).get("words", []))
    ]
    weak = grades.get("weak", [])
    activity_results = activity_results or {}
    coaching_notes = coaching_notes or []
    support_grades = [result.get("grade") for result in activity_results.values()]
    error_points: list[str] = []
    if weak:
        error_points.append("跟读发音需要关注：" + "、".join(weak[:4]))
    for note in coaching_notes[:3]:
        corrected = (note.get("corrected_text") or "").strip()
        if corrected:
            error_points.append(f"可以更自然地说：{corrected}")
    if "B" in support_grades:
        error_points.append("部分回答需要关键词提示，下次先留出独立思考时间")
    if "C" in support_grades:
        error_points.append("部分句子在示范跟读后完成，建议隔天再独立复述")
    if "D" in support_grades:
        error_points.append("有任务本次暂未完成，下次从该任务重新开始")

    record = {
        "course_id": lesson.get("id", ""),
        "course_title": f"Unit {lesson.get('unit', '')} {lesson.get('title_zh', '')}",
        "segments_grades": grades.get("segments", {}),
        "student_lines": student_lines[:12],
        "weak_lines": weak_lines[:6],
        "coaching_notes": coaching_notes[:8],
        "summary": {
            "error_points": error_points,
            "strengths": f"完成 {len(student_lines)} 次开口，持续保持练习",
        },
        "review_plan": {
            "day1": f"重练 {seg_names[0] if seg_names else '第一环节'} 的未独立完成任务",
            "day3": "复述本次用过提示或自然纠正的句子" if coaching_notes or any(g in support_grades for g in ("B", "C")) else "用自己的说法复述本次对话",
            "day7": "三段整合对话完整走一遍",
        },
        "closing": "You took your time and kept speaking. That is real progress.",
    }
    if enabled():
        try:
            system = (
                "你是儿童英语学习记录员。只根据提供的真实证据，用简短中文总结优势、"
                "需要逐步改善的一项语法或发音问题，以及第 1/3/7 天复习建议。不要编造错误。"
            )
            user = json.dumps(
                {
                    "course": record["course_title"],
                    "segment_grades": record["segments_grades"],
                    "student_lines": record["student_lines"],
                    "coaching_notes": record["coaching_notes"],
                    "weak_words": weak[:4],
                },
                ensure_ascii=False,
            )
            record["llm_note"] = chat_reasoning(system, user, max_tokens=700)
        except Exception:
            pass
    return record
