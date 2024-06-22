# Nutrisho

A recipe manager built with DJango. Inspired by the excellent <http://www.obeythetestinggoat.com/book/chapter_01.html>

## Running the app

```bash
❯ source venv/bin/activate
❯ cd nutrisho
❯ python manage.py runserver
```

## Importing yaml recipes

Create a folder recipes_xxxx/, next to the other ones, then ..

```bash
❯ source venv/bin/activate
❯ cd nutrisho
❯ python manage.py batch_load_yaml_recipes ../recipes_xxxx/
```

Then go to <http://127.0.0.1:8000/recipes/>

## LICENSE

This is licensed under the [0BSD license](LICENSE.md).
