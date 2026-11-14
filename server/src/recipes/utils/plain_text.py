"""The tag-free text of an inline-HTML field (#32).

`Recipe.recipe_name` and `.short_description` are stored as typed, inline tags
and all (#17), and sanitized only on render. Search and the per-owner name
check want the words a reader sees, so `<u>Foo</u>` reads as `Foo`. Kept free
of Django imports, like the other utils, so migrations can use it too.
"""

from html import unescape
from html.parser import HTMLParser


class _TextCollector(HTMLParser):
    """Keep the text between tags; a `<br>` is a word break."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:  # noqa: ARG002 - HTMLParser API
        if tag == "br":
            self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: str) -> str:
    """`value` without tags, entities decoded, white space collapsed to single spaces."""
    collector = _TextCollector()
    collector.feed(value)
    # `feed()` holds back what it cannot parse (`oven<gas 4`): that is text too,
    # as in the render-time sanitizer (#50).
    if collector.rawdata:
        collector.parts.append(unescape(collector.rawdata))
        collector.rawdata = ""
    collector.close()
    return " ".join("".join(collector.parts).split())
