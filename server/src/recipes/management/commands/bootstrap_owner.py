"""Create the site owner's superuser account once, with no built-in credentials."""

import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

USERNAME_VAR = "DJANGO_SUPERUSER_USERNAME"
EMAIL_VAR = "DJANGO_SUPERUSER_EMAIL"
PASSWORD_VAR = "DJANGO_SUPERUSER_PASSWORD"


class Command(BaseCommand):
    help = (
        f"Create the owner superuser from {USERNAME_VAR}, {EMAIL_VAR} and {PASSWORD_VAR}, "
        "prompting for any that are unset. Does nothing if the username already exists."
    )

    def add_arguments(self, parser):
        """Register command-line arguments."""
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="Fail instead of prompting when a variable is unset.",
        )

    def handle(self, *args, **options):
        """Create the owner unless an account with that username exists."""
        interactive = options["interactive"]
        user_model = get_user_model()

        username = self._value(var=USERNAME_VAR, prompt="Username: ", interactive=interactive)
        if user_model.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f"User {username!r} already exists; nothing to do")
            )
            return

        email = self._value(var=EMAIL_VAR, prompt="Email: ", interactive=interactive)
        try:
            validate_email(email)
        except ValidationError as exc:
            msg = f"Invalid email address: {email!r}"
            raise CommandError(msg) from exc

        password = os.environ.get(PASSWORD_VAR, "")
        if not password:
            password = self._prompt_password(interactive=interactive)
        user = user_model(username=username, email=email)
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            msg = "Password rejected: " + " ".join(exc.messages)
            raise CommandError(msg) from exc

        user_model.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created superuser {username!r}"))

    def _value(self, *, var: str, prompt: str, interactive: bool) -> str:
        """Read a variable from the environment, prompting if it is unset or blank."""
        value = os.environ.get(var, "").strip()
        if value:
            return value
        if not interactive:
            msg = f"{var} is not set"
            raise CommandError(msg)
        try:
            value = input(prompt).strip()
        except EOFError as exc:
            msg = f"{var} is not set and there is no input to prompt"
            raise CommandError(msg) from exc
        if not value:
            msg = f"{var} is required"
            raise CommandError(msg)
        return value

    def _prompt_password(self, *, interactive: bool) -> str:
        """Ask for the password twice without echoing it."""
        if not interactive:
            msg = f"{PASSWORD_VAR} is not set"
            raise CommandError(msg)
        try:
            password = getpass.getpass("Password: ")
            confirmation = getpass.getpass("Password (again): ")
        except EOFError as exc:
            msg = f"{PASSWORD_VAR} is not set and there is no input to prompt"
            raise CommandError(msg) from exc
        if password != confirmation:
            msg = "Passwords do not match"
            raise CommandError(msg)
        return password
