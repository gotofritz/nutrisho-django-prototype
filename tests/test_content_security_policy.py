"""Tests for the Content-Security-Policy and the template rules it relies on (#62).

The policy allows scripts and styles from the app's own origin only, so no
template may carry inline JavaScript or CSS: no ``<script>`` body, no ``on*=``
handler, no ``hx-on`` or ``hx-trigger`` filter (htmx evals those) and no
``style=`` attribute. The browser-side code lives in ``static/js/app.js``.
"""

import json
import re
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "recipes" / "templates"
# The inline SVG icons are templates too: a style= in them is blocked like any other.
TEMPLATE_FILES = sorted(p for p in TEMPLATES.rglob("*") if p.suffix in {".html", ".svg"})


def _policy(response) -> dict[str, list[str]]:
    """The enforced policy as ``{directive: [values]}``."""
    header = response.headers.get("Content-Security-Policy")
    assert header, "no Content-Security-Policy header"
    directives = (part.split() for part in header.split(";") if part.strip())
    return {name: values for name, *values in directives}


@pytest.fixture
def staff_client(db) -> Client:
    """A client signed in as a superuser, for the Django admin."""
    client = Client()
    client.force_login(User.objects.create_superuser(username="boss", password="x"))
    return client


# --- the header --------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("anonymous", [True, False], ids=["login-page", "recipe-list"])
def test_pages_enforce_a_same_origin_policy(auth_client, anonymous):
    """Scripts, styles and everything else come from the app itself."""
    response = (
        Client().get(reverse("login")) if anonymous else auth_client.get(reverse("recipes:home"))
    )
    assert response.status_code == 200
    policy = _policy(response)
    assert policy["default-src"] == ["'self'"]
    assert policy["script-src"] == ["'self'"]
    assert policy["style-src"] == ["'self'"]
    assert policy["object-src"] == ["'none'"]
    assert policy["base-uri"] == ["'none'"]
    assert policy["form-action"] == ["'self'"]
    assert policy["frame-ancestors"] == ["'none'"]


@pytest.mark.django_db
def test_policy_allows_no_inline_code_or_eval(auth_client):
    """The point of the policy: injected markup cannot run script or style."""
    header = auth_client.get(reverse("recipes:home")).headers["Content-Security-Policy"]
    assert "unsafe-inline" not in header
    assert "unsafe-eval" not in header
    assert "unsafe-hashes" not in header


@pytest.mark.django_db
def test_policy_is_enforced_not_report_only(auth_client):
    """A violation is blocked, not just logged."""
    response = auth_client.get(reverse("recipes:home"))
    assert "Content-Security-Policy-Report-Only" not in response.headers


@pytest.mark.django_db
def test_admin_inline_code_runs_under_a_nonce(staff_client):
    """Django's admin tags its few inline blocks with the request's nonce."""
    response = staff_client.get(reverse("admin:recipes_ingredient_changelist"))
    assert response.status_code == 200
    nonce = re.search(r"'nonce-([^']+)'", " ".join(_policy(response)["script-src"]))
    assert nonce, "admin page sent no script nonce"
    assert f'nonce="{nonce.group(1)}"' in response.content.decode()
    assert f"'nonce-{nonce.group(1)}'" in _policy(response)["style-src"]


# --- htmx --------------------------------------------------------------------


@pytest.mark.django_db
def test_htmx_does_not_eval_or_inject_styles(auth_client):
    """Eval (hx-on, trigger filters) and the injected indicator <style> are both off."""
    html = auth_client.get(reverse("recipes:home")).content.decode()
    meta = re.search(r'name="htmx-config" content=\'([^\']*)\'', html)
    assert meta
    config = json.loads(meta.group(1))
    assert config["allowEval"] is False
    assert config["includeIndicatorStyles"] is False


@pytest.mark.django_db
def test_htmx_does_not_settle_style_attributes(auth_client):
    """The settle step of htmx never writes a `style` attribute, which the CSP blocks (#63).

    A swapped-in element whose id is already on the page briefly takes the old
    element's settled attributes; `app.js` sizes textareas through their
    `style`, so re-rendering an open form would copy it as an inline style.
    """
    html = auth_client.get(reverse("recipes:home")).content.decode()
    meta = re.search(r'name="htmx-config" content=\'([^\']*)\'', html)
    assert meta
    assert "style" not in json.loads(meta.group(1))["attributesToSettle"]


# --- the app script ----------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("anonymous", [True, False], ids=["login-page", "recipe-list"])
def test_pages_load_the_app_script(auth_client, anonymous):
    """Every page loads the one static script, deferred, after htmx."""
    response = (
        Client().get(reverse("login")) if anonymous else auth_client.get(reverse("recipes:home"))
    )
    html = response.content.decode()
    srcs = re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', html)
    assert "/static/js/app.js" in srcs
    htmx = next(i for i, src in enumerate(srcs) if "django_htmx/htmx" in src)
    assert srcs.index("/static/js/app.js") > htmx, "app.js uses htmx, so it must load after it"
    tag = re.search(r'<script\b[^>]*src="/static/js/app.js"[^>]*>', html)
    assert tag
    assert " defer" in tag.group(0)


def test_app_script_ships_as_a_static_file():
    """``base.html`` asks for a file that is on the static path."""
    assert finders.find("js/app.js") is not None


# --- the template rules ------------------------------------------------------


def _rel(path: Path) -> str:
    return str(path.relative_to(TEMPLATES))


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=_rel)
def test_template_has_no_inline_script(path):
    """Every ``<script>`` loads a file; a script body would be blocked."""
    for tag in re.findall(r"<script\b[^>]*>", path.read_text()):
        assert "src=" in tag, f"inline <script> in {_rel(path)}"


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=_rel)
def test_template_has_no_inline_event_handler(path):
    """``onclick=`` and friends are inline script; use a delegated listener."""
    handlers = re.findall(r"\son[a-z]+\s*=", path.read_text())
    assert handlers == [], f"inline handler in {_rel(path)}"


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=_rel)
def test_template_has_no_htmx_eval(path):
    """``hx-on`` and ``hx-trigger="event[filter]"`` need eval, which is off."""
    html = path.read_text()
    assert "hx-on" not in html, f"hx-on in {_rel(path)}"
    for trigger in re.findall(r'hx-trigger="([^"]*)"', html):
        assert "[" not in trigger, f"hx-trigger filter in {_rel(path)}: {trigger}"
    assert not re.search(r"hx-vals=['\"]\s*(js|javascript):", html), f"js: hx-vals in {_rel(path)}"


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=_rel)
def test_template_has_no_inline_style(path):
    """``style=`` and ``<style>`` are inline CSS; use a class."""
    html = path.read_text()
    assert not re.search(r"\sstyle\s*=", html), f"style= attribute in {_rel(path)}"
    assert "<style" not in html, f"<style> in {_rel(path)}"
