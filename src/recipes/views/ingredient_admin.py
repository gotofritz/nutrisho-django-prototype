"""HTMX views for the shared-Ingredient clean-up tool (Miller columns).

Thin wrappers over `recipes.services.ingredient_admin`; each returns one of the
column or workspace partials under `templates/recipes/ingredient_admin/`.
Selection lives in the request (`ingredient_ids`) and is echoed back into every
re-rendered partial, so there is no client-side store.
"""

from django.contrib.auth.models import AbstractBaseUser
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from recipes.forms.ingredient_admin_forms import IngredientForm
from recipes.models import Ingredient, Recipe
from recipes.services.ingredient_admin import (
    IngredientInUseError,
    delete_ingredients,
    merge_ingredients,
    recipes_for_ingredients,
    recipes_referencing_ingredients,
    search_ingredients,
    selected_ingredients,
)
from recipes.views._types import AuthedRequest

_T = "recipes/ingredient_admin/"

# Selected-ingredient count each action needs before it makes sense.
_MINIMUM_SELECTED = {"edit": 1, "delete": 1, "merge": 2}


def _payload(request: AuthedRequest) -> QueryDict:
    """Whichever of POST/GET carries this request's selection."""
    return request.POST if request.method == "POST" else request.GET


def _selected_ids(data: QueryDict) -> list[int]:
    """Selected ingredient ids, skipping anything non-numeric."""
    ids: list[int] = []
    for raw in data.getlist("ingredient_ids"):
        try:
            ids.append(int(raw))
        except ValueError:
            continue
    return ids


def _filters(data: QueryDict) -> tuple[str, bool]:
    """The column-2 filters carried by this request: search text and unused-only."""
    return data.get("q", ""), bool(data.get("unused"))


def _selection(data: QueryDict, *, query: str, unused_only: bool) -> list[int]:
    """The ids this request selects.

    `toggle_all` is the header checkbox: it clears the selection when every listed
    row is already selected, and otherwise takes the lot. It only ever reaches for
    what column 2 currently lists — what the search text and the unused filter
    leave, not the whole table — matching how filtering already narrows the
    selection to whatever stays visible.
    """
    selected_ids = _selected_ids(data)
    if not data.get("toggle_all"):
        return selected_ids
    listed_ids = [
        ingredient.pk for ingredient in search_ingredients(query, unused_only=unused_only)
    ]
    if listed_ids and set(listed_ids).issubset(selected_ids):
        return []
    return listed_ids


def _optional_id(raw: str | None) -> int | None:
    """One optional numeric id from a form field; None when absent or junk."""
    try:
        return int(raw)  # ty: ignore[invalid-argument-type]  # TypeError handled
    except TypeError, ValueError:
        return None


def _list_context(*, query: str, unused_only: bool, selected_ids: list[int]) -> dict[str, object]:
    """Context for column 2: the filtered ingredient list plus header counts.

    The header checkbox is tri-state, and only listed rows decide which state:
    ticked when they are all selected, dashed when some are, clear otherwise.
    """
    ingredients = list(search_ingredients(query, unused_only=unused_only))
    listed_selected = {i.pk for i in ingredients} & set(selected_ids)
    all_selected = bool(ingredients) and len(listed_selected) == len(ingredients)
    return {
        "query": query,
        "unused_only": unused_only,
        "ingredients": ingredients,
        "found_count": len(ingredients),
        "selected_ids": selected_ids,
        "selected_count": len(selected_ids),
        "all_selected": all_selected,
        "some_selected": bool(listed_selected) and not all_selected,
    }


def _matches_context(*, selected_ids: list[int], owner: AbstractBaseUser) -> dict[str, object]:
    """Context for columns 3 and 4: the owner's recipes touched by the selection.

    Column 4 follows column 3, as Miller columns do. A lone match previews itself,
    since there is nothing else to pick; any other count clears the pane, so a
    preview can never outlive the matches it came from.
    """
    recipes = list(recipes_for_ingredients(ingredient_ids=selected_ids, owner=owner))
    return {
        "recipes": recipes,
        "match_count": len(recipes),
        "selected_count": len(selected_ids),
        "recipe": recipes[0] if len(recipes) == 1 else None,
    }


def _columns_context(
    *, owner: AbstractBaseUser, query: str, unused_only: bool, selected_ids: list[int]
) -> dict[str, object]:
    """Context for columns 2-4; column 4 stays empty until a recipe is picked."""
    return _list_context(
        query=query, unused_only=unused_only, selected_ids=selected_ids
    ) | _matches_context(selected_ids=selected_ids, owner=owner)


def _delete_context(*, selected_ids: list[int]) -> dict[str, object]:
    """Context for the delete confirmation: victims, blast radius, replacements."""
    victims = list(selected_ingredients(selected_ids))
    return {
        "victims": victims,
        "victim_count": len(victims),
        "affected_count": recipes_referencing_ingredients(selected_ids).count(),
        "replacements": search_ingredients("").exclude(pk__in=selected_ids),
    }


