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
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import azure_speech, dialogue_manager, lesson_contract, llm, storage

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

# Active learning state is owned by the server.  The browser sends only an id;
# any legacy session object in a request is used solely to read that id.
ACTIVE_SESSIONS: dict[str, dict] = {}
_AUDIO_CACHE: dict[str, dict] = {}
_AUDIO_TTL_SECONDS = 120


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
        "deepseek_model": llm.model_name(),
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
    errors = lesson_contract.validate_for_import(lesson)
    if errors:
        return JSONResponse({"ok": False, "error": "教案校验失败:" + "; ".join(errors[:12])}, status_code=400)
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
    session_id = uuid.uuid4().hex[:10]
    session, opening = dialogue_manager.new_session(
        ctx,
        session_id,
        time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    session["has_review"] = bool(ctx.get("review_errors"))
    session["_lesson"] = deepcopy(ctx)
    ACTIVE_SESSIONS[session_id] = session
    pending = session.get("pending") or {}
    segment_idx = pending.get("segment_idx", 0)
    return {
        "ok": True,
        "session": dialogue_manager.public_session(session),
        "ai_message": opening,
        "segment": ctx["segments"][segment_idx] if 0 <= segment_idx < len(ctx.get("segments", [])) else {"code": "REVIEW", "name_zh": "往期易错点"},
        "review_count": len(ctx.get("review_errors", [])),
    }


def _active_session_id(payload: dict) -> str:
    legacy = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    return str(payload.get("session_id") or legacy.get("id") or "").strip()


def _cache_audio(raw: bytes, session_id: str) -> str:
    now = time.time()
    for key, item in list(_AUDIO_CACHE.items()):
        if now - item.get("created", 0) > _AUDIO_TTL_SECONDS:
            _AUDIO_CACHE.pop(key, None)
    while len(_AUDIO_CACHE) >= 20:
        oldest = min(_AUDIO_CACHE, key=lambda key: _AUDIO_CACHE[key].get("created", 0))
        _AUDIO_CACHE.pop(oldest, None)
    audio_id = uuid.uuid4().hex[:12]
    _AUDIO_CACHE[audio_id] = {"raw": raw, "created": now, "session_id": session_id}
    return audio_id


@app.post("/api/recognize")
async def recognize(audio: UploadFile | None = File(None), session_id: str = Form(""), expected: str = Form("")):
    """First pass: bilingual speech-to-text only. Audio is cached briefly.

    If the subsequent turn analysis confirms a repeat action, /api/chat/reply
    reuses the cached bytes for a second, scripted pronunciation assessment.
    """
    raw = await audio.read() if audio else b""
    session = ACTIVE_SESSIONS.get(session_id)
    server_expected = ((session or {}).get("pending") or {}).get("target_text", "")
    result = azure_speech.transcribe(raw, expected=server_expected or expected)
    audio_id = _cache_audio(raw, session_id) if raw else None
    if raw:
        storage.add_usage(stt_seconds=max(3, len(raw) / 32000))
    else:
        storage.add_usage(stt_seconds=max(3, len((server_expected or expected).split()) * 2))
    return {"ok": True, **result, "audio_id": audio_id}


@app.post("/api/tts")
def tts(payload: dict):
    """AI 文本合成语音(带说话风格)。真实模式返回 mp3;失败/mock 返回 browser 标记由前端兜底。

    可选传 style(friendly/cheerful/hopeful/chat/excited/assistant)、voice(音色白名单)、
    demo(跟读示范句自然降速);style/voice 不传则后端自动处理。
    """
    text = (payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "缺少文本"}, status_code=400)
    style = payload.get("style")
    voice = payload.get("voice")
    result = azure_speech.tts(
        text,
        voice=voice if isinstance(voice, str) else "",
        style=style if isinstance(style, str) else None,
        demo=bool(payload.get("demo")),
    )
    if result.get("mode") == "azure":
        storage.add_usage(tts_chars=len(text))
        return Response(content=result["audio"], media_type="audio/mpeg")
    return {"ok": True, "mode": "browser", "text": text}


