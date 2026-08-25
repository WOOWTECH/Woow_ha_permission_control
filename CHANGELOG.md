# Changelog

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
  `node --test tests/permission_policy.test.mjs` (34 tests, 5 new). The
  fixtures in the first are the two element hierarchies Home Assistant has
  actually shipped, so one traversal is shown to cover both.

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