def _merge_context(*, selected_ids: list[int]) -> dict[str, object]:
    """Context for the merge chooser: the candidates to pick a survivor from."""
    return {"candidates": list(selected_ingredients(selected_ids))}


def _fragment(
    request: AuthedRequest, template: str, context: dict[str, object], *, oob: bool = False
) -> str:
    """Render one partial, optionally flagged for an out-of-band swap."""
    return render_to_string(_T + template, context | {"oob": oob}, request=request)


def _actions_context(*, selected_count: int, active_action: str | None = None) -> dict[str, object]:
    return {"selected_count": selected_count, "active_action": active_action}


def _actions_oob(request: AuthedRequest, *, selected_ids: list[int], action: str | None) -> str:
    return _fragment(
        request,
        "_action_buttons.html",
        _actions_context(selected_count=len(selected_ids), active_action=action),
        oob=True,
    )


def _guard(*, action: str, selected_ids: list[int]) -> HttpResponse | None:
    """422 when too few ingredients are selected for `action`, else None.

    The buttons render `disabled` for the same thresholds, so this only fires on
    a hand-rolled or racing request — but the endpoints must not depend on the
    markup to stay honest.
    """
    minimum = _MINIMUM_SELECTED[action]
    if len(selected_ids) >= minimum:
        return None
    return HttpResponse(
        render_to_string(
            _T + "_guard_message.html",
            {"minimum": minimum, "noun": "ingredient" if minimum == 1 else "ingredients"},
        ),
        status=422,
    )


def _columns_response(
    request: AuthedRequest, *, query: str, unused_only: bool, selected_ids: list[int]
) -> HttpResponse:
    """Restore columns 2-4 and reset the column-1 buttons."""
    return HttpResponse(
        _fragment(
            request,
            "_columns.html",
            _columns_context(
                owner=request.user,
                query=query,
                unused_only=unused_only,
                selected_ids=selected_ids,
            ),
        )
        + _actions_oob(request, selected_ids=selected_ids, action=None)
    )


def _workspace_response(
    request: AuthedRequest,
    template: str,
    context: dict[str, object],
    *,
    action: str,
    selected_ids: list[int],
) -> HttpResponse:
    """A collapsed workspace panel, plus the column-1 buttons turned into Cancel.

    The panel carries the selection as hidden inputs: it replaces column 2, so
    the checkboxes Cancel would otherwise read are no longer in the DOM.
    """
    return HttpResponse(
        _fragment(request, template, context | {"selected_ids": selected_ids})
        + _actions_oob(request, selected_ids=selected_ids, action=action)
    )


@require_GET
def ingredient_manage(request: AuthedRequest) -> HttpResponse:
    """Full-page four-column shell."""
    query, unused_only = _filters(request.GET)
    return render(
        request,
        _T + "manager.html",
        _columns_context(
            owner=request.user,
            query=query,
            unused_only=unused_only,
            selected_ids=_selected_ids(request.GET),
        ),
    )


@require_GET
def ingredient_manage_search(request: AuthedRequest) -> HttpResponse:
    """Column 2: ingredient list filtered by `q`, with columns 3 and 1 kept in step.

    Filtering narrows the selection to whatever stays visible, so the match
    column and the action buttons are refreshed out of band alongside it. Select
    all arrives here too, for the same reason: it changes the selection, so the
    same three fragments have to come back.
    """
    query, unused_only = _filters(request.GET)
    selected_ids = _selection(request.GET, query=query, unused_only=unused_only)
    matches = _matches_context(selected_ids=selected_ids, owner=request.user)
    return HttpResponse(
        _fragment(
            request,
            "_ingredient_list.html",
            _list_context(query=query, unused_only=unused_only, selected_ids=selected_ids),
        )
        + _fragment(request, "_recipe_matches.html", matches, oob=True)
        + _fragment(request, "_recipe_preview.html", matches, oob=True)
        + _actions_oob(request, selected_ids=selected_ids, action=None)
    )


@require_GET
def ingredient_manage_recipes(request: AuthedRequest) -> HttpResponse:
    """Column 3: the owner's recipes matching the selection.

    Triggered by ticking a checkbox, so it also refreshes column 2's header
    counts, the preview and the action buttons out of band.
    """
    query, unused_only = _filters(request.GET)
    selected_ids = _selected_ids(request.GET)
    matches = _matches_context(selected_ids=selected_ids, owner=request.user)
    return HttpResponse(
        _fragment(request, "_recipe_matches.html", matches)
        + _fragment(request, "_recipe_preview.html", matches, oob=True)
        + _fragment(
            request,
            "_ingredient_count.html",
            _list_context(query=query, unused_only=unused_only, selected_ids=selected_ids),
            oob=True,
        )
        + _actions_oob(request, selected_ids=selected_ids, action=None)
    )


