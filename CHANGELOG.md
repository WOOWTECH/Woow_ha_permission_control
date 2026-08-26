# Changelog

## v2.0.7 — 2026-08-26

### Fixed

- **The loading overlay could strand an administrator on every page, with no
  timeout.** `ha_sidebar_filter.js` puts an opaque, full-viewport,
  click-swallowing overlay up synchronously above its own imports, and the only
  code that takes it down is at the end of `init()` — past both dynamic imports,
  a permissions fetch, a filter application and five subscriptions. Anything
  that throws on that path left the overlay up for the life of the page.
  Because it goes up before anyone knows who the user is, that covered
  administrators too, including on the Permission Manager panel — the one screen
  that could fix whatever caused it. Recovery was a hard reload with a cleared
  cache, or SSH. Shipped in v2.0.4 as a side effect of moving the overlay above
  the import while fixing #9.

  An administrator's release now lives in the same synchronous block as the
  overlay: a 100 ms poll for `hass.user`, which the Home Assistant frontend
  populates whether or not this integration's modules ever evaluate. It depends
  on nothing below the imports, and it cannot be missing when the overlay is
  present. An administrator is handed the untouched baseline by
  `applySidebarFilter()` anyway, so there is nothing for them to wait for.
  Reported as issue #15.

  The watch has no deadline — one would be racing a slow-but-healthy load and
  would strand the administrator it exists to free — but after 30 seconds with
  no `hass.user` it says so on the console, once, and keeps watching.

  **A non-admin is left exactly as they are.** What the overlay should do for
  them when the Filter never reports is issue #12's question, and answering it
  here by accident is how the current behaviour arrived.

### Added

- `docs/adr/0009` records why the release sits above the imports rather than
  anywhere more convenient, why the CSS deadman issue #15 also offers was
  rejected — the timeout it needs is longer than the slowest healthy load, and
  what it would then do to a non-admin is #12's decision — and why the removal
  is outright rather than faded.

- `tests/loading_overlay.test.mjs` slices the overlay block out of the shipped
  file and evaluates it against a fake document, because that region cannot be
  imported: it is the top of a module whose next statement is a top-level
  `await import()`. Source-text invariants in the idiom of
  `tests/frontend_assets.test.mjs` hold the two placement rules — all of it
  above the first `await import(`, and no call to `removeLoadingOverlay()`.

## v2.0.6 — 2026-08-26

### Fixed

- **The routing anchor's hiding was undone on the same page load that applied
  it.** `filterPanels()` keeps the panel Home Assistant is routing to in
  `hass.panels` as a hidden anchor, and the hiding is that the anchor has no
  title — `PanelInfo` carries no field for hiding a panel, and the sidebar drops
  one whose title is missing. Two other places in this integration write titles
  onto panels by id, and the ids they name are this repo's own two panels:
  `updateSidebarTitleViaHass()`, called by `init()` immediately after the
  filtering, and `frontend/sidebar-title.js`, on a timer. So a non-admin with
  Control Panel Closed, loading `/ha-control-panel` with nowhere permitted to be
  sent, got a clickable sidebar entry for a panel they were denied, underneath
  the Access Denied Filter. `permission_policy.js` now marks an anchor and both
  writers ask before they write. Reported as issue #6, Mechanism A.

- **The anchor named the panel the document loaded with, and was never
  recomputed.** The navigation hooks re-checked access after a client-side route
  change but did not re-filter, so after any navigation the anchor still named
  the panel the page had loaded with and the newly routed denied panel was the
  one missing from `hass.panels` — the missing-route condition the anchor exists
  to prevent, reachable by the back button, an in-card link or Home Assistant's
  own `navigate()`. A route change now recomputes the map against the URL as it
  then is. Issue #6, Mechanism B.

  **This repairs the route rather than getting there first.** The hooks report a
  navigation that has already happened — the `pushState` wrapper calls Home
  Assistant's own `pushState` before scheduling the report, and `popstate` fires
  after the URL has changed — so Home Assistant still routes against the stale
  map and the anchor goes back a settle delay and one round trip later. What
  changes is that the map is wrong for a few hundred milliseconds instead of
  until the next full page load. `docs/adr/0008` records what closing that
  window would take and why it is not this change.

