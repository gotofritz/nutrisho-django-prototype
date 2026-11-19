"""Tests for the recipes URLconf (#77)."""

import uuid

import pytest
from django.urls import resolve, reverse


@pytest.mark.parametrize("kind", ["step", "ingredient", "group"])
def test_each_move_pair_shares_one_view(kind: str) -> None:
    """Up and down keep their own URL names but resolve to one view and a direction."""
    recipe_id = uuid.uuid7()
    up = resolve(reverse(f"recipes:{kind}_move_up", args=[recipe_id, 2]))
    down = resolve(reverse(f"recipes:{kind}_move_down", args=[recipe_id, 2]))
    assert up.func is down.func
    assert up.kwargs["direction"] == "up"
    assert down.kwargs["direction"] == "down"
