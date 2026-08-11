# Project Agent Guide

## Project overview

This repository is Yuelin's PC/iPad-landscape English speaking tutor. Its goal
is natural, interesting conversation with gradual grammar and pronunciation
coaching. It is not a sentence-clicking or automatic-scoring app.

## Read first

For non-trivial work, read the relevant files in this order:

1. `docs/ai-context.md`
2. `docs/product.md` for product behavior
3. `docs/architecture.md` for code and data flow
4. `docs/lesson-contract.md` for lesson changes
5. `docs/business-rules.md` for dialogue/scoring changes
6. `docs/ui-guidelines.md` for frontend changes

Do not use chat history as the only source of durable project knowledge.

## Technology and boundaries

- Python 3.13, FastAPI, vanilla HTML/CSS/JavaScript.
- DeepSeek V4 Flash handles language understanding and response drafting.
- Azure Speech provides bilingual STT, explicit-repeat pronunciation
  assessment, and TTS.
- The independent lesson repository produces `lesson-v2` JSON files.
- This website must never import code or read lessons directly from an
  external absolute path. The projects integrate only through versioned JSON.
- Keep legacy TXT/DOCX imports compatible while lesson-v2 is adopted.

## Working principles

- Inspect existing behavior and tests before changing code.
- Prefer the smallest coherent change; avoid unrelated rewrites or new
  dependencies.
- The backend owns lesson state, progression, grading, and pronunciation
  eligibility. The browser renders server state.
- Never derive pronunciation scores without real audio.
- Preserve unrelated local changes and runtime data.
- Mark uncertain product facts as `TODO / Needs confirmation` in docs.

## Business invariants

- Ordinary answers, learner questions, help requests, free talk, off-topic
  talk, and typed text never receive pronunciation scores.
- Pronunciation assessment requires `expected_action=repeat`, a
  `repeat_attempt`, a non-empty `reference_text`, and real audio.
- `ask_question` is a lesson task; a relevant learner question completes it.
  A spontaneous question during other actions pauses and resumes the task.
- A/B/C/D measure independence: A independent, B hint, C model/repeat,
  D skipped/not completed. They never map from pronunciation score.
- Small grammar errors use one gentle recast while meaning and speaking flow
  come first.

## UI rules

- Supported layouts: PC and iPad landscape. Mobile portrait is out of scope.
- Conversation stays on the left; speaking/task controls stay on the right.
- The learner sees total pronunciation score, one focus word, and
  encouragement only. Detailed metrics belong to parent mode.
- Do not expose A/B/C/D or technical metrics during ordinary conversation.

## Validation

For a normal backend or lesson-contract change run:

```powershell
.\venv\Scripts\python.exe -m compileall app server.py tests
.\venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static\app.js
git diff --check
```

For UI or interaction changes, also verify at 1440x900 and 1024x768 in a real
browser and inspect console errors. For lesson files, run:

```powershell
.\venv\Scripts\python.exe scripts\validate_lessons.py <path>
```

## Security

- Never print, commit, or copy `.env`, API keys, tokens, or private audio.
- Do not publish production/runtime data or `data/uploads/`.
- Do not change parent access, cloud resources, or external deployments unless
  explicitly requested.

## Git

- Use `codex/` branches for substantial work.
- Keep commits focused and use `feat:`, `fix:`, `refactor:`, `test:`, or
  `docs:` messages that explain intent.
- Review staged scope and `git diff --check` before committing.
- Do not mix runtime counters such as `data/usage.json` into feature commits.

## Completion checklist

- Product and business invariants still hold.
- Lesson-v2 and legacy imports remain compatible when affected.
- Relevant automated tests pass.
- PC/iPad layout is verified when UI changes.
- Docs are updated only for durable behavior or decisions.
- Diff contains no secrets, unrelated files, or generated runtime data.
