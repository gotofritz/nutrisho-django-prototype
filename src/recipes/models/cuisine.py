from django.db import models


class Cuisine(models.Model):
    id = models.AutoField(primary_key=True)
    cuisine = models.CharField(
        "region.area.subarea just as placeholder", max_length=200, unique=True
    )
    objects = models.Manager()

    def natural_key(self):
        return self.cuisine

    def __str__(self) -> str:
        return str(self.cuisine)