@require_GET
def ingredient_manage_preview(request: AuthedRequest, recipe_id: int) -> HttpResponse:
    """Column 4: inert, owner-scoped render of one recipe.

    Deliberately not a stripped-down `partials/_recipe_content.html`: that
    template pulls in the navbars and the add/edit HTMX triggers, none of which
    belong in a preview pane.
    """
    recipe = get_object_or_404(Recipe, id=recipe_id, owner=request.user)
    return render(request, _T + "_recipe_preview.html", {"recipe": recipe})


@require_GET
def ingredient_manage_cancel(request: AuthedRequest) -> HttpResponse:
    """Restore columns 2-4 after an action panel is dismissed."""
    query, unused_only = _filters(request.GET)
    return _columns_response(
        request,
        query=query,
        unused_only=unused_only,
        selected_ids=_selected_ids(request.GET),
    )


@require_GET
def ingredient_manage_edit(request: AuthedRequest) -> HttpResponse:
    """Workspace: one edit form per selected ingredient."""
    selected_ids = _selected_ids(request.GET)
    blocked = _guard(action="edit", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    panels = [
        {"ingredient": ingredient, "form": IngredientForm(instance=ingredient)}
        for ingredient in selected_ingredients(selected_ids)
    ]
    return _workspace_response(
        request, "_edit_panels.html", {"panels": panels}, action="edit", selected_ids=selected_ids
    )


@require_POST
def ingredient_manage_save(request: AuthedRequest, ingredient_id: int) -> HttpResponse:
    """Persist one ingredient; invalid input returns the panel with its errors.

    Editing a single ingredient closes the workspace on save, since the panel is
    the only thing in it and re-rendering it looks like nothing happened. Editing
    several keeps them open and marks this one saved: closing on the first save
    would throw away whatever is typed in its siblings.
    """
    ingredient = get_object_or_404(Ingredient, pk=ingredient_id)
    form = IngredientForm(data=request.POST, instance=ingredient)
    if not form.is_valid():
        return render(
            request, _T + "_ingredient_panel.html", {"ingredient": ingredient, "form": form}
        )
    form.save()
    selected_ids = _selected_ids(request.POST)
    if len(selected_ids) > 1:
        return render(
            request,
            _T + "_ingredient_panel.html",
            {"ingredient": ingredient, "form": form, "saved": True},
        )
    query, unused_only = _filters(request.POST)
    response = _columns_response(
        request, query=query, unused_only=unused_only, selected_ids=selected_ids
    )
    # The form targets itself; the whole workspace has to go instead.
    response["HX-Retarget"] = "#columns"
    response["HX-Reswap"] = "outerHTML"
    return response


@require_http_methods(["GET", "POST"])
def ingredient_manage_delete(request: AuthedRequest) -> HttpResponse:
    """GET shows the delete confirmation; POST performs the delete.

    A delete that would strand recipes needs a replacement ingredient, and comes
    back as 422 with the picker until one is chosen.
    """
    payload = _payload(request)
    selected_ids = _selected_ids(payload)
    blocked = _guard(action="delete", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    if request.method == "POST":
        try:
            delete_ingredients(
                ingredient_ids=selected_ids,
                replacement_id=_optional_id(payload.get("replacement_id")),
            )
        except IngredientInUseError as error:
            return HttpResponse(
                _fragment(
                    request,
                    "_delete_confirm.html",
                    _delete_context(selected_ids=selected_ids)
                    | {"selected_ids": selected_ids, "error": str(error)},
                ),
                status=422,
            )
        # The selection is gone with the rows, so the columns come back empty-handed.
        query, unused_only = _filters(payload)
        return _columns_response(request, query=query, unused_only=unused_only, selected_ids=[])
    return _workspace_response(
        request,
        "_delete_confirm.html",
        _delete_context(selected_ids=selected_ids),
        action="delete",
        selected_ids=selected_ids,
    )


@require_http_methods(["GET", "POST"])
def ingredient_manage_merge(request: AuthedRequest) -> HttpResponse:
    """GET shows the survivor chooser; POST merges the rest into the survivor.

    The survivor has to be one of the selected ingredients — merging into
    something the user never picked would move recipes they never looked at.
    """
    payload = _payload(request)
    selected_ids = _selected_ids(payload)
    blocked = _guard(action="merge", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    if request.method == "POST":
        survivor_id = _optional_id(payload.get("survivor_id"))
        if survivor_id is None or survivor_id not in selected_ids:
            return HttpResponse(
                _fragment(
                    request,
                    "_merge_chooser.html",
                    _merge_context(selected_ids=selected_ids)
                    | {
                        "selected_ids": selected_ids,
                        "error": "Pick which ingredient to keep.",
                    },
                ),
                status=422,
            )
        get_object_or_404(Ingredient, pk=survivor_id)
        merge_ingredients(survivor_id=survivor_id, victim_ids=selected_ids)
        # The survivor is all that is left of the selection, so it stays ticked.
        query, unused_only = _filters(payload)
        return _columns_response(
            request, query=query, unused_only=unused_only, selected_ids=[survivor_id]
        )
    return _workspace_response(
        request,
        "_merge_chooser.html",
        _merge_context(selected_ids=selected_ids),
        action="merge",
        selected_ids=selected_ids,
    )
