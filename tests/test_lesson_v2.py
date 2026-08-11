# -*- coding: utf-8 -*-
"""Contract tests for the independent lesson-v2 content project."""

from __future__ import annotations

import json
import unittest

from app import dialogue_manager, lesson_contract, lesson_engine, llm, parser


def sample_lesson() -> dict:
    def segment(code, name, task):
        return {
            "code": code,
            "name_zh": name,
            "duration_minutes": 6,
            "mission": f"Complete {name} in a natural dialogue.",
            "interest_hook": "Let the learner choose a real answer.",
            "language_targets": {
                "active_vocabulary": ["hello"],
                "receptive_vocabulary": [],
                "sentence_frames": [task["sample_answers"][0]],
                "pronunciation_focus": [],
                "grammar_focus": [],
            },
            "tasks": [task],
            "transition": "Let's continue.",
            "assessment": {"pass_rule": "Complete the meaning goal."},
        }

    return {
        "schema_version": "2.0",
        "id": "unit99-contract-test",
        "unit": 99,
        "title_zh": "契约测试",
        "title_en": "Contract Test",
        "duration_minutes": 20,
        "language_standard": "en-US",
        "learning_outcomes": ["Speak in three task types."],
        "teaching_rules": ["Meaning before correction."],
        "segments": [
            segment(
                "ANSWER",
                "自然回答",
                {
                    "id": "ANSWER_Q1",
                    "title": "Say a name",
                    "expected_action": "open_answer",
                    "teacher_prompt": "What's your name?",
                    "completion_rule": {"semantic_goal": "say a name", "required_any": ["name", "I'm"]},
                    "sample_answers": ["My name is Yuelin.", "I'm Yuelin."],
                    "help": {"hint": "Start with My name...", "model": "My name is Yuelin."},
                    "correction": {"priority": "Use is after My name.", "strategy": "recast"},
                },
            ),
            segment(
                "ASK",
                "角色提问",
                {
                    "id": "ASK_Q1",
                    "title": "Ask about an animal",
                    "expected_action": "ask_question",
                    "teacher_prompt": "It has two long ears.",
                    "completion_rule": {"semantic_goal": "ask a relevant animal question"},
                    "sample_answers": ["Can it jump?", "Is it a rabbit?"],
                    "help": {"hint": "Ask: Can it...", "model": "Can it jump?"},
                    "correction": {"priority": "Use question word order.", "strategy": "recast"},
                },
            ),
            segment(
                "REPEAT",
                "明确跟读",
                {
                    "id": "REPEAT_Q1",
                    "title": "Repeat one sentence",
                    "expected_action": "repeat",
                    "teacher_prompt": "Listen and repeat: Nice to meet you.",
                    "completion_rule": {"semantic_goal": "repeat the model sentence"},
                    "sample_answers": ["Nice to meet you."],
                    "reference_text": "Nice to meet you.",
                    "help": {"hint": "Listen once more.", "model": "Nice to meet you."},
                    "correction": {"priority": "Keep the phrase smooth.", "strategy": "one_word_feedback"},
                },
            ),
        ],
        "integration_challenge": "Use the three skills in one short conversation.",
        "exit_checks": ["Answer", "Ask", "Repeat"],
    }


class LessonV2Tests(unittest.TestCase):
    def setUp(self):
        self.original_enabled = llm.enabled
        llm.enabled = lambda: False

    def tearDown(self):
        llm.enabled = self.original_enabled

    def test_contract_and_json_parser_accept_v2(self):
        lesson = sample_lesson()
        self.assertEqual(lesson_contract.validate_v2(lesson), [])
        parsed = parser.parse_lesson_file("unit99.lesson.json", json.dumps(lesson).encode("utf-8"))
        self.assertEqual(parsed["schema_version"], "2.0")
        self.assertEqual([a["expected_action"] for a in lesson_engine.build_activities(parsed)], ["open_answer", "ask_question", "repeat"])

    def test_role_question_completes_instead_of_becoming_an_interruption(self):
        lesson = lesson_contract.normalize_v2(sample_lesson())
        session, _ = dialogue_manager.new_session(lesson, "role-question", "test")
        session["activity_pos"] = 1
        session["task_idx"] = 1
        session["segment_idx"] = 1
        session["pending"] = lesson_engine.make_pending(lesson_engine.build_activities(lesson)[1])
        decision = dialogue_manager.analyze(session, "Can it jump?")
        result = dialogue_manager.apply_turn(session, lesson, "Can it jump?", decision, input_mode="typed")
        self.assertEqual(result["turn"]["intent"], "question")
        self.assertTrue(result["turn"]["task_completed"])
        self.assertTrue(result["turn"]["progressed"])
        self.assertIsNone(result["pronunciation"])

    def test_repeat_reference_is_for_audio_only(self):
        lesson = lesson_contract.normalize_v2(sample_lesson())
        session, _ = dialogue_manager.new_session(lesson, "repeat", "test")
        session["activity_pos"] = 2
        session["task_idx"] = 2
        session["segment_idx"] = 2
        session["pending"] = lesson_engine.make_pending(lesson_engine.build_activities(lesson)[2])
        decision = dialogue_manager.analyze(session, "Nice to meet you.")
        result = dialogue_manager.apply_turn(session, lesson, "Nice to meet you.", decision, input_mode="typed")
        self.assertEqual(result["turn"]["task_action"], "await_audio_repeat")
        self.assertFalse(result["turn"]["progressed"])
        self.assertIsNone(result["pronunciation"])

    def test_invalid_repeat_contract_is_rejected(self):
        lesson = sample_lesson()
        del lesson["segments"][2]["tasks"][0]["reference_text"]
        self.assertTrue(any("reference_text" in error for error in lesson_contract.validate_v2(lesson)))


if __name__ == "__main__":
    unittest.main()
