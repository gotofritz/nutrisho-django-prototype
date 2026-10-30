from django.apps import AppConfig


class RecipesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "recipes"

    def ready(self) -> None:
        """Connect signal receivers."""
        from recipes import signals  # noqa: F401 - connects the receivers
