"""HTMX views for the staff cuisine tool (plan 011).

Modelled on the ingredient clean-up tool, but simpler: column 1 holds the
search box and the actions, `#cuisine-columns` holds the node list and the
staff member's matching recipes, and every browsing response re-renders that
block whole, with the action buttons refreshed out of band. An action replaces
the block with a workspace panel; Cancel brings the columns back. Selection
lives in the request (`cuisine_ids`), never on the client.
"""

from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from recipes.forms.cuisine_admin_forms import CuisineForm
from recipes.models import Cuisine
from recipes.services.cuisine_admin import (
    CuisineHasChildrenError,
    cuisine_rows,
    delete_cuisines,
    merge_cuisines,
    recipes_for_cuisines,
    recipes_using_cuisines,
    selected_cuisines,
)
from recipes.views._types import AuthedRequest

_T = "recipes/cuisine_admin/"

# Selected-node count each action needs, as (minimum, maximum); None means no upper bound.
_SELECTION_BOUNDS: dict[str, tuple[int, int | None]] = {
    "edit": (1, 1),
    "merge": (2, None),
    "delete": (1, None),
}


def _payload(request: AuthedRequest) -> QueryDict:
    return request.POST if request.method == "POST" else request.GET


def _selected_ids(data: QueryDict) -> list[int]:
    ids: list[int] = []
    for raw in data.getlist("cuisine_ids"):
        try:
            ids.append(int(raw))
        except ValueError:
            continue
    return ids


def _optional_id(raw: str | None) -> int | None:
    try:
        return int(raw)  # ty: ignore[invalid-argument-type]  # TypeError handled
    except TypeError, ValueError:
        return None


def _actions(request: AuthedRequest, *, selected_ids: list[int], oob: bool) -> str:
    return render_to_string(
        _T + "_actions.html",
        {"selected_count": len(selected_ids), "oob": oob},
        request=request,
    )


def _columns_context(request: AuthedRequest, *, query: str, selected_ids: list[int]) -> dict:
    return {
        "query": query,
        "rows": cuisine_rows(query),
        "selected_ids": selected_ids,
        "selected_count": len(selected_ids),
        "recipes": list(recipes_for_cuisines(cuisine_ids=selected_ids, owner=request.user)),
    }


def _columns_response(request: AuthedRequest, *, selected_ids: list[int]) -> HttpResponse:
    query = _payload(request).get("q", "")
    context = _columns_context(request, query=query, selected_ids=selected_ids)
    return HttpResponse(
        render_to_string(_T + "_columns.html", context, request=request)
        + _actions(request, selected_ids=selected_ids, oob=True)
    )


def _workspace(
    request: AuthedRequest,
    template: str,
    context: dict,
    *,
    selected_ids: list[int],
    status: int = 200,
) -> HttpResponse:
    return HttpResponse(
        render_to_string(_T + template, context | {"selected_ids": selected_ids}, request=request),
        status=status,
    )


def _guard(request: AuthedRequest, *, action: str, selected_ids: list[int]) -> HttpResponse | None:
    """422 when the selection is the wrong size for `action`, else None."""
    minimum, maximum = _SELECTION_BOUNDS[action]
    count = len(selected_ids)
    if count >= minimum and (maximum is None or count <= maximum):
        return None
    context = {
        "exact": maximum == minimum,
        "minimum": minimum,
        "noun": "cuisine" if minimum == 1 else "cuisines",
    }
    return _workspace(request, "_guard.html", context, selected_ids=selected_ids, status=422)


@require_GET
def cuisine_manage(request: AuthedRequest) -> HttpResponse:
    """Full page: column 1 plus the columns block."""
    selected_ids = _selected_ids(request.GET)
    context = _columns_context(request, query=request.GET.get("q", ""), selected_ids=selected_ids)
    return render(request, _T + "manager.html", context)


