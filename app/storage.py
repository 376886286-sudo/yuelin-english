# -*- coding: utf-8 -*-
"""本地 JSON 存储:课程库 / 会话记录 / 设置。"""

import json
import time
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COURSES_FILE = DATA_DIR / "courses.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
UPLOADS_DIR = DATA_DIR / "uploads"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- 课程库
def list_courses() -> list:
    return _load(COURSES_FILE, [])


def get_course(course_id: str) -> dict | None:
    for c in list_courses():
        if c["id"] == course_id:
            return c
    return None


def save_course(lesson: dict, preview: bool = False) -> dict:
    courses = list_courses()
    course = {
        "id": uuid.uuid4().hex[:10],
        "created": _now(),
        "preview": preview,
        **lesson,
    }
    courses.append(course)
    _save(COURSES_FILE, courses)
    return course


def delete_course(course_id: str) -> bool:
    courses = [c for c in list_courses() if c["id"] != course_id]
    _save(COURSES_FILE, courses)
    return True


# ---------------------------------------------------------------- 会话记录
def list_sessions() -> list:
    return _load(SESSIONS_FILE, [])


def get_session(session_id: str) -> dict | None:
    for s in list_sessions():
        if s["id"] == session_id:
            return s
    return None


def save_session(session: dict) -> dict:
    sessions = list_sessions()
    sessions.append(session)
    _save(SESSIONS_FILE, sessions)
    return session


# ---------------------------------------------------------------- 设置
def get_settings() -> dict:
    return _load(DATA_DIR / "settings.json", {})


def save_settings(settings: dict):
    _save(DATA_DIR / "settings.json", settings)


# ---------------------------------------------------------------- 易错点复习包
def get_review_pack() -> dict:
    """当前复习包:{errors: [{text, drill, source}], updated: str}。家长确认后写入。"""
    return _load(DATA_DIR / "review_pack.json", {"errors": [], "updated": ""})


def save_review_pack(pack: dict):
    pack["updated"] = _now()
    _save(DATA_DIR / "review_pack.json", pack)


def review_errors_from_sessions() -> list:
    """聚合所有历史记录的易错点(去重),供家长挑选。
    每项含易错点描述 text、配套跟读句 drill、来源 source。"""
    seen, out = set(), []
    for s in list_sessions():
        weak_lines = s.get("weak_lines", []) or []
        source = f"{s.get('course_title', '')} · {s.get('date', '')}"
        if weak_lines:
            for line in weak_lines:
                key = line.lower()
                if key not in seen:
                    seen.add(key)
                    out.append({"text": line, "drill": line, "source": source})
        for point in (s.get("summary", {}) or {}).get("error_points", []):
            key = "P:" + point
            if key not in seen:
                seen.add(key)
                out.append({"text": point, "drill": "", "source": source})
    return out


# ---------------------------------------------------------------- 用量
def get_usage() -> dict:
    data = _load(DATA_DIR / "usage.json", {})
    month = time.strftime("%Y-%m")
    if data.get("month") != month:
        data = {"month": month, "stt_seconds": 0, "tts_chars": 0, "pron_seconds": 0}
    return data


def add_usage(**delta):
    usage = get_usage()
    for k, v in delta.items():
        usage[k] = usage.get(k, 0) + v
    _save(DATA_DIR / "usage.json", usage)
    return usage


def save_upload(filename: str, raw: bytes) -> Path:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe = filename.replace("\\", "_").replace("/", "_")
    path = UPLOADS_DIR / f"{uuid.uuid4().hex[:6]}_{safe}"
    path.write_bytes(raw)
    return path
