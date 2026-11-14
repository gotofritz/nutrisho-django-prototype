"""Seed the curated cuisine tree and move existing cuisines onto it (plan 011).

The list was agreed with the owner as a starting point; staff edit it in Django
admin afterwards. It lives here rather than in a data file so that this
migration always does the same thing, whatever the file says later.

Existing cuisines were flat names typed into the editor (`Italian`, `Thai`).
Each one is matched, ignoring case, against an adjective in `ALIASES` or else a
node name that occurs exactly once in the tree; a match moves its recipes onto
the node and deletes the old row. `fusion` and `modern` are styles, not places:
their recipes get the global tag of that name and lose the cuisine. Anything
else is kept as a top-level node, so no recipe loses its cuisine, for staff to
re-parent or merge in admin.
"""

from django.db import migrations

# area -> region -> subregions
TREE: dict[str, dict[str, list[str]]] = {
    "eu": {
        "france": [
            "provence",
            "alsace",
            "brittany",
            "burgundy",
            "lyon",
            "normandy",
            "south west",
            "basque",
            "corsica",
        ],
        "germany": ["bavaria", "swabia"],
        "austria": [],
        "switzerland": [],
        "benelux": ["belgium", "netherlands", "luxembourg"],
        "nordic": ["denmark", "sweden", "norway", "finland", "iceland"],
        "slavic": ["poland", "czechia", "slovakia", "russia", "ukraine", "belarus"],
        "hungary": [],
        "romania": [],
        "baltic": ["estonia", "latvia", "lithuania"],
        "jewish": ["ashkenazi", "sephardi"],
    },
    "med": {
        "italy": [
            "sicily",
            "sardinia",
            "campania",
            "lazio",
            "tuscany",
            "liguria",
            "piedmont",
            "veneto",
            "emilia-romagna",
            "lombardy",
            "puglia",
            "calabria",
            "south tyrol",
        ],
        "spain": [
            "catalonia",
            "basque country",
            "andalusia",
            "galicia",
            "valencia",
            "castile",
            "canary islands",
        ],
        "portugal": [],
        "greece": ["crete", "cyprus"],
        "malta": [],
        "balkans": [
            "serbia",
            "croatia",
            "bosnia",
            "slovenia",
            "montenegro",
            "north macedonia",
            "albania",
            "bulgaria",
        ],
    },
    "middle east": {
        "levant": ["lebanon", "syria", "palestine", "jordan"],
        "israel": [],
        "turkey": [],
        "iran": [],
        "iraq": [],
        "kurdish": [],
        "gulf": ["saudi arabia", "emirates", "kuwait", "qatar", "bahrain", "oman"],
        "yemen": [],
        "egypt": [],
        "sudan": [],
        "morocco": [],
        "algeria": [],
        "tunisia": [],
        "libya": [],
        "caucasus": ["armenia", "georgia", "azerbaijan"],
    },
    "africa": {
        "west": ["nigeria", "ghana", "senegal", "ivory coast", "mali", "sierra leone"],
        "east": ["ethiopia", "eritrea", "kenya", "tanzania", "uganda", "somalia"],
        "central": ["congo", "cameroon"],
        "south": ["south africa", "mozambique", "zimbabwe", "madagascar", "mauritius"],
    },
    "asia": {
        "china": [
            "cantonese",
            "sichuan",
            "hunan",
            "shanghai",
            "jiangsu",
            "zhejiang",
            "fujian",
            "anhui",
            "shandong",
            "beijing",
            "yunnan",
            "xinjiang",
            "hakka",
            "teochew",
            "dongbei",
            "hong kong",
            "taiwan",
        ],
        "japan": ["okinawa", "kansai", "hokkaido"],
        "korea": [],
        "mongolia": [],
        "tibet": [],
        "central asia": ["uzbekistan", "kazakhstan", "kyrgyzstan", "tajikistan", "turkmenistan"],
        "thailand": ["isan", "north", "south"],
        "vietnam": ["north", "central", "south"],
        "cambodia": [],
        "laos": [],
        "myanmar": [],
        "malaysia": ["nyonya"],
        "singapore": [],
        "indonesia": ["java", "bali", "sumatra", "padang"],
        "philippines": [],
        "pacific islands": ["fiji", "samoa", "tonga"],
    },
    "south asia": {
        "india": [
            "punjab",
            "kashmir",
            "rajasthan",
            "gujarat",
            "maharashtra",
            "goa",
            "bengal",
            "odisha",
            "assam",
            "hyderabad",
            "chettinad",
            "kerala",
            "tamil nadu",
            "karnataka",
            "mughlai",
            "parsi",
            "awadh",
            "indo-chinese",
        ],
        "pakistan": [],
        "afghanistan": [],
        "nepal": [],
        "bangladesh": [],
        "sri lanka": [],
        "bhutan": [],
    },
    "anglo": {
        "uk": ["england", "scotland", "wales", "northern ireland"],
        "ireland": [],
        "us": [
            "south",
            "cajun",
            "creole",
            "soul food",
            "new england",
            "california",
            "hawaii",
            "tex-mex",
            "barbecue",
        ],
        "canada": [],
        "australia": [],
        "new zealand": ["maori"],
    },
    "latin": {
        "mexico": ["oaxaca", "yucatan", "puebla", "north"],
        "central america": [
            "guatemala",
            "el salvador",
            "honduras",
            "nicaragua",
            "costa rica",
            "panama",
        ],
        "caribbean": [
            "cuba",
            "puerto rico",
            "dominican republic",
            "haiti",
            "jamaica",
            "trinidad",
            "barbados",
        ],
        "brazil": ["bahia", "minas gerais"],
        "argentina": [],
        "uruguay": [],
        "chile": [],
        "peru": ["nikkei", "chifa"],
        "bolivia": [],
        "colombia": [],
        "venezuela": [],
        "ecuador": [],
    },
}