- **A route change costs one permission round trip, not two.** Recomputing the
  map and re-checking access each needed `get_panel_permissions`; one fetch now
  feeds both, on hooks that fire on every in-page link.

- **`updateSidebarTitleViaHass()` put an unmarked panel map on `hass`.** It
  assigned `hass` itself rather than going through `applyPanels()`, so the map
  it left there carried neither ADR-0007's mark nor the equality check. It now
  goes through `applyPanels()` like every other write.

- **`sidebar-title.js` stripped the mark that says a panel map is filtered.** It
  replaces `hass.panels` with an `Object.assign` copy, because `ha-sidebar`
  memoises on the identity of that map, and `Object.assign` copies own
  enumerable properties while ADR-0007's mark is deliberately neither enumerable
  nor a string key. The sidebar filter was therefore free to re-read its
  unfiltered baseline out of a map it had produced itself — ADR-0007's
  contamination, reintroduced from a file that decision does not cover. Not part
  of issue #6; found and fixed in the block this change was already rewriting.

### Added

- `docs/adr/0008` records why "this panel is hidden" gets one owner, why the
  mark is a non-enumerable `Symbol.for` key rather than an exported identity
  (`sidebar-title.js` is a classic script and cannot import an ES module), and
  why recomputing the map from the navigation hooks does not reintroduce the
  mid-route rebuild issue #4 was about. It also names what it does not answer:
  `sidebar-title.js` duplicates the sidebar filter's own title code and should
  probably not exist, and ADR-0005's second case is worth re-measuring now that
  the obstacle hiding it is gone.

- `tests/routing_anchor.test.mjs` holds the wiring as source-text invariants,
  since reaching it needs a browser: every title writer asks `isAnchoredPanel()`,
  `sidebar-title.js` spells the symbol the way the policy does, the string
  appears in exactly two files, the navigation hooks reach
  `applySidebarFilter()`, a route change costs one fetch, and nothing outside
  `applyPanels()` puts a panel map on `hass`. Each was checked by breaking it.
  The mark itself is a pure-function concern and is tested as one in
  `tests/permission_policy.test.mjs`.

### Verified

Deployed to 192.168.2.6 (HA 2026.7.2), restarted, and driven as the non-admin
with the Control Panel Closed and no permitted redirect destination — the
scenario issue #6 describes. `tests/verify_issue_6.py` watches the anchor's
title over nine seconds rather than reading it once, because the defect is a
*later* write undoing an earlier one. Read-only: the permission store was
byte-identical before and after (`8c76507b…`), and the one Permission level the
run needed was set and restored through the service API.

- **Mechanism A reproduces on v2.0.5 and stops on v2.0.6.** On v2.0.5 the
  anchor's title is `"控制面板"` from +13 ms and stays that way. On v2.0.6 it is
  `null` across all 18 samples, with the anchor mark present throughout.

- **Mechanism A's reported impact does not reproduce, on this Home Assistant.**
  The issue predicts "a clickable sidebar entry for a panel they are denied".
  There is none, on either release — because `show_in_sidebar: false` hides the
  panel by itself. `tests/probe_show_in_sidebar.py` establishes that by flipping
  one field at a time on a permitted panel: the row goes when the field is set,
  comes back when it is restored, and goes again when the title is nulled
  instead. Issue #6's premise that "`PanelInfo` has no `show_in_sidebar` field"
  is wrong for HA 2026.7.2, so the anchor was hidden by one layer while the
  other was being undone.

- **Mechanism B is not fixed.** Navigating client-side from a denied
  `/ha-control-panel` to a denied `/config`, Home Assistant rewrites the URL to
  `/notfound/0` before the navigation hooks fire — so the recompute reads
  `notfound`, which is exempt, and anchors nothing. The route for `config` is
  absent on v2.0.6 exactly as on v2.0.5. What did change: the stale anchor for
  the panel the document loaded with is now dropped. `docs/adr/0008` records the
  measurement and what closing the window would take.

- **Console errors are unchanged at 1**, the v2.0.5+ baseline.

### Found while verifying, not fixed here

Measured while Home Assistant was still finishing its startup, the non-admin's
`hass.panels` held all **28** of the instance's panels instead of the filtered
4, with the full sidebar rendered. Home Assistant had replaced the map wholesale
and nothing put the filtering back. That is issue #12 — "the Filters fail open"
— caught in the act, it predates this change, and it is more serious than either
mechanism above.

