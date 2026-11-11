"""Tags, cuisine and source on the recipe page, and the columns dropped as unused (#65)."""

import pytest
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist

from recipes.models import Cuisine, Recipe, Step, Tag


@pytest.fixture
def recipe(user):
    """A bare recipe."""
    return Recipe.objects.create(recipe_name="Caponata", owner=user)


def _page(auth_client, recipe) -> str:
    return auth_client.get(f"/recipes/{recipe.pk}/").content.decode()


@pytest.mark.django_db
def test_tags_show_as_links_to_the_filtered_list(auth_client, user, recipe):
    """Each tag links to the recipe list filtered by it, A to Z."""
    quick = Tag.objects.create(tag="quick")
    summer = Tag.objects.create(tag="Summer", owner=user)
    recipe.tag.add(summer, quick)
    content = _page(auth_client, recipe)
    assert f'href="/recipes/?tag={quick.pk}"' in content
    assert f'href="/recipes/?tag={summer.pk}"' in content
    assert content.index(">quick</a>") < content.index(">Summer</a>")


@pytest.mark.django_db
def test_no_tag_list_without_tags(auth_client, recipe):
    """Nothing to show, no empty list."""
    assert "recipe-tags" not in _page(auth_client, recipe)


@pytest.mark.django_db
def test_cuisine_links_to_the_filtered_list(auth_client, recipe):
    """The cuisine path links to the list filtered by that node."""
    med = Cuisine.objects.create(cuisine="testland")
    italy = Cuisine.objects.create(cuisine="north", parent=med)
    recipe.cuisine = italy
    recipe.save()
    content = _page(auth_client, recipe)
    assert f'href="/recipes/?cuisine={italy.pk}"' in content
    assert ">testland.north</a>" in content


@pytest.mark.django_db
def test_a_web_source_is_a_link(auth_client, recipe):
    """A URL opens the page it names, without passing on the opener."""
    recipe.source_instance = "https://example.com/caponata"
    recipe.save()
    content = _page(auth_client, recipe)
    assert '<a href="https://example.com/caponata" rel="noopener noreferrer"' in content


@pytest.mark.django_db
def test_a_book_source_is_plain_text(auth_client, recipe):
    """`Moro, p. 112` is shown as typed, not linked."""
    recipe.source_instance = "Moro, p. 112"
    recipe.save()
    content = _page(auth_client, recipe)
    assert "Moro, p. 112" in content
    assert 'href="Moro' not in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "source",
    ["javascript:alert(1)", "ftp://example.com/x", "example.com/caponata", "http://"],
)
def test_only_http_urls_become_links(auth_client, recipe, source):
    """Anything but a whole http(s) URL is text: no script or other scheme in an href."""
    recipe.source_instance = source
    recipe.save()
    content = _page(auth_client, recipe)
    assert "recipe-source" in content
    assert 'rel="noopener noreferrer"' not in content


@pytest.mark.django_db
def test_no_source_line_without_a_source(auth_client, recipe):
    """Blank source, nothing shown."""
    assert "recipe-source" not in _page(auth_client, recipe)


@pytest.mark.django_db
def test_metadata_form_labels_the_source(auth_client, recipe):
    """The form field reads "Source", with a hint at what goes in it."""
    content = auth_client.get(f"/recipes/{recipe.pk}/metadata/").content.decode()
    assert ">Source:</label>" in content


@pytest.mark.django_db
def test_detail_page_with_every_detail_keeps_a_constant_query_count(
    auth_client, user, recipe, django_assert_max_num_queries
):
    """Tags and the cuisine's ancestors come with the page, not one query each."""
    area = Cuisine.objects.create(cuisine="testland")
    region = Cuisine.objects.create(cuisine="north", parent=area)
    recipe.cuisine = Cuisine.objects.create(cuisine="sicily", parent=region)
    recipe.source_instance = "https://example.com"
    recipe.save()
    for i in range(5):
        recipe.tag.add(Tag.objects.create(tag=f"t{i}"))
    with django_assert_max_num_queries(10):
        response = auth_client.get(f"/recipes/{recipe.pk}/")
    assert response.status_code == 200


def test_the_source_model_is_gone():
    """`Source` was never written by any code path; `source_instance` is the source."""
    with pytest.raises(LookupError):
        apps.get_model("recipes", "Source")
    with pytest.raises(FieldDoesNotExist):
        Recipe._meta.get_field("source")  # ty: ignore[unresolved-attribute]  # no Django stubs


@pytest.mark.parametrize("name", ["duration", "extra_info"])
def test_unused_step_columns_are_gone(name):
    """Never written, and #19's reusable steps need neither."""
    with pytest.raises(FieldDoesNotExist):
        Step._meta.get_field(name)  # ty: ignore[unresolved-attribute]  # no Django stubs