# How cuisines were typed before the tree (adjectives), lower case -> path.
ALIASES: dict[str, str] = {
    "european": "eu",
    "french": "eu.france",
    "german": "eu.germany",
    "austrian": "eu.austria",
    "swiss": "eu.switzerland",
    "belgian": "eu.benelux.belgium",
    "dutch": "eu.benelux.netherlands",
    "scandinavian": "eu.nordic",
    "nordic": "eu.nordic",
    "danish": "eu.nordic.denmark",
    "swedish": "eu.nordic.sweden",
    "norwegian": "eu.nordic.norway",
    "finnish": "eu.nordic.finland",
    "polish": "eu.slavic.poland",
    "czech": "eu.slavic.czechia",
    "russian": "eu.slavic.russia",
    "ukrainian": "eu.slavic.ukraine",
    "hungarian": "eu.hungary",
    "romanian": "eu.romania",
    "jewish": "eu.jewish",
    "mediterranean": "med",
    "italian": "med.italy",
    "sicilian": "med.italy.sicily",
    "sardinian": "med.italy.sardinia",
    "neapolitan": "med.italy.campania",
    "roman": "med.italy.lazio",
    "tuscan": "med.italy.tuscany",
    "spanish": "med.spain",
    "catalan": "med.spain.catalonia",
    "basque": "med.spain.basque country",
    "portuguese": "med.portugal",
    "greek": "med.greece",
    "cypriot": "med.greece.cyprus",
    "maltese": "med.malta",
    "balkan": "med.balkans",
    "middle eastern": "middle east",
    "levantine": "middle east.levant",
    "lebanese": "middle east.levant.lebanon",
    "syrian": "middle east.levant.syria",
    "palestinian": "middle east.levant.palestine",
    "israeli": "middle east.israel",
    "turkish": "middle east.turkey",
    "persian": "middle east.iran",
    "iranian": "middle east.iran",
    "iraqi": "middle east.iraq",
    "yemeni": "middle east.yemen",
    "egyptian": "middle east.egypt",
    "moroccan": "middle east.morocco",
    "algerian": "middle east.algeria",
    "tunisian": "middle east.tunisia",
    "north african": "middle east",
    "georgian": "middle east.caucasus.georgia",
    "armenian": "middle east.caucasus.armenia",
    "african": "africa",
    "west african": "africa.west",
    "east african": "africa.east",
    "nigerian": "africa.west.nigeria",
    "ghanaian": "africa.west.ghana",
    "senegalese": "africa.west.senegal",
    "ethiopian": "africa.east.ethiopia",
    "eritrean": "africa.east.eritrea",
    "kenyan": "africa.east.kenya",
    "south african": "africa.south.south africa",
    "asian": "asia",
    "chinese": "asia.china",
    "cantonese": "asia.china.cantonese",
    "sichuan": "asia.china.sichuan",
    "szechuan": "asia.china.sichuan",
    "taiwanese": "asia.china.taiwan",
    "japanese": "asia.japan",
    "korean": "asia.korea",
    "mongolian": "asia.mongolia",
    "tibetan": "asia.tibet",
    "thai": "asia.thailand",
    "vietnamese": "asia.vietnam",
    "cambodian": "asia.cambodia",
    "khmer": "asia.cambodia",
    "lao": "asia.laos",
    "laotian": "asia.laos",
    "burmese": "asia.myanmar",
    "malaysian": "asia.malaysia",
    "singaporean": "asia.singapore",
    "indonesian": "asia.indonesia",
    "filipino": "asia.philippines",
    "south asian": "south asia",
    "indian": "south asia.india",
    "punjabi": "south asia.india.punjab",
    "goan": "south asia.india.goa",
    "bengali": "south asia.india.bengal",
    "keralan": "south asia.india.kerala",
    "pakistani": "south asia.pakistan",
    "afghan": "south asia.afghanistan",
    "nepali": "south asia.nepal",
    "nepalese": "south asia.nepal",
    "bangladeshi": "south asia.bangladesh",
    "sri lankan": "south asia.sri lanka",
    "british": "anglo.uk",
    "english": "anglo.uk.england",
    "scottish": "anglo.uk.scotland",
    "welsh": "anglo.uk.wales",
    "irish": "anglo.ireland",
    "american": "anglo.us",
    "cajun": "anglo.us.cajun",
    "creole": "anglo.us.creole",
    "southern": "anglo.us.south",
    "canadian": "anglo.canada",
    "australian": "anglo.australia",
    "kiwi": "anglo.new zealand",
    "latin american": "latin",
    "mexican": "latin.mexico",
    "caribbean": "latin.caribbean",
    "cuban": "latin.caribbean.cuba",
    "jamaican": "latin.caribbean.jamaica",
    "brazilian": "latin.brazil",
    "argentinian": "latin.argentina",
    "argentine": "latin.argentina",
    "chilean": "latin.chile",
    "peruvian": "latin.peru",
    "colombian": "latin.colombia",
    "venezuelan": "latin.venezuela",
}

