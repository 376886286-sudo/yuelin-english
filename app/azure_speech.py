# -*- coding: utf-8 -*-
"""Azure 语音模块。

有 AZURE_SPEECH_KEY + AZURE_SPEECH_REGION 时接入 Azure Speech SDK:
- recognize:PushAudioInputStream 喂入 WAV/PCM 字节,ASR + free-form 发音评估(reference_text="")
- pronunciation:真实评估需要音频,无音频时沿用 mock 逐词打分(打字输入兜底)
- tts:SpeechSynthesizer 合成 mp3 字节

无 Key / SDK 未安装时:
- recognize:mock 返回当前环节预期句(由调用方传入 expected)
- tts:返回提示文本,由前端用浏览器 SpeechSynthesis 朗读
"""

import os
import threading

try:
    import azure.cognitiveservices.speech as speechsdk
    SDK_AVAILABLE = True
except ImportError:
    speechsdk = None
    SDK_AVAILABLE = False

# 孩子单句练习:音频超过该时长视为无效(避免空白音频卡住识别)
RECOGNIZE_TIMEOUT_S = 12


def _key() -> str:
    return (os.getenv("AZURE_SPEECH_KEY") or "").strip()


def _region() -> str:
    return (os.getenv("AZURE_SPEECH_REGION") or "").strip()


def enabled() -> bool:
    return bool(_key() and _region() and SDK_AVAILABLE)


def status() -> dict:
    return {
        "enabled": enabled(),
        "asr": bool(enabled()),
        "tts": bool(enabled()),
        "pronunciation": bool(enabled()),
        "region": _region() or "eastasia",
        "sdk": SDK_AVAILABLE,
    }


def _score_label(score: int) -> str:
    """与 mock 对齐的评级口径:>=85 good,>=75 fair,否则 weak。"""
    if score >= 85:
        return "good"
    if score >= 75:
        return "fair"
    return "weak"


def recognize(audio_bytes: bytes = None, expected: str = "", mode: str = "mock") -> dict:
    """识别音频并做发音评估。

    - 真实模式:音频字节 → ASR(free-form 发音评估),返回 {text, mode, expected, feedback}
    - mock 模式:返回预期句,便于前端链路跑通
    """
    if enabled() and audio_bytes:
        return _real_recognize(audio_bytes)
    return {
        "text": expected or "I like it.",
        "mode": mode,
        "expected": bool(expected),
    }


def _real_recognize(audio_bytes: bytes) -> dict:
    """真实 ASR(中英自动检测)+ 英文 free-form 发音评估(在子线程跑,防止空音频卡死请求)。

    - 孩子说英文:识别 + 逐词发音评估
    - 孩子说中文:识别出中文文本,不做发音评估(feedback=None,由对话层转中文引导)
    """
    if not audio_bytes or len(audio_bytes) < 500:
        # 空/极短音频直接视为没听清,不浪费一次调用
        return {"text": "", "mode": "azure", "expected": False, "feedback": None}

    result_box = {}

    def run():
        try:
            speech_config = speechsdk.SpeechConfig(subscription=_key(), region=_region())
            # 停顿 1.2 秒视为说完;静音最多等 4 秒
            try:
                speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "1200")
                speech_config.set_property(speechsdk.PropertyId.Speech_InitialSilenceTimeoutMs, "4000")
            except Exception:
                pass

            push = speechsdk.audio.PushAudioInputStream()
            audio_config = speechsdk.audio.AudioConfig(stream=push)
            # 中英自动检测:孩子说英文/中文都能识别出来
            auto_detect = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                languages=["en-US", "zh-CN"]
            )
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config,
                auto_detect_source_language_config=auto_detect,
            )
            # free-form 发音评估:不限定参考文本,识别与逐词评分一次完成
            # 注意:SDK 1.51 必须显式指定 grading_system/granularity,否则评估不生效(恒为 5 分)
            pron = speechsdk.PronunciationAssessmentConfig(
                reference_text="",
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
                enable_miscue=True,
            )
            pron.apply_to(recognizer)

            push.write(audio_bytes)
            push.close()

            result = recognizer.recognize_once()
            text = ""
            feedback = None
            detected = ""
            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = (result.text or "").strip()
                try:
                    detected = speechsdk.AutoDetectSourceLanguageResult(result).language or ""
                except Exception:
                    detected = ""
                # 英文才做发音评估;中文(或语言未知)不评估
                if text and (not detected or detected.lower().startswith("en")):
                    try:
                        pa = speechsdk.PronunciationAssessmentResult(result)
                        words = []
                        for w in pa.words or []:
                            score = int(round(w.accuracy_score))
                            words.append({"word": w.word, "score": score, "label": _score_label(score)})
                        if words:
                            feedback = {
                                "words": words,
                                "overall": int(round(pa.accuracy_score)),
                                "weak": [w["word"] for w in words if w["label"] == "weak"],
                            }
                    except Exception:
                        feedback = None
            result_box["ok"] = True
            result_box["text"] = text
            result_box["feedback"] = feedback
            result_box["detected"] = detected
        except Exception as e:  # noqa: BLE001 - 语音失败不能打挂对话,降级为"没听清"
            result_box["ok"] = False
            result_box["error"] = str(e)
            result_box["text"] = ""
            result_box["feedback"] = None
            result_box["detected"] = ""

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=RECOGNIZE_TIMEOUT_S)

    if not result_box:
        return {"text": "", "mode": "azure", "expected": False, "feedback": None,
                "error": "recognition timeout"}
    return {
        "text": result_box.get("text", ""),
        "mode": "azure",
        "expected": False,
        "feedback": result_box.get("feedback"),
        "detected": result_box.get("detected", ""),
        "error": result_box.get("error"),
    }


