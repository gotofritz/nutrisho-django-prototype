"""Fill a development database with sample recipes that exercise the awkward cases (#71).

A fresh database is empty, so trying the ingredient clean-up tool or reviewing a
UI change meant building recipes by hand. This seeds four recipes for one user,
covering what the app has to cope with:

- **duplicates** for the clean-up tool: `onion`/`onions` (plural by rule),
  `chilli`/`chillies` (plural by override), a private `Onion` beside the global
  `onion` (case), `aubergine`/`eggplant` (spelling variant), private rows to
  promote, and an unused global row (`saffron`);
- **plurals** on display: `2 aubergines`, `200 g onion`, invariant `broccoli`;
- **groups**: one unnamed group, and named ones (`For the soup`, `To serve`);
- **substitutes**, **step titles** (and untitled steps), inline tags in titles,
  blurbs and steps, global and private tags, and cuisines at every depth.

Never runs under the production settings. Re-running adds only the recipes that
are missing; `--reset` deletes the demo recipes first, which also brings back
any duplicate the clean-up tool has merged away since.
"""

import secrets
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recipes.models import Ingredient, IngredientGroup, IngredientInRecipe, Recipe, Step, Tag
from recipes.services.name_resolution import find_cuisine, find_unit, resolve_tag
from recipes.utils.plain_text import plain_text

PRODUCTION_SETTINGS = "nutrisho.settings.prod"
DEFAULT_USERNAME = "demo"

# Created in the user's private list rather than the global one.
PRIVATE_INGREDIENTS = frozenset({"Onion", "smoked paprika"})
# Plural overrides set when the global row is created; existing rows are left alone.
PLURAL_OVERRIDES = {"chilli": "chillies", "broccoli": "broccoli"}
# Global rows no recipe uses: what the clean-up tool's "Unused only" filter finds.
UNUSED_INGREDIENTS = ("saffron",)
GLOBAL_TAGS = frozenset({"vegetarian"})


@dataclass(frozen=True)
class Item:
    """One ingredient line: name, then what the recipe editor shows beside it."""

    name: str
    quantity: str | None = None
    unit: str = ""
    preparation: str = ""
    substitute: str | None = None


@dataclass(frozen=True)
class DemoRecipe:
    """A recipe to seed: groups map a group name to its lines, steps are (title, text)."""

    name: str
    description: str
    servings: int
    cuisine: str
    groups: dict[str, list[Item]]
    steps: list[tuple[str, str]]
    tags: list[str] = field(default_factory=list)


RECIPES = (
    DemoRecipe(
        name="Pasta alla Norma",
        description="Fried <i>aubergine</i>, tomato and salted ricotta.\nSicily's favourite pasta.",
        servings=4,
        cuisine="med.italy.sicily",
        tags=["vegetarian", "weeknight"],
        groups={
            "": [
                Item("aubergine", "2", preparation="cut into cubes"),
                Item("spaghetti", "400", "g"),
                Item("olive oil", "4", "tbsp"),
                Item("garlic", "2", "cloves", "sliced"),
                Item("tomato", "800", "g", "tinned, chopped"),
                Item("ricotta salata", "80", "g", "grated", substitute="pecorino"),
                Item("basil", "1", "handful"),
            ]
        },
        steps=[
            ("AUBERGINES", "Fry the aubergine in the oil until <b>golden</b> on every side."),
            ("SAUCE", "Soften the garlic in the same pan, add the tomatoes and simmer for 15 min."),
            ("", "Toss the spaghetti with the sauce, then top with the aubergine and cheese."),
        ],
    ),
    DemoRecipe(
        name="<u>Shakshuka</u>",
        description="Eggs poached in a spiced pepper and tomato sauce.",
        servings=2,
        cuisine="middle east",
        tags=["vegetarian"],
        groups={
            "": [
                Item("onions", "1", preparation="sliced"),
                Item("red pepper", "2", preparation="sliced"),
                Item("chillies", "1", preparation="chopped"),
                Item("onion", "200", "g", "chopped"),
                Item("tomato", "400", "g"),
                Item("smoked paprika", "1", "tsp"),
                Item("cumin", "1", "tsp"),
                Item("egg", "4"),
                Item("parsley", preparation="chopped, to serve"),
            ]
        },
        steps=[
            ("", "Soften the onion, pepper and chilli in a wide pan for 10 minutes."),
            ("", "Stir in the spices, then the tomatoes, and simmer until <i>thick</i>."),
            ("", "Make four hollows, crack in the eggs, cover and cook until just set."),
        ],
    ),
    DemoRecipe(
        name="Minestrone",
        description="A thick vegetable soup. <b>Better the next day.</b>",
        servings=6,
        cuisine="med.italy",
        tags=["batch cooking"],
        groups={
            "For the soup": [
                Item("Onion", "1", preparation="diced"),
                Item("carrot", "2", preparation="diced"),
                Item("celery", "2", "sticks", "diced"),
                Item("courgette", "1", preparation="diced"),
                Item("broccoli", "2", preparation="in florets"),
                Item("chilli", "1"),
                Item("cannellini beans", "400", "g", substitute="borlotti beans"),
                Item("ditalini", "100", "g"),
                Item("vegetable stock", "1.5", "l"),
            ],
            "To serve": [
                Item("parmesan", "40", "g", "grated", substitute="pecorino"),
                Item("olive oil"),
            ],
        },
        steps=[
            ("FOR THE SOFFRITTO", "Sweat the onion, carrot and celery in oil for 10 minutes."),
            ("FOR THE SOUP", "Add the rest but the pasta, cover with stock, simmer for 30 min."),
            ("", "Cook the pasta in the soup, then serve with parmesan and a thread of oil."),
        ],
    ),
    DemoRecipe(
        name="Baba ganoush",
        description="Smoky <b>eggplant</b> dip.",
        servings=6,
        cuisine="middle east.levant.lebanon",
        tags=["vegetarian", "weeknight"],
        groups={
            "Dip": [
                Item("eggplant", "2"),
                Item("tahini", "3", "tbsp"),
                Item("lemon", "1", preparation="juiced"),
                Item("garlic", "1", "clove", "crushed"),
                Item("salt", "1", "pinch"),
            ],
            "Topping": [
                Item("pomegranate seeds", "2", "tbsp"),
                Item("parsley", "1", "handful"),
                Item("olive oil", "1", "tbsp"),
                Item("smoked paprika", "1", "pinch"),
            ],
        },
        steps=[
            ("CHAR", "Blacken the eggplants over a flame until they collapse."),
            ("", "Scoop out the flesh and beat it with the tahini, lemon, garlic and salt."),
            ("", "Spread on a plate and finish with the topping."),
        ],
    ),
)


