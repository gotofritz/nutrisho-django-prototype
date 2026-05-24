# AGENTS.md

## Read First

- `README.md` — project overview
- `docs/initial-context.md` — architecture and constraints
- `docs/plans/*.md` — active plans

## Project Rules

- Use `gh` for all GitHub operations
- Use `task` for workflow discovery
- Run commands from project root

## Plans

- Active: `docs/plans/`
- Archive: `docs/archive/`
- Archive completed plans in the same PR

## Architecture

Update `docs/initial-context.md` before merging changes affecting:
- architecture
- boundaries
- core patterns

## Workflow

Use TDD (`red → green → refactor`).

Reference: `.claude/skills/tdd.md`

Required flow:

1. Write failing test
2. Confirm correct failure
3. Implement minimal fix
4. Refactor with tests green
5. Run `task qa` before PR

## Decision Order

Prioritize:

1. Correctness
2. Passing tests
3. Simplicity
4. Existing patterns
5. Minimal diffs

## Commits & Branches

### Commits

- Small, atomic commits
- Imperative present tense
- Subject ≤ 72 chars
- Reference issues when relevant

### Branches

- `feature/<name>`
- `fix/<name>`

## Pull Requests

- Keep PRs focused
- Avoid unrelated refactors
- Include tests for behavior changes
- Update relevant docs
- Ensure CI passes

## Code Standards

- Concise docstrings for public/non-obvious modules
- Root-relative imports
- Imports at file top
- Minimize lint/type suppressions
- Document suppressions

## Python

### Tooling

- `uv`
- `ruff`
- `ty`
- `pytest`

### Libraries

- CLI: `click`
- Models: `pydantic`

### Rules

- Type hints required
- Prefer native types
- Use named args for multi-parameter functions

### Testing

- Use `pytest`
- Allowed: `faker`, `polyfactory`, `pytest-data`
- Use either function-based or class-based tests, never both
- Shared fixtures/mocks in `conftest.py`

## Environment

```bash
source .venv/bin/activate
```

## Failure Policy

- Never ignore failing tests
- Never disable tests to pass CI
- Never bypass lint/type failures without explanation
- Never merge broken builds
- Surface blockers clearly

## Agent Constraints

- Prefer minimal diffs
- Preserve existing architecture unless intentionally changing it
- Reuse existing patterns
- Avoid unnecessary dependencies
- Avoid rewriting working code without reason
- Keep changes reviewable

## Enforcement

- Pre-commit enabled
- CI via GitHub Actions
- All checks must pass before merge Project Info

