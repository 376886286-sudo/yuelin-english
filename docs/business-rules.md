# Business rules

## Turn classification and progression

DeepSeek may understand and draft language, but only backend state rules can
advance a task or start scoring. A learner question during an answer/repeat
task pauses and resumes it. A question completes the task only when the lesson
declares `expected_action=ask_question`.

Help, free talk, off-topic talk, unclear input, and service degradation do not
silently complete tasks. Two unsuccessful attempts may promote a task to an
explicit model-and-repeat state.

## Pronunciation

The single valid trigger is:

```text
expected_action == repeat
and intent == repeat_attempt
and reference_text is not empty
and input_mode == audio
```

Typed input never creates pronunciation evidence. STT never automatically
runs pronunciation assessment.

## Correction

- Respond to meaning first.
- Correct at most one priority issue in a turn.
- Prefer a natural recast over a grammar lecture.
- Do not require immediate repetition unless the explicit teaching strategy
  promotes the task to repeat.
- Parent records may preserve original/corrected pairs as coaching evidence.

## Grades

- A: independently completed.
- B: completed after a keyword/first-sound hint.
- C: completed after a full model or explicit repeat.
- D: skipped or not completed.

Pronunciation numbers are a separate dimension and cannot change A/B/C/D.
