# -*- coding: utf-8 -*-
"""DeepSeek 模块(mock 模式)。

有 DEEPSEEK_API_KEY 时走真实 HTTP 调用;否则用本地规则引擎模拟:
- 教案解析由 parser 完成,这里做规则增强
- 教师对话按教案环节推进
- 会话记录 / 复习计划按固定模板生成
"""

import json
import os
import random

import httpx

from . import parser

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"


def _key() -> str:
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


def enabled() -> bool:
    return bool(_key())


def _chat(system: str, user: str, max_tokens: int = 1200) -> str:
    resp = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def chat_json(system: str, user: str, max_tokens: int = 600) -> dict:
    """Call DeepSeek JSON Output and return a decoded object.

    Errors intentionally propagate so the dialogue layer can mark the turn as
    degraded without advancing the pending lesson task by accident.
    """
    resp = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "temperature": 0.2,
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.strip("`").removeprefix("json").strip()
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("DeepSeek JSON output must be an object")
    return data


def _has_chinese(text: str) -> bool:
    """是否含中文字符(用于识别孩子说中文 / 翻译判断)。"""
    return any("\u4e00" <= c <= "\u9fff" for c in (text or ""))


def translate_zh(text: str) -> str:
    """英文 → 简单中文(给"看中文"按钮用)。无 Key 返回空串。"""
    if not enabled() or not text:
        return ""
    system = (
        "你是儿童英语学习助手。把英文翻译成简单、口语化的中文,"
        "适合 8-10 岁孩子看懂。只输出译文,不要解释、不要加引号。"
    )
    try:
        return _chat(system, text, max_tokens=200)
    except Exception:
        return ""


# ---------------------------------------------------------------- 教案解析
def parse_lesson(filename: str, raw: bytes) -> dict:
    """解析教案文件:图片走视觉(未配 Key 时占位),文档走文本解析。"""
    lesson = parser.parse_lesson_file(filename, raw)
    if lesson.get("source_type") == "image" and enabled():
        # TODO: DeepSeek 视觉接口就绪后接入
        pass
    return lesson


# ---------------------------------------------------------------- 教师对话
def teacher_system_prompt(lesson: dict, segment_idx: int = 0) -> str:
    seg = lesson["segments"][segment_idx] if lesson.get("segments") else {}
    rules = "\n".join(f"- {r}" for r in lesson.get("rules", []))
    return (
        "你是悦琳的英语口语教师。严格按教案带读,不自由发挥、不加新内容。\n"
        f"【当前单元】{lesson.get('title_zh', '')} {lesson.get('title_en', '')}\n"
        f"【当前环节】{seg.get('code', '')} {seg.get('name_zh', '')} {seg.get('minutes', 0)}分钟\n"
        f"【环节任务】{seg.get('task', '')}\n"
        f"【关键句型】{'; '.join(seg.get('patterns', []))}\n"
        f"【必做对话】" + " / ".join(f"{r}:{t}" for r, t in seg.get("dialogue", [])) + "\n"
        f"【换词与纠错】{seg.get('variation', '')}\n"
        f"【过关标准】{seg.get('pass_rule', '')}\n"
        f"【转场句】{seg.get('transition', '')}\n"
        f"【带读规则】\n{rules}\n"
        "回复要求:每轮最多两句简短英语;先肯定再纠错;听不懂就用更简单的英语重复;"
        "完成本环节后说出转场句并提示'这一段完成'。"
    )


def teacher_first_message(lesson: dict) -> str:
    """会话开场白:直接使用第一环节必做对话的 A 句。"""
    seg = lesson["segments"][0] if lesson.get("segments") else {}
    opening = seg.get("dialogue", [])
    if opening:
        return opening[0][1]
    return "Hello! Let's start our English practice."


