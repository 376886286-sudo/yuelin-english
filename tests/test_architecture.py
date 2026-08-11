# -*- coding: utf-8 -*-
"""Architecture-level contracts for DeepSeek V4 and split speech services."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app import azure_speech, llm


class _Response:
    def __init__(self, content: str):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


class ArchitectureTests(unittest.TestCase):
    def test_json_turn_call_uses_v4_flash_non_thinking_and_retries_empty_content(self):
        calls = []

        def fake_post(*args, **kwargs):
            calls.append(kwargs["json"])
            return _Response("") if len(calls) == 1 else _Response('{"intent":"answer"}')

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test", "DEEPSEEK_MODEL": "deepseek-v4-flash"}, clear=False):
            with patch("app.llm.httpx.post", side_effect=fake_post):
                result = llm.chat_json("Return JSON", "hello", retries=1)

        self.assertEqual(result["intent"], "answer")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["model"], "deepseek-v4-flash")
        self.assertEqual(calls[0]["thinking"], {"type": "disabled"})
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})

    def test_reasoning_call_explicitly_enables_thinking(self):
        captured = {}

        def fake_post(*args, **kwargs):
            captured.update(kwargs["json"])
            return _Response("summary")

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test", "DEEPSEEK_MODEL": "deepseek-v4-flash"}, clear=False):
            with patch("app.llm.httpx.post", side_effect=fake_post):
                self.assertEqual(llm.chat_reasoning("system", "user"), "summary")
        self.assertEqual(captured["thinking"], {"type": "enabled"})

    def test_transcribe_and_scripted_assessment_are_separate_capabilities(self):
        transcription = azure_speech.transcribe(b"", expected="Hello")
        missing_reference = azure_speech.assess_scripted(b"audio", "")
        self.assertEqual(transcription["text"], "Hello")
        self.assertNotIn("score", transcription)
        self.assertEqual(missing_reference["error"], "missing reference_text")

    def test_default_tts_voice_is_natural_multilingual_voice(self):
        with patch.dict(os.environ, {"AZURE_TTS_VOICE_EN": "", "TTS_VOICE": ""}, clear=False):
            self.assertEqual(azure_speech.tts_voice(), "en-US-AvaMultilingualNeural")


if __name__ == "__main__":
    unittest.main()
