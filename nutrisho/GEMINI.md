# Project Info

- Issue tracker: Github
- Repository: Use `gh` CLI for all GitHub operations
- Task runner is Taskfile

## Development Standards

**Start here:** README.md for purpose, docs/project-plan.md for current state

## Code

- Every important file has a docstring at the top explaining its purpose
- Type hints on all function signatures. Use native types when possible, i.e. `list` and not `List`
- Use pydantic for data models
- All imports root-relative
- When adding an import, prefer adding to the top of the file rather than in the body
- All commands should be run from the project root
- At the start of a session run source .venv/bin/activate
- Organise work in small, atomic commits
- Limit linting exceptions. If you have to, add a comment explaining why you think you have to.

## Python

- Tools: TBC
- Django
- Enforce named arguments for functions with >1 parameter
- Testing: pytest with faker, polyfactory, pytest-data
- Always create a conftest for mocks
