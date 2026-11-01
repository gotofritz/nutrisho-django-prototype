"""Tests for the self-hosted web fonts (#52).

Inconsolata and Lobster used to come from ``fonts.googleapis.com``, which sent
every visitor's IP to Google, blocked rendering and stood in the way of a strict
CSP. These tests pin that the fonts ship from ``static/`` instead, swap in
rather than block, and that the files the page asks for exist.
"""

import posixpath
import re
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders

STYLE_CSS = "css/style.css"


@pytest.fixture
def home_html(auth_client) -> str:
    """Rendered recipe list, which extends ``base.html``."""
    response = auth_client.get("/recipes/")
    assert response.status_code == 200
    return response.content.decode()


@pytest.fixture
def style_css() -> str:
    """The app stylesheet that declares the ``@font-face`` rules."""
    path = finders.find(STYLE_CSS)
    assert path is not None, f"{STYLE_CSS} is not on the static path"
    return Path(path).read_text()


def _font_faces(css: str) -> list[str]:
    return re.findall(r"@font-face\s*\{[^}]*\}", css)


def _font_preloads(html: str) -> list[str]:
    return [
        tag
        for tag in re.findall(r"<link\b[^>]*>", html)
        if 'rel="preload"' in tag and 'as="font"' in tag
    ]


@pytest.mark.django_db
def test_page_loads_nothing_from_google_fonts(home_html):
    """No visitor request goes to Google's font CDN."""
    assert "fonts.googleapis.com" not in home_html
    assert "fonts.gstatic.com" not in home_html


@pytest.mark.django_db
def test_page_links_no_third_party_stylesheet_or_script(home_html):
    """Every stylesheet and script is served by the app itself."""
    external = re.findall(r'(?:href|src)="(https?://[^"]+)"', home_html)
    assert external == []


@pytest.mark.parametrize("family", ["Inconsolata", "Lobster"])
def test_style_declares_font_face_for_family(style_css, family):
    """Each family the stylesheet uses has a self-hosted ``@font-face``."""
    families = re.findall(r'font-family:\s*"([^"]+)"', "".join(_font_faces(style_css)))
    assert family in families


def test_every_font_face_swaps_instead_of_blocking(style_css):
    """Text renders in the fallback font until the web font arrives."""
    faces = _font_faces(style_css)
    assert faces
    for face in faces:
        assert "font-display: swap" in face, face


def test_every_font_face_url_is_a_woff2_on_the_static_path(style_css):
    """Each ``@font-face`` points at a woff2 file that actually ships."""
    css_dir = posixpath.dirname(STYLE_CSS)
    faces = _font_faces(style_css)
    assert faces
    for face in faces:
        urls = re.findall(r'url\("([^"]+)"\)', face)
        assert urls, face
        for url in urls:
            assert url.endswith(".woff2"), url
            target = posixpath.normpath(posixpath.join(css_dir, url))
            assert finders.find(target) is not None, f"{target} is not on the static path"


@pytest.mark.django_db
def test_page_preloads_the_latin_font_files(home_html):
    """The fonts start downloading with the HTML, not after the CSS is parsed."""
    preloads = _font_preloads(home_html)
    hrefs = sorted(re.findall(r'href="/static/([^"]+)"', "".join(preloads)))
    assert hrefs == [
        "fonts/inconsolata/inconsolata-latin-400.woff2",
        "fonts/lobster/lobster-latin-400.woff2",
    ]
    for href in hrefs:
        assert finders.find(href) is not None, f"{href} is not on the static path"


@pytest.mark.django_db
def test_font_preloads_are_cors_woff2(home_html):
    """A font preload without ``crossorigin`` is fetched twice by the browser."""
    preloads = _font_preloads(home_html)
    assert preloads
    for tag in preloads:
        assert 'type="font/woff2"' in tag, tag
        assert re.search(r"\scrossorigin\b", tag), tag


@pytest.mark.django_db
def test_preloads_come_before_the_stylesheets(home_html):
    """The preloads sit ahead of the CSS so they are discovered first."""
    head = home_html.split("</head>", 1)[0]
    first_preload = head.index('as="font"')
    first_stylesheet = head.index('rel="stylesheet"')
    assert first_preload < first_stylesheet


@pytest.mark.parametrize("family", ["inconsolata", "lobster"])
def test_font_licence_ships_with_the_files(family):
    """The SIL OFL requires the licence to travel with the font files."""
    path = finders.find(f"fonts/{family}/OFL.txt")
    assert path is not None
    assert "SIL Open Font License" in Path(path).read_text()
