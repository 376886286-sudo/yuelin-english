# -*- coding: utf-8 -*-
"""Azure 语音模块(mock 模式)。

有 AZURE_SPEECH_KEY 时接入 Azure Speech SDK(ASR / 发音评估 / TTS);
无 Key 时:
- recognize:mock 返回当前环节预期句(由调用方传入 expected)
- pronunciation:mock 逐词打分
- tts:返回提示文本,由前端用浏览器 SpeechSynthesis 朗读
"""

import os


def _key() -> str:
    return (os.getenv("AZURE_SPEECH_KEY") or "").strip()


def enabled() -> bool:
    return bool(_key() and os.getenv("AZURE_SPEECH_REGION"))


def status() -> dict:
    return {
        "enabled": enabled(),
        "asr": bool(enabled()),
        "tts": bool(enabled()),
        "pronunciation": bool(enabled()),
        "region": os.getenv("AZURE_SPEECH_REGION", "eastasia"),
    }


def recognize(audio_bytes: bytes = None, expected: str = "", mode: str = "mock") -> dict:
    """识别音频。mock 模式返回预期句;真实模式待 SDK 接入。"""
    if enabled():
        # TODO: azure-cognitiveservices-speech SDK 接入
        # from azure.cognitiveservices.speech import SpeechConfig, SpeechRecognizer, AudioConfig
        pass
    return {
        "text": expected or "I like it.",
        "mode": mode,
        "expected": bool(expected),
    }


def pronunciation(text: str) -> list:
    """逐词发音评估。mock:见 llm.mock_word_scores。"""
    from .llm import mock_word_scores
    return mock_word_scores(text)


def tts(text: str) -> dict:
    """合成语音。mock:返回文本交由浏览器朗读。"""
    if enabled():
        # TODO: SpeechSynthesizer 接入,返回音频文件
        pass
    return {"mode": "browser", "text": text}