class Command(BaseCommand):
    help = (
        "Seed sample recipes for a development user (default 'demo', created as staff "
        "if missing). Refuses to run under the production settings."
    )

    def add_arguments(self, parser):
        """Register command-line arguments."""
        parser.add_argument(
            "--username",
            default=DEFAULT_USERNAME,
            help=f"Who owns the recipes (default {DEFAULT_USERNAME!r}). An existing "
            "account is used as it is; a missing one is created as staff.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete this user's demo recipes and seed them again.",
        )

    def handle(self, *args, **options):
        """Create the user if needed, then whichever demo recipes they lack."""
        if settings.SETTINGS_MODULE == PRODUCTION_SETTINGS:
            msg = (
                "seed_demo writes sample data: refusing the production settings "
                f"({PRODUCTION_SETTINGS})"
            )
            raise CommandError(msg)

        with transaction.atomic():
            user = self._user(username=options["username"])
            if options["reset"]:
                names = [plain_text(r.name) for r in RECIPES]
                Recipe.objects.filter(owner=user, plain_name__in=names).delete()
            created = [recipe.name for recipe in RECIPES if self._seed(recipe=recipe, owner=user)]
            if created:
                for name in UNUSED_INGREDIENTS:
                    _global_ingredient(name)

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Seeded {len(created)} recipe(s) for {user.username!r}")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"The demo recipes already exist for {user.username!r}; nothing to do "
                    "(--reset rebuilds them)"
                )
            )

    def _user(self, *, username: str) -> User:
        """The existing account, or a new staff one with a random password, printed once."""
        user = User.objects.filter(username=username).first()
        if user is None:
            password = secrets.token_urlsafe(12)
            user = User.objects.create_user(username=username, password=password, is_staff=True)
            self.stdout.write(f"Created staff user {username!r} with password {password}")
        elif not user.is_staff:
            self.stdout.write(
                self.style.WARNING(
                    f"{username!r} is not staff, so the ingredient and cuisine tools are closed "
                    "to them"
                )
            )
        return user

    def _seed(self, *, recipe: DemoRecipe, owner: User) -> bool:
        """Create `recipe` for `owner` unless they have one of that name; True if created."""
        if Recipe.objects.filter(owner=owner, plain_name=plain_text(recipe.name)).exists():
            return False
        row = Recipe(
            owner=owner,
            recipe_name=recipe.name,
            short_description=recipe.description,
            servings=recipe.servings,
            cuisine=find_cuisine(recipe.cuisine),
        )
        row.save()
        for group_index, (group_name, items) in enumerate(recipe.groups.items()):
            group = IngredientGroup.objects.create(
                recipe=row, group_name=group_name, index_in_sequence=group_index
            )
            for item_index, item in enumerate(items):
                IngredientInRecipe.objects.create(
                    ingredient_group=group,
                    index_in_sequence=item_index,
                    ingredient=_ingredient(name=item.name, owner=owner),
                    substitute=_ingredient(name=item.substitute, owner=owner)
                    if item.substitute
                    else None,
                    quantity=Decimal(item.quantity) if item.quantity else None,
                    unit=find_unit(item.unit),
                    preparation=item.preparation,
                )
        for step_index, (title, text) in enumerate(recipe.steps):
            Step.objects.create(
                recipe=row, index_in_sequence=step_index, step_title=title, step_text=text
            )
        tags = [
            _global_tag(name) if name in GLOBAL_TAGS else resolve_tag(name, owner=owner)
            for name in recipe.tags
        ]
        row.tags.add(*tags)  # ty: ignore[unresolved-attribute]  # reverse M2M
        return True


def _ingredient(*, name: str, owner: User) -> Ingredient:
    """The global row of that name, or the owner's private one for `PRIVATE_INGREDIENTS`."""
    if name not in PRIVATE_INGREDIENTS:
        return _global_ingredient(name)
    found = Ingredient.objects.filter(owner=owner, ingredient_name__iexact=name).first()
    return found or Ingredient.objects.create(ingredient_name=name, owner=owner)


def _global_ingredient(name: str) -> Ingredient:
    """The global row of that name, ignoring case, created with its plural override if new."""
    found = Ingredient.objects.filter(owner__isnull=True, ingredient_name__iexact=name).first()
    return found or Ingredient.objects.create(
        ingredient_name=name, plural_name=PLURAL_OVERRIDES.get(name, "")
    )


def _global_tag(name: str) -> Tag:
    """The global tag of that name, ignoring case, created if missing."""
    found = Tag.objects.filter(owner__isnull=True, tag__iexact=name).first()
    return found or Tag.objects.create(tag=name)
