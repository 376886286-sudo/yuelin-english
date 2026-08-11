# UI guidelines

## Supported form factors

- Desktop baseline: 1440x900.
- Minimum supported iPad landscape: 1024x768.
- Mobile portrait is not a release requirement.

## Learning layout

- Left: chronological conversation and feedback.
- Right: persistent task/speaking controls.
- Bottom-only primary controls are not allowed on supported layouts.
- Right controls remain reachable without scrolling the entire page.
- Conversation may scroll independently.

## Information hierarchy

- Primary: current prompt, learner's real response, teacher response, mic.
- Secondary: translation and replay.
- Explicit repeat only: target sentence and pronunciation expectation.
- Learner pronunciation feedback: total score, encouragement, one focus word.
- Parent details: accuracy, fluency, completeness, prosody, weak words,
  corrections, and independence grade.

## Interaction

- Microphone and Space key provide the main speaking path.
- Typed input remains available for accessibility and service fallback, but it
  never simulates pronunciation.
- During processing, disable conflicting actions and show a clear state.
- Errors return to a recoverable idle/retry state without losing the task.
