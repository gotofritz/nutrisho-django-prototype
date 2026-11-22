"""The API keys page (#150): make a key, shown once; list your keys; revoke one."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from recipes.forms.api_key_form import ApiKeyForm
from recipes.models import ApiToken
from recipes.services.api_tokens import (
    MAX_TOKENS_PER_USER,
    TokenLimitError,
    expires_on,
    is_expired,
    make_own_token,
    user_tokens,
)
from recipes.views._types import AuthedRequest


def _page(request: AuthedRequest, *, form: ApiKeyForm, new_key: str = "") -> HttpResponse:
    rows = [
        {"token": token, "expires_on": expires_on(token), "expired": is_expired(token)}
        for token in user_tokens(user=request.user)
    ]
    context: dict[str, object] = {"form": form, "rows": rows, "max_keys": MAX_TOKENS_PER_USER}
    if new_key:
        context["new_key"] = new_key
    return render(request, "recipes/api_keys.html", context)


@never_cache
@require_http_methods(["GET", "POST"])
def api_keys(request: AuthedRequest) -> HttpResponse:
    """List the signed-in user's keys; a valid post makes one and shows its key, this once."""
    if request.method != "POST":
        return _page(request, form=ApiKeyForm())
    form = ApiKeyForm(data=request.POST)
    if not form.is_valid():
        return _page(request, form=form)
    try:
        _, key = make_own_token(
            user=request.user, name=form.cleaned_data["name"], days=form.cleaned_data["days"]
        )
    except TokenLimitError:
        form.add_error(
            None, f"You have {MAX_TOKENS_PER_USER} keys, the most you may hold: revoke one first."
        )
        return _page(request, form=form)
    return _page(request, form=ApiKeyForm(), new_key=key)


@require_POST
def api_key_revoke(request: AuthedRequest, token_id: int) -> HttpResponse:
    """Delete one of the signed-in user's keys, which stops it working; another's is a 404."""
    token = get_object_or_404(ApiToken, pk=token_id, user=request.user)
    name = token.name or "the key"
    token.delete()
    messages.success(request, f"Revoked “{name}”.")
    return redirect("recipes:api_keys")
