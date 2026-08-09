# -*- coding: utf-8 -*-
"""Regression coverage for the smart-turn acceptance scenarios."""

from __future__ import annotations

import unittest

import server
from app import llm


class DialogueFlowTests(unittest.TestCase):
    def setUp(self):
        self.original_enabled = llm.enabled
        self.original_chat_json = llm.chat_json
        self.original_pronunciation = server.azure_speech.pronunciation
        self.original_add_usage = server.storage.add_usage
        self.original_save_session = server.storage.save_session
        llm.enabled = lambda: False
        server.storage.add_usage = lambda **delta: {**delta}
        server.storage.save_session = lambda session: session
        server.ACTIVE_SESSIONS.clear()
        server._AUDIO_CACHE.clear()
        self.course = server.storage.list_courses()[0]

    def tearDown(self):
        llm.enabled = self.original_enabled
        llm.chat_json = self.original_chat_json
        server.azure_speech.pronunciation = self.original_pronunciation
        server.storage.add_usage = self.original_add_usage
        server.storage.save_session = self.original_save_session
        server.ACTIVE_SESSIONS.clear()
        server._AUDIO_CACHE.clear()

    def start(self):
        response = server.chat_session({"course_id": self.course["id"]})
        return response["session"]["id"], response

    def reply(self, session_id: str, text: str, **extra):
        return server.chat_reply(
            {
                "session_id": session_id,
                "text": text,
                "input_mode": extra.pop("input_mode", "typed"),
                **extra,
            }
        )

    def finish_meet_first_activity(self, sid):
        return self.reply(sid, "My name is Yuelin.")

    def move_to_feel(self, sid):
        self.reply(sid, "My name is Yuelin.")
        result = self.reply(sid, "Nice to meet you, too.")
        self.assertEqual(result["session"]["pending"]["id"], "FEEL_Q1")
        return result

    def test_session_has_pending_and_chronological_opening(self):
        _, start = self.start()
        session = start["session"]
        self.assertEqual(session["pending"]["id"], "MEET_Q1")
        self.assertEqual([e["role"] for e in session["history"]], ["ai"])
        self.assertEqual(session["history"][0]["text"], start["ai_message"])

    def test_t01_open_answer_progresses_without_pronunciation_score(self):
        sid, _ = self.start()
        result = self.reply(sid, "My name is Yuelin.")
        self.assertEqual(result["turn"]["user_act"], "answer")
        self.assertTrue(result["turn"]["progressed"])
        self.assertFalse(result["turn"]["should_score"])
        self.assertIsNone(result["pronunciation"])
        self.assertIsNone(result["segment_grade"])

    def test_t02_open_answer_variation_is_accepted(self):
        sid, _ = self.start()
        self.move_to_feel(sid)
        result = self.reply(sid, "Good!")
        self.assertEqual(result["turn"]["semantic_result"], "valid")
        self.assertTrue(result["turn"]["progressed"])
        self.assertFalse(result["turn"]["should_score"])

    def test_t03_english_question_answers_and_resumes_without_progress(self):
        sid, _ = self.start()
        result = self.reply(sid, "What does name mean?")
        self.assertEqual(result["turn"]["user_act"], "question")
        self.assertFalse(result["turn"]["progressed"])
        self.assertFalse(result["turn"]["should_score"])
        self.assertEqual(result["session"]["pending"]["id"], "MEET_Q1")
        self.assertIn("Name means", result["ai_message"]["text"])
        self.assertIn("What's your name?", result["ai_message"]["text"])

    def test_t04_chinese_question_answers_and_resumes(self):
        sid, _ = self.start()
        result = self.reply(sid, "name 是什么意思？")
        self.assertEqual(result["turn"]["user_act"], "question")
        self.assertFalse(result["turn"]["progressed"])
        self.assertEqual(result["session"]["pending"]["id"], "MEET_Q1")
        self.assertIsNone(result["pronunciation"])

    def test_t05_reverse_question_is_not_an_answer(self):
        sid, _ = self.start()
        result = self.reply(sid, "What's your name?")
        self.assertEqual(result["turn"]["user_act"], "question")
        self.assertFalse(result["turn"]["progressed"])

    def test_t06_help_request_gives_hint(self):
        sid, _ = self.start()
        result = self.reply(sid, "I don't know how to say it.")
        self.assertEqual(result["turn"]["user_act"], "help_request")
        self.assertEqual(result["turn"]["support_level"], "hint")
        self.assertFalse(result["turn"]["progressed"])
        self.assertEqual(result["session"]["pending"]["hint_level"], 1)

    def test_t07_repeat_audio_uses_scripted_pronunciation(self):
        sid, _ = self.start()
        self.reply(sid, "...")
        self.reply(sid, "...")
        server._AUDIO_CACHE["audio1"] = {"raw": b"x" * 2000, "created": 1, "session_id": sid}
        server.azure_speech.pronunciation = lambda raw, target: {
            "mode": "mock", "reference_text": target, "score": 90,
            "accuracy": 90, "fluency": 88, "completeness": 100,
            "prosody": 87, "words": [], "weak_words": [], "error": None,
        }
        result = self.reply(
            sid,
            "My name is Yuelin.",
            input_mode="audio",
            audio_id="audio1",
        )
        self.assertTrue(result["turn"]["should_score"])
        self.assertEqual(result["pronunciation"]["reference_text"], "My name is Mike.")

    def test_t08_low_repeat_score_retries_once(self):
        sid, _ = self.start()
        self.reply(sid, "...")
        self.reply(sid, "...")
        server._AUDIO_CACHE["audio2"] = {"raw": b"x" * 2000, "created": 1, "session_id": sid}
        server.azure_speech.pronunciation = lambda raw, target: {
            "mode": "mock", "reference_text": target, "score": 72,
            "accuracy": 72, "fluency": 75, "completeness": 60,
            "prosody": 70, "words": [], "weak_words": ["name"], "error": None,
        }
        result = self.reply(sid, "My name is Yuelin.", input_mode="audio", audio_id="audio2")
        self.assertFalse(result["turn"]["progressed"])
        self.assertEqual(result["turn"]["task_action"], "retry")
        self.assertEqual(result["session"]["pending"]["repeat_attempts"], 1)

    def test_repeat_service_error_holds_task_without_showing_fake_score(self):
        sid, _ = self.start()
        self.reply(sid, "...")
        self.reply(sid, "...")
        server._AUDIO_CACHE["audio-error"] = {"raw": b"x" * 2000, "created": 1, "session_id": sid}
        server.azure_speech.pronunciation = lambda raw, target: {
            "mode": "azure", "reference_text": target, "score": 0,
            "accuracy": 0, "fluency": 0, "completeness": 0,
            "prosody": None, "words": [], "weak_words": [], "error": "timeout",
        }
        result = self.reply(sid, "My name is Yuelin.", input_mode="audio", audio_id="audio-error")
        self.assertTrue(result["degraded"])
        self.assertTrue(result["turn"]["speech_degraded"])
        self.assertFalse(result["turn"]["progressed"])
        self.assertFalse(result["turn"]["should_score"])
        self.assertIsNone(result["pronunciation"])

    def test_t09_typed_input_never_has_pronunciation(self):
        sid, _ = self.start()
        result = self.reply(sid, "My name is Yuelin.")
        self.assertFalse(result["turn"]["should_score"])
        self.assertIsNone(result["pronunciation"])

    def test_t10_three_questions_do_not_advance(self):
        sid, _ = self.start()
        for text in ("What's your name?", 'What does "name" mean?', "Can I ask a question?"):
            result = self.reply(sid, text)
        self.assertEqual(result["session"]["segment_idx"], 0)
        self.assertEqual(result["session"]["pending"]["id"], "MEET_Q1")

    def test_t11_hint_then_completion_grades_segment_b(self):
        sid, _ = self.start()
        self.reply(sid, "I don't know how to say it.")
        first = self.reply(sid, "My name is Yuelin.")
        self.assertEqual(first["turn"]["support_level"], "hint")
        result = self.reply(sid, "Nice to meet you, too.")
        self.assertEqual(result["segment_grade"], "B")

    def test_t12_demo_then_completion_grades_segment_c(self):
        sid, _ = self.start()
        self.reply(sid, "...")
        demo = self.reply(sid, "...")
        self.assertEqual(demo["session"]["pending"]["expected_mode"], "repeat")
        repeated = self.reply(sid, "My name is Yuelin.")
        self.assertEqual(repeated["turn"]["support_level"], "demo")
        result = self.reply(sid, "Nice to meet you, too.")
        self.assertEqual(result["segment_grade"], "C")

    def test_t13_independent_completion_grades_segment_a(self):
        sid, _ = self.start()
        self.reply(sid, "My name is Yuelin.")
        result = self.reply(sid, "Nice to meet you, too.")
        self.assertEqual(result["segment_grade"], "A")

    def test_t14_skip_grades_segment_d(self):
        sid, _ = self.start()
        self.reply(sid, "skip")
        result = self.reply(sid, "Nice to meet you, too.")
        self.assertEqual(result["segment_grade"], "D")

    def test_t15_history_is_opening_then_student_ai_pairs(self):
        sid, _ = self.start()
        result = self.reply(sid, "My name is Yuelin.")
        self.assertEqual([e["role"] for e in result["session"]["history"]], ["ai", "student", "ai"])
        self.assertEqual(result["session"]["history"][1]["intent"], "answer")

    def test_t16_interruption_resumes_same_pending_task(self):
        sid, _ = self.start()
        before = server.ACTIVE_SESSIONS[sid]["pending"]["id"]
        result = self.reply(sid, "What does worried mean?")
        self.assertEqual(result["session"]["pending"]["id"], before)
        self.assertEqual(result["turn"]["task_action"], "pause_and_resume")

    def test_t17_mixed_language_answer_is_understood(self):
        sid, _ = self.start()
        self.move_to_feel(sid)
        result = self.reply(sid, "我觉得 happy")
        self.assertEqual(result["turn"]["language"], "mixed")
        self.assertEqual(result["turn"]["semantic_result"], "valid")
        self.assertTrue(result["turn"]["progressed"])

    def test_t18_llm_timeout_marks_degraded_and_holds_state(self):
        sid, _ = self.start()
        llm.enabled = lambda: True
        llm.chat_json = lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("forced"))
        result = self.reply(sid, "My name is Yuelin.")
        self.assertTrue(result["degraded"])
        self.assertTrue(result["turn"]["degraded"])
        self.assertFalse(result["turn"]["progressed"])
        self.assertEqual(result["session"]["pending"]["id"], "MEET_Q1")
        self.assertEqual(result["session"]["degraded_count"], 1)

    def test_complete_course_and_summary_use_only_real_evidence(self):
        sid, _ = self.start()
        for text in (
            "My name is Yuelin.",
            "Nice to meet you, too.",
            "I feel happy.",
            "I can't find my cap.",
            "It's in the box.",
            "Yes, it is.",
            "They're on the desk.",
        ):
            result = self.reply(sid, text)
        self.assertTrue(result["session"]["done"])
        self.assertEqual(result["session"]["grades"]["segments"], {"MEET": "A", "FEEL": "A", "FIND": "A"})
        summary = server.summary({"session_id": sid, "duration_min": 5})
        self.assertEqual(summary["record"]["summary"]["error_points"], [])
        self.assertNotIn("be 动词不能丢", str(summary["record"]))


if __name__ == "__main__":
    unittest.main()
