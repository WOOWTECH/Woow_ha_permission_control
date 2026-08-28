# A frontend asset carries its cache buster onto what it pulls in

> **Still live**, with a narrower scope after
> [ADR-0011](0011-the-panel-decision-moves-into-the-backend.md). The Filters
> this rule was written for are deleted by #20, but the two panels still
> import `lit.js` and `tests/frontend_assets.test.mjs` still holds the rule.
> Read it as being about those files.

Issue #9: every asset the integration *registers* carried `?v={PANEL_VERSION}`;
every asset an asset *imports* carried nothing. Six specifiers, across five
files, reached `permission_policy.js`, `shadow_dom.js` and `lit.js` with no
version at all.

That gap is not cosmetic, because of where the code sits. Both Filters live
inside the modules with no buster. A browser holding a stale — or, mid-upgrade,
a missing — `permission_policy.js` while loading a fresh
`ha_sidebar_filter.js?v=…` evaluates neither module, so nothing filters and a
non-admin sees every panel and no Access Denied overlay. Of the ways this
integration can break, that is the worst direction: it fails open.

The issue said this had not been reproduced on a live instance. It has now, on
192.168.2.6 (HA 2026.7.2), by `tests/verify_issue_9.py`. Two measurements
matter. First, every asset under `/ha_permission_manager_frontend/` is served
with **no `Cache-Control` header at all** — only an `ETag` — so what a browser
keeps is entirely up to its own heuristics. Second, with one older
`permission_policy.js` served at the unversioned URL v2.0.3 asks for, the
non-admin's `hass.panels` went from 5 panels to 28. Twenty-three panels the
Filter should have hidden were offered, no Access Denied overlay appeared, and
the only trace was one line in the console. Silent, and open.

## The decision

**`PANEL_VERSION` is the only cache buster, and a module propagates it.**

An import specifier is a string inside a JS file; it cannot read `PANEL_VERSION`
from `const.py`. But Home Assistant registers each entry point *with* the
version, so the specifier does not need to know the version — it needs to know
the query its own URL already has:

```js
/** This module's cache buster, carried onto everything it pulls in (ADR-0006). */
const ASSET_VERSION_QUERY = new URL(import.meta.url).search;

const { isPermitted } = await import(`./permission_policy.js${ASSET_VERSION_QUERY}`);
```

The name says *query*, not *version*, because that is what it holds: the whole
`?v=2.0.4`, question mark included. One bump of `PANEL_VERSION` in `const.py`
then moves the entry point and everything it reaches, in one step, with nothing
to remember. Two entry points that pull in the same module at the same version
resolve to the same URL, so they still share one instance of it.

`tests/frontend_assets.test.mjs` is the check the issue asked for, and
`.github/workflows/tests.yml` is what runs it. It reads `__init__.py` and every
`frontend/*.js` as text and fails when: a registration is not of the form
`f"{FRONTEND_URL_BASE}/<name>.js?v={PANEL_VERSION}"` — including one written as
a bare literal URL, which is how this would most plausibly come back; a
registration names a file `frontend/` does not hold; a first-party specifier
lacks `${ASSET_VERSION_QUERY}`; a module that uses the buster does not declare
it exactly once, in the one spelling above; a module in `frontend/` is reached
by neither a registration nor another module; or `manifest.json` and `const.py`
disagree about the version. The rule holds because a test holds it, not because
a release step is followed.

## What was rejected

**Registering `permission_policy.js` with `add_extra_js_url` too.** That serves
it at `…/permission_policy.js?v=2.0.4`, which is a *different* URL from the
`./permission_policy.js` an importer asks for — a second fetch, a second module
instance, and the importer's copy still unbusted. It looks like a fix and is
not one.

**Cache headers that force revalidation, so the version query stops being
load-bearing.** This is the stronger fix, and it covers assets nobody
remembered to bust. It is not taken here because Home Assistant's
`StaticPathConfig` offers only "cache hard" or "no header at all"; getting
`Cache-Control: no-cache` means registering a custom static resource on
`hass.http.app.router`, which is Home Assistant internals, and which none of
this repo's tests — all of which run without Home Assistant installed — could
cover. Worth revisiting if the propagation rule is ever found leaking.

## Where the rule can still fail quietly

`new URL(import.meta.url).search` is `""` for a module served without a query,
and then every specifier it propagates onto is byte-identical to the unbusted
one this decision exists to remove. It degrades to the old behaviour rather
than to something worse, but it degrades *silently*, which is the property
issue #9 is actually about.

The guard against it is at the registration end, where the empty query would
have to originate: the test above rejects any registration without
`?v={PANEL_VERSION}`. On top of that, the two Filters — and only the two
Filters — warn on the console when their own query is empty, following ADR-0005's
rule that a Filter which cannot do its job says so. The panels are left silent
deliberately: a panel that fails to load is a blank page somebody reports,
whereas an unfiltered sidebar is a page that looks entirely normal.

## What this costs

A static `import` is fetched by the browser's preload scanner, in parallel with
the module that declares it. A dynamic `import()` is fetched when execution
reaches it, so the dependency now costs one serial round trip. On the local
network these integrations run on, that is milliseconds.

It is not, however, milliseconds of *unprotected* page: `ha_sidebar_filter.js`
now raises its loading overlay above the import rather than below it. A static
import already delayed the whole module body until the dependency resolved, so
the overlay went up no earlier before this change than it does now.

Two assets also move from "never cached" to "cached until the next release":
`sidebar-title.js`, which was busted with a restart timestamp, and
`ha_access_denied.js`, which the sidebar filter fetched with `Date.now()`.
Neither was ever a fail-open risk — a query that always changes is always
fresh. They change because a version query that says which release a browser is
running is worth more than a re-download per restart, and because one rule with
two exceptions is a rule nobody can check.

## What this decision does not cover

**The Filters still fail open.** This decision removes one way the modules can
fail to evaluate; it does not change what happens when they do. Serving the same
broken module at the URL v2.0.4 *does* ask for — a syntax error, a bad deploy, a
fetch the browser refuses, none of which a cache buster can prevent — still
leaks the same 23 panels into `hass.panels`.

What did change, and only as a side effect: the page is now covered while that
happens. Moving the loading overlay above the import means a failed import
leaves the overlay up, measured at `opacity: 1`, because the code that removes
it is inside the module that never ran. So the failure went from invisible to a
page nobody can use. That is better than silence and it is not fail-closed —
the panels are still there, behind the overlay, for anything that reads
`hass.panels` rather than the screen. Do not mistake the overlay for the
sentinel.

Issue #9 raises the real question separately and it is still open: a small
always-loaded classic script that hides the sidebar until a module reports
itself alive. Until that exists, the buster is a way of making the failure
rarer, not a way of making it safe.
