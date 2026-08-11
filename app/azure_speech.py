# -*- coding: utf-8 -*-
"""Azure 语音模块。

有 AZURE_SPEECH_KEY + AZURE_SPEECH_REGION 时接入 Azure Speech SDK:
- transcribe:PushAudioInputStream 喂入 WAV/PCM 字节,只做中英自动识别
- assess_scripted:固定 en-US + reference_text,只做 scripted 跟读评估
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


def _tts_key() -> str:
    return (os.getenv("AZURE_TTS_KEY") or _key()).strip()


def _tts_region() -> str:
    return (os.getenv("AZURE_TTS_REGION") or _region()).strip()


def enabled() -> bool:
    return bool(_key() and _region() and SDK_AVAILABLE)


def tts_enabled() -> bool:
    return bool(_tts_key() and _tts_region() and SDK_AVAILABLE)


def status() -> dict:
    return {
        "enabled": enabled(),
        "asr": bool(enabled()),
        "tts": tts_enabled(),
        "pronunciation": bool(enabled()),
        "region": _region() or "eastasia",
        "tts_region": _tts_region() or _region() or "eastasia",
        "tts_dedicated_resource": bool(os.getenv("AZURE_TTS_KEY") and os.getenv("AZURE_TTS_REGION")),
        "sdk": SDK_AVAILABLE,
    }


def _score_label(score: int) -> str:
    """与 mock 对齐的评级口径:>=85 good,>=75 fair,否则 weak。"""
    if score >= 85:
        return "good"
    if score >= 75:
        return "fair"
    return "weak"


def transcribe(audio_bytes: bytes = None, expected: str = "", mode: str = "mock") -> dict:
    """普通语音识别,不做发音评估。

    - 真实模式:音频字节 → 双语 ASR,返回 {text, mode, detected}
    - mock 模式:返回预期句,便于前端链路跑通
    """
    if enabled() and audio_bytes:
        return _real_transcribe(audio_bytes)
    return {
        "text": expected or "I like it.",
        "mode": mode,
        "expected": bool(expected),
    }


def recognize(audio_bytes: bytes = None, expected: str = "", mode: str = "mock") -> dict:
    """Compatibility alias; new code should call transcribe()."""
    return transcribe(audio_bytes, expected=expected, mode=mode)


def _real_transcribe(audio_bytes: bytes) -> dict:
    """真实 ASR(中英自动检测),在子线程跑以防空音频卡死请求。"""
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
            push.write(audio_bytes)
            push.close()

            result = recognizer.recognize_once()
            text = ""
            detected = ""
            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = (result.text or "").strip()
                try:
                    detected = speechsdk.AutoDetectSourceLanguageResult(result).language or ""
                except Exception:
                    detected = ""
            result_box["ok"] = True
            result_box["text"] = text
            result_box["detected"] = detected
        except Exception as e:  # noqa: BLE001 - 语音失败不能打挂对话,降级为"没听清"
            result_box["ok"] = False
            result_box["error"] = str(e)
            result_box["text"] = ""
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
        "feedback": None,
        "detected": result_box.get("detected", ""),
        "error": result_box.get("error"),
    }


def assess_scripted(audio_bytes: bytes, reference_text: str) -> dict:
    """Scripted 跟读评估;调用方必须同时提供音频和后端目标句。"""
    reference_text = (reference_text or "").strip()
    if not reference_text:
        return {"score": 0, "accuracy": 0, "fluency": 0, "completeness": 0,
                "prosody": None, "words": [], "weak_words": [], "error": "missing reference_text"}
    if enabled() and audio_bytes:
        return _real_assess_scripted(audio_bytes, reference_text)

    # Mock is used only for an audio turn. Typed text never calls this function.
    words = [
        {"word": word.strip(".,!?"), "score": 90, "label": "good", "error_type": "None"}
        for word in reference_text.split() if word.strip(".,!?")
    ]
    return {
        "mode": "mock",
        "reference_text": reference_text,
        "score": 90,
        "accuracy": 90,
        "fluency": 90,
        "completeness": 100,
        "prosody": 90,
        "words": words,
        "weak_words": [],
        "error": None,
    }


def pronunciation(audio_bytes: bytes, reference_text: str) -> dict:
    """Compatibility alias; new code should call assess_scripted()."""
    return assess_scripted(audio_bytes, reference_text)


def _real_assess_scripted(audio_bytes: bytes, reference_text: str) -> dict:
    """Fixed en-US scripted assessment with completeness and optional prosody."""
    if not audio_bytes or len(audio_bytes) < 500:
        return {"mode": "azure", "reference_text": reference_text, "score": 0,
                "accuracy": 0, "fluency": 0, "completeness": 0, "prosody": None,
                "words": [], "weak_words": [], "error": "audio too short"}

    result_box = {}

    def run():
        try:
            speech_config = speechsdk.SpeechConfig(subscription=_key(), region=_region())
            speech_config.speech_recognition_language = "en-US"
            push = speechsdk.audio.PushAudioInputStream()
            audio_config = speechsdk.audio.AudioConfig(stream=push)
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config,
            )
            config = speechsdk.PronunciationAssessmentConfig(
                reference_text=reference_text,
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
                enable_miscue=True,
            )
            try:
                config.enable_prosody_assessment()
            except (AttributeError, RuntimeError):
                pass
            config.apply_to(recognizer)
            push.write(audio_bytes)
            push.close()
            result = recognizer.recognize_once()
            if result.reason != speechsdk.ResultReason.RecognizedSpeech:
                result_box.update({"ok": False, "error": str(result.reason)})
                return

            assessment = speechsdk.PronunciationAssessmentResult(result)
            words = []
            for word in assessment.words or []:
                score = int(round(word.accuracy_score or 0))
                raw_error = getattr(word, "error_type", None)
                error_type = str(raw_error).split(".")[-1] if raw_error else "None"
                label = "weak" if error_type in {"Omission", "Insertion", "Mispronunciation"} else _score_label(score)
                words.append(
                    {
                        "word": word.word,
                        "score": score,
                        "label": label,
                        "error_type": error_type,
                    }
                )
            pronunciation_score = int(round(getattr(assessment, "pronunciation_score", 0) or 0))
            accuracy = int(round(assessment.accuracy_score or 0))
            fluency = int(round(assessment.fluency_score or 0))
            completeness = int(round(assessment.completeness_score or 0))
            raw_prosody = assessment.prosody_score
            prosody = int(round(raw_prosody)) if raw_prosody is not None else None
            result_box.update(
                {
                    "ok": True,
                    "recognized_text": (result.text or "").strip(),
                    "score": pronunciation_score or accuracy,
                    "accuracy": accuracy,
                    "fluency": fluency,
                    "completeness": completeness,
                    "prosody": prosody,
                    "words": words,
                    "weak_words": [word["word"] for word in words if word["label"] == "weak"],
                }
            )
        except Exception as exc:  # noqa: BLE001 - speech failure must degrade safely
            result_box.update({"ok": False, "error": str(exc)})

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=RECOGNIZE_TIMEOUT_S)
    if not result_box:
        result_box = {"ok": False, "error": "pronunciation timeout"}
    return {
        "mode": "azure",
        "reference_text": reference_text,
        "score": result_box.get("score", 0),
        "accuracy": result_box.get("accuracy", 0),
        "fluency": result_box.get("fluency", 0),
        "completeness": result_box.get("completeness", 0),
        "prosody": result_box.get("prosody"),
        "words": result_box.get("words", []),
        "weak_words": result_box.get("weak_words", []),
        "recognized_text": result_box.get("recognized_text", ""),
        "error": result_box.get("error"),
    }


# 可选音色(家长设置页展示)
TTS_VOICE_OPTIONS = {
    "en-US-AvaMultilingualNeural": "Ava 女声(自然对话,默认推荐)",
    "en-US-EmmaMultilingualNeural": "Emma 女声(温和自然)",
    "en-US-AriaNeural": "Aria 女声(沉稳大气)",
    "en-US-JennyNeural": "Jenny 女声(温暖亲切)",
    "en-US-Emma2:DragonHDLatestNeural": "Emma2 Dragon HD(拟真对话,需支持区域)",
    "en-US-GuyNeural": "Guy 男声(沉稳男老师)",
    "en-US-AndrewMultilingualNeural": "Andrew 男声(温和男老师)",
}


def tts_voice() -> str:
    """Current English teacher voice, read dynamically from environment."""
    v = (os.getenv("AZURE_TTS_VOICE_EN") or os.getenv("TTS_VOICE") or "").strip()
    return v if v in TTS_VOICE_OPTIONS else "en-US-AvaMultilingualNeural"


def tts_voice_zh() -> str:
    return (os.getenv("AZURE_TTS_VOICE_ZH") or "zh-CN-XiaoxiaoNeural").strip()


def _is_hd_voice(voice: str) -> bool:
    return ":DragonHD" in (voice or "")

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
    """Synthesize a natural teacher voice with optional dedicated TTS resource.

    - style: 传入白名单内的风格名则强制使用;不传/无效则按文本内容自动挑选
    - demo: 跟读示范句只放慢语速,不再强行升高音调
    - 文本含中文时使用 AZURE_TTS_VOICE_ZH 或 Xiaoxiao
    - Dragon HD 使用自然韵律和轻量 temperature,不叠加 express-as 变调
    - 风格合成失败自动降级为无风格版本,保证朗读不中断
    - 真实模式:返回 {"mode": "azure", "audio": mp3字节, "style": 实际风格}
    - 失败/mock:返回 {"mode": "browser", "text": 原文},前端用浏览器朗读兜底
    """
    if not (tts_enabled() and text):
        return {"mode": "browser", "text": text}

    if _has_chinese(text):
        voice = tts_voice_zh()
        style = None
        rate, pitch = "0.98", "+0%"
        demo = False
    else:
        voice = voice if voice in TTS_VOICE_OPTIONS else tts_voice()
        style = None if _is_hd_voice(voice) else (style if style in TTS_STYLES else _pick_style(text))
        rate = "1.0" if style == "chat" else ("0.96" if style == "friendly" else "0.98")
        if demo:
            rate, pitch = "0.90", "+0%"
        else:
            pitch = "+0%"
    try:
        speech_config = speechsdk.SpeechConfig(subscription=_tts_key(), region=_tts_region())
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
        )
        safe = _add_breaks(_escape_xml(text))
        # HD voices infer conversational prosody from content; keep SSML light.
        if _is_hd_voice(voice):
            lang = "zh-CN" if voice.lower().startswith("zh-cn") else "en-US"
            styled = (
                f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">'
                f'<voice name="{voice}" parameters="temperature=0.7">'
                f'<prosody rate="{rate}">{safe}</prosody></voice></speak>'
            )
        elif style:
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
        lang = "zh-CN" if voice.lower().startswith("zh-cn") else "en-US"
        plain = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">'
            f'<voice name="{voice}"><prosody rate="{rate}" pitch="{pitch}">{safe}</prosody></voice></speak>'
        )
        result = _synthesize(speech_config, plain)
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return {"mode": "azure", "audio": bytes(result.audio_data), "style": "plain", "demo": demo}
    except Exception:
        pass
    return {"mode": "browser", "text": text}
