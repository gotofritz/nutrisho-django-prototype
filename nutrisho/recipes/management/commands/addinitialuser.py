from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db.utils import IntegrityError


class Command(BaseCommand):
    help = "Adds a single recipe (pass it as arg)"

    def handle(self, *args, **options):
        try:
            User.objects.create(username="gotofritz")
            self.stdout.write(self.style.SUCCESS("Successfully created user"))
        except IntegrityError:
            self.stdout.write(self.style.SUCCESS("User already created"))
