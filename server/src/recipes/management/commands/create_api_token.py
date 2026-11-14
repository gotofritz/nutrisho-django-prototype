"""Make an API token for a user, for the recipe clipper or another script (#78)."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from recipes.services.api_tokens import create_token


class Command(BaseCommand):
    help = "Make an API token for a user and print its key, which is shown only this once"

    def add_arguments(self, parser):
        """Register command-line arguments."""
        parser.add_argument("username", help="The user the token signs in as")
        parser.add_argument("--name", default="", help="What the token is for, e.g. clipper")

    def handle(self, *args, **options):
        """Make the token and print its key."""
        user = get_user_model().objects.filter(username=options["username"]).first()
        if user is None:
            msg = f"No user named “{options['username']}”."
            raise CommandError(msg)
        _, key = create_token(user=user, name=options["name"])
        self.stdout.write("Send this as “Authorization: Bearer <key>”. It is not shown again:")
        self.stdout.write(key)