## v2.0.5 — 2026-08-26

### Fixed

- **The sidebar filter registered everything a second time when it
  re-initialised.** Home Assistant replaces its `home-assistant` element on
  logout/login, the Filter watches for that and re-initialises, and
  re-initialisation added five WebSocket subscriptions, two DOM listeners and a
  wrapper around `history.pushState` on top of the ones the previous run had
  left in place — once per re-initialisation, for the life of the tab. There was
  no unsubscribe and no `removeEventListener` anywhere in the file. The
  subscriptions are now held and released before the next run subscribes, and
  the navigation hooks are installed once on `window`, `document` and `history`,
  none of which a re-initialisation replaces. Reported as issue #5, split out of
  #4.

- **Each re-initialisation made one navigation cost another permission round
  trip.** The `pushState` wrapper captured whatever `history.pushState` was at
  the time, which on the second run is the first wrapper, so the wrappers nested
  rather than replaced. After N re-initialisations a single client-side
  navigation scheduled N `checkCurrentPanelAccess()` calls, each with its own
  `get_panel_permissions` request. The hook is now installed once per document,
  however many times it is asked for.

- **A reset re-read the unfiltered baseline from the filtered map.**
  `resetState()` dropped the baseline and `storeOriginalPanels()` re-derived it
  from `hass.panels`, which by then is the map this integration produced. Every
  panel the user had no View level on was missing from the baseline for the rest
  of the session, so granting a Permission level afterwards could not bring the
  panel back without a full page reload. Maps this integration puts on `hass` are
  now marked, a baseline is never read from a marked one, and a reset asks for a
  fresh baseline rather than throwing away the one it has — so a dashboard added
  while the tab was logged out is still picked up.

### Added

- `frontend/filter_lifecycle.js` holds the three answers above, and
  `tests/filter_lifecycle.test.mjs` drives them: a fake `hass.connection` counts
  what stays live across a subscribe → release → subscribe cycle, a fake
  `history` counts how many wrappers one `pushState` runs, and the baseline
  rules are checked against a marked map. The mark is non-enumerable, because
  object spread copies enumerable symbol keys and an inherited mark would lock
  the baseline out for good.

- The sidebar filter's own wiring is held as source-text invariants in the same
  file, since reaching that code needs a browser: every `subscribeEvents` call
  is held, `resetState()` releases them, and the file hooks no navigation of its
  own. Each was checked by breaking it.

- `docs/adr/0007` records why the three registrations get three different
  answers, and why the other two Filters are left alone: `ha_lovelace_filter.js`
  never re-initialises, so it has nothing to accumulate on. It notes the other
  side of that coin as a separate, unmeasured question — after a logout it is
  still holding a subscription made on the closed connection, and it will not
  make another.

### Verified

Deployed to 192.168.2.6 (HA 2026.7.2), restarted, and driven as both identities.
`tests/verify_issue_5.py` wraps `hass.connection.subscribeEvents` before the
Filter runs, so it watches the Filter make its own subscriptions rather than
inferring them, and counts the 150 ms checks one `history.pushState` schedules.
Only the re-initialisation is simulated: a second `home-assistant` element
inserted ahead of the first, which is the condition the Filter's own
MutationObserver watches for. Read-only — the permission store was byte-identical
before and after.

- **The accumulation reproduces on v2.0.4 and stops on v2.0.5.** After one
  re-initialisation, v2.0.4 held **2 live subscriptions** each of
  `user_updated`, `homeassistant_auth_updated` and `lovelace_updated`, and one
  `pushState` cost **2** checks and 2 `get_panel_permissions` round trips.
  v2.0.5 holds **1 of each** and costs **1** check, with one `released`
  recorded per event type — the unsubscribe that never used to happen.

- **Four of the five subscriptions never worked for a non-admin.** Home
  Assistant refuses a non-admin's `subscribe_events` for `user_updated`,
  `homeassistant_auth_updated` and `permission_manager_updated`; only
  `lovelace_updated` and `core_config_updated` are accepted. Those rejections
  are the four `Unauthorized` console errors this instance shows on every
  non-admin page. Holding a subscription means catching them, so v2.0.5 drops
  that count from 4 to 1 — the one left belongs to the lovelace filter, which
  has no teardown. The dead subscriptions are a defect of their own and are not
  fixed here.

