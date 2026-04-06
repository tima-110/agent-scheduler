# TODO

## Ideas
- [ ] Rename CLI to `agent-handler` (or similar)
- [ ] Write a sample/example task row when initializing the sheet (after header) so the user has a template to follow
- [ ] Interactive CLI for managing task rows — guided add/remove/edit of schedule entries directly from the terminal (no need to open the sheet manually)

- [x] Make `model` optional in TaskEntry — agent CLIs have their own defaults; only pass `--model` if explicitly set

## Fixes
- [x] Fix gws command shape (`+read` not `export`)
- [x] `sync`/`init` error handling — surface gws stderr instead of raw traceback
- [x] `init` detects empty sheet and offers to write header row
- [x] `setup-sheet` standalone command for writing header row

## Testing Notes
