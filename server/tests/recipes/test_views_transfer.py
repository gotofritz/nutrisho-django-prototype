"""Tests for the export download and the import page (#78)."""

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from recipes.forms import import_form
from recipes.models import Recipe


@pytest.fixture
def client(user) -> Client:
    """The owner, signed in."""
    c = Client()
    c.force_login(user)
    return c


def _upload(content: object, *, name: str = "recipes.json") -> SimpleUploadedFile:
    raw = content if isinstance(content, bytes) else json.dumps(content).encode()
    return SimpleUploadedFile(name, raw, content_type="application/json")


def _post(client: Client, upload: SimpleUploadedFile | None):
    data = {"file": upload} if upload is not None else {}
    return client.post(reverse("recipes:import"), data)


@pytest.mark.django_db
def test_export_downloads_the_users_recipes(client, rich_recipe):
    """A JSON attachment holding the user's recipes, markup and all."""
    response = client.get(reverse("recipes:export"))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert response["Content-Disposition"].startswith('attachment; filename="nutrisho-recipes-')
    document = json.loads(response.content)
    assert document["format"] == "nutrisho"
    assert [r["recipe_name"] for r in document["recipes"]] == [
        "<u>Pasta</u> alla Norma",
        "Old soup",
    ]


@pytest.mark.django_db
def test_export_is_get_only(client):
    """Export changes nothing, so it answers GET alone."""
    assert client.post(reverse("recipes:export")).status_code == 405


@pytest.mark.django_db
def test_import_page_offers_both(client):
    """The page links the download and has a multipart upload form."""
    response = client.get(reverse("recipes:import"))
    assert response.status_code == 200
    html = response.content.decode()
    # The body is boosted: htmx would fetch the download and swap it into the page.
    assert f'href="{reverse("recipes:export")}" download hx-boost="false"' in html
    assert 'enctype="multipart/form-data"' in html
    assert 'type="file"' in html


@pytest.mark.django_db
def test_config_links_the_page(client):
    """The Config page leads to import and export."""
    html = client.get(reverse("recipes:config")).content.decode()
    assert f'href="{reverse("recipes:import")}"' in html


@pytest.mark.django_db
def test_import_a_nutrisho_export(client, user, other_user, rich_recipe):
    """Another user's export comes in whole, live recipes linked and trashed ones marked."""
    other = Client()
    other.force_login(other_user)
    document = json.loads(client.get(reverse("recipes:export")).content)

    response = _post(other, _upload(document))

    assert response.status_code == 200
    imported = Recipe.objects.get(owner=other_user, plain_name="Pasta alla Norma")
    html = response.content.decode()
    assert "Imported 2 recipes" in html
    assert f'href="{imported.get_absolute_url()}"' in html
    assert 'Old soup <span class="import-note">(in the trash)</span>' in html
    assert Recipe.objects.trashed().filter(owner=other_user, recipe_name="Old soup").exists()


@pytest.mark.django_db
def test_import_says_what_it_renamed_and_left_out(client, user):
    """A name already taken and a cuisine the server lacks are both reported."""
    Recipe.objects.create(recipe_name="Soup", owner=user, servings=1)
    document = {
        "format": "nutrisho",
        "version": 1,
        "recipes": [{"recipe_name": "Soup", "cuisine": "atlantis"}],
    }
    html = _post(client, _upload(document)).content.decode()
    assert "Imported 1 recipe<" in html
    assert "Soup Imported" in html
    assert "renamed, since you already had “Soup”" in html
    assert "there is no cuisine “atlantis” here" in html


@pytest.mark.django_db
def test_import_json_ld(client, user):
    """A recipe page's JSON-LD is imported too."""
    page = [{"@context": "https://schema.org", "@type": "Recipe", "name": "Toast"}]
    _post(client, _upload(page, name="toast.jsonld"))
    assert Recipe.objects.filter(owner=user, recipe_name="Toast").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("upload", "message"),
    [
        (b"{not json", "This is not JSON: Expecting property name enclosed in double quotes"),
        (b"\xff\xfe", "This is not UTF-8 text."),
        (json.dumps({"@type": "WebPage"}).encode(), "No recipe found"),
        (json.dumps({"format": "nutrisho", "version": 9}).encode(), "Unsupported version 9"),
    ],
    ids=["not-json", "not-utf8", "no-recipe", "bad-version"],
)
def test_import_refuses_a_bad_file(client, upload: bytes, message: str):
    """The form says what is wrong, and nothing is written."""
    response = _post(client, _upload(upload))
    assert response.status_code == 200
    assert message in response.content.decode()
    assert not Recipe.objects.exists()


@pytest.mark.django_db
def test_import_refuses_a_large_file(client, monkeypatch):
    """An upload over the limit is not read."""
    monkeypatch.setattr(import_form, "MAX_IMPORT_BYTES", 10)
    response = _post(client, _upload({"format": "nutrisho", "version": 1, "recipes": []}))
    assert "The file is over 0 MB." in response.content.decode()


@pytest.mark.django_db
def test_import_needs_a_file(client):
    """Posting without a file asks for one."""
    response = _post(client, None)
    assert "This field is required." in response.content.decode()


@pytest.mark.django_db
def test_import_refuses_deeply_nested_json(client):
    """Deep nesting is refused, never a server error.

    Whether the decoder itself gives up depends on the platform's stack: where
    it does, the form says so; where it does not, there is no recipe in it.
    """
    response = _post(client, _upload(b"[" * 100_000 + b"]" * 100_000))
    html = response.content.decode()
    assert response.status_code == 200
    assert "This JSON is nested too deeply." in html or "No recipe found" in html
    assert not Recipe.objects.exists()