- **Revoking a Permission through a service fires no event.**
  `set_permission` and `bulk_set_permissions` both fire
  `permission_manager_updated`, but `remove_user_permissions` and
  `remove_resource_permissions` are silent — measured by listening on an admin
  page while calling each. Revocation is the direction where a live page
  matters most. Found while looking for a way to drive the subscriptions; not
  fixed here.


## v2.0.4 — 2026-08-25

### Fixed

- **The modules holding the Filters had no cache buster, and a stale copy
  failed open.** Every asset the integration registers carried
  `?v={PANEL_VERSION}`; every asset one of those then imported carried nothing.
  Six specifiers across five files reached `permission_policy.js`,
  `shadow_dom.js` and `lit.js` unversioned, and the frontend directory is served
  with no cache headers, so browsers cached them heuristically. A browser
  holding a stale — or, mid-upgrade, a missing — `permission_policy.js` while
  loading a fresh `ha_sidebar_filter.js?v=…` evaluates neither module. Both
  Filters live inside those modules, so nothing filters: a non-admin sees every
  panel in the sidebar and no Access Denied overlay. Each module now reads the
  version query off its own URL and carries it onto everything it pulls in, so
  one bump of `PANEL_VERSION` moves the whole graph at once. Reported as issue
  #9, found by a code review of `822b6ed..3e2e1d2`.

- **A Filter served without a version query said nothing about it.** The
  propagation above yields an empty query for a module loaded without one, and
  every specifier then reverts to exactly the unbusted form this release
  removes — silently, which is the property the issue is about. The two Filters
  now warn on the console in that case, following ADR-0005's rule that a Filter
  which cannot do its job says so. The panels stay silent on purpose: a panel
  that fails to load is a blank page somebody reports, an unfiltered sidebar is
  a page that looks entirely normal.

### Changed

- **`sidebar-title.js` and the Access Denied Filter are now cached like
  everything else.** `sidebar-title.js` was busted with a restart timestamp and
  `ha_access_denied.js` was fetched with `Date.now()`, so both were re-downloaded
  constantly and neither version query said anything about which release a
  browser was running. Neither was a fail-open risk — a query that always
  changes is always fresh — so this is a trade, not a fix: they move from "never
  cached" to "cached until the next release", in exchange for one rule with no
  exceptions left to check.

- `ha_sidebar_filter.js` raises its loading overlay above the import rather than
  below it. Its own comment says the overlay "must execute synchronously before
  any async work", and pulling in the policy module is now the first async work
  the file does.

- `docs/adr/0006` records the rule, what it costs, and where it can still fail
  quietly. Rejected: the issue's suggestion of registering `permission_policy.js`
  through `add_extra_js_url` as well — that serves it at a different URL from the
  one importers ask for, leaving the importers' copy exactly as unbusted as
  before. Also rejected, but on cost rather than correctness: cache headers that
  force revalidation, which would make the version query stop being load-bearing.

### Added

- `tests/frontend_assets.test.mjs` — the release check the issue asked for. It
  reads `__init__.py` and every `frontend/*.js` as text and fails on a
  registration that is not busted by `PANEL_VERSION` (including one written as a
  bare literal URL), a registration naming a file `frontend/` does not hold, a
  first-party specifier without the propagated buster, a module in `frontend/`
  that nothing reaches, and `manifest.json` and `const.py` disagreeing about the
  version.

- `.github/workflows/tests.yml` — the release step that check is attached to.
  Runs the offline suites on every push and pull request: `node --test
  tests/*.test.mjs` and `python -m pytest tests/test_panel_policy.py`. The
  live-instance suites are deliberately not in it; they need a Home Assistant to
  point at.

- `tests/verify_issue_9.py` — drives a real browser against a running instance
  and makes the version skew happen on purpose, by serving an older
  `permission_policy.js` at the unversioned URL a release asks for. Read-only;
  it never writes a Permission.

### Verified

Deployed to 192.168.2.6 (HA 2026.7.2), restarted, and driven as both identities.

- **The defect reproduces, which it never had before.** On v2.0.3, with one
  older `permission_policy.js` served at the unversioned URL, the non-admin's
  `hass.panels` went from 5 panels to 28. Twenty-three panels the Filter should
  have hidden were offered, no Access Denied overlay appeared, and the only
  trace was one console line. Silent, and open.