@require_GET
def cuisine_manage_columns(request: AuthedRequest) -> HttpResponse:
    """The columns block for the current search and selection; also Cancel."""
    return _columns_response(request, selected_ids=_selected_ids(request.GET))


@require_http_methods(["GET", "POST"])
def cuisine_manage_add(request: AuthedRequest) -> HttpResponse:
    """GET shows a blank form, preset inside the one selected node; POST creates it."""
    selected_ids = _selected_ids(_payload(request))
    if request.method == "POST":
        form = CuisineForm(data=request.POST)
        if form.is_valid():
            node = form.save()
            return _columns_response(request, selected_ids=[node.pk])
        return _workspace(
            request, "_form.html", {"form": form}, selected_ids=selected_ids, status=422
        )
    initial = {"parent": selected_ids[0]} if len(selected_ids) == 1 else {}
    return _workspace(
        request, "_form.html", {"form": CuisineForm(initial=initial)}, selected_ids=selected_ids
    )


@require_GET
def cuisine_manage_edit(request: AuthedRequest) -> HttpResponse:
    """Workspace: the edit form for the one selected node."""
    selected_ids = _selected_ids(request.GET)
    blocked = _guard(request, action="edit", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    node = get_object_or_404(Cuisine, pk=selected_ids[0])
    return _workspace(
        request,
        "_form.html",
        {"form": CuisineForm(instance=node), "node": node},
        selected_ids=selected_ids,
    )


@require_POST
def cuisine_manage_save(request: AuthedRequest, cuisine_id: int) -> HttpResponse:
    """Rename or move one node; validation errors come back as 422."""
    node = get_object_or_404(Cuisine, pk=cuisine_id)
    form = CuisineForm(data=request.POST, instance=node)
    if form.is_valid():
        form.save()
        return _columns_response(request, selected_ids=[node.pk])
    return _workspace(
        request, "_form.html", {"form": form, "node": node}, selected_ids=[node.pk], status=422
    )


@require_http_methods(["GET", "POST"])
def cuisine_manage_merge(request: AuthedRequest) -> HttpResponse:
    """GET asks which node survives; POST moves every recipe onto it."""
    selected_ids = _selected_ids(_payload(request))
    blocked = _guard(request, action="merge", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    context: dict = {"candidates": selected_cuisines(selected_ids)}
    if request.method == "POST":
        survivor_id = _optional_id(request.POST.get("survivor_id"))
        if survivor_id is None or survivor_id not in selected_ids:
            context["error"] = "Pick which cuisine to keep."
        else:
            try:
                merge_cuisines(survivor_id=survivor_id, victim_ids=selected_ids)
            except CuisineHasChildrenError as error:
                context["error"] = str(error)
            else:
                return _columns_response(request, selected_ids=[survivor_id])
        return _workspace(request, "_merge.html", context, selected_ids=selected_ids, status=422)
    return _workspace(request, "_merge.html", context, selected_ids=selected_ids)


@require_http_methods(["GET", "POST"])
def cuisine_manage_delete(request: AuthedRequest) -> HttpResponse:
    """GET shows the confirmation; POST deletes, moving recipes to the replacement."""
    selected_ids = _selected_ids(_payload(request))
    blocked = _guard(request, action="delete", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    context: dict = {
        "victims": selected_cuisines(selected_ids),
        "affected_count": recipes_using_cuisines(selected_ids).count(),
        "replacements": [row for row in cuisine_rows() if row.cuisine.pk not in selected_ids],
    }
    if request.method == "POST":
        try:
            delete_cuisines(
                cuisine_ids=selected_ids,
                replacement_id=_optional_id(request.POST.get("replacement_id")),
            )
        except CuisineHasChildrenError as error:
            context["error"] = str(error)
            return _workspace(
                request, "_delete.html", context, selected_ids=selected_ids, status=422
            )
        return _columns_response(request, selected_ids=[])
    return _workspace(request, "_delete.html", context, selected_ids=selected_ids)
