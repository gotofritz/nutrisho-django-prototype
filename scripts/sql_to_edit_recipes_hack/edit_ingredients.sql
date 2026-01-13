-- INSERT INTO recipes_ingredientgroup (index_in_sequence, recipe_id, group_name)
-- VALUES
--   (3, 119, 'Liquids (Optional)'),
--   (4, 119, 'Tomato mixture'),
--   (5, 119, 'Garnish');


-- UPDATE recipes_ingredientinrecipe set
--   preparation = "mashed (optional)"
-- WHERE id = 3682;

-- DELETE FROM recipes_ingredientinrecipe
-- WHERE id = 3676;

INSERT INTO recipes_ingredientinrecipe
  (ingredient_group_id, index_in_sequence, quantity, unit, ingredient_id, preparation, note)
VALUES
   (756, 2, 2,     'cloves',    19, 'chopped', '')
  -- ,(753, 4, 1,     'tsp',      27, '', '')
  -- ,(752, 1, 0.5,   'cup',     205, '', '')
  -- ,(752, 2, 1,     'tbsp',     33, '', '')
  -- ,(754, 2, 20,       'g',     86, 'grated', '')
  -- ,(754, 2, 1,'small knob',    63, '', '')
  ;