- **Every asset is served with no `Cache-Control` header at all** — only an
  `ETag`. What a browser keeps is entirely up to its own heuristics, so the
  version query was the only thing standing between a release and a stale
  module. That was argued from the code before; it is measured now.
- **On v2.0.4 the same stale copy is never fetched.** The Filters ask for
  `permission_policy.js?v=2.0.4`, so the copy sitting at the unversioned URL is
  a cache entry nothing consults. Panels back to 5, Access Denied present.
- **The three registered assets are injected as `?v=2.0.4`**, `sidebar-title.js`
  included, which is the timestamp change taking effect.
- **No regression.** `tests/verify_issue_10.py` reports the same behaviour as
  v2.0.3: the denied Dashboard hidden, exactly one message, no stuck overlay,
  zero console errors as admin. Both panels render after their `lit.js` import
  moved from static to dynamic, with no module or Lit errors.

### Still open

- **The Filters fail open.** Serving the same broken module at the URL v2.0.4
  *does* ask for still leaks the same 23 panels — measured, not argued. No cache
  buster can prevent that. The page is now covered while it happens, because a
  failed import leaves the loading overlay up at `opacity: 1`, so the failure is
  a page nobody can use rather than a page that looks normal. That is a side
  effect of moving the overlay, not a sentinel, and it is not fail-closed.
  Issue #9 raises the real question as a separate decision.

## v2.0.3 — 2026-08-25

### Fixed

- **The lovelace filter could never hide the default dashboard.** It walked a
  spelt-out path through Home Assistant's element hierarchy that ended at
  `ha-panel-lovelace`. On HA 2026.7.2 the default dashboard renders under
  `ha-panel-home`, and `partial-panel-resolver` has no shadow root at all, so
  the walk returned early — silently, without a log or a counter. It also only
  ran on `/` and `/lovelace*`, and the default dashboard is served at `/home`.
  Two hard-coded pieces of Home Assistant's vocabulary, each enough on its own
  to stop the Filter dead. The Filter now searches the shadow tree for the
  dashboard element instead of naming the way to it, and runs on every path.

- **A decision to hide that hid nothing said nothing.** Every `return` on the
  old traversal was silent, which is why this went unnoticed for a release.
  When the Permission store says hide and no dashboard element is found, the
  Filter now warns on the console, naming the path and what it looked for —
  once per path, and only after a grace period, so a dashboard that has not
  rendered yet is not reported as a missing one.

- **The "no access" message reached Home Assistant's own 404 page.** Running on
  every path took the lovelace filter to `notfound`, which is where Home
  Assistant lands a browser that asks for a panel this user's filtered
  `hass.panels` no longer holds. `isExemptPanel()` already says such a page
  carries no Permission; `shouldShowDashboard()` now agrees with it. Found by
  running the Filter against the live instance, not by reading it.

- **Two "no access" messages would have stacked.** Fixing the actuation above
  made the lovelace filter's centred message run on the default dashboard for
  the first time — on top of the Access Denied Filter, which already replaces
  the page. The message is now shown only where that overlay is absent, which
  is the case it exists for: a client-side navigation into a denied dashboard,
  where the overlay's check never re-runs.

### Changed

- The Filter hides the dashboard element itself rather than reaching inside it
  for `#view` and `.toolbar`. Those ids are Home Assistant's internals in
  exactly the way the traversal was.

- `docs/adr/0005` records the design call the issue asked for: both layers stay,
  because they cover different moments, but finding an element in Home
  Assistant's shadow tree is done one way, and a Filter that decides to act and
  then acts on nothing says so. The sidebar and Access Denied Filters still
  spell out walks of their own; those walks work on 2026.7.2 and converting
  them belongs with issue #6, which already owns those files.

- DOM mutations no longer run the filter directly; they schedule it, at most
  once every 150 ms. The search is cheaper than the walk was fragile, but a
  rendered dashboard mutates constantly.

- New `shadow_dom.js` holds the search, `permission_policy.js` gains
  `isDashboardPath`. Both are pure and unit tested offline:
  `node --test tests/shadow_dom.test.mjs` (12 tests) and
  `node --test tests/permission_policy.test.mjs` (38 tests, 9 new). The
  fixtures in the first are the two element hierarchies Home Assistant has
  actually shipped, so one traversal is shown to cover both.

