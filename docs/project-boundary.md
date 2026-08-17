# Website and learning-library boundary

## Two independent systems

| System | Local location on this computer | Responsibility |
| --- | --- | --- |
| Yuelin learning library | `G:\CodexPorjekt\悦琳学习库` | Chinese, mathematics, English, source materials, lesson authoring, preview/review content, exercise sheets, review cards, and long-term learning records |
| English speaking website | `C:\Users\haitao.li\WorkBuddy\英语口语网站` | FastAPI service, browser UI, speech/LLM integration, lesson runtime, session state, assessment, and parent-facing review |

The paths above are workspace locations for people and development tools. They
must never be embedded in website runtime code or lesson JSON.

## Ownership

The learning library is authoritative for learning content. Its AI-native
English speaking project owns canonical `*.lesson.json` files, the matching
schema, authoring standards, teacher guides, and curriculum map. Chinese,
mathematics, non-speaking English practice, preview, and review content also
remain in the learning library.

The website is authoritative for application code and runtime behavior. It
owns the API, UI, speech services, dialogue rules, lesson state, session
records, and pronunciation evidence. Files under `data/` are runtime copies or
records; they are not the canonical lesson source.

## Only integration boundary

The two projects exchange one artifact:

```text
learning library canonical lesson-v2 JSON
                    |
                    | validate, then upload a file
                    v
website parent mode -> preview -> confirm -> runtime course copy
```

The artifact must use `schema_version: "2.0"`. The website may also accept
legacy TXT/DOCX/PDF files for compatibility, but new speaking lessons are
maintained only as lesson-v2 JSON.

The projects must not use:

- Python imports across repositories;
- symlinks, junctions, or shared source directories;
- website code that reads the learning-library absolute path;
- lesson files containing website paths, API keys, recordings, or runtime
  records;
- automatic copying of Chinese, mathematics, or non-speaking English content
  into the speaking website.

## Handoff workflow

1. Author the lesson in the learning library's AI-native speaking project.
2. Run that project's independent validator.
3. Start the website locally and optionally run the lesson project's HTTP
   compatibility check against `http://localhost:8000`.
4. In website parent mode, upload the selected `*.lesson.json`.
5. Review the preview and confirm it into the website course library.
6. Keep future lesson edits in the learning library; upload a new validated
   version instead of editing the website runtime copy as the source.

If another learning module later needs a website, define a new versioned
contract first. Do not extend this speaking website through ad-hoc access to
learning-library folders.
