from argparse import ArgumentError
import json
from django.core.management.base import BaseCommand
from django.utils.encoding import force_str
import yaml
import unicodedata
import re
from pathlib import Path

from recipes.models.ingredient import Ingredient
from recipes.models.cuisine import Cuisine
from recipes.models.ingredient_group import IngredientGroup
from recipes.models.ingredient_in_recipe import IngredientInRecipe
from recipes.models.recipe import Recipe
from recipes.models.step import Step
from recipes.models.tag import Tag


class Command(BaseCommand):
    help = "Dumps all the recipes as yaml files"

    @classmethod
    def clean(cls, s):
        if s is None:
            return None
        tmp = force_str(s)
        tmp = re.sub(r" {2,}", " ", tmp)
        return tmp.strip()

    def add_arguments(self, parser):
        parser.add_argument("dir", type=str, help="Path to recipe")

    def handle(self, *args, **options):
        dir = Path(options["dir"])
        if not dir.is_dir():
            raise ArgumentError("You need to pass a dir where yml files can be saved")

        all_recipes = (x for x in Recipe.objects.all())
        for recipe in all_recipes:
            as_data = {}
            as_data["description"] = recipe.short_description
            as_data["title"] = recipe.recipe_name.strip()
            as_data["cuisine"] = (
                recipe.cuisine.cuisine if recipe.cuisine is not None else None
            )
            as_data["source"] = recipe.source_instance
            as_data["tags"] = [tag.tag for tag in recipe.tag.all()]
            as_data["directions"] = {
                "step": [step.step_text for step in recipe.step.all()]
            }
            as_data["ingredients"] = {"serves": 1, "group": []}
            for group in recipe.ingredients_group.all():
                group = {
                    "name": group.group_name,
                    "ingredient": [
                        {
                            "measurement": ing.unit,
                            "name": ing.ingredient.ingredient_name,
                            "preparation": ing.preparation,
                            "quantity": None
                            if ing.quantity is None
                            else str(ing.quantity),
                        }
                        for ing in group.ingredient.all()
                    ],
                }
                as_data["ingredients"]["group"].append(group)
            filename = unicodedata.normalize("NFKC", as_data["title"])
            filename = re.sub(r"[^\w\s-]", "", filename)
            with open(dir / f"{filename}.yml", "w", encoding="utf-8") as stream:
                yaml.dump(as_data, stream, indent=4, allow_unicode=True)
            print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            print(dir / f"{filename}.yml")
            print(yaml.dump(as_data, indent=2))
