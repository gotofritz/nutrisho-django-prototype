# Nutrisho

A recipe manager built with DJango. Inspired by the excellent <http://www.obeythetestinggoat.com/book/chapter_01.html>

## Running the app

```bash
❯ task run
```

## Importing yaml recipes

Create a folder recipes_xxxx/, next to the other ones, then ..

```bash
❯ source venv/bin/activate
❯ cd nutrisho
❯ python manage.py batch_load_yaml_recipes ../recipes_xxxx/
```

Then go to <http://127.0.0.1:8000/recipes/>

## Editing recipes

You need to do it directly in the SQL, in `sql_to_edit_recipes_hack/`

```bash
❯ sqlite3 ~/work/nutrisho-django-prototype/nutrisho/db.sqlite3 < ~/work/nutrisho-django-prototype/nutrisho/sql_to_edit_recipes_hack/edit_recipe.sql
```

## LICENSE

This is licensed under the [0BSD license](LICENSE.md).
