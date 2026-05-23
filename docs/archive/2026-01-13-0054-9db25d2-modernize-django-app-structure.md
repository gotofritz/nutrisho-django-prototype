# Project Plan: Phase 1, Step 2 - Modernize Django App Structure

**Goal:** Refactor the project structure to use the standard `src/` layout, improving organization and packaging.

## Current State

- The project code currently resides in a nested `nutrisho/` directory:
  - `nutrisho/nutrisho/` (Project settings)
  - `nutrisho/recipes/` (Main application)
  - `nutrisho/manage.py`
- An existing `src/` directory contains only `__pycache__` artifacts.
- `pyproject.toml` is configured for the project but may need adjustment for the `src` layout.

## Implementation Steps

### 1. Cleanup & Preparation

- [x] **Clean `src/`**: Remove the existing `src/` directory containing artifacts.
- [x] **Create Directories**: Create new `src/` and `scripts/` directories.

### 2. Relocate Codebase

- [x] **Move Project Config**: Move `nutrisho/nutrisho` to `src/nutrisho`.
- [x] **Move App**: Move `nutrisho/recipes` to `src/recipes`.
- [x] **Move Entry Points**:
  - [x] Move `nutrisho/manage.py` to the project root.
  - [x] Move `nutrisho/import.py` to `scripts/import.py` (or `src/scripts` if it's a module).
- [x] **Cleanup**: Remove the now empty (or nearly empty) `nutrisho/` directory.

### 3. Configuration Updates

- [x] **`pyproject.toml`**:
  - Ensure build system discovery finds packages in `src`.
  - Update `[project]` or tool config if necessary to explicitly point to `src`.
- [x] **`manage.py`**:
  - Adjust imports if necessary (though with editable install, it should work).
  - Ensure `sys.path` is correct if running without installation.
- [x] **`src/nutrisho/settings.py`**:
  - Update `BASE_DIR` calculation to point to the project root (up 3 levels from settings file: `src/nutrisho/settings.py` -> `src/nutrisho` -> `src` -> `root`).
  - Verify `TEMPLATES` and `STATIC` configuration works with the new paths.

### 4. Verification

- [x] **Install**: Run `uv sync` (or reinstall in editable mode) to ensure the `src` layout is recognized.
- [x] **Check**: Run `python manage.py check`.
- [x] **Test**: Run `task test` (or `pytest`) to ensure no import errors.
- [x] **Run**: Verify the development server starts with `python manage.py runserver`.

## Blockers/Risks

- **Import paths**: Hardcoded imports in the codebase (unlikely in this setup, but possible in scripts) might break.
- **IDE config**: `.vscode/settings.json` might need updating to recognize `src` as a source root.
