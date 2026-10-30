"""Concurrent writes against a file-backed SQLite database (issue #38).

With Django's default DEFERRED transactions, two overlapping write requests
both take a read lock and the second one to upgrade to a write lock fails with
`database is locked` straight away, ignoring the busy timeout. IMMEDIATE
transactions take the write lock up front, so overlapping requests queue.
"""

import random
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection, connections
from django.test import Client

from recipes.models import Recipe, Step

THREADS = 8
MOVES_PER_THREAD = 15


def _move_steps(*, user, recipe_id: int, step_ids: list[int], seed: int) -> list[int]:
    """POST random step moves from one thread; return the status codes."""
    client = Client(raise_request_exception=False)
    client.force_login(user)
    rng = random.Random(seed)
    try:
        return [
            client.post(
                f"/recipes/{recipe_id}/steps/{rng.choice(step_ids)}/"
                f"move-{rng.choice(['up', 'down'])}/"
            ).status_code
            for _ in range(MOVES_PER_THREAD)
        ]
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_concurrent_step_moves_neither_fail_nor_break_the_sequence(user):
    """Overlapping step moves all succeed and leave index_in_sequence contiguous."""
    assert connection.settings_dict["TEST"]["NAME"], "needs a file-backed test database"
    recipe = Recipe.objects.create(recipe_name="Busy recipe", owner=user)
    step_ids = [
        Step.objects.create(recipe=recipe, step_text=f"Step {i}", index_in_sequence=i).pk
        for i in range(5)
    ]

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        futures = [
            pool.submit(_move_steps, user=user, recipe_id=recipe.pk, step_ids=step_ids, seed=seed)
            for seed in range(THREADS)
        ]
        statuses = [status for future in futures for status in future.result()]

    assert statuses.count(500) == 0
    assert statuses == [200] * THREADS * MOVES_PER_THREAD
    indexes = sorted(Step.objects.filter(recipe=recipe).values_list("index_in_sequence", flat=True))
    assert indexes == list(range(5))
