# -*- coding: utf-8 -*-
"""HTTP contract and server-owned session regression tests."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

import server
from app import llm


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.original_enabled = llm.enabled
        self.original_transcribe = server.azure_speech.transcribe
        self.original_assess_scripted = server.azure_speech.assess_scripted
        self.original_add_usage = server.storage.add_usage
        llm.enabled = lambda: False
        server.storage.add_usage = lambda **delta: delta
        server.azure_speech.transcribe = lambda raw, expected="", mode="mock": {
            "text": expected or "My name is Yuelin.",
            "mode": "mock",
            "expected": bool(expected),
            "feedback": None,
        }
        server.azure_speech.assess_scripted = lambda raw, target: {
            "mode": "mock", "reference_text": target, "score": 91,
            "accuracy": 91, "fluency": 90, "completeness": 100,
            "prosody": 89, "words": [], "weak_words": [], "error": None,
        }
        server.ACTIVE_SESSIONS.clear()
        server._AUDIO_CACHE.clear()
        self.course_id = server.storage.list_courses()[0]["id"]

    def tearDown(self):
        llm.enabled = self.original_enabled
        server.azure_speech.transcribe = self.original_transcribe
        server.azure_speech.assess_scripted = self.original_assess_scripted
        server.storage.add_usage = self.original_add_usage
        server.ACTIVE_SESSIONS.clear()
        server._AUDIO_CACHE.clear()

    def start(self):
        response = self.client.post("/api/chat/session", json={"course_id": self.course_id})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_home_and_basic_routes_load(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/status").status_code, 200)
        self.assertEqual(self.client.get("/api/lessons").status_code, 200)

    def test_reply_has_structured_turn_contract(self):
        start = self.start()
        response = self.client.post(
            "/api/chat/reply",
            json={"session_id": start["session"]["id"], "text": "What does name mean?", "input_mode": "typed"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("turn", data)
        self.assertIn("pronunciation", data)
        self.assertIn("segment_grade", data)
        self.assertEqual(data["turn"]["task_action"], "answer_then_resume")

    def test_unified_text_turn_never_returns_pronunciation(self):
        start = self.start()
        response = self.client.post(
            "/api/turn/text",
            json={"session_id": start["session"]["id"], "text": "My name is Yuelin."},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["turn"]["intent"], "answer")
        self.assertIsNone(data["pronunciation"])

    def test_unified_audio_turn_transcribes_and_answers_without_scoring_normal_answer(self):
        start = self.start()
        response = self.client.post(
            "/api/turn/audio",
            data={"session_id": start["session"]["id"]},
            files={"audio": ("speech.wav", b"x" * 2000, "audio/wav")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["student_text"], "My name is Yuelin.")
        self.assertIsNone(data["pronunciation"])
        self.assertEqual(data["transcription"]["mode"], "mock")

    def test_unified_audio_turn_assesses_only_after_repeat_state_is_active(self):
        start = self.start()
        sid = start["session"]["id"]
        calls = []

        def assess(raw, target):
            calls.append(target)
            return {
                "mode": "mock", "reference_text": target, "score": 92,
                "accuracy": 92, "fluency": 91, "completeness": 100,
                "prosody": 90, "words": [], "weak_words": [], "error": None,
            }

        server.azure_speech.assess_scripted = assess
        self.client.post("/api/turn/text", json={"session_id": sid, "text": "..."})
        self.client.post("/api/turn/text", json={"session_id": sid, "text": "..."})

        response = self.client.post(
            "/api/turn/audio",
            data={"session_id": sid},
            files={"audio": ("speech.wav", b"x" * 2000, "audio/wav")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(calls, ["My name is Mike."])
        self.assertTrue(data["turn"]["should_score"])
        self.assertEqual(data["pronunciation"]["reference_text"], "My name is Mike.")

    def test_client_cannot_tamper_with_progress_or_grade(self):
        start = self.start()
        fake = {**start["session"], "segment_idx": 99, "pending": None, "grades": {"segments": {"MEET": "A"}}}
        response = self.client.post(
            "/api/chat/reply",
            json={"session": fake, "text": "What does name mean?", "input_mode": "typed"},
        )
        data = response.json()
        self.assertEqual(data["session"]["segment_idx"], 0)
        self.assertEqual(data["session"]["pending"]["id"], "MEET_Q1")
        self.assertEqual(data["session"]["grades"]["segments"], {})

    def test_recognize_is_asr_only_and_returns_short_lived_audio_id(self):
        start = self.start()
        response = self.client.post(
            "/api/recognize",
            data={"session_id": start["session"]["id"]},
            files={"audio": ("speech.wav", b"x" * 2000, "audio/wav")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["audio_id"])
        self.assertIsNone(data["feedback"])

    def test_scripted_assessment_runs_only_for_repeat_audio(self):
        start = self.start()
        sid = start["session"]["id"]
        self.client.post("/api/chat/reply", json={"session_id": sid, "text": "...", "input_mode": "typed"})
        self.client.post("/api/chat/reply", json={"session_id": sid, "text": "...", "input_mode": "typed"})
        recognized = self.client.post(
            "/api/recognize",
            data={"session_id": sid},
            files={"audio": ("speech.wav", b"x" * 2000, "audio/wav")},
        ).json()
        response = self.client.post(
            "/api/chat/reply",
            json={
                "session_id": sid,
                "text": "My name is Yuelin.",
                "input_mode": "audio",
                "audio_id": recognized["audio_id"],
            },
        )
        data = response.json()
        self.assertTrue(data["turn"]["should_score"])
        self.assertEqual(data["pronunciation"]["reference_text"], "My name is Mike.")


if __name__ == "__main__":
    unittest.main()
