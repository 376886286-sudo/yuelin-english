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
    """真实 ASR + free-form 发音评估(在子线程跑,防止空音频卡死请求)。"""
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
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config, audio_config=audio_config, language="en-US"
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
            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = (result.text or "").strip()
                if text:
                    pa = speechsdk.PronunciationAssessmentResult(result)
                    words = []
                    for w in pa.words or []:
                        score = int(round(w.accuracy_score))
                        words.append({"word": w.word, "score": score, "label": _score_label(score)})
                    feedback = {
                        "words": words,
                        "overall": int(round(pa.accuracy_score)),
                        "weak": [w["word"] for w in words if w["label"] == "weak"],
                    }
            result_box["ok"] = True
            result_box["text"] = text
            result_box["feedback"] = feedback
        except Exception as e:  # noqa: BLE001 - 语音失败不能打挂对话,降级为"没听清"
            result_box["ok"] = False
            result_box["error"] = str(e)
            result_box["text"] = ""
            result_box["feedback"] = None

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
        "error": result_box.get("error"),
    }


def pronunciation(text: str) -> list:
    """逐词发音评估。

    真实模式需要音频才能评估;此处只拿到文本(打字输入 / mock 链路),
    沿用 mock 逐词打分,保证 feedback 结构一致。
    """
    from .llm import mock_word_scores
    return mock_word_scores(text)


TTS_VOICE = "en-US-JennyNeural"  # 女声,清晰、适合带读


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def tts(text: str, voice: str = TTS_VOICE) -> dict:
    """合成语音。

    - 真实模式:返回 {"mode": "azure", "audio": mp3字节}
    - 失败/mock:返回 {"mode": "browser", "text": 原文},前端用浏览器朗读兜底
    """
    if enabled() and text:
        try:
            speech_config = speechsdk.SpeechConfig(subscription=_key(), region=_region())
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
            )
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
            ssml = (
                f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
                f'<voice name="{voice}"><prosody rate="0.95">{_escape_xml(text)}</prosody></voice></speak>'
            )
            result = synthesizer.speak_ssml(ssml)
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                return {"mode": "azure", "audio": bytes(result.audio_data)}
        except Exception:
            pass
    return {"mode": "browser", "text": text}
