import json
import re
from pathlib import Path

import yaml
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from recipes.models.cuisine import Cuisine
from recipes.models.ingredient import Ingredient
from recipes.models.ingredient_group import IngredientGroup
from recipes.models.ingredient_in_recipe import IngredientInRecipe
from recipes.models.recipe import Recipe
from recipes.models.step import Step
from recipes.models.tag import Tag


class Command(BaseCommand):
    help = "Adds a single recipe or a directory. Source must be yml"

    @classmethod
    def clean(cls, s):
        if s is None:
            return None
        tmp = re.sub(r"\n", " ", s)
        tmp = re.sub(r" {2,}", " ", tmp)
        return tmp.strip()

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", type=str, help="Path to recipe")

    def handle(self, *args, **options):
        user = User.objects.get(username="gotofritz")

        files_to_load = []
        for passed_path in [Path(x) for x in options["paths"]]:
            if passed_path.is_dir():
                files_to_load += [x for x in passed_path.iterdir()]
            else:
                files_to_load.append(passed_path)
        for source_path in files_to_load:
            with open(source_path, "r") as stream:
                recipe_dict = yaml.safe_load(stream)
                print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
                print(source_path)
                print(json.dumps(recipe_dict, indent=2))

                if recipe_dict["cuisine"]:
                    cuisine, _ = Cuisine.objects.get_or_create(
                        cuisine=recipe_dict["cuisine"]
                    )
                    cuisine.save()
                else:
                    cuisine = None

                recipe, _ = Recipe.objects.get_or_create(
                    recipe_name=Command.clean(recipe_dict["title"]),
                    short_description=Command.clean(recipe_dict["description"]),
                    source_instance=recipe_dict["source"] or "",
                    owner=user,
                    cuisine=cuisine,
                )
                recipe.save()

                for i, step_raw in enumerate(recipe_dict["directions"]["step"]):
                    step, _ = Step.objects.get_or_create(
                        step_text=Command.clean(step_raw),
                        index_in_sequence=i + 1,
                        recipe=recipe,
                    )
                    step.save()

                # whatever i used to convert to yaml, was inconsistent; if only a single
                # entry, it'd do a dict and not a list
                serves = (
                    int(recipe_dict["ingredients"]["serves"])
                    if hasattr(recipe_dict["ingredients"], "serves")
                    else 4
                )

                if not isinstance(recipe_dict["ingredients"]["group"], list):
                    recipe_dict["ingredients"]["group"] = [
                        recipe_dict["ingredients"]["group"]
                    ]
                for i, group_dict in enumerate(recipe_dict["ingredients"]["group"]):
                    group, _ = IngredientGroup.objects.get_or_create(
                        group_name=Command.clean(group_dict.get("name")),
                        index_in_sequence=i + 1,
                        recipe=recipe,
                    )
                    group.save()

                    if not isinstance(group_dict["ingredient"], list):
                        group_dict["ingredient"] = [group_dict["ingredient"]]
                    for j, ingredient_raw in enumerate(group_dict["ingredient"]):
                        ingredient, _ = Ingredient.objects.get_or_create(
                            ingredient_name=Command.clean(ingredient_raw.get("name")),
                        )
                        ingredient.save()

                        try:
                            (
                                ingredient_in_recipe,
                                _,
                            ) = IngredientInRecipe.objects.get_or_create(
                                ingredient=ingredient,
                                unit=ingredient_raw.get("measurement"),
                                preparation=ingredient_raw.get("preparation"),
                                quantity=ingredient_raw.get("quantity"),
                                ingredient_group=group,
                                index_in_sequence=j + 1,
                            )
                        except Exception as e:
                            print(
                                f"ERROR with {recipe.recipe_name} / {ingredient.ingredient_name}"
                            )
                            raise e
                        ingredient_in_recipe.save()

                for tag_raw in recipe_dict["tags"]:
                    tag, _ = Tag.objects.get_or_create(tag=tag_raw.strip())
                    tag.save()
                    tag.recipe.set([recipe])

        self.stdout.write(self.style.SUCCESS("Successfully created plans"))
