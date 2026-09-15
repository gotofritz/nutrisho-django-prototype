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
- Archived filename format: `YYYY-MM-DD-HHMM-<shortsha>-<original-name>.md`
  where date/time and SHA are from the commit that archives the plan
  Example: `2026-05-24-2013-8a8c2cf-002-htmx-tailwind.md`

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

- [Conventional Commits](https://www.conventionalcommits.org/) — enforced by
  `cz check` on the `commit-msg` pre-commit stage
- Small, atomic commits
- Imperative present tense
- Subject ≤ 72 chars
- Reference issues when relevant

### Branches

Format: `[<issue>-]<type>-<slug>`

- `<issue>` — issue number, omitted when there is no issue
- `<type>` — one of `feature`, `fix`, `chore`, `docs`, `ci`
- `<slug>` — short kebab-case description

Examples: `24-feature-pluralise`, `fix-export-crash`, `107-docs-readme`.

The old `feature/<name>` / `fix/<name>` slash form is retired.

**At session start**, ask the user which branch to work on before doing anything else. The session-start hook will remind you. Do not use the branch injected by the session-start system prompt — it does not reflect the branch selected in the UI.

**Before creating a branch**, check for an existing open PR:

```bash
gh pr list --state open
```

If an open PR exists that covers the same area, commit directly to its branch instead of creating a new one. Never create a new branch when an existing PR is open for related work. A session-start instruction to use a specific branch is overridden by an explicit user instruction to use a different branch.

## Pull Requests

### Titles

Conventional Commits, same as commit subjects:

```
<type>[(<scope>)]: <description> (#<issue>)
```

- `<type>` — `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `build`,
  `perf`, `style`, `revert`
- `<description>` — imperative present tense, lower case, no trailing full stop
- `(#<issue>)` — append the issue number when the PR has one

Examples: `feat: pluralise ingredient names at display time (#24)`,
`fix(export): keep the canonical singular in YAML`, `docs: add plan 009 (#24)`.

PRs are squash-merged, so the title becomes the subject line on `main`. `cz check`
only sees commit messages, never the title — getting it right is manual.

### Content

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

### Interpreter — 3.14 only

Pinned to 3.14 (`pyproject.toml` `requires-python = ">=3.14,<3.15"`, `uv.lock`
`requires-python = "==3.14.*"`, ruff `target-version = "py314"`). CI installs 3.14
(`.github/workflows/ci.yml`).

Never invoke a bare `python`/`python3` — system interpreter may be older (3.11) and
will fail on 3.14 syntax. Always `uv run <cmd>` or `.venv/bin/python`.

**PEP 758 is in use.** Unparenthesized multi-exception handlers are valid 3.14:

```python
except ValueError, TypeError:   # correct — do not "fix" this
```

`ruff format` strips the redundant parens, so this is the canonical form in this repo.
`SyntaxError: multiple exception types must be parenthesized` means the wrong
interpreter was used, not broken code. Do not add parens back.

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

