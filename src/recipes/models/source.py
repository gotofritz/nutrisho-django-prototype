from django.db import models


class Source(models.Model):
    short_name = models.CharField("A short name like 'Moro book'", max_length=64, unique=True)
    source = models.CharField(
        "Anything that will let you find the source: ISDN, url...",
        max_length=255,
        unique=True,
    )
    parent = models.ForeignKey(
        "self",
        related_name="children",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )

    def natural_key(self):
        return self.short_name
