#!/bin/bash

if [ $# -eq 0 ]; then
    echo "Usage: $0 RECIPE_ID1 [RECIPE_ID2 ...]"
    exit 1
fi

DB_PATH="/Users/fritz/work/nutrisho-django-prototype/nutrisho/db.sqlite3"

for RECIPE_ID in "$@"; do
    echo "Processing RECIPE: $RECIPE_ID"

    sqlite-utils query $DB_PATH "DELETE FROM recipes_ingredientinrecipe WHERE ingredient_group_id in (SELECT id from recipes_ingredientgroup WHERE recipe_id=$RECIPE_ID);"
    sqlite-utils query $DB_PATH "DELETE FROM recipes_ingredientgroup WHERE recipe_id=$RECIPE_ID;"
    sqlite-utils query $DB_PATH "DELETE FROM recipes_step WHERE recipe_id=$RECIPE_ID;"
    sqlite-utils query $DB_PATH "DELETE FROM recipes_tag_recipe WHERE recipe_id=$RECIPE_ID;"
    sqlite-utils query $DB_PATH "DELETE FROM recipes_recipe WHERE id=$RECIPE_ID;"

    echo "Finished processing $RECIPE_ID"
    echo
done

echo "All specified IDs have been processed."
