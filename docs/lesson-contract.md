# Lesson-v2 contract

`lesson-v2` is the stable interface between the independent lesson repository
and this website. The authoritative runtime validator is
`app/lesson_contract.py`; the lesson repository carries a matching JSON Schema.

## Top-level requirements

- `schema_version`: exactly `2.0`
- `id`, `unit`, `title_zh`, `title_en`
- `duration_minutes`
- `language_standard`, currently `en-US`
- exactly three `segments`
- `learning_outcomes`, `teaching_rules`, `exit_checks`

## Segment requirements

Each segment has a unique uppercase `code`, Chinese name, duration, mission,
interest hook, language targets, tasks, transition, and pass rule.

Active vocabulary should normally contain 4-7 items. Receptive vocabulary is
separate. Grammar and pronunciation focus are lists so authors can deliberately
keep them small.

## Task requirements

Every task explicitly declares:

- `expected_action`: `open_answer`, `fixed_answer`, `ask_question`, `repeat`,
  or `free_talk`
- `teacher_prompt`
- a semantic `completion_rule`
- two or more natural `sample_answers` where practical
- `help` and `correction` strategies

`reference_text` is allowed only for `repeat`. Sample answers are semantic
examples, not pronunciation references and not exact-match requirements.

## Action semantics

- `open_answer`: multiple personal answers can complete the task.
- `fixed_answer`: a specific knowledge target exists, but wording may vary.
- `ask_question`: a relevant learner-role question completes the task.
- `repeat`: explicit audio repetition; real audio is required for scoring.
- `free_talk`: guided extension with a defined speaking goal.

## Import

Upload a file named like `unit03.lesson.json`, review the server preview, then
confirm it into the course library. Validate before upload:

```powershell
.\venv\Scripts\python.exe scripts\validate_lessons.py G:\path\to\units
```
