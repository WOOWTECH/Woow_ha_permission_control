# A Filter releases what it registered before it runs again

Issue #5: Home Assistant replaces its `home-assistant` element on logout/login,
the sidebar filter watches for that and re-initialises, and re-initialising
registered everything a second time without removing what the previous run had
registered. Five WebSocket subscriptions, two DOM listeners and a wrapper around
`history.pushState` accumulated once per re-initialisation, for the life of the
tab. There was no `removeEventListener` and no unsubscribe anywhere in the file;
`subscribeEvents` returns an unsubscribe function and all five return values were
discarded.

The `pushState` wrapper was worse than a leak. Each run captured whatever
`history.pushState` was at the time — on the second run, the first wrapper — so
the wrappers nested rather than replaced, and after N re-initialisations one
navigation scheduled N `checkCurrentPanelAccess()` calls, each with its own
`get_panel_permissions` round trip.

## The decision

**A Filter releases its registrations before it runs again, and registers
nothing twice that it cannot release.** What that means differs by registration,
because the three kinds differ in what a re-initialisation does to them:

- **WebSocket subscriptions belong to a connection a logout closes.** They have
  to be made again, so they have to be released again. `createSubscriptions()`
  in `frontend/filter_lifecycle.js` holds what each `subscribeEvents` resolves
  to, and `resetState()` releases them all.
- **The navigation hooks sit on `window`, `document` and `history`,** none of
  which the re-initialisation replaces. They are installed once and stay
  installed: `installNavigationHooks()` marks the `history` object it hooked and
  is a no-op every time after the first.
- **The unfiltered baseline is not a registration,** but it is lost on the same
  path, so it is fixed here. See below.

The alternative for the navigation hooks was the symmetrical one: keep
references to the handlers and remove them on reset, as with the subscriptions.
Rejected because it restores state that was never disturbed — and because
restoring `history.pushState` correctly means putting back the value captured on
the *first* wrap, which is the same "install once" fact, spelt in a way that has
somewhere left to go wrong. Nothing is gained by unhooking a `window` that is
about to be re-hooked.

The subscriptions are released synchronously in the sense that matters: the held
list is taken and emptied in one turn, before any `await`, so the run that
follows the reset registers onto an empty set rather than into the one being
released. `init()` also carries a run number, because it is a chain of awaits and
a reset can land in the middle of one; a run the reset overtook returns instead
of subscribing. The number is checked twice — once before subscribing and again
inside `subscribeToChanges()` after its own wait — because a reset landing in
*that* wait would release a list the five subscriptions have not joined yet, and
they would then be added on top of the new run's.

## The baseline gets contaminated on the same path

`resetState()` set `originalPanels = null`, and `storeOriginalPanels()` then
re-derived the baseline from `hass.panels` — which by that point is the map this
integration produced, not Home Assistant's own. Every panel the user has no View
level on was therefore missing from the baseline for the rest of the session, so
granting a Permission level afterwards could not bring the panel back without a
full page reload. Since v2.0.1 the filtered map can also carry a hidden anchor
panel with `title: null`, which would be rebaselined in that state.

**A baseline is never read from a map this integration produced.** `applyPanels()`
marks every map it puts on `hass`, and `nextBaseline()` refuses a marked
candidate. The mark is a **non-enumerable** `Symbol.for` key, and both halves are
load-bearing. The symbol is what makes it safe to hang on a map that goes on to
`hass`: Home Assistant enumerates the panels with `Object.keys` and serialises
them, and neither sees a symbol. Non-enumerable is what keeps the mark on the one
object it is true of — object spread copies own enumerable symbol keys like any
other property, so a mark left enumerable would ride every `{ ...panels }` Home
Assistant takes, and no map descended from a filtered one could ever be read as a
baseline again. That is a defect a test can pass straight over, and this one did
until it was made to assert on the copy rather than on what the copy produced.

A reset marks the baseline stale rather than dropping it. Dropping it forces a
re-read from whatever `hass.panels` holds at that moment; marking it stale asks
for a re-read and keeps the old baseline when the only thing on offer is the
filtered map. That way a dashboard added while the tab was logged out is still
picked up, and a refusal costs the session nothing it had.

Following ADR-0005's rule that a Filter which cannot do its job says so, the
refusal is a console warning, and it says whether a baseline was kept or whether
there is none.

## What this does not cover

**The other two Filters are left alone.** `ha_lovelace_filter.js` cannot
accumulate registrations, because it has no re-initialisation to accumulate
them on: its `init()` sets `initialized = true` and nothing ever clears it, and
it watches the DOM rather than watching for the `home-assistant` element being
replaced. That is also the reason not to give it this module — it registers its
one subscription, its `popstate` listener and its MutationObserver exactly once
per page load, and there is nothing to release them before.

What that leaves, and what this decision does not answer, is the other side of
the same coin: after a logout the lovelace filter is still holding a
subscription made on the connection that logout closed, and it will not make
another. Whether that subscription survives Home Assistant's own reconnect was
not measured, and it is a different defect from the one issue #5 reports.

The registrations are counted in `tests/filter_lifecycle.test.mjs`, against a
fake connection. The sidebar filter's own wiring cannot be reached without a
browser and a Home Assistant, so the same file holds it as three source-text
invariants instead, in the idiom `tests/frontend_assets.test.mjs` established:
every `subscribeEvents` call is held by `subscriptions.add()`, `resetState()`
releases them, and the file registers no `popstate`, `click` or `pushState` hook
of its own. Each was checked by breaking it. What no test covers is whether the
subscriptions are the *right* five, or what the handlers do.
