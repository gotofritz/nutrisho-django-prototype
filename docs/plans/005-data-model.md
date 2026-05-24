# Plan 005: Data Model Improvements

## Status: Draft

## Goal

Review and refactor existing models. Introduce `pydantic` for data validation where appropriate.

## Tasks

- Audit existing models for missing constraints, null/blank inconsistencies, missing `__str__` methods
- Use `pydantic` for data structures passed between layers (e.g. YAML parsing, form data)
- Add model-level validation where Django ORM allows
- Review `IngredientInRecipe.quantity` precision (FloatField vs DecimalField)

## TDD cycles

(Define specific cycles once audit is complete)