def teacher_reply(lesson: dict, segment_idx: int, student_text: str, prev_exchanges: list) -> dict:
    """根据孩子回答生成教师回应。

    - 教案环节内:按必做对话 A/B 交替推进(真实模式由 LLM 生成台词)
    - 环节完成判断统一用规则(与 mock 一致),保证环节能推进、会话能结束
    - 教案环节全部完成、且家长已确认复习包时:进入 REVIEW 环节(逐条重练往期易错句)
    """
    review_errors = lesson.get("review_errors", [])
    total = len(lesson.get("segments", []))
    is_review = segment_idx >= total and total > 0 and review_errors

    if is_review:
        return _review_reply(lesson, segment_idx, student_text, prev_exchanges, review_errors)

    seg = lesson["segments"][segment_idx] if lesson.get("segments") else {}
    dialogue = seg.get("dialogue", [])
    # 孩子说中文 → 用中文理解她,并引导她用英文说目标句(不计入环节完成进度)
    if _has_chinese(student_text) and enabled():
        return _chinese_guide_reply(lesson, segment_idx, student_text, dialogue)
    # 只统计"当前环节"的学生发言,避免换词巩固轮污染进度
    student_count = len([1 for e in prev_exchanges
                         if e.get("role") == "student" and e.get("segment_idx", 0) == segment_idx])
    code = seg.get("code", "")

    # ---- 环节完成判断(规则):必做对话说完 + 换词巩固一轮(若有) ----
    next_a = 2 * student_count + 2  # 开场 AI 已说 A1,孩子每答一轮,AI 说下一句 A
    variation_round = next_a == len(dialogue) and student_count == 1 and bool(seg.get("variation"))
    seg_done = next_a >= len(dialogue) and not variation_round

    if seg_done:
        # 环节完成 → 统一用转场台词(真实/ mock 一致,保证与环节推进同步)
        if segment_idx + 1 < total:
            nxt = lesson["segments"][segment_idx + 1]
            return {
                "text": f"Excellent! {seg.get('transition', '')} Now let's do {nxt.get('name_zh', '')}.",
                "segment": nxt.get("code", ""),
                "done": False,
                "next_segment": True,
                "role": "teacher",
            }
        if review_errors:
            return {
                "text": "Well done! Now let's review some tricky sentences. Please repeat after me.",
                "segment": "REVIEW",
                "done": False,
                "next_segment": True,
                "review_start": True,
                "role": "teacher",
            }
        return {
            "text": "Excellent work today! You took your time and kept speaking. That is real progress.",
            "segment": code, "done": True,
            "role": "teacher",
        }

    # ---- 环节内台词:真实模式 LLM 生成,mock 按剧本推进 ----
    if enabled():
        try:
            system = teacher_system_prompt(lesson, segment_idx)
            history = "\n".join(
                f"{'教师' if e['role'] == 'ai' else '悦琳'}:{e['text']}" for e in prev_exchanges[-6:]
            )
            text = _chat(system, f"之前的对话:\n{history}\n悦琳刚才说:{student_text}\n请按带读规则回复。")
            return {"text": text, "segment": code, "done": False, "role": "teacher"}
        except Exception:
            pass

    if next_a < len(dialogue):
        return {"text": dialogue[next_a][1], "segment": code, "done": False, "role": "teacher"}

    if variation_round:
        # 换词巩固:示范孩子要说的句子 → demo 音色
        return {
            "text": f"Great! Let's change it up. {dialogue[1][1]}",
            "segment": code, "done": False, "role": "demo",
        }

    # 理论到不了这里(seg_done 已处理),兜底回一句并保持环节
    return {"text": "Nice! Let's try once more.", "segment": code, "done": False, "role": "teacher"}


def _chinese_guide_reply(lesson: dict, segment_idx: int, student_text: str, dialogue: list) -> dict:
    """孩子说中文时:用中文肯定她,给出目标英文句,引导她用英文说。"""
    seg = lesson["segments"][segment_idx] if lesson.get("segments") else {}
    code = seg.get("code", "")
    target = ""
    if len(dialogue) > 1:
        target = dialogue[1][1]  # B 句 = 孩子该说的句子
    if not target:
        target = (seg.get("patterns") or [""])[0]
    system = (
        "你是悦琳的英语口语教师。悦琳刚才用中文说了话。"
        "请用中文回应:1) 先简短肯定她愿意开口(一句);2) 告诉她这句用英语怎么说,"
        f"给出目标句: {target};3) 用中文鼓励她用英语说一遍。"
        "总长度不超过两行,不要加新内容。"
    )
    try:
        text = _chat(system, f"悦琳说: {student_text}", max_tokens=220)
    except Exception:
        text = f"没关系,这句用英语说: {target}。来,跟着说一遍!"
    return {"text": text, "segment": code, "done": False, "role": "teacher", "guide_zh": True}


