# One place owns a panel being hidden, and the anchor follows the route

Issue #6, against the routing anchor v2.0.1 added in `822b6ed`. `filterPanels()`
keeps the panel Home Assistant is routing to in `hass.panels` as a hidden
anchor, so the router always has a route for the current URL and never throws
reading `.url_path` off a panel that filtering removed. Two separate things
stopped the anchor holding, and both are adapter wiring around a decision the
policy module had already made correctly.

## The hiding had three owners

The anchor is hidden **twice**: by having no title, and by `show_in_sidebar:
false`. Issue #6 says the second of those is a belief about Home Assistant that
was never true — "`PanelInfo` has no `show_in_sidebar` field … So `title: null`
is the whole of the hiding."

**Measured on HA 2026.7.2, that is wrong, and it matters.**
`tests/probe_show_in_sidebar.py` flips one field at a time on a panel the user
*is* permitted and watches its sidebar row: `show_in_sidebar: false` removes the
row on its own and restoring the field brings it back, and `title: null` removes
it on its own too. Either layer suffices on this release.

That is why Mechanism A cost nothing a user could see. The title was being
restored — measured, at +13 ms on v2.0.5 — and the sidebar still showed no row
for the denied panel, because the other layer was doing the hiding by itself.
The defect was real and the reported impact was not.

Two other places in this integration write titles onto panels by id, and the
ids they name are `ha_permission_manager` and `ha-control-panel` — this repo's
own two panels, and therefore two of the panels most likely to be the one a
denied non-admin is anchored to:

- `updateSidebarTitleViaHass()` in `ha_sidebar_filter.js`, called by `init()`
  immediately after `applySidebarFilter()`.
- `frontend/sidebar-title.js`, on a timer, in place on the panel object.

So a non-admin with `ha-control-panel` Closed, loading `/ha-control-panel` with
nowhere permitted to be redirected to, got the panel anchored and its title
restored on the same page load. On v2.0.5 that is `title: "控制面板"` from
+13 ms onward; on v2.0.6 it is `null` for the whole nine-second watch. What it
did *not* get, on this Home Assistant, is the sidebar entry the issue predicts —
see above.

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

### This does not restore the route, and cannot — measured

The hooks report a navigation that has **already happened**. The `pushState`
wrapper calls Home Assistant's own `pushState` first and schedules the report
after it, and `popstate` fires once the URL has changed;
`tests/filter_lifecycle.test.mjs` pins that ordering.

The first draft of this decision said the anchor therefore "goes back a settle
delay and one round trip later". **It does not go back at all**, and the
instance is what says so. Navigating client-side from a denied
`/ha-control-panel` to a denied `/config` on 192.168.2.6:

| | v2.0.5 | v2.0.6 |
|---|---|---|
| URL after the navigation | `/notfound/0` | `/notfound/0` |
| route for `config` | absent | **still absent** |
| stale `ha-control-panel` anchor | still there | **dropped** |

Home Assistant does not leave the URL alone. It rewrites it to `/notfound/0`
before the hook fires, and by then `panelIdFromPath()` reads `notfound`, which
`isExemptPanel()` answers for — so the recompute anchors nothing. The
information the anchor needs, *which panel the user asked for*, is gone by the
time this code is allowed to run.

So Mechanism B is **not fixed** in the sense issue #6 asks for. What v2.0.6
actually changes is the other half: the map no longer carries a stale anchor for
the panel the document loaded with. That is worth having — the map stops
asserting a route that is no longer the user's — but it is not "the anchor
follows the route", and the `url_path` crash class the issue is worried about is
reached or not reached exactly as before.

Closing it means filtering **before** the navigation: recomputing off
permissions already held, synchronously, inside the `pushState` wrapper ahead of
the call through, so Home Assistant routes against a map that already holds the
anchor. That needs a pre-navigation hook `installNavigationHooks()` does not
have, and it must work from cached permissions rather than a fetch. `popstate`
has no "before" at all, so the back button keeps the window regardless — which
means even that design closes some of this and not all of it.

That is a redesign, not an adjustment, and it is recorded on issue #6 rather
than done here.

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

**Both mechanisms were reproduced on a live instance after the fact.** The issue
is explicit that both were read off the code; `tests/verify_issue_6.py` points an
instrument at each, and the records are in `tests/screenshots/issue-6/`. What the
run also turned up is a third thing this decision does not address: measured
while Home Assistant was still finishing its startup, the non-admin's
`hass.panels` held all **28** of the instance's panels rather than the filtered
4 — Home Assistant had replaced the map wholesale and nothing put the filtering
back. That is issue #12, "the Filters fail open", caught in the act. It is not
caused by this change and is not fixed by it, and it is a good deal more serious
than either mechanism here.

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
