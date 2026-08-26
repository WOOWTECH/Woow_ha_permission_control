# One place owns a panel being hidden, and the anchor follows the route

Issue #6, against the routing anchor v2.0.1 added in `822b6ed`. `filterPanels()`
keeps the panel Home Assistant is routing to in `hass.panels` as a hidden
anchor, so the router always has a route for the current URL and never throws
reading `.url_path` off a panel that filtering removed. Two separate things
stopped the anchor holding, and both are adapter wiring around a decision the
policy module had already made correctly.

## The hiding had three owners

The anchor is hidden by having **no title** — `PanelInfo` carries no field for
hiding a panel, and Home Assistant's sidebar drops a panel whose `title` is
falsy unless it is that user's own default. So `title: null` was the whole of
the mechanism, and `show_in_sidebar: false` alongside it was a belief about
Home Assistant that was never true. (It is still set. Two releases have shipped
it, nothing reads it, and removing it changes a serialised map for no gain.)

Two other places in this integration write titles onto panels by id, and the
ids they name are `ha_permission_manager` and `ha-control-panel` — this repo's
own two panels, and therefore two of the panels most likely to be the one a
denied non-admin is anchored to:

- `updateSidebarTitleViaHass()` in `ha_sidebar_filter.js`, called by `init()`
  immediately after `applySidebarFilter()`.
- `frontend/sidebar-title.js`, on a timer, in place on the panel object.

So a non-admin with `ha-control-panel` Closed, loading `/ha-control-panel` with
nowhere permitted to be redirected to, got the panel anchored, its title
restored on the same page load, and a clickable sidebar entry for a panel they
were denied — underneath the Access Denied Filter.

**The decision: `permission_policy.js` owns "this panel is hidden", and every
place that is about to write a panel title asks it first.** The answer is a
mark on the anchor object, read back through `isAnchoredPanel()`.

The mark is a **non-enumerable** `Symbol.for` key, for the reasons ADR-0007
gives for the filtered-map mark: Home Assistant enumerates a panel's keys and
serialises it, and `panelsEqual()` compares the serialised maps, so a mark
either of them could see would make every re-filter look like a change.

`Symbol.for` rather than an exported object identity, because `sidebar-title.js`
is a **classic script** — `add_extra_js_url` loads it as one, and it cannot
import an ES module. The global symbol registry is the contract between the two
files, and `tests/routing_anchor.test.mjs` holds the string to being spelt in
exactly those two.

The alternative was the rule "never title a panel whose title is null". It is
one line and needs no mark. Rejected because it is a coincidence rather than a
statement: it happens to be true only because both panels are registered with a
`sidebar_title`, and it says nothing about *why* this particular null is not to
be filled in. A mark says what it means, and it is what a reader of either title
writer now finds.

## The anchor named the panel the document loaded with

`applySidebarFilter()` reads `window.location.pathname` when it runs, and the
navigation hooks — `popstate`, a document `click` handler and a `pushState`
wrapper — called only `checkCurrentPanelAccess()`. So after any client-side
navigation the anchor still named the panel the document had loaded with, and
the newly routed denied panel was absent from `hass.panels`: exactly the
missing-route condition the anchor exists to prevent.

**The decision: a route change recomputes the panel map, not only the access
check.** The hooks now report to `onRouteChanged()`, which does both.

Replacing `hass.panels` mid-route is the rebuild that makes Home Assistant's
router read `route.path` off undefined, which is why `applyPanels()` skips a map
that says the same thing as the one already there. Doing it from these hooks is
safe for the same reason it is late: `installNavigationHooks()` reports a
navigation after `ROUTER_SETTLE_MS`, by which time the router has landed.

`onRouteChanged()` fetches permissions **once** and hands the result to both
halves. Each fetching for itself would have doubled what a navigation costs, on
hooks that fire on every in-page link — the shape of the defect ADR-0007 records
under the nested `pushState` wrappers.

### This repairs the route; it does not get there first

The hooks report a navigation that has **already happened**. The `pushState`
wrapper calls Home Assistant's own `pushState` first and schedules the report
after it, and `popstate` fires once the URL has changed;
`tests/filter_lifecycle.test.mjs` pins that ordering. Home Assistant therefore
routes against the map as it was, and the anchor goes back a settle delay and
one `get_panel_permissions` round trip later.

So what issue #6 describes as "the missing-route condition the anchor exists to
prevent" is still entered on every client-side navigation into a denied panel.
What changes is that it is now left: before this, the map stayed wrong until the
next full page load. Whatever Home Assistant does with an unresolvable route —
on 192.168.2.6 it rendered `notfound`, per ADR-0005 — it now does briefly rather
than for the rest of the session.

Closing the window means filtering **before** the navigation: recomputing off
permissions already held, synchronously, inside the `pushState` wrapper ahead of
the call through. That is a different change — it needs a pre-navigation hook
`installNavigationHooks()` does not have, it must work from cached permissions
rather than a fetch, and `popstate` has no "before" at all, so the back button
would keep the window regardless. It is not what issue #6 asked for; that issue
asks to "recompute the anchor when the route changes — call
`applySidebarFilter()` … from the same three hooks", which is what this is.

The residual window is worth measuring on a live instance before it is worth
closing. Whether it is visible at all depends on what Home Assistant renders in
those few hundred milliseconds, and neither mechanism in issue #6 has been
observed in a browser yet.

### Two things about `applyPanels()` that this leans on

