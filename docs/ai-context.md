# AI context

Yuelin English is a local-first speaking tutor for a primary-school learner.
The experience should feel like a patient teacher who understands answers,
questions, help requests, and side comments, then returns naturally to the
lesson. Grammar and pronunciation improve gradually without turning every
utterance into a test.

## Current architecture

- FastAPI serves API routes and the vanilla SPA.
- `app/turn_manager.py` classifies a learner turn with DeepSeek V4 Flash JSON
  Output plus deterministic safety guards.
- `app/dialogue_manager.py` owns chronological history and state transitions.
- `app/lesson_engine.py` compiles legacy dialogue lessons or explicit
  lesson-v2 tasks into pending activities.
- `app/azure_speech.py` separates STT from scripted pronunciation assessment.
- Local JSON files store courses, session summaries, review packs, and usage.

## Stable decisions

- Website and lesson repository are separate projects.
- `lesson-v2` JSON is their only integration contract.
- Existing TXT/DOCX imports remain compatibility paths, not the preferred
  authoring format.
- PC and iPad landscape are the supported client layouts.
- DeepSeek does language work; deterministic backend rules retain final
  authority over progression and scoring.

## Useful commands

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe scripts\validate_lessons.py <lesson-or-directory>
python server.py
```

See `docs/lesson-contract.md` before changing lesson fields and
`docs/business-rules.md` before changing turn behavior.
