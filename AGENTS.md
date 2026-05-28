# AGENTS.md

## General Rules

- Annotate every new method and logic blocks in Korean. (refer to gui.py for style references)
- Follow the existing layered architecture.
- Do not bypass the document backend abstraction.
- Add or update tests for every parser behavior change.
- Run `pytest tests` before reporting completion.

## Aseprite Decoder Rules

Before modifying the Aseprite decoder, read:

- `docs/aseprite_codec_extension_plan.txt`
- `docs/aseprite_test_strategy.txt`

The decoder must preserve unknown chunks as raw payloads.
Do not drop unsupported chunks.
Do not change binary parsing behavior without adding tests.