def _process_turn(session_id: str, student_text: str, input_mode: str, audio_bytes: bytes | None = None):
    """One server-owned turn: understand, optionally assess, then transition."""
    session = ACTIVE_SESSIONS.get(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "会话不存在或已过期,请重新开始"}, status_code=404)
    student_text = str(student_text or "").strip()
    if not student_text:
        return JSONResponse({"ok": False, "error": "没有识别到内容,请再说一次"}, status_code=400)
    lesson = session.get("_lesson") or _course_ctx(storage.get_course(session.get("course_id", "")) or {})
    analysis = dialogue_manager.analyze(session, student_text)
    input_mode = input_mode if input_mode in {"audio", "typed"} else "typed"
    pronunciation = None
    pending = session.get("pending") or {}
    completed_segment_name = pending.get("segment_name", "")
    expected_action = pending.get("expected_action") or pending.get("expected_mode") or "open_answer"
    intent = analysis.get("intent") or analysis.get("user_act")
    reference_text = pending.get("reference_text") or pending.get("target_text", "")

    # This is the only pronunciation trigger in the application.
    if (
        expected_action == "repeat"
        and intent in {"repeat_attempt", "repeat"}
        and input_mode == "audio"
        and audio_bytes
        and reference_text
    ):
        pronunciation = azure_speech.assess_scripted(audio_bytes, reference_text)
        storage.add_usage(pron_seconds=max(3, len(audio_bytes) / 32000))
        if pronunciation.get("error"):
            analysis = {**analysis, "speech_degraded": True}
    try:
        result = dialogue_manager.apply_turn(
            session,
            lesson,
            student_text,
            analysis,
            input_mode=input_mode,
            pronunciation=pronunciation,
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    grade = result.get("segment_grade")
    return {
        "ok": True,
        "student_text": student_text,
        **result,
        # Temporary compatibility fields for older front-end clients.
        "feedback": result.get("pronunciation"),
        "grade": grade,
        "segment_name": completed_segment_name if grade else (session.get("pending") or {}).get("segment_name", ""),
        "encouragement": _encouragement(grade) if grade else None,
        "guide_zh": False,
    }


@app.post("/api/turn/text")
def turn_text(payload: dict):
    """Unified typed turn. Typed input can never produce pronunciation data."""
    return _process_turn(
        _active_session_id(payload),
        str(payload.get("text") or ""),
        "typed",
        audio_bytes=None,
    )


@app.post("/api/turn/audio")
async def turn_audio(audio: UploadFile | None = File(None), session_id: str = Form("")):
    """Unified audio turn: bilingual STT → intent → optional scripted assessment."""
    raw = await audio.read() if audio else b""
    if not raw:
        return JSONResponse({"ok": False, "error": "缺少录音,请重新录制"}, status_code=400)
    session = ACTIVE_SESSIONS.get(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "会话不存在或已过期,请重新开始"}, status_code=404)
    pending = session.get("pending") or {}
    expected_action = pending.get("expected_action") or pending.get("expected_mode") or "open_answer"
    # Only scripted repeat tasks may bias recognition toward a reference sentence.
    # Open conversation must remain genuinely open instead of being pulled toward
    # the authored sample answer by Azure's phrase hints.
    expected = (pending.get("reference_text") or pending.get("target_text", "")) if expected_action == "repeat" else ""
    transcription = azure_speech.transcribe(raw, expected=expected)
    storage.add_usage(stt_seconds=max(3, len(raw) / 32000))
    text = (transcription.get("text") or "").strip()
    if not text:
        return JSONResponse(
            {"ok": False, "error": transcription.get("error") or "没有听清,请再说一次"},
            status_code=422,
        )
    result = _process_turn(session_id, text, "audio", audio_bytes=raw)
    if isinstance(result, JSONResponse):
        return result
    return {
        **result,
        "transcription": {
            "text": text,
            "language": transcription.get("detected", ""),
            "mode": transcription.get("mode", "mock"),
        },
    }


