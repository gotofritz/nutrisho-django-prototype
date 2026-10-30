from django.db import models
from django.db.models.functions import Lower


class Cuisine(models.Model):
    id = models.AutoField(primary_key=True)
    cuisine = models.CharField(
        "region.area.subarea just as placeholder", max_length=200, unique=True
    )
    objects = models.Manager()

    class Meta:
        constraints = [
            # Italian and italian are the same cuisine; the editor resolves typed
            # names case-insensitively (recipes.services.name_resolution).
            models.UniqueConstraint(Lower("cuisine"), name="cuisine_ci_unique"),
        ]

    def __str__(self) -> str:
        """Return the cuisine name."""
        return str(self.cuisine)

    def natural_key(self):
        """Return the natural key used by fixtures."""
        return self.cuisine
