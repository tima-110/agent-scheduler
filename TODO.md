# TODO

## Ideas
- [x] Rename CLI to `agent-handler`
- [x] Write a sample/example task row when initializing the sheet (after header) so the user has a template to follow
- [x] Interactive CLI for managing task rows — `agent-handler task add/edit/remove`

- [x] Add `stream-json` as an output format option — Claude Code and Gemini support `--output-format stream-json`
- [x] Make `model` optional in TaskEntry — agent CLIs have their own defaults; only pass `--model` if explicitly set

## Fixes
- [x] Fix gws command shape (`+read` not `export`)
- [x] `sync`/`init` error handling — surface gws stderr instead of raw traceback
- [x] `init` detects empty sheet and offers to write header row
- [x] `setup-sheet` standalone command for writing header row

## Testing Notes
