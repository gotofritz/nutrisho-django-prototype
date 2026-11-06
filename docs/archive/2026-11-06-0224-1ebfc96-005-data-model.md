# Plan 005: Data Model Improvements

## Status: Superseded (2026-11-06, #69)

Never started; archived unfinished. Its tasks were settled or moved to issues:

- `IngredientInRecipe.quantity` is already a `DecimalField`.
- `pydantic` was never adopted: data crossing layers goes through Django forms
  and model fields, and AGENTS.md now says so.
- The model audit became the 2026-10-30 assessment (plan 01): hidden or unused
  fields are #65, reverse accessor names #79, units #67.

## Goal

Review and refactor existing models. Introduce `pydantic` for data validation where appropriate.

## Tasks

- Audit existing models for missing constraints, null/blank inconsistencies, missing `__str__` methods
- Use `pydantic` for data structures passed between layers (e.g. form data)
- Add model-level validation where Django ORM allows
- Review `IngredientInRecipe.quantity` precision (FloatField vs DecimalField)

## TDD cycles

(Define specific cycles once audit is complete)
