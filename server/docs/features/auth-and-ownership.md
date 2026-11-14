# Login and ownership (`nutrisho/middleware.py`, `recipes/views/_auth.py`)

Login is the default, not a decorator (#48). `HtmxLoginRequiredMiddleware`
subclasses Django's `LoginRequiredMiddleware`, so every view needs a signed-in
user unless it is marked `@login_not_required`: Django's login and
password-reset views, the admin login, and `/healthz`. Its
`handle_no_permission` sends a plain request a 302 to the login page and an htmx
request an empty 200 with `HX-Redirect`, because htmx would otherwise swap the
login page into the panel. The `next` it adds is always safe to GET: the current
URL for a page (or a boosted GET), the Referer for a fragment or a POST. Django
admin is behind the same middleware; its views carry a `login_url`, so an
anonymous visit to `/admin/` still goes to `/admin/login/`.

Log-out (#59) is a POST form to Django's `LogoutView` (it refuses GET) in the
site header (`partials/_site_header.html`) on every signed-in page; it lands on
the login page. `registration/login.html` extends `base.html`. The log-out and log-in
forms both carry `hx-boost="false"`: logging in rotates the CSRF token, and a
boosted swap would leave the old one in `<body hx-headers>`. The login page
also clears htmx's `htmx-history-cache` in localStorage, so Back on a shared
device cannot replay a recipe after log-out.

A recipe-scoped view loads its recipe with `owned_recipe(request=..., recipe_id=...)`,
which 404s on another user's recipe as on a missing one, then loads child rows
through that recipe (`Step` with `recipe=recipe`, and so on). Never look a recipe
up by id alone. A recipe in the trash (#75) is missing to `owned_recipe` too, so
it cannot be viewed or edited; the trash's restore and purge views load it with
`trashed_recipe`, which is owner-scoped the same way.

`tests/test_route_access.py` walks the URLconf, so a new route is covered as soon
as it exists: an anonymous request (GET or POST, plain or htmx) must be sent to
the login page unless the route is in its `PUBLIC_ROUTES` allowlist, the set of
`login_not_required` routes must equal that list, and on every route with a
`recipe_id` another user, even staff, must get 404 and write nothing. A new path
parameter needs a value in its `path_values` fixture.
