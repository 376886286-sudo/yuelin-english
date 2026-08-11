# -*- coding: utf-8 -*-
"""Compatibility wrapper for the V4 Flash turn manager."""

from .turn_manager import (  # noqa: F401
    ANSWER_QUALITIES,
    INTENTS,
    RESPONSE_ACTIONS,
    analyze_turn,
    expected_action,
)

USER_ACTS = INTENTS
SEMANTIC_RESULTS = {"valid", "invalid", "not_applicable"}
