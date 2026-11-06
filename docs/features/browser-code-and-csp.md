# Browser code, assets and the Content-Security-Policy

Every asset is served by the app itself: pages make no third-party requests. The web fonts (Inconsolata, Lobster) are self-hosted as woff2 under `static/fonts/` with their OFL licences, declared with `font-display: swap` in `css/style.css`, and preloaded from `base.html`. A new font goes the same way, never through a font CDN.

## Browser code and the CSP (#62)

All of the app's JavaScript is one file, `static/js/app.js`, which `base.html`
loads on every page, deferred and after htmx. It is one file rather than one per
page because `hx-boost` swaps `<body>` without touching `<head>`: a script only
some pages load would be missing after a boosted visit. Every listener is
delegated to `document` and does nothing on a page without its markup.
Templates opt in with data attributes, never with inline code:
`data-cancel-draft`, `data-close-panel`, `data-panel-toggle`,
`data-position-in`/`-of`/`-row`, `data-split-at`, `data-indeterminate` and
`data-clear-history` (the header of `app.js` lists what each does).

Django's `ContentSecurityPolicyMiddleware` enforces `SECURE_CSP` (in
`settings/base.py`): everything from `'self'`, no `'unsafe-inline'`, no
`'unsafe-eval'`, no plugins, no `<base>`, forms post only to the app and no page
may be framed. The app renders user-entered HTML on purpose (sanitised to a few
inline tags), so this is defence in depth: injected markup could neither run a
script nor apply a style. In practice that means no template may contain
inline `<script>`, `on*=` handlers, `style=` attributes or `<style>`, and no
`hx-on` or `hx-trigger="event[filter]"`: htmx evals those, and `htmx-config`
sets `allowEval: false` (use the `target:<selector>` trigger modifier instead
of a filter). `htmx-config` also sets `includeIndicatorStyles: false`, since
htmx would otherwise inject a `<style>`. `tests/test_content_security_policy.py`
checks every template and inline SVG icon for all of these. Django's admin tags
its few inline blocks with a per-request nonce (`CSP.NONCE`, via the `csp`
context processor); the nonce only appears in the header on pages that use one.
With `DEBUG=True`, django-htmx's error page for a failed htmx request shows
unstyled, because its inline CSS and scripts are blocked; a full-page error is
exempt (Django turns the CSP off for its own debug pages).
