# -*- coding: utf-8 -*-
"""英语口语陪练网站 · 后端主程序(FastAPI)

运行:python server.py  →  http://localhost:8000
- 无 API Key 时全链路 mock 可跑(教案解析 / 会话 / 发音评估 / TTS)
- 配置 .env 后自动切换真实服务(DeepSeek / Azure 语音)
"""

import json
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import azure_speech, llm, storage

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"


def _load_env():
    """启动时把 .env 注入环境变量(不依赖第三方包),使设置页保存的 Key 生效。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

app = FastAPI(title="英语口语陪练", version="0.1.0")


def _config() -> dict:
    try:
        return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _pin() -> str:
    env_pin = (os.getenv("PARENT_PIN") or "").strip()
    return env_pin or str(_config().get("pin", "1234"))


# ---------------------------------------------------------------- 状态
@app.get("/api/status")
def api_status():
    return {
        "ok": True,
        "student": _config().get("student", {}),
        "deepseek": "mock" if not llm.enabled() else "live",
        "azure": azure_speech.status(),
        "courses": len(storage.list_courses()),
        "sessions": len(storage.list_sessions()),
    }


# ---------------------------------------------------------------- 家长验证
@app.post("/api/parent/verify")
def parent_verify(pin: str = Form(...)):
    if pin == _pin():
        return {"ok": True}
    return JSONResponse({"ok": False, "error": "PIN 不正确"}, status_code=403)


# ---------------------------------------------------------------- 教案上传
@app.post("/api/lessons/upload")
async def lesson_upload(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        lesson = llm.parse_lesson(file.filename, raw)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    storage.save_upload(file.filename, raw)  # 原始文件归档
    if lesson.get("image_pending"):
        return {"ok": True, "preview": lesson, "pending_image": True}
    return {"ok": True, "preview": lesson}


@app.post("/api/lessons")
def lesson_confirm(payload: dict):
    """确认预览教案入库为课程。"""
    lesson = payload.get("lesson", {})
    if not lesson.get("title_zh") or not lesson.get("segments"):
        return JSONResponse({"ok": False, "error": "教案缺少标题或环节,请重新上传"}, status_code=400)
    course = storage.save_course(lesson)
    return {"ok": True, "course": course}


@app.get("/api/lessons")
def lessons_list():
    return {"ok": True, "courses": storage.list_courses()}


@app.delete("/api/lessons/{course_id}")
def lesson_delete(course_id: str):
    if not storage.get_course(course_id):
        return JSONResponse({"ok": False, "error": "课程不存在"}, status_code=404)
    storage.delete_course(course_id)
    return {"ok": True}


# ---------------------------------------------------------------- 学习会话
def _course_ctx(course: dict) -> dict:
    """课程上下文:附加家长确认过的复习包(仅本次会话使用,不改存储)。"""
    pack = storage.get_review_pack()
    if pack.get("errors"):
        return {**course, "review_errors": pack["errors"]}
    return course


@app.post("/api/chat/session")
def chat_session(payload: dict):
    """开始一个新会话:选课程 → 返回开场白。"""
    course = storage.get_course(payload.get("course_id", ""))
    if not course:
        return JSONResponse({"ok": False, "error": "课程不存在"}, status_code=404)
    ctx = _course_ctx(course)
    session = {
        "id": uuid.uuid4().hex[:10],
        "course_id": course["id"],
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "segment_idx": 0,
        "exchanges": [],
        "grades": {"segments": {}, "weak": []},
        "done": False,
        "has_review": bool(ctx.get("review_errors")),
    }
    return {
        "ok": True,
        "session": session,
        "ai_message": llm.teacher_first_message(ctx),
        "segment": ctx["segments"][0] if ctx.get("segments") else {},
        "review_count": len(ctx.get("review_errors", [])),
    }


@app.post("/api/recognize")
async def recognize(audio: UploadFile | None = File(None), expected: str = Form("")):
    """识别孩子音频。mock:直接返回预期句。"""
    raw = await audio.read() if audio else b""
    result = azure_speech.recognize(raw, expected=expected)
    storage.add_usage(stt_seconds=max(3, len(expected.split()) * 2))
    return {"ok": True, **result}


def _mock_grade(feedback: dict) -> str:
    """按发音评估结果给环节评级:A 独立 / B 提示 / C 示范 / D 未完成(mock)。"""
    overall = feedback.get("overall", 0)
    weak_count = len(feedback.get("weak", []))
    if overall >= 88 and weak_count == 0:
        return "A"
    if overall >= 78:
        return "B"
    if overall >= 65:
        return "C"
    return "D"


@app.post("/api/chat/reply")
def chat_reply(payload: dict):
    """孩子说话后:发音评估 + AI 回应。"""
    session = payload.get("session", {})
    student_text = (payload.get("text") or "").strip()
    course = storage.get_course(session.get("course_id", ""))
    if not course:
        return JSONResponse({"ok": False, "error": "课程不存在"}, status_code=404)
    ctx = _course_ctx(course)

    total = len(course.get("segments", []))
    segment_idx = session.get("segment_idx", 0)
    seg_key = course["segments"][segment_idx]["code"] if segment_idx < total else "REVIEW"

    words = azure_speech.pronunciation(student_text)
    feedback = {
        "words": words,
        "overall": round(sum(w["score"] for w in words) / len(words)) if words else 0,
        "weak": [w["word"] for w in words if w["label"] == "weak"],
    }

    ai = llm.teacher_reply(ctx, segment_idx, student_text, session.get("exchanges", []))
    new_segment_idx = segment_idx + 1 if ai.get("next_segment") else segment_idx
    grade = _mock_grade(feedback)

    session["exchanges"].append({"role": "ai", "text": ai["text"]})
    session["exchanges"].append({
        "role": "student", "text": student_text, "feedback": feedback,
        "segment_idx": segment_idx,
    })
    session["segment_idx"] = new_segment_idx
    session["grades"]["segments"][seg_key] = grade
    session["done"] = bool(ai.get("done"))
    seg_name = ""
    if segment_idx < total:
        seg_name = course["segments"][segment_idx].get("name_zh", "") or course["segments"][segment_idx].get("code", "")
    elif ai.get("review_start"):
        seg_name = "往期易错点"
    return {
        "ok": True,
        "session": session,
        "ai_message": ai,
        "feedback": feedback,
        "grade": grade,
        "segment_name": seg_name,
        "encouragement": _encouragement(grade),
    }


def _encouragement(grade: str) -> str:
    """按评级给鼓励文案(孩子优先,绝不批评)。"""
    return {
        "A": "🌟 完美!发音清晰又准确",
        "B": "👍 很棒!继续保持",
        "C": "💪 不错,再练一次会更好",
        "D": "🌱 没关系,多说就熟悉了",
    }.get(grade, "👍 收到!")


@app.post("/api/summary")
def summary(payload: dict):
    """结束会话:生成跟读记录并入库。"""
    session = payload.get("session", {})
    course = storage.get_course(session.get("course_id", ""))
    if not course:
        return JSONResponse({"ok": False, "error": "课程不存在"}, status_code=404)
    record = llm.generate_record(course, session.get("exchanges", []), session.get("grades", {}))
    record["id"] = uuid.uuid4().hex[:10]
    record["date"] = time.strftime("%Y-%m-%d %H:%M")
    record["duration_min"] = payload.get("duration_min", 0)
    session["grades"].setdefault("weak", record["summary"]["error_points"][:2])
    storage.save_session({"id": record["id"], **record, "raw": session})
    return {"ok": True, "record": record}


# ---------------------------------------------------------------- 易错点复习包(家长确认)
@app.get("/api/review/errors")
def review_errors():
    """往期易错点聚合(供家长勾选确认)。"""
    return {"ok": True, "errors": storage.review_errors_from_sessions()}


@app.get("/api/review/pack")
def review_pack_get():
    return {"ok": True, "pack": storage.get_review_pack()}


@app.post("/api/review/pack")
def review_pack_save(payload: dict):
    """家长确认后的复习包:{errors: [{text, drill, source}]}。"""
    errors = payload.get("errors", [])
    if len(errors) > 6:
        return JSONResponse({"ok": False, "error": "复习内容最多选 6 条,避免负担过重"}, status_code=400)
    pack = {"errors": errors}
    storage.save_review_pack(pack)
    return {"ok": True, "pack": storage.get_review_pack()}


# ---------------------------------------------------------------- 会话记录
@app.get("/api/sessions")
def sessions_list():
    records = []
    for s in storage.list_sessions():
        records.append({
            "id": s["id"],
            "course_title": s.get("course_title", ""),
            "date": s.get("date", ""),
            "segments_grades": s.get("segments_grades", {}),
            "duration_min": s.get("duration_min", 0),
        })
    return {"ok": True, "records": records}


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: str):
    s = storage.get_session(session_id)
    if not s:
        return JSONResponse({"ok": False, "error": "记录不存在"}, status_code=404)
    return {"ok": True, "record": s}


# ---------------------------------------------------------------- 设置 / 用量
@app.get("/api/config")
def api_config():
    return {
        "ok": True,
        "student": _config().get("student", {}),
        "mock": not (llm.enabled() or azure_speech.enabled()),
        "deepseek": llm.enabled(),
        "azure": azure_speech.enabled(),
    }


@app.post("/api/config/keys")
def save_keys(payload: dict):
    """保存 Key 到 .env(本地)。"""
    lines = []
    env_file = ROOT / ".env"
    env = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env["DEEPSEEK_API_KEY"] = payload.get("deepseek_key", env.get("DEEPSEEK_API_KEY", ""))
    env["AZURE_SPEECH_KEY"] = payload.get("azure_key", env.get("AZURE_SPEECH_KEY", ""))
    env["AZURE_SPEECH_REGION"] = payload.get("azure_region", env.get("AZURE_SPEECH_REGION", "eastasia"))
    for k, v in env.items():
        lines.append(f"{k}={v}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "note": "已保存。需重启服务生效。"}


@app.get("/api/usage")
def usage():
    return {"ok": True, "usage": storage.get_usage()}


# ---------------------------------------------------------------- 静态页面
app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("英语口语陪练 · http://localhost:8000")
    print(f"  DeepSeek : {'LIVE' if llm.enabled() else 'mock'}")
    print(f"  Azure    : {'LIVE' if azure_speech.enabled() else 'mock'}")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