`updateSidebarTitleViaHass()` now goes through `applyPanels()` instead of
assigning `hass` itself, and has dropped its own per-panel "did the title
change" check. `applyPanels()` subsumes that check — `panelsEqual()` compares
the whole map — so the behaviour is the same, and going through it is what makes
the map it produces carry ADR-0007's mark. That trades one risk for another: the
old code put an **unmarked** map on `hass`, so a later reset could rebaseline
from a filtered map; the new code marks a map derived from whatever `hass` held,
so if that was Home Assistant's own unfiltered map, a later baseline read is
refused. ADR-0007 is explicit that those two are not equal in cost —
contamination survives until a full page reload, a refusal costs a warning and
keeps the baseline already held — so the new side is the right one to be wrong
on.

`applyPanels()` skips assigning when the maps are content-equal, and the anchor
mark is deliberately invisible to `panelsEqual()`. So a freshly-marked map is
**not** put on `hass` when an unmarked map with the same contents is already
there, and the anchor the title writers then read would carry no mark. Nothing
reaches that state today: the mark is lost only by a panel-level copy, the one
panel-level copy that exists (`{ ...panel, title }`) now skips anchors, and every
map-level copy — Home Assistant's, `sidebar-title.js`'s, this file's — carries
the panel objects by reference. It is an unenforced premise rather than a live
defect, and it is recorded here because the guard reads as if it were enforced.

## What was fixed alongside, and why here

`sidebar-title.js` replaces `hass.panels` with `Object.assign({}, panels)`,
because `ha-sidebar` memoises on the identity of that map. `Object.assign` copies
own **enumerable** properties, and ADR-0007's filtered mark is deliberately
neither enumerable nor a string key — so the copy stripped it, and the sidebar
filter was then free to re-read its unfiltered baseline out of a map it had
produced itself. That is ADR-0007's contamination, reintroduced from a file that
decision does not cover. The copy now carries the mark on.

This is not part of issue #6. It is three lines inside the block this change was
already rewriting, in a file this change was already teaching to recognise the
integration's own marks, so it is fixed and named here rather than left for a
reader to rediscover.

## What this does not answer

**ADR-0005's deferred DOM walks are still deferred, and this is the pass it
named.** That decision says the walks in `ha_sidebar_filter.js` "belong in that
pass, not this one", meaning the issue-#6 pass — and this change does edit
`updateSidebarTitle()`, one of the functions whose body is a spelt-out walk. It
inserts one question into it and converts nothing.

The deferral has not been dropped, it has moved somewhere it can be seen: issue
#11 was opened the day after ADR-0005 was written, names every walk in both
files including this one, and records that all of them were measured working on
HA 2026.7.2. Converting them is a behaviour-risk refactor against no present
defect; issue #6 is a defect fix. Putting the two in one commit means neither
can be reverted without the other, and a live verification of the anchor would
be verifying the walks at the same time. So the rule ADR-0005 states still has
one of three Filters following it, and #11 is what closes that gap.

**Three modules now hand-roll the same non-enumerable mark.** `anchorPanel()`
here, `markFiltered()` in `filter_lifecycle.js`, and `copyPanels()` in
`sidebar-title.js` each spell the same `Object.defineProperty` shape. Sharing it
would mean this module — pure by definition, and importing nothing — taking a
dependency on the lifecycle adapter, and it would not reach `sidebar-title.js`
at all, which cannot import either of them. Three spellings of four lines is the
cheaper of the two prices.

**`sidebar-title.js` should probably not exist.** It duplicates
`updateSidebarTitleViaHass()` — the same two panel ids, the same translations,
the same map replacement — and the duplication is what made one missing
question a defect in two places. Folding it into the sidebar filter is the real
"one owner" answer for titles, and it is a larger change: an asset registered in
`__init__.py`, with its own retry and polling schedule. Not done here.

**ADR-0005's second case is now worth re-measuring.** That decision keeps the
lovelace filter partly on the strength of a client-side navigation into a denied
dashboard, and records that the case could not be reached on 192.168.2.6 because
the stale anchor sent the router to `notfound` first. With the anchor recomputed
that obstacle is gone, and whether the case is reachable is an open question
again — ADR-0005 says so itself.

**Neither mechanism was reproduced on a live instance before being fixed.** The
issue is explicit that both were read off the code. What a browser does with
either is what a verification run has to answer.

## Tests

The mark is a pure-function concern and is tested as one in
`tests/permission_policy.test.mjs`: an anchor says it is one, a panel the user
has a View level on does not, and the mark is invisible to `Object.keys`, to
`Object.getOwnPropertyNames` and to `JSON.stringify`.

Two facts behind Mechanism B are behavioural rather than textual, and are tested
as such. `tests/permission_policy.test.mjs` shows *why* a route change must
re-filter: the map built at one path holds no route for another, so a navigation
is a real change to `hass.panels` rather than a no-op `applyPanels()` would skip.
`tests/filter_lifecycle.test.mjs` shows *what the hooks can do about it*: a
navigation is reported only after it has happened, which is the whole of the
residual window above.

The rest of the wiring is not reachable without a browser and a Home Assistant, so
`tests/routing_anchor.test.mjs` holds it as source-text invariants, in the idiom
`tests/frontend_assets.test.mjs` established and ADR-0007 reuses: every title
writer asks `isAnchoredPanel()`, `sidebar-title.js` spells the symbol the way the
policy does, the anchor string appears in exactly two files, the navigation hooks
reach `applySidebarFilter()`, a route change costs one permission round trip, and
nothing outside `applyPanels()` puts a panel map on `hass`. Each was checked by
breaking it.

Those tests prove the wiring is *spelt*. They cannot prove it works.
