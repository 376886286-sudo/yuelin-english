# -*- coding: utf-8 -*-
"""DeepSeek 模块(mock 模式)。

有 DEEPSEEK_API_KEY 时走真实 HTTP 调用;否则用本地规则引擎模拟:
- 教案解析由 parser 完成,这里做规则增强
- 教师对话按教案环节推进
- 会话记录 / 复习计划按固定模板生成
"""

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

    - 教案环节内:按必做对话 A/B 交替推进
    - 教案环节全部完成、且家长已确认复习包时:进入 REVIEW 环节(逐条重练往期易错句)
    """
    review_errors = lesson.get("review_errors", [])
    total = len(lesson.get("segments", []))
    is_review = segment_idx >= total and total > 0 and review_errors

    if is_review:
        return _review_reply(lesson, segment_idx, student_text, prev_exchanges, review_errors)

    seg = lesson["segments"][segment_idx] if lesson.get("segments") else {}
    dialogue = seg.get("dialogue", [])
    # 只统计"当前环节"的学生发言,避免换词巩固轮污染进度
    student_count = len([1 for e in prev_exchanges
                         if e.get("role") == "student" and e.get("segment_idx", 0) == segment_idx])
    code = seg.get("code", "")

    if enabled():
        try:
            system = teacher_system_prompt(lesson, segment_idx)
            history = "\n".join(
                f"{'教师' if e['role'] == 'ai' else '悦琳'}:{e['text']}" for e in prev_exchanges[-6:]
            )
            text = _chat(system, f"之前的对话:\n{history}\n悦琳刚才说:{student_text}\n请按带读规则回复。")
            return {"text": text, "segment": code, "done": False}
        except Exception:
            pass

    # ---- mock:按 A/B 交替推进必做对话
    # 开场 AI 已说 dialogue[0](A1),孩子应说 dialogue[1](B1)
    # 孩子已说 n 个 B 句 → AI 下一句 = dialogue[2n+2](若存在)
    next_a = 2 * student_count + 2
    if next_a < len(dialogue):
        return {"text": dialogue[next_a][1], "segment": code, "done": False}

    # 必做对话完成 → 先做一轮换词巩固(仅一次),再转场到下一环节或结束
    if next_a == len(dialogue) and student_count == 1 and seg.get("variation"):
        return {
            "text": f"Great! Let's change it up. {dialogue[1][1]}",
            "segment": code, "done": False,
        }

    if segment_idx + 1 < total:
        nxt = lesson["segments"][segment_idx + 1]
        return {
            "text": f"Excellent! {seg.get('transition', '')} Now let's do {nxt.get('name_zh', '')}.",
            "segment": nxt.get("code", ""),
            "done": False,
            "next_segment": True,
        }

    # 教案完成,若有家长确认的复习包 → 进入 REVIEW;否则结束
    if review_errors:
        return {
            "text": "Well done! Now let's review some tricky sentences. Please repeat after me.",
            "segment": "REVIEW",
            "done": False,
            "next_segment": True,
            "review_start": True,
        }

    return {
        "text": "Excellent work today! You took your time and kept speaking. That is real progress.",
        "segment": code, "done": True,
    }


def _review_reply(lesson, segment_idx, student_text, prev_exchanges, review_errors):
    """REVIEW 环节:逐条重练往期易错句,全部完成后结束会话。"""
    done_count = len([1 for e in prev_exchanges
                      if e.get("role") == "student" and e.get("segment_idx", 0) == segment_idx])
    if done_count == 0:
        first = review_errors[0]
        prompt = first.get("drill") or first.get("text")
        return {
            "text": f"Listen and repeat: {prompt}",
            "segment": "REVIEW", "done": False,
        }
    if done_count < len(review_errors):
        item = review_errors[done_count]
        prompt = item.get("drill") or item.get("text")
        return {
            "text": f"Great! One more. {prompt}",
            "segment": "REVIEW", "done": False,
        }
    return {
        "text": "Perfect! You reviewed all the tricky sentences today. You took your time and kept speaking. That is real progress.",
        "segment": "REVIEW", "done": True,
    }


# ---------------------------------------------------------------- 记录与规划
def generate_record(lesson: dict, exchanges: list, grades: dict) -> dict:
    """生成跟读记录(替代豆包的手动记录,结构固定、不丢上下文)。"""
    seg_names = [s.get("name_zh", s.get("code", "")) for s in lesson.get("segments", [])]
    student_lines = [e["text"] for e in exchanges if e.get("role") == "student"]
    # 说错的句子(含 weak 发音词),用于家长挑选复习
    weak_lines = [
        e["text"] for e in exchanges
        if e.get("role") == "student" and any(
            w.get("label") == "weak" for w in (e.get("feedback", {}) or {}).get("words", [])
        )
    ]
    weak = grades.get("weak", [])

    record = {
        "course_id": lesson.get("id", ""),
        "course_title": f"Unit {lesson.get('unit', '')} {lesson.get('title_zh', '')}",
        "segments_grades": grades.get("segments", {}),
        "student_lines": student_lines[:12],
        "weak_lines": weak_lines[:6],
        "summary": {
            "error_points": [
                "be 动词不能丢:单数 is / 复数 are",
                "定冠词 the 不要省略",
                "单词混淆注意区分(如 book/boat)",
                "疑问句语序:Where + be + 主语",
            ][: max(2, len(weak) % 4 + 2)],
            "strengths": f"完成 {len(student_lines)} 次开口,持续保持练习",
        },
        "review_plan": {
            "day1": f"重练 {seg_names[0] if seg_names else '第一环节'} 的过关句型",
            "day3": "完成一次整句跟读,注意语音点",
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