def _review_reply(lesson, segment_idx, student_text, prev_exchanges, review_errors):
    """REVIEW 环节:逐条重练往期易错句,全部完成后结束会话。"""
    done_count = len([1 for e in prev_exchanges
                      if e.get("role") == "student" and e.get("segment_idx", 0) == segment_idx])
    if done_count == 0:
        first = review_errors[0]
        prompt = first.get("drill") or first.get("text")
        return {
            "text": f"Listen and repeat: {prompt}",
            "segment": "REVIEW", "done": False, "role": "demo",
        }
    if done_count < len(review_errors):
        item = review_errors[done_count]
        prompt = item.get("drill") or item.get("text")
        return {
            "text": f"Great! One more. {prompt}",
            "segment": "REVIEW", "done": False, "role": "demo",
        }
    return {
        "text": "Perfect! You reviewed all the tricky sentences today. You took your time and kept speaking. That is real progress.",
        "segment": "REVIEW", "done": True, "role": "teacher",
    }


# ---------------------------------------------------------------- 记录与规划
def generate_record(lesson: dict, exchanges: list, grades: dict, activity_results: dict | None = None) -> dict:
    """生成跟读记录(替代豆包的手动记录,结构固定、不丢上下文)。"""
    seg_names = [s.get("name_zh", s.get("code", "")) for s in lesson.get("segments", [])]
    student_lines = [e["text"] for e in exchanges if e.get("role") == "student"]
    # 说错的句子(含 weak 发音词),用于家长挑选复习
    weak_lines = [
        e["text"] for e in exchanges
        if e.get("role") == "student" and any(
            w.get("label") == "weak" for w in (e.get("pronunciation", {}) or {}).get("words", [])
        )
    ]
    weak = grades.get("weak", [])
    activity_results = activity_results or {}
    support_grades = [result.get("grade") for result in activity_results.values()]
    error_points = []
    if weak:
        error_points.append("发音需要关注:" + "、".join(weak[:4]))
    if "B" in support_grades:
        error_points.append("部分回答需要关键词提示,下次先留出独立思考时间")
    if "C" in support_grades:
        error_points.append("部分句子在示范跟读后完成,建议隔天再独立复述")
    if "D" in support_grades:
        error_points.append("有任务本次暂未完成,下次从该任务重新开始")

    record = {
        "course_id": lesson.get("id", ""),
        "course_title": f"Unit {lesson.get('unit', '')} {lesson.get('title_zh', '')}",
        "segments_grades": grades.get("segments", {}),
        "student_lines": student_lines[:12],
        "weak_lines": weak_lines[:6],
        "summary": {
            "error_points": error_points,
            "strengths": f"完成 {len(student_lines)} 次开口,持续保持练习",
        },
        "review_plan": {
            "day1": f"重练 {seg_names[0] if seg_names else '第一环节'} 的未独立完成任务",
            "day3": "复述本次用过提示的句子" if any(g in support_grades for g in ("B", "C")) else "用自己的说法复述本次对话",
            "day7": "三段整合对话完整走一遍",
        },
        "closing": "You took your time and kept speaking. That is real progress.",
    }
    if enabled():
        try:
            system = (
                "你是英语跟读记录员。根据练习记录输出结构化总结:分段评级、真实语句摘录、"
                "易错词总结(2-4条)、第1/3/7天复习计划(每项一句)。结尾必须包含:"
                "You took your time and kept speaking. That is real progress."
            )
            user = f"课程:{record['course_title']}\n各环节评级:{record['segments_grades']}\n孩子说过的句子:{chr(10).join(record['student_lines'])}"
            text = _chat(system, user, max_tokens=800)
            record["llm_note"] = text
        except Exception:
            pass
    return record


def mock_word_scores(text: str, weak_hint: str = "") -> list:
    """mock 发音评估:按词打分,偶尔制造一个低分词。"""
    words = text.split()
    scores = []
    low_done = False
    for w in words:
        s = random.randint(82, 100)
        if not low_done and s < 88 and len(words) > 2:
            s = random.randint(62, 74)
            low_done = True
        scores.append({"word": w, "score": s, "label": "good" if s >= 85 else "fair" if s >= 75 else "weak"})
    return scores
