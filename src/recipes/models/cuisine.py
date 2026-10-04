from django.db import models


class Cuisine(models.Model):
    id = models.AutoField(primary_key=True)
    cuisine = models.CharField(
        "region.area.subarea just as placeholder", max_length=200, unique=True
    )
    objects = models.Manager()

    def __str__(self) -> str:
        """Return the cuisine name."""
        return str(self.cuisine)

    def natural_key(self):
        """Return the natural key used by fixtures."""
        return self.cuisine
