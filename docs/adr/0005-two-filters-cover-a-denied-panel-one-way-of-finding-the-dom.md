# Two Filters cover a denied panel, and there is one way of finding the DOM

> **Superseded by [ADR-0011](0011-the-panel-decision-moves-into-the-backend.md).**
> Both Filters, and the Access Denied page they put up, were deleted in
> v3.0.0 (#20): the Panel Gate makes a denied panel absent, so there is
> nothing left to cover and no DOM to find it in. Kept as the record of how
> they worked, and of why two of them existed.

Issue #10 asked whether the lovelace filter should exist at all, now that the
sidebar filter's Access Denied Filter covers a denied panel: "Two layers that
disagree about how to find the DOM are worse than one that works."

It keeps existing. The two layers do not overlap as much as they look:

- The Access Denied Filter runs from `checkCurrentPanelAccess()`, which the
  sidebar filter calls on load and on its navigation hooks. It replaces a
  denied page.
- The lovelace filter hides dashboard content from whatever state the page is
  actually in, on every DOM mutation. It is the layer that still acts when the
  overlay's check does not re-run — a dashboard that renders after the overlay
  has decided, or a client-side navigation into a denied dashboard (issue #6,
  Mechanism B).

That second case is argued from the code, not observed. Driving a client-side
navigation to a denied `/home` on 192.168.2.6 does not reach a denied dashboard
at all: the sidebar filter has already taken `home` out of `hass.panels`, so
Home Assistant's router lands on `notfound` instead. On that instance the gap
this layer is kept for is currently hidden behind #6's own defect. The layer is
kept on the strength of the first case, which is ordinary, and on fail-secure
grounds; if #6 is fixed and the second case still cannot be reached, this
decision is worth reopening.

Deleting the second layer would trade a defect for a gap. What the issue
correctly rejects is not the second layer but the disagreement, so:

**Finding an element in Home Assistant's shadow tree is done one way, by
searching for the element's name.** That way is `frontend/shadow_dom.js`. No
Filter may spell out a path through Home Assistant's element hierarchy to
reach content it acts on. That hierarchy is not an API — between releases
`partial-panel-resolver` lost its shadow root and the default dashboard moved
from `ha-panel-lovelace` to `ha-panel-home`, and the spelt-out walk answered
"nothing here" to both, silently, for a release.

**A Filter that decides to act and then acts on nothing says so.** Every
`return` on the old traversal was silent, which is why this cost a release
rather than a page load.

## What this decision does not yet cover

`ha_sidebar_filter.js` and `ha_access_denied.js` still spell out walks of their
own, to `ha-sidebar` and `ha-drawer` rather than to dashboard content. Measured
on HA 2026.7.2 those walks still work, so converting them is a change with
behaviour risk and no present defect, on files issue #6 is already about — it
belongs in that pass, not this one. Until then this ADR states the rule and one
of three Filters follows it.

The Filters also keep two names for the same concept in Home Assistant's two
vocabularies: `DASHBOARD_ROOTS` (element names) in the lovelace filter and
`DASHBOARD_COMPONENT_NAMES` (panel component names) in `permission_policy.js`.
They are not merged, because merging them would put a DOM element name into the
module that is pure by definition. Each cross-references the other.
