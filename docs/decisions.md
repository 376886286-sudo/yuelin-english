# Decisions

## 2026-08-11: keep website and lesson repository independent

The website owns runtime code; the lesson project owns authored content and
standards. Integration uses versioned lesson-v2 JSON. This prevents absolute
path coupling and lets either project evolve independently.

## 2026-08-11: retain FastAPI and vanilla SPA

The existing stack already supports the product and has regression coverage.
A framework migration would add risk without improving the central learning
experience. Infrastructure and domain boundaries are improved in place.

## 2026-08-11: DeepSeek understands; backend decides

LLM output improves natural intent understanding, but deterministic rules own
progression, repeat eligibility, grades, and state recovery.

## 2026-08-11: en-US is the current speech standard

Azure recognition, pronunciation assessment, and teacher voices are en-US.
New canonical lessons should use American spelling/pronunciation guidance until
an explicit, end-to-end decision changes all three services together.

## 2026-08-11: lesson-v2 is preferred; legacy remains supported

Legacy TXT/DOCX imports are useful for migration, but their inferred intent is
not reliable enough for long-term authoring. New content uses explicit tasks.