- `tests/verify_issue_10.py` drives a real browser against a running instance,
  once per identity, and asks the page the questions this issue asks. It writes
  no Permission.

### Note on v2.0.2

`7600f14`'s commit message called the pre-2.0.2 blanking regression "observed
rather than argued" on 192.168.2.6. The decision half was measured and is
correct; the consequence half was not observable there, because the traversal
fixed above meant v2.0.1 would have left that dashboard visible too. The v2.0.2
fix stands and is unit tested — only the strength of that one live claim was
overstated.

## v2.0.2 — 2026-08-25

### Fixed

- **The permission matrix still offered the panel v2.0.1 stopped honouring.**
  v2.0.1 taught discovery and `get_panel_permissions` about panels Home
  Assistant registers but never routes to; the matrix built its own panel list
  and learned nothing. An administrator saw the stub `lovelace` toggle, granted
  View on it, and the level saved — then `get_panel_permissions` dropped it. A
  toggle that saves and does nothing is worse than the entry it replaced. The
  matrix now reads the same list everything else honours.

- **`get_all_permissions` and `get_panel_permissions` disagreed.** Only the
  latter dropped unroutable panels, so the two endpoints reported different
  levels for the same stored row. Both now make the same exclusion. The
  Permission store is still left untouched either way.

- **Granting `panel_home` left the dashboard blank.** The lovelace filter looked
  for a permission key equal to or containing `lovelace`, then fell through to
  its fail-secure default. So the migration this changelog documents — grant
  `panel_home` for the default dashboard — hid the very dashboard it granted.
  A dashboard is now governed by the Permission on the panel Home Assistant is
  routing to, resolved the same way the sidebar filter resolves it. This also
  fixes dashboards added by hand: `/dashboard-kitchen` is governed by
  `panel_dashboard-kitchen`, where before no grant could ever reveal it.

### Changed

- The panel decisions shared by discovery and the WebSocket API move into
  `panel_policy.py`, which imports nothing from Home Assistant and is unit
  tested offline: `python -m pytest tests/test_panel_policy.py`. Its frontend
  counterpart `permission_policy.js` gains `shouldShowDashboard`, covered by
  `node --test tests/permission_policy.test.mjs`. Building the panel list in
  two places is what let the matrix drift from what the integration honours;
  there is now one answer to each question.

## v2.0.1 — 2026-08-25

### Fixed

- **A Closed panel could leave the page navigating forever.** v2.0.0 stopped the
  redirect from a denied panel when the destination was denied too, but not when
  Home Assistant did not serve the destination at all. Home Assistant's own
  default dashboard is `home`, and it rewrites `/lovelace` to `/home` on
  instances with no legacy overview — so a user granted `panel_lovelace` was sent
  to `/lovelace`, rerouted to `/home`, denied there, and sent to `/lovelace`
  again: 85 `location.replace()` calls in 25 seconds on the reported instance.
  A redirect destination now has to be a panel Home Assistant actually serves,
  and the redirect is self-limiting — one browsing session issues at most one
  init-time redirect, handed back only once a page settles somewhere permitted.
  No arrangement of Permission levels or dashboard routing can loop.
- **The frontend threw `Cannot read properties of undefined (reading 'url_path')`
  repeatedly** while a non-admin sat on a Closed panel. Filtering the panel out of
  `hass.panels` left Home Assistant's router with no route for the current URL and
  nothing to resolve its default panel to. The panel being routed to now stays in
  the map as an anchor hidden from the sidebar, and Home Assistant's own
  `notfound` panel — which it never lists in the sidebar — is always kept so its
  default-panel lookup has somewhere to land. The Access Denied Filter still
  covers the anchored panel's content, and a user with every panel Closed still
  sees a sidebar with no panels in it.

- **Granting the `lovelace` panel grew a dead sidebar entry.** Home Assistant
  keeps a stub `lovelace` panel on any instance without a legacy overview
  dashboard, and opening it sends the browser straight to `/home`. Discovery
  offered it as a Resource anyway, so an admin who granted View on it gave the
  user a sidebar entry that only ever reached Access Denied. Discovery no longer
  offers a panel Home Assistant will not route to, and `get_panel_permissions`
  no longer reports one. The test is word-for-word Home Assistant's own
  (`component_name == "lovelace"` with no `config.mode`), so the two cannot
  drift. Grant `panel_home` for the default dashboard.

  A level set on such a panel before this release stays in the Permission store
  untouched — it is ignored, not deleted, so it comes back to life if the panel
  ever becomes real.

