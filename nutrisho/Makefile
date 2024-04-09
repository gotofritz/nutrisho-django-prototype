SHELL := bash
.SHELLFLAGS := -eu -o pipefail
.ONESHELL:
.DELETE_ON_ERROR:

venv:
	poetry shell || true
.PHONY: venv

clean:
	rm ./db.sqlite3 || true
	rm ./recipes/migrations/0* || true
.PHONY: clean

filldb: venv clean
	 python manage.py makemigrations
	 python manage.py migrate
	 python manage.py addinitialuser
	 python manage.py batch_load_yaml_recipes ../recipes_yaml/
.PHONY: filldb

createsuperuser: venv
	 DJANGO_SUPERUSER_PASSWORD=fritz python manage.py createsuperuser --noinput --username fritz --email fritzthecat@gmail.com
.PHONY: createsuperuser