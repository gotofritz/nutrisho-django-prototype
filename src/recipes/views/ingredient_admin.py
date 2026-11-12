"""HTMX views for the shared-Ingredient clean-up tool (Miller columns).

Thin wrappers over `recipes.services.ingredient_admin`; each returns one of the
column or workspace partials under `templates/recipes/ingredient_admin/`.
Selection lives in the request (`ingredient_ids`) and is echoed back into every
re-rendered partial, so there is no client-side store.
"""

from typing import TypedDict

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from recipes.forms.ingredient_admin_forms import IngredientForm
from recipes.models import Ingredient, IngredientAlias
from recipes.services.ingredient_admin import (
    AliasError,
    IngredientInUseError,
    add_alias,
    delete_ingredients,
    merge_ingredients,
    merge_plural_ingredients,
    promote_ingredients,
    recipes_for_ingredients,
    recipes_referencing_ingredients,
    remove_alias,
    search_ingredients,
    selected_ingredients,
    suggest_singular,
)
from recipes.services.recipe_contents import with_ingredients
from recipes.views._auth import owned_recipe
from recipes.views._types import AuthedRequest

_T = "recipes/ingredient_admin/"

# Selected-ingredient count each action needs before it makes sense, as
# (minimum, maximum); a maximum of None means "no upper bound". Merging a plural
# is capped at 2 because with two plural rows picked there is no way to tell
# which spelling should become the survivor's plural.
_SELECTION_BOUNDS: dict[str, tuple[int, int | None]] = {
    "edit": (1, None),
    "delete": (1, None),
    "merge": (2, None),
    "merge_plural": (2, 2),
    "promote": (1, None),
    "alias": (1, 1),
}


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


class _Filters(TypedDict):
    """The column-2 filters, as every context helper takes them."""

    query: str
    unused_only: bool
    plurals_only: bool
    private_only: bool


def _filters(data: QueryDict) -> _Filters:
    """The column-2 filters carried by this request.

    A mapping rather than a tuple, so the set of filters can grow without every
    call site having to unpack one more positional value: each of them just
    forwards it as `**filters`.
    """
    return {
        "query": data.get("q", ""),
        "unused_only": bool(data.get("unused")),
        "plurals_only": bool(data.get("plurals")),
        "private_only": bool(data.get("private")),
    }


def _selection(
    data: QueryDict, *, query: str, unused_only: bool, plurals_only: bool, private_only: bool
) -> list[int]:
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
        ingredient.pk
        for ingredient in search_ingredients(
            query, unused_only=unused_only, plurals_only=plurals_only, private_only=private_only
        )
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


