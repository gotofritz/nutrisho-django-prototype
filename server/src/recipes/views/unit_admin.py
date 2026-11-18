"""HTMX views for the staff unit tool (#154).

Built like the cuisine tool: column 1 holds the search box, the filters and
the actions, `#unit-columns` holds the unit list and the staff member's
matching recipes, and every browsing response re-renders that block whole,
with the action buttons refreshed out of band. An action replaces the block
with a workspace panel; Cancel brings the columns back. Selection lives in the
request (`unit_ids`), never on the client.
"""

from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from recipes.forms.unit_admin_forms import UnitForm
from recipes.models import Unit
from recipes.services.unit_admin import (
    UnitScopeError,
    delete_units,
    merge_units,
    promote_units,
    recipes_for_units,
    rows_using_units,
    selected_units,
    unit_rows,
)
from recipes.views._types import AuthedRequest

_T = "recipes/unit_admin/"

# Selected-unit count each action needs, as (minimum, maximum); None means no upper bound.
_SELECTION_BOUNDS: dict[str, tuple[int, int | None]] = {
    "edit": (1, 1),
    "promote": (1, None),
    "merge": (2, None),
    "delete": (1, None),
}


def _payload(request: AuthedRequest) -> QueryDict:
    return request.POST if request.method == "POST" else request.GET


def _selected_ids(data: QueryDict) -> list[int]:
    ids: list[int] = []
    for raw in data.getlist("unit_ids"):
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


def _columns_context(request: AuthedRequest, *, selected_ids: list[int]) -> dict:
    data = _payload(request)
    private_only = data.get("private") == "1"
    unused_only = data.get("unused") == "1"
    by_added = data.get("sort") == "added"
    query = data.get("q", "")
    return {
        "query": query,
        "private_only": private_only,
        "unused_only": unused_only,
        "by_added": by_added,
        "rows": unit_rows(
            query, private_only=private_only, unused_only=unused_only, by_added=by_added
        ),
        "selected_ids": selected_ids,
        "selected_count": len(selected_ids),
        "recipes": list(recipes_for_units(unit_ids=selected_ids, owner=request.user)),
    }


def _columns_response(request: AuthedRequest, *, selected_ids: list[int]) -> HttpResponse:
    context = _columns_context(request, selected_ids=selected_ids)
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
        "noun": "unit" if minimum == 1 else "units",
    }
    return _workspace(request, "_guard.html", context, selected_ids=selected_ids, status=422)


@require_GET
def unit_manage(request: AuthedRequest) -> HttpResponse:
    """Full page: column 1 plus the columns block."""
    context = _columns_context(request, selected_ids=_selected_ids(request.GET))
    return render(request, _T + "manager.html", context)


@require_GET
def unit_manage_columns(request: AuthedRequest) -> HttpResponse:
    """The columns block for the current search and selection; also Cancel."""
    return _columns_response(request, selected_ids=_selected_ids(request.GET))


@require_http_methods(["GET", "POST"])
def unit_manage_add(request: AuthedRequest) -> HttpResponse:
    """GET shows a blank form; POST creates a global unit."""
    selected_ids = _selected_ids(_payload(request))
    if request.method == "POST":
        form = UnitForm(data=request.POST)
        if form.is_valid():
            unit = form.save()
            return _columns_response(request, selected_ids=[unit.pk])
        return _workspace(
            request, "_form.html", {"form": form}, selected_ids=selected_ids, status=422
        )
    return _workspace(request, "_form.html", {"form": UnitForm()}, selected_ids=selected_ids)


@require_GET
def unit_manage_edit(request: AuthedRequest) -> HttpResponse:
    """Workspace: the edit form for the one selected unit."""
    selected_ids = _selected_ids(request.GET)
    blocked = _guard(request, action="edit", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    unit = get_object_or_404(Unit.objects.select_related("owner"), pk=selected_ids[0])
    return _workspace(
        request,
        "_form.html",
        {"form": UnitForm(instance=unit), "unit": unit},
        selected_ids=selected_ids,
    )


@require_POST
def unit_manage_save(request: AuthedRequest, unit_id: int) -> HttpResponse:
    """Rename one unit or change its plural, dimension and aliases; errors are 422."""
    unit = get_object_or_404(Unit.objects.select_related("owner"), pk=unit_id)
    form = UnitForm(data=request.POST, instance=unit)
    if form.is_valid():
        form.save()
        return _columns_response(request, selected_ids=[unit.pk])
    return _workspace(
        request, "_form.html", {"form": form, "unit": unit}, selected_ids=[unit.pk], status=422
    )


@require_http_methods(["GET", "POST"])
def unit_manage_promote(request: AuthedRequest) -> HttpResponse:
    """GET asks what the units measure; POST makes them global."""
    selected_ids = _selected_ids(_payload(request))
    blocked = _guard(request, action="promote", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    context: dict = {
        "candidates": selected_units(selected_ids),
        "dimensions": Unit.DIMENSION_CHOICES,
    }
    if request.method == "POST":
        try:
            promoted = promote_units(selected_ids, dimension=request.POST.get("dimension", ""))
        except ValueError as error:
            context["error"] = str(error)
            return _workspace(
                request, "_promote.html", context, selected_ids=selected_ids, status=422
            )
        return _columns_response(request, selected_ids=promoted)
    return _workspace(request, "_promote.html", context, selected_ids=selected_ids)


@require_http_methods(["GET", "POST"])
def unit_manage_merge(request: AuthedRequest) -> HttpResponse:
    """GET asks which unit survives; POST moves every row onto it."""
    selected_ids = _selected_ids(_payload(request))
    blocked = _guard(request, action="merge", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    context: dict = {"candidates": selected_units(selected_ids)}
    if request.method == "POST":
        survivor_id = _optional_id(request.POST.get("survivor_id"))
        if survivor_id is None or survivor_id not in selected_ids:
            context["error"] = "Pick which unit to keep."
        else:
            get_object_or_404(Unit, pk=survivor_id)
            try:
                merge_units(
                    survivor_id=survivor_id,
                    victim_ids=selected_ids,
                    keep_aliases=request.POST.get("keep_aliases") == "1",
                )
            except UnitScopeError as error:
                context["error"] = str(error)
            else:
                return _columns_response(request, selected_ids=[survivor_id])
        return _workspace(request, "_merge.html", context, selected_ids=selected_ids, status=422)
    return _workspace(request, "_merge.html", context, selected_ids=selected_ids)


@require_http_methods(["GET", "POST"])
def unit_manage_delete(request: AuthedRequest) -> HttpResponse:
    """GET shows the confirmation; POST deletes, moving rows to the replacement."""
    selected_ids = _selected_ids(_payload(request))
    blocked = _guard(request, action="delete", selected_ids=selected_ids)
    if blocked is not None:
        return blocked
    context: dict = {
        "victims": selected_units(selected_ids),
        "affected_count": rows_using_units(selected_ids).count(),
        "replacements": [
            row for row in unit_rows() if row.unit.pk not in selected_ids and not row.owner_name
        ],
    }
    if request.method == "POST":
        replacement_id = _optional_id(request.POST.get("replacement_id"))
        if replacement_id is not None:
            get_object_or_404(Unit, pk=replacement_id)
        try:
            delete_units(unit_ids=selected_ids, replacement_id=replacement_id)
        except UnitScopeError as error:
            context["error"] = str(error)
            return _workspace(
                request, "_delete.html", context, selected_ids=selected_ids, status=422
            )
        return _columns_response(request, selected_ids=[])
    return _workspace(request, "_delete.html", context, selected_ids=selected_ids)
