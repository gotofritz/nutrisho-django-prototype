from django.db import models


class Cuisine(models.Model):
    cuisine = models.CharField(
        "region.area.subarea just as placeholder", max_length=200, unique=True
    )

    def natural_key(self):
        return self.cuisine