- **Home Assistant's router could throw `reading 'path'` during a redirect.**
  The Filters replaced `hass.panels` on every permission event, even when the
  result was identical, and a rebuild landing mid-navigation left the router
  reading `route.path` off undefined. The panel map is now replaced only when it
  actually changed.

### Added

- `frontend/permission_policy.js` — the panel-level Permission decisions as pure
  functions, unit tested in `tests/permission_policy.test.mjs`
  (`node --test tests/permission_policy.test.mjs`).

### Known trade-off

Keeping the Closed panel routable means Home Assistant now mounts it and the
Access Denied Filter covers it, where before it was never mounted at all. The
panel's markup is therefore present in the DOM behind the Filter. The Filters
have always been a way to hide what a user has no business seeing, not a
security boundary — Home Assistant's own auth and this integration's backend
are what actually enforce access — but the stable page costs this much.

## v2.0.0 — 2026-08-24

The three integrations in this repo are now one.

### Breaking

- **`ha_area_control` and `ha_label_control` no longer exist.** Both shipped panels
  that `ha_permission_manager`'s Control Panel already replaced. Remove them from
  `custom_components/` and delete their config entries.
- **The `/area-control` and `/label-control` panel URLs are gone.** Everything lives
  in Control Panel (`/ha-control-panel`), which has Areas and Labels as tabs.
  Bookmarks to the old URLs break; no redirect shim is registered.
- **HACS users must re-add this repository.** The domain is deliberately unchanged
  (`ha_permission_manager`), so if you keep `WOOWTECH/hacs-ha_permission_manager`
  as a custom repository HACS will go on serving you v1.0.3. Remove all three
  `WOOWTECH/hacs-*` custom repositories and add
  `WOOWTECH/Woow_ha_permission_control` instead.
- **Frontend assets moved off `/local/`.** They are served from
  `/ha_permission_manager_frontend/` now. This only matters if you referenced those
  URLs yourself.

### Unchanged on purpose

- The domain, the permission store at `.storage/ha_permission_manager`, the config
  entry, and all 14 services. Existing permissions survive the upgrade untouched.
- The WebSocket command names `area_control/*` and `label_control/*`, despite the
  domains being gone. Renaming them is a separate breaking change with its own
  deprecation window — see ADR-0004.

### Fixed

- **A user whose default panel was Closed was locked out of Home Assistant
  entirely.** The sidebar filter redirected away from a denied panel to
  `hass.defaultPanel` without checking whether that panel was permitted either;
  when it was not, the redirect bounced straight back and looped forever, leaving
  a blank page with no way to reach even the panels the user *did* have access
  to. The redirect now only fires when the destination is actually permitted and
  is not the page being left; otherwise the Access Denied page renders, with the
  sidebar intact.

### Changed

- Repo is laid out as a standard HACS integration: `custom_components/ha_permission_manager/`
  plus a root `hacs.json`. The dist-repo mirroring (`hacs-dist.json` and its workflow)
  is deleted — it only existed to satisfy HACS's one-integration-per-repo rule.
- `www/` renamed to `frontend/`; static files are mounted from the package directory
  rather than a hardcoded `config/custom_components/...` path, so the integration
  works wherever it is installed.
- Added `zh-Hans` translations.
- Removed permission levels 2 and 3 from the translations. Only Closed (0) and
  View (1) have ever existed in code.
- Removed the `WS_GET_*` constants, which named WebSocket commands that were never
  registered, and the `AREA_PANEL_*` / `LABEL_PANEL_*` constants.

### Upgrading

1. Delete the **Area Control** and **Label Control** integrations in
   Settings → Devices & Services.
2. Remove `custom_components/ha_area_control/` and `custom_components/ha_label_control/`.
3. Update **Permission Manager** to v2.0.0.
4. Restart Home Assistant. Your permissions are preserved.

## v1.0.3 / v1.0.4 / v2.0.1 — 2026-04

Last release of the three-integration layout. See git history.
