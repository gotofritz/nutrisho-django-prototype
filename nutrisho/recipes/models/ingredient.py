from django.db import models


class Ingredient(models.Model):
    CONSTRAINT_CHOICES = [
        ("PSC", "Pescatarian"),
        ("VGT", "Vegetarian"),
        ("VGN", "Vegan"),
    ]
    GROUP_CHOICES = [
        ("VEG", "Vegetable"),
        ("MEA", "Meat"),
        ("SEA", "Seafood"),
        ("FSH", "Fish"),
        ("GRA", "Grain"),
        ("GRN", "Green"),
        ("SPI", "Spice"),
        ("CHE", "Cheese"),
        ("MLK", "Milk product"),
        ("FAT", "Fat"),
        ("CND", "Condiment"),
        ("PUL", "Pulse"),
        ("NUT", "Nut"),
        ("SEE", "Seed"),
        ("FRU", "Fruit"),
        ("EGG", "Egg"),
        ("CHM", "Chemical"),
        ("MSC", "Misc"),
    ]
    name = models.CharField(max_length=64, unique=True)
    dietary_constraint = models.CharField(
        "vegetarian etc", choices=CONSTRAINT_CHOICES, null=True, max_length=32
    )
    family = models.CharField(
        "Anything that will let you find the source: ISDN, url...",
        max_length=32,
        choices=GROUP_CHOICES,
        null=True,
    )

    def natural_key(self):
        return self.name
