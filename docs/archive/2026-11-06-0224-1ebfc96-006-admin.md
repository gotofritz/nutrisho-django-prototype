# Plan 006: Admin Interface

## Status: Superseded (2026-11-06, #69)

Never started as written; archived unfinished. Every model is registered in
`src/recipes/admin.py`, and the curation work this plan meant for Django admin
moved into purpose-built staff tools instead: the ingredient clean-up tool
(plans 007 and 008) and the cuisine tool (plan 011). Any further admin polish
can be an issue of its own.

## Goal

Customise Django admin for better management of recipes, ingredients, and other models.

## Tasks

- Register all models with admin
- Add list display fields, search, and filters for Recipe, Ingredient, Cuisine, Tag
- Add inline editors for IngredientInRecipe and Step within Recipe admin
- Add bulk actions

## TDD cycles

(Define specific cycles once scope is confirmed)
