# Testing and release checks

## Automated checks

```powershell
.\venv\Scripts\python.exe -m compileall app server.py tests
.\venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static\app.js
git diff --check
```

The unit/integration suite covers API ownership, dialogue state, interruption
recovery, explicit repeat scoring, degradation, history order, grades, and the
lesson-v2 contract.

## Lesson release gate

```powershell
.\venv\Scripts\python.exe scripts\validate_lessons.py <file-or-directory>
```

A release lesson must validate, contain three segments, use unique task IDs,
mark learner-role questions as `ask_question`, and reserve reference text for
explicit repeat tasks.

## UI release gate

For layout or interaction changes, use a running local server and check:

- 1440x900 desktop.
- 1024x768 iPad landscape.
- ordinary answer, spontaneous question, learner-role question, help, explicit
  repeat card, typed repeat, parent details, and console errors.

## Real service smoke test

When credentials are available and service integration changed, test one
DeepSeek fast JSON turn, one optional reasoning call, one Azure TTS call, and a
real microphone STT/repeat flow. Never print secrets or audio.
