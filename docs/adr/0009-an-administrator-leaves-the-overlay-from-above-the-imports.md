# An administrator leaves the overlay from above the imports

Issue #15, against the loading overlay as it has shipped since v2.0.4.
`ha_sidebar_filter.js` puts an opaque, full-viewport, click-swallowing overlay
over every Home Assistant page, synchronously, above its own imports. The only
code that takes it down is `removeLoadingOverlay()` at the end of `init()` —
past two dynamic imports, a permissions fetch, a filter application and five
subscriptions.

Everything on that path is code that can fail, and when it does the overlay
stays up for the life of the page, with no timeout. Recovery is a hard reload
with a cleared cache; if the cause is a deploy that copied five files out of
six, it is SSH.

## The overlay is created before anyone knows who the user is

That is not an oversight in the ordering — it is what the overlay is for. It
covers the gap across the first async work this file does, and the first async
work is pulling in the module that would say who the user is. So the overlay
necessarily precedes the answer.

The consequence is that it covers **administrators**, on every page, including
the Permission Manager panel — the one screen that could fix whatever caused it.
Nothing about the failure is admin-specific and nothing about the overlay
distinguishes them.

It arrived as a side effect. v2.0.4 moved the overlay above the import while
fixing #9, and ADR-0006 records that move — "the page is now covered while that
happens … a page nobody can use", and "do not mistake the overlay for the
sentinel". What it does not say is who is under the cover. #12 measured what
that changed: on a broken frontend the page is
now covered rather than merely unfiltered. The console line measured there —
`panelsEqual is not a function` — is a runtime throw **after** the module
evaluated, not an import rejection, so the exposed window is the whole path from
evaluation to `removeLoadingOverlay()`.

## The decision: the release rides in the same block as the overlay

A 100 ms poll for `document.querySelector("home-assistant")?.hass?.user`,
started immediately after the overlay is appended and above both imports. When
the user is readable and `is_admin`, the overlay is removed. When the user is
readable and is not, the poll stops and nothing else happens.

Two properties make this the shape rather than a smaller edit elsewhere:

- **It depends on nothing below the imports.** Not on `permission_policy.js`,
  not on `filter_lifecycle.js`, not on `fetchPermissions()`, not on
  `removeLoadingOverlay()`. `hass.user` is populated by the Home Assistant
  frontend, which is running whether or not this integration's modules are.
- **It cannot be absent when the overlay is present.** Both are in the same
  synchronous prologue, so the only failure that skips the release — the module
  never evaluating at all — is also the failure that puts no overlay up.

The watch is not a registration in ADR-0007's sense and `resetState()` does not
release it. It clears itself the moment the user is readable, it is started once
per module evaluation rather than once per init, and a re-initialisation does
not raise a second overlay for a second watch to answer for.

An administrator loses nothing by being let out early. `applySidebarFilter()`
hands an administrator the untouched baseline, so no panel of theirs is ever
hidden and there is no half-filtered state the overlay could be concealing.

The removal is outright rather than faded. The fade in `removeLoadingOverlay()`
sets `opacity: 0` and finishes the job on a 300 ms timer; code that does not run
is the failure this exists to survive, and a release that needs a second timer
to complete has borrowed back the thing it was written to avoid.

### The overlay can be pending rather than present

When there is no `document.body` yet the overlay is appended from a
`DOMContentLoaded` listener. An overlay that has not been appended is one the
release cannot see, and it would land *after* the release had gone looking —
an administrator stranded by the code meant to let them out. So the release
records itself and the deferred append reads that record before it appends.

**The record is an attribute on `documentElement`, not a variable in this
module.** Two cache-buster queries on one page would be two modules and one
document, and a module-scoped flag would only suppress the append belonging to
the copy that did the releasing. The overlay is a document-level thing; so is
the fact that it has been released.

A module script runs after the parser has built the body, so this branch is not
the normal path. It is two lines, and the alternative is a window that opens
only on the load whose timing happens to be unusual.

## What was rejected: a deadman in CSS

Issue #15 offers a keyframe animation on the overlay that ends at `opacity: 0;
pointer-events: none` after N seconds. It needs no JavaScript to fire, which is
genuinely stronger than a poll — it survives even a page where nothing of ours
runs after the overlay goes up.

It is rejected because **N is not ours to choose.** The deadman fires for
everyone, so N has to be longer than the slowest healthy load or it reveals a
page mid-filter. The slowest healthy load is bounded by `waitForHass()`'s own
15-second patience, plus a permissions round trip, plus five subscriptions — so
any defensible N leaves an administrator covered for something like half a
minute, and then shows a non-admin an unfiltered page.

That second half is the decision issue #12 owns: what a non-admin should see
when the Filter never reports. #15 says explicitly that it must not answer it by
accident, which is how the current behaviour got here. A poll that asks who the
user is answers only for the user it can name.

## What this does not answer

**A non-admin is left exactly as they were.** An overlay that outlives a failed
init still outlives it, with no timeout, for anyone who is not an administrator.
That is #12's question and the shape of its answer is #16 — the Panel Gate,
which decides in the backend and takes the whole failure class with it.

**The overlay's existence.** It is expected to disappear along with the Filters
when the Gate lands. This is a hotfix for the releases before that, and the poll
is written to be deleted with the block it lives in.

**The watch has no deadline, and that is the second thing N was wrong for.** A
first draft gave up after 30 seconds, on the reasoning that this was twice
`waitForHass()`'s own patience. It is not comparable: `waitForHass()` starts its
clock *inside* `init()`, after both imports have resolved, while this one starts
at module evaluation. So the deadline would have been racing a slow-but-healthy
load, and losing that race means stranding the administrator the whole thing
exists to free — issue #15's defect, restored by its own fix.

What 30 seconds now buys is a console line, once, following ADR-0005's rule that
a Filter which cannot do its job says so. The watch continues. A `hass` that
never appears is a page with a broken Home Assistant frontend, and ten
`querySelector` calls a second on such a page is a smaller thing than an
administrator who cannot reach the Permission Manager panel.

## How it is held

`tests/loading_overlay.test.mjs`. The prologue cannot be imported — it is the
top of a module whose next statement is a top-level `await import()` of assets
that only exist behind a running Home Assistant — so the test slices it out of
the shipped file between two markers and **evaluates that text** against a fake
document. Source-text invariants in the idiom of
`tests/frontend_assets.test.mjs` hold the two placement rules: the whole block
is above the first `await import(`, and it never calls
`removeLoadingOverlay()`.

What the tests cannot prove is what a browser does with it. That is what a
verification run on a live instance is for, in the shape of
`tests/verify_issue_9.py`: break the frontend on purpose, load a page as an
administrator, and watch the overlay go.
