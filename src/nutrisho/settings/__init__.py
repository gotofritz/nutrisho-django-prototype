import os

if os.environ.get("DJANGO_SETTINGS_MODULE") == "nutrisho.settings":
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "nutrisho.settings is not a valid settings module. "
        "Set DJANGO_SETTINGS_MODULE to nutrisho.settings.dev, "
        "nutrisho.settings.prod, or nutrisho.settings.test."
    )