# Styles rather than places: these become global tags (plan 011).
STYLE_TAGS = ("fusion", "modern")


def _node(cuisine_model, *, name: str, parent):
    """The child of `parent` called `name` ignoring case, created on a miss."""
    found = cuisine_model.objects.filter(parent=parent, cuisine__iexact=name).first()
    return found or cuisine_model.objects.create(cuisine=name, parent=parent)


def seed_tree(cuisine_model) -> dict[str, object]:
    """Create every node of `TREE`; return them by path.

    An existing top-level row with an area's name is adopted as that area.
    """
    nodes: dict[str, object] = {}
    for area, regions in TREE.items():
        area_node = _node(cuisine_model, name=area, parent=None)
        nodes[area] = area_node
        for region, subregions in regions.items():
            region_node = _node(cuisine_model, name=region, parent=area_node)
            nodes[f"{area}.{region}"] = region_node
            for subregion in subregions:
                nodes[f"{area}.{region}.{subregion}"] = _node(
                    cuisine_model, name=subregion, parent=region_node
                )
    return nodes


def _target(name: str, nodes: dict[str, object]):
    """The tree node an old flat cuisine name stands for, or None."""
    lowered = name.strip().lower()
    if lowered in ALIASES:
        return nodes[ALIASES[lowered]]
    if lowered in nodes:
        return nodes[lowered]
    by_leaf = [node for path, node in nodes.items() if path.rsplit(".", 1)[-1] == lowered]
    return by_leaf[0] if len(by_leaf) == 1 else None


def map_legacy_cuisines(*, cuisine_model, recipe_model, tag_model, legacy_ids, nodes) -> None:
    """Move recipes off the old flat rows onto the tree; keep what doesn't match."""
    node_ids = {node.pk for node in nodes.values()}
    for legacy in cuisine_model.objects.filter(pk__in=legacy_ids).exclude(pk__in=node_ids):
        lowered = legacy.cuisine.strip().lower()
        recipes = recipe_model.objects.filter(cuisine=legacy)
        if lowered in STYLE_TAGS:
            tag = tag_model.objects.filter(tag__iexact=lowered, owner__isnull=True).first()
            tag.recipe.add(*recipes)
            recipes.update(cuisine=None)
            legacy.delete()
            continue
        target = _target(legacy.cuisine, nodes)
        if target is None:
            continue  # kept as a top-level node for staff to sort out
        recipes.update(cuisine=target)
        legacy.delete()


def seed(apps, schema_editor):
    """Seed the tree and the style tags, then fold the old flat cuisines in."""
    Cuisine = apps.get_model("recipes", "Cuisine")
    Recipe = apps.get_model("recipes", "Recipe")
    Tag = apps.get_model("recipes", "Tag")
    legacy_ids = list(Cuisine.objects.values_list("pk", flat=True))
    for name in STYLE_TAGS:
        if not Tag.objects.filter(tag__iexact=name, owner__isnull=True).exists():
            Tag.objects.create(tag=name, owner=None)
    nodes = seed_tree(Cuisine)
    map_legacy_cuisines(
        cuisine_model=Cuisine,
        recipe_model=Recipe,
        tag_model=Tag,
        legacy_ids=legacy_ids,
        nodes=nodes,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("recipes", "0020_cuisine_tree"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop, elidable=False),
    ]