def pronunciation(text: str) -> list:
    """逐词发音评估。

    真实模式需要音频才能评估;此处只拿到文本(打字输入 / mock 链路),
    沿用 mock 逐词打分,保证 feedback 结构一致。
    """
    from .llm import mock_word_scores
    return mock_word_scores(text)


# 可选音色(家长设置页展示)
TTS_VOICE_OPTIONS = {
    "en-US-JennyNeural": "Jenny 女声(温暖亲切,推荐)",
    "en-US-AriaNeural": "Aria 女声(沉稳大气)",
    "en-US-AvaMultilingualNeural": "Ava 女声(自然流畅)",
    "en-US-GuyNeural": "Guy 男声(沉稳男老师)",
    "en-US-AndrewMultilingualNeural": "Andrew 男声(温和男老师)",
}


def tts_voice() -> str:
    """当前老师音色(动态读 env,支持家长设置页保存后生效)。"""
    v = (os.getenv("TTS_VOICE") or "").strip()
    return v if v in TTS_VOICE_OPTIONS else "en-US-JennyNeural"

# JennyNeural 官方支持的说话风格(微软文档 StyleList),这里只用适合孩子陪练的
TTS_STYLES = {
    "friendly": "温暖亲切,默认带读/教学",
    "cheerful": "积极快乐,用于表扬鼓励",
    "hopeful": "温暖期待,用于纠音引导",
    "chat": "随意放松,用于自由对话",
    "excited": "兴奋热情,用于大幅进步时",
    "assistant": "温和从容,用于环节引导",
}

# 表扬/鼓励特征词(命中 → cheerful)
_PRAISE_HINTS = (
    "great", "perfect", "wonderful", "awesome", "amazing", "excellent",
    "good job", "well done", "fantastic", "brilliant", "bravo", "nice work",
    "you did it", "keep going", "keep it up", "star", "high five",
    "🌟", "👍", "💪", "🌱", "🎉", "⭐",
)
# 纠音/引导特征词(命中 → hopeful)
_COACH_HINTS = (
    "try again", "listen", "say it", "say it again", "repeat", "practice",
    "follow me", "after me", "copy me", "let's try", "let us try", "one more time",
    "pay attention", "carefully", "slower",
)
# 提问/对话特征(句尾问号 → chat)
_QUESTION_MARKS = ("?", "？")


def _pick_style(text: str) -> str:
    """按文本内容自动挑选说话风格,让 AI 语音有语气变化。"""
    low = (text or "").lower()
    if any(h in low for h in _PRAISE_HINTS):
        return "cheerful"
    if any(h in low for h in _COACH_HINTS):
        return "hopeful"
    if any(q in text for q in _QUESTION_MARKS):
        return "chat"
    return "friendly"


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_SENT_END_RE = None
_ABBREV_RE = None


