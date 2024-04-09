-- Replace id by hand, then run
-- sqlite3 /Users/fritz/work/nutrisho-django-prototype/nutrisho/db.sqlite3  < /Users/fritz/work/nutrisho-django-prototype/nutrisho/nutrisho/remove_a_recipe.sql

DELETE FROM recipes_ingredientinrecipe WHERE ingredient_group_id in (SELECT id from recipes_ingredientgroup WHERE recipe_id=350);
DELETE FROM recipes_ingredientgroup WHERE recipe_id=350;
DELETE FROM recipes_step WHERE recipe_id=350;
DELETE FROM recipes_tag_recipe WHERE recipe_id=350;
DELETE FROM recipes_recipe WHERE id=350;