@app.post("/api/chat/reply")
def chat_reply(payload: dict):
    """Compatibility endpoint for clients using recognize → reply."""
    session_id = _active_session_id(payload)
    input_mode = payload.get("input_mode") if payload.get("input_mode") in {"audio", "typed"} else ("audio" if payload.get("audio_id") else "typed")
    cached = _AUDIO_CACHE.pop(payload.get("audio_id", ""), None) if input_mode == "audio" else None
    raw = cached.get("raw") if cached and cached.get("session_id") == session_id else None
    return _process_turn(session_id, str(payload.get("text") or ""), input_mode, audio_bytes=raw)


def _encouragement(grade: str) -> str:
    """按任务完成支持等级鼓励,不把 A/B/C/D 说成发音分。"""
    return {
        "A": "🌟 这一段独立完成啦!",
        "B": "👍 用一点提示就完成了!",
        "C": "💪 跟着示范完成了,很棒!",
        "D": "🌱 先放一放也没关系,下次再来!",
    }.get(grade, "👍 收到!")


@app.post("/api/summary")
def summary(payload: dict):
    """结束会话:生成跟读记录并入库。"""
    session_id = _active_session_id(payload)
    session = ACTIVE_SESSIONS.get(session_id)
    if not session:
        return JSONResponse({"ok": False, "error": "会话不存在或已过期"}, status_code=404)
    course = storage.get_course(session.get("course_id", ""))
    if not course:
        return JSONResponse({"ok": False, "error": "课程不存在"}, status_code=404)
    record = llm.generate_record(
        course,
        session.get("history", []),
        session.get("grades", {}),
        session.get("activity_results", {}),
        session.get("coaching_notes", []),
    )
    record["id"] = uuid.uuid4().hex[:10]
    record["date"] = time.strftime("%Y-%m-%d %H:%M")
    record["duration_min"] = payload.get("duration_min", 0)
    record["degraded_count"] = session.get("degraded_count", 0)
    session["grades"].setdefault("weak", record["summary"]["error_points"][:2])
    storage.save_session({"id": record["id"], **record, "raw": dialogue_manager.public_session(session)})
    ACTIVE_SESSIONS.pop(session_id, None)
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


@app.post("/api/translate")
def translate(payload: dict):
    """AI 消息 → 简单中文(供"看中文"按钮)。无 Key 时返回空串。"""
    text = (payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "缺少文本"}, status_code=400)
    if llm._has_chinese(text):
        return {"ok": True, "zh": text}  # 本身是中文,原样返回
    zh = llm.translate_zh(text)
    return {"ok": True, "zh": zh}


# ---------------------------------------------------------------- 设置 / 用量
@app.get("/api/config")
def api_config():
    return {
        "ok": True,
        "student": _config().get("student", {}),
        "mock": not (llm.enabled() or azure_speech.enabled()),
        "deepseek": llm.enabled(),
        "deepseek_model": llm.model_name(),
        "azure": azure_speech.enabled(),
        "tts_voice": azure_speech.tts_voice(),
        "tts_voice_zh": azure_speech.tts_voice_zh(),
        "tts_region": azure_speech.status().get("tts_region"),
        "tts_voice_options": azure_speech.TTS_VOICE_OPTIONS,
    }


@app.post("/api/config/keys")
def save_keys(payload: dict):
    """保存 Key / 音色到 .env(本地)。"""
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
    voice = payload.get("tts_voice", "")
    if voice in azure_speech.TTS_VOICE_OPTIONS:
        env["AZURE_TTS_VOICE_EN"] = voice
        # Keep the old variable in sync for older local deployments.
        env["TTS_VOICE"] = voice
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
