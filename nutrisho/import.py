import re
from os.path import basename
from pathlib import Path

import xmltodict
import yaml

SRC_DIR = Path("/Library/WebServer/Documents/recipes")
TARGET_DIR = Path("../recipes_yaml")

p = Path(SRC_DIR)
for path_xml_recipe in p.glob("*.xml"):
    xml_recipe = open(path_xml_recipe, encoding="utf8").read()
    xml_recipe = re.sub(r" xmlns:[a-z]+=\".+?\"", "", xml_recipe)
    xml_recipe = re.sub(r" lang=\"en-uk\"", "", xml_recipe)
    # print(xml_recipe)
    recipe_as_dict = xmltodict.parse(xml_recipe, dict_constructor=dict)
    if "img" in recipe_as_dict["recipe"]:
        del recipe_as_dict["recipe"]["img"]
    path_yaml_recipe = TARGET_DIR / basename(path_xml_recipe.with_suffix(".yml"))
    selection = None
    while selection not in {"k", "d"}:
        selection = input("Keep (k) or delete (d)?")
    if selection == "k":
        recipe_as_yaml = {
            "title": recipe_as_dict["recipe"]["title"],
            "source": recipe_as_dict["recipe"]["source"],
            "directions": recipe_as_dict["recipe"]["directions"],
            "ingredients": recipe_as_dict["recipe"]["ingredients"],
            "description": recipe_as_dict["recipe"]["description"],
        }
        if "cuisine" in recipe_as_dict["recipe"]:
            cuisine_parts = [
                part.lower()
                for part in recipe_as_dict["recipe"]["cuisine"].values()
                if part is not None
            ]
            recipe_as_yaml["cuisine"] = "." + ".".join(cuisine_parts) if cuisine_parts else None

        if "tags" in recipe_as_dict["recipe"]:
            tags = recipe_as_dict["recipe"]["tags"]
            if tags is None or recipe_as_dict["recipe"]["tags"]["tag"] is None:
                recipe_as_yaml["tags"] = []
            elif isinstance(recipe_as_dict["recipe"]["tags"]["tag"], str):
                recipe_as_yaml["tags"] = [recipe_as_dict["recipe"]["tags"]["tag"].lower()]
            else:
                recipe_as_yaml["tags"] = [
                    tag.lower()
                    for tag in recipe_as_dict["recipe"]["tags"]["tag"]
                    if tag is not None
                ]

        # print(json.dumps(recipe_as_yaml, indent=4))
        with open(path_yaml_recipe, "w") as file:
            yaml.dump(recipe_as_yaml, file)
        # input("..")
    path_xml_recipe.unlink(missing_ok=False)
