# Architecture

## System flow

```text
Browser audio/text
       |
       v
FastAPI /api/turn/audio or /api/turn/text
       |
       +-- Azure STT (audio only)
       |
       v
Turn Manager: semantic intent + natural response draft
       |
       v
Dialogue Manager + Lesson Engine: deterministic state transition
       |
       +-- Azure scripted assessment only for explicit repeat audio
       |
       v
Server-owned session -> browser rendering -> optional Azure TTS
```

## Module ownership

- `server.py`: transport, API orchestration, active session lookup.
- `app/lesson_contract.py`: lesson-v2 validation and compatibility mirrors.
- `app/parser.py`: file extraction and legacy/v2 import.
- `app/lesson_engine.py`: ordered activities and pending-task construction.
- `app/turn_manager.py`: one semantic decision per learner turn.
- `app/dialogue_manager.py`: history, interruption/resume, hints, completion.
- `app/scoring.py`: independence grades only.
- `app/azure_speech.py`: STT, scripted pronunciation, and TTS capabilities.
- `app/storage.py`: local persistence.
- `static/`: UI rendering; no teaching-rule authority.

## Project boundary

The lesson project may be stored anywhere and may have its own tools and
history. The website does not import it. A lesson enters this repository only
through upload/validation of a `schema_version: "2.0"` JSON artifact.

## Compatibility

- Preferred: lesson-v2 JSON with explicit tasks/actions.
- Supported: legacy TXT/MD/DOCX/DOC/PDF parsing.
- Legacy content uses inferred actions and is therefore less reliable for
  learner-role questions or open semantic variants.