def _list_context(
    *,
    query: str,
    unused_only: bool,
    plurals_only: bool,
    private_only: bool,
    selected_ids: list[int],
) -> dict[str, object]:
    """Context for column 2: the filtered ingredient list plus header counts.

    The header checkbox is tri-state, and only listed rows decide which state:
    ticked when they are all selected, dashed when some are, clear otherwise.
    """
    ingredients = list(
        search_ingredients(
            query, unused_only=unused_only, plurals_only=plurals_only, private_only=private_only
        )
    )
    listed_selected = {i.pk for i in ingredients} & set(selected_ids)
    all_selected = bool(ingredients) and len(listed_selected) == len(ingredients)
    return {
        "query": query,
        "unused_only": unused_only,
        "plurals_only": plurals_only,
        "private_only": private_only,
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
    *,
    owner: AbstractBaseUser,
    query: str,
    unused_only: bool,
    plurals_only: bool,
    private_only: bool,
    selected_ids: list[int],
) -> dict[str, object]:
    """Context for columns 2-4; column 4 stays empty until a recipe is picked."""
    return _list_context(
        query=query,
        unused_only=unused_only,
        plurals_only=plurals_only,
        private_only=private_only,
        selected_ids=selected_ids,
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
    """422 when the selection is the wrong size for `action`, else None.

    The buttons render `disabled` for the same bounds, so this only fires on a
    hand-rolled or racing request — but the endpoints must not depend on the
    markup to stay honest.
    """
    minimum, maximum = _SELECTION_BOUNDS[action]
    count = len(selected_ids)
    if count >= minimum and (maximum is None or count <= maximum):
        return None
    exact = maximum == minimum
    return HttpResponse(
        render_to_string(
            _T + "_guard_message.html",
            {
                "minimum": minimum,
                "exact": exact,
                "noun": "ingredient" if minimum == 1 else "ingredients",
            },
        ),
        status=422,
    )


def _columns_response(
    request: AuthedRequest,
    *,
    query: str,
    unused_only: bool,
    plurals_only: bool,
    private_only: bool,
    selected_ids: list[int],
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
                plurals_only=plurals_only,
                private_only=private_only,
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
    return render(
        request,
        _T + "manager.html",
        _columns_context(
            owner=request.user,
            **_filters(request.GET),
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
    filters = _filters(request.GET)
    selected_ids = _selection(request.GET, **filters)
    matches = _matches_context(selected_ids=selected_ids, owner=request.user)
    return HttpResponse(
        _fragment(
            request,
            "_ingredient_list.html",
            _list_context(**filters, selected_ids=selected_ids),
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
    filters = _filters(request.GET)
    selected_ids = _selected_ids(request.GET)
    matches = _matches_context(selected_ids=selected_ids, owner=request.user)
    return HttpResponse(
        _fragment(request, "_recipe_matches.html", matches)
        + _fragment(request, "_recipe_preview.html", matches, oob=True)
        + _fragment(
            request,
            "_ingredient_count.html",
            _list_context(**filters, selected_ids=selected_ids),
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
    recipe = with_ingredients(owned_recipe(request=request, recipe_id=recipe_id))
    return render(request, _T + "_recipe_preview.html", {"recipe": recipe})


@require_GET
def ingredient_manage_cancel(request: AuthedRequest) -> HttpResponse:
    """Restore columns 2-4 after an action panel is dismissed."""
    return _columns_response(
        request,
        **_filters(request.GET),
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
    response = _columns_response(request, **_filters(request.POST), selected_ids=selected_ids)
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
        return _columns_response(request, **_filters(payload), selected_ids=[])
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
        try:
            merge_ingredients(survivor_id=survivor_id, victim_ids=selected_ids)
        except IngredientInUseError as error:
            return HttpResponse(
                _fragment(
                    request,
                    "_merge_chooser.html",
                    _merge_context(selected_ids=selected_ids)
                    | {"selected_ids": selected_ids, "error": str(error)},
                ),
                status=422,
            )
        # The survivor is all that is left of the selection, so it stays ticked.
        return _columns_response(request, **_filters(payload), selected_ids=[survivor_id])
    return _workspace_response(
        request,
        "_merge_chooser.html",
        _merge_context(selected_ids=selected_ids),
        action="merge",
        selected_ids=selected_ids,
    )


def _merge_plural_context(*, selected_ids: list[int]) -> dict[str, object]:
    """Context for the plural chooser: the pair, and which half looks singular.

    The guess runs the rule both ways — whichever name pluralises into the other
    is the singular. When neither does (a pair the owner picked by hand, or one
    the rule spells differently) the first is offered, which is the shorter name
    in the usual `apple`/`apples` shape because column 2 sorts alphabetically.
    """
    candidates = list(selected_ingredients(selected_ids))
    return {"candidates": candidates, "suggested_id": suggest_singular(candidates)}


@require_http_methods(["GET", "POST"])
def ingredient_manage_merge_plural(request: AuthedRequest) -> HttpResponse:
    """GET asks which of the two is the singular; POST folds the plural into it.

    The plural-aware Merge: the row that goes is not merely deleted, its spelling
    is written onto the survivor's `plural_name`, so the name disappearing from
    column 2 is the one the recipe page renders above a quantity of 1. A plain
    Merge drops it and leaves the rule guessing.
    """
    payload = _payload(request)
    selected_ids = _selected_ids(payload)
    blocked = _guard(action="merge_plural", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    if request.method == "POST":
        singular_id = _optional_id(payload.get("singular_id"))
        if singular_id is None or singular_id not in selected_ids:
            return HttpResponse(
                _fragment(
                    request,
                    "_merge_plural_chooser.html",
                    _merge_plural_context(selected_ids=selected_ids)
                    | {
                        "selected_ids": selected_ids,
                        "error": "Pick which one is the singular.",
                    },
                ),
                status=422,
            )
        plural_id = next(pk for pk in selected_ids if pk != singular_id)
        try:
            merge_plural_ingredients(singular_id=singular_id, plural_id=plural_id)
        except IngredientInUseError as error:
            return HttpResponse(
                _fragment(
                    request,
                    "_merge_plural_chooser.html",
                    _merge_plural_context(selected_ids=selected_ids)
                    | {"selected_ids": selected_ids, "error": str(error)},
                ),
                status=422,
            )
        # The singular is all that is left of the pair, so it stays ticked.
        return _columns_response(request, **_filters(payload), selected_ids=[singular_id])
    return _workspace_response(
        request,
        "_merge_plural_chooser.html",
        _merge_plural_context(selected_ids=selected_ids),
        action="merge_plural",
        selected_ids=selected_ids,
    )


def _promote_context(*, selected_ids: list[int]) -> dict[str, object]:
    """Context for the promote confirmation.

    Lists each selected private row with what promoting it will fold in: other
    users' rows of the same name, and an existing global row it would merge
    into. Global rows in the selection are listed as already global.
    """
    rows = []
    for ingredient in selected_ingredients(selected_ids):
        same_name = Ingredient.objects.filter(
            ingredient_name__iexact=ingredient.ingredient_name
        ).exclude(pk=ingredient.pk)
        rows.append(
            {
                "ingredient": ingredient,
                "existing_global": same_name.filter(owner__isnull=True).first(),
                "others": list(same_name.filter(owner__isnull=False).select_related("owner")),
            }
        )
    return {"rows": rows}


@require_http_methods(["GET", "POST"])
def ingredient_manage_promote(request: AuthedRequest) -> HttpResponse:
    """GET shows what Promote will do; POST makes the selection global.

    A private row becomes global, or merges into the global row that already
    has its name; other users' private rows of that name are folded in, so their
    recipes share the global row too (plan 011).
    """
    payload = _payload(request)
    selected_ids = _selected_ids(payload)
    blocked = _guard(action="promote", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    if request.method == "POST":
        promoted = promote_ingredients(selected_ids)
        return _columns_response(request, **_filters(payload), selected_ids=promoted)
    return _workspace_response(
        request,
        "_promote_confirm.html",
        _promote_context(selected_ids=selected_ids),
        action="promote",
        selected_ids=selected_ids,
    )


def _alias_context(*, ingredient: Ingredient) -> dict[str, object]:
    """Context for the alias panel: the ingredient and its aliases, A-Z."""
    return {
        "ingredient": ingredient,
        "alias_name": "",
        "aliases": list(
            IngredientAlias.objects.filter(canonical=ingredient).order_by(
                Lower("alias_name"), "alias_name"
            )
        ),
    }


def _alias_notice(*, name: str, merged: int) -> str:
    """What the panel says after adding `name`, convergence included."""
    if not merged:
        return f"Added “{name}”."
    noun = "ingredient" if merged == 1 else "ingredients"
    return f"Added “{name}” and merged {merged} existing {noun} of that name into it."


@require_http_methods(["GET", "POST"])
def ingredient_manage_alias(request: AuthedRequest) -> HttpResponse:
    """GET lists the selected ingredient's aliases; POST adds or removes one.

    The explicit mapping path of plan 008: declare `eggplant → aubergine`
    before anything is scraped. A name that already exists as ingredient rows
    is merged into the selected one rather than shadowed (`add_alias`). The
    panel stays open after each change, so several aliases can go in at once;
    Done closes it.
    """
    payload = _payload(request)
    selected_ids = _selected_ids(payload)
    blocked = _guard(action="alias", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    ingredient = get_object_or_404(Ingredient, pk=selected_ids[0])
    if request.method == "GET":
        return _workspace_response(
            request,
            "_alias_panel.html",
            _alias_context(ingredient=ingredient),
            action="alias",
            selected_ids=selected_ids,
        )
    extra: dict[str, object] = {"selected_ids": selected_ids}
    status = 200
    remove_id = _optional_id(payload.get("remove_alias_id"))
    if remove_id is not None:
        if IngredientAlias.objects.filter(pk=remove_id, canonical=ingredient).exists():
            remove_alias(alias_id=remove_id)
    else:
        name = payload.get("alias_name", "").strip()
        try:
            merged = add_alias(canonical_id=ingredient.pk, alias_name=name)
        except (AliasError, ValidationError) as error:
            message = error.messages[0] if isinstance(error, ValidationError) else str(error)
            extra |= {"error": message, "alias_name": name}
            status = 422
        else:
            extra["notice"] = _alias_notice(name=name, merged=merged)
    return HttpResponse(
        _fragment(request, "_alias_panel.html", _alias_context(ingredient=ingredient) | extra),
        status=status,
    )