def _add_breaks(text: str) -> str:
    """在句号/感叹号/问号后插入短停顿,让朗读节奏更像真人。

    先用占位符保护常见缩写(Mr./Mrs./Dr./St. 等),避免句中被切断。
    """
    global _SENT_END_RE, _ABBREV_RE
    if _SENT_END_RE is None:
        import re
        # 句末标点后接空格或行尾才断句(避免 Mr. 这类缩写)
        _SENT_END_RE = re.compile(r'([.!?])(?=\s|$)')
        _ABBREV_RE = re.compile(
            r'\b(?:Mr|Mrs|Ms|Dr|St|Jr|Sr|Prof|Rev|Gen|Capt|Lt|Col|Sgt|etc|vs|approx|dept|No)\.',
            re.IGNORECASE)
    placeholders = {}

    def _protect(m):
        token = f"\x00{len(placeholders)}\x00"
        placeholders[token] = m.group(0)
        return token

    protected = _ABBREV_RE.sub(_protect, text)
    out = _SENT_END_RE.sub(r'\1<break time="280ms"/>', protected)
    for k, v in placeholders.items():
        out = out.replace(k, v)
    return out


def _synthesize(speech_config: speechsdk.SpeechConfig, ssml: str) -> speechsdk.SpeechSynthesisResult:
    """合成一次,返回 SDK result(不在本函数处理异常)。"""
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
    return synthesizer.speak_ssml(ssml)


def _has_chinese(text: str) -> bool:
    """是否含中文字符。"""
    return any("\u4e00" <= c <= "\u9fff" for c in (text or ""))


def tts(text: str, voice: str = "", style: str | None = None, demo: bool = False) -> dict:
    """合成语音,带说话风格与语气调整。

    - style: 传入白名单内的风格名则强制使用;不传/无效则按文本内容自动挑选
    - demo: 跟读示范句 → 音调提高、语速放慢,像"小朋友示范",与老师声音区分
    - 文本含中文(如 AI 的中文引导语) → 自动切到中文语音 Xiaoxiao,中英混读
    - 风格合成失败自动降级为无风格版本,保证朗读不中断
    - 真实模式:返回 {"mode": "azure", "audio": mp3字节, "style": 实际风格}
    - 失败/mock:返回 {"mode": "browser", "text": 原文},前端用浏览器朗读兜底
    """
    if not (enabled() and text):
        return {"mode": "browser", "text": text}

    if _has_chinese(text):
        # 中文引导:用中文语音(中英混合朗读),不套英文风格
        voice = "zh-CN-XiaoxiaoNeural"
        style = None
        rate, pitch = "1.02", "+2%"
        demo = False
    else:
        voice = voice if voice in TTS_VOICE_OPTIONS else tts_voice()
        style = style if style in TTS_STYLES else _pick_style(text)
        # 语速:对话/提问自然语速;带读/示范稍慢便于模仿
        rate = "1.0" if style == "chat" else ("0.96" if style == "friendly" else "0.98")
        if demo:
            rate, pitch = "0.92", "+12%"
        else:
            pitch = "+5%"
    try:
        speech_config = speechsdk.SpeechConfig(subscription=_key(), region=_region())
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
        )
        safe = _add_breaks(_escape_xml(text))
        # 语气层:风格 + 场景语速 + 句间停顿
        if style:
            styled = (
                f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
                f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">'
                f'<voice name="{voice}">'
                f'<mstts:express-as style="{style}">'
                f'<prosody rate="{rate}" pitch="{pitch}">{safe}</prosody>'
                f'</mstts:express-as></voice></speak>'
            )
        else:
            lang = "zh-CN" if voice.startswith("zh-CN") else "en-US"
            styled = (
                f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">'
                f'<voice name="{voice}"><prosody rate="{rate}" pitch="{pitch}">{safe}</prosody></voice></speak>'
            )
        result = _synthesize(speech_config, styled)
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return {"mode": "azure", "audio": bytes(result.audio_data), "style": style or "zh", "demo": demo}
        # 风格不受支持时降级:无风格版本再试一次
        plain = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
            f'<voice name="{voice}"><prosody rate="{rate}" pitch="{pitch}">{safe}</prosody></voice></speak>'
        )
        result = _synthesize(speech_config, plain)
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return {"mode": "azure", "audio": bytes(result.audio_data), "style": "plain", "demo": demo}
    except Exception:
        pass
    return {"mode": "browser", "text": text}
