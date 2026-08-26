/**
 * The routing anchor holds for as long as it is the routed panel (issue #6).
 *
 * Run:  node --test tests/routing_anchor.test.mjs
 *
 * `filterPanels()` keeps the panel Home Assistant is routing to as a hidden
 * anchor, so the router always has a route for the current URL. Whether the
 * anchor is *built* correctly is decided by pure functions and tested in
 * tests/permission_policy.test.mjs. What decided it did not hold was two pieces
 * of adapter wiring around those functions:
 *
 * - **Mechanism A** — the hiding is a missing title, and two other places in
 *   this integration write titles onto exactly the panels that get anchored.
 *   Both ran on the same page load that applied the hiding and undid it.
 * - **Mechanism B** — the anchor names the panel the *document* loaded with.
 *   The navigation hooks re-checked access after a client-side route change but
 *   never recomputed the panel map, so the anchor went stale the moment the
 *   user navigated.
 *
 * Reaching that wiring needs a browser and a Home Assistant. So, in the idiom
 * tests/frontend_assets.test.mjs established and ADR-0007 reuses, it is read as
 * source text instead. These tests prove the wiring is *spelt*; they cannot
 * prove it *works*. What it does in a browser is what the verification run on a
 * live instance is for.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (name) =>
  readFileSync(
    new URL(`../custom_components/ha_permission_manager/frontend/${name}`, import.meta.url),
    "utf8",
  );

const POLICY = read("permission_policy.js");
const SIDEBAR_FILTER = read("ha_sidebar_filter.js");
const SIDEBAR_TITLE = read("sidebar-title.js");

/**
 * The body of a named function, braces balanced.
 *
 * The one-line `/\{([^}]*)\}/` that serves for a short function does not reach
 * these: every function below holds an `if` or a loop, and stopping at the
 * first `}` would read almost none of it — and pass.
 */
function functionBody(source, name) {
  const start = new RegExp(`function\\s+${name}\\s*\\([^)]*\\)\\s*\\{`).exec(source);
  assert.ok(start, `${name}() is defined`);

  let depth = 0;
  for (let i = start.index + start[0].length - 1; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start.index, i + 1);
    }
  }
  assert.fail(`${name}() has an unbalanced body`);
}

// === Mechanism A: one owner for "this panel is hidden" ===

/**
 * The mark permission_policy.js puts on an anchor, read out of its source
 * rather than written twice here. The point of the whole mechanism is that one
 * spelling is shared, so a test that spelt its own would not be testing it.
 */
const ANCHOR_SYMBOL = (() => {
  const match = /Symbol\.for\("(ha_permission_manager\.anchored_panel)"\)/.exec(POLICY);
  assert.ok(match, "permission_policy.js marks an anchor with a registered symbol");
  return match[1];
})();

test("everywhere the sidebar filter writes a panel title, it asks first", () => {
  // Both of these name ha_permission_manager and ha-control-panel explicitly,
  // which are the two panels this integration ships and therefore two of the
  // panels most likely to be the one a denied non-admin is anchored to.
  for (const name of ["updateSidebarTitleViaHass", "updateSidebarTitle"]) {
    assert.match(
      functionBody(SIDEBAR_FILTER, name),
      /isAnchoredPanel\(/,
      `${name}() puts a title on a panel it names by id, and an anchor is ` +
        "hidden by having none — so it has to ask whether this one is an anchor",
    );
  }

  assert.match(
    SIDEBAR_FILTER,
    /isAnchoredPanel,/,
    "and it asks the module that owns the answer, rather than re-deciding",
  );
});

test("sidebar-title.js asks the same question, in the one spelling there is", () => {
  // A classic script loaded by add_extra_js_url: it cannot import the policy,
  // so the global symbol registry is the contract between the two files.
  assert.match(
    SIDEBAR_TITLE,
    new RegExp(`Symbol\\.for\\("${ANCHOR_SYMBOL.replace(/\./g, "\\.")}"\\)`),
    "sidebar-title.js writes titles onto the same two panels on a timer, so " +
      "an anchor it does not recognise is an anchor undone a second later",
  );

  assert.match(
    functionBody(SIDEBAR_TITLE, "updateTitles"),
    /ANCHORED\]/,
    "and it asks before it writes, not merely at the top of the file",
  );
});

test("nothing outside those two files claims to know what an anchor is", () => {
  // permission_policy.js sets the mark, sidebar-title.js reads it because it
  // cannot import. Everything else imports isAnchoredPanel(). A third spelling
  // of the string is a second owner of "hidden", which is the defect.
  const spellings = [POLICY, SIDEBAR_FILTER, SIDEBAR_TITLE].filter((source) =>
    source.includes(ANCHOR_SYMBOL),
  );
  assert.equal(spellings.length, 2, "the symbol string is spelt in exactly two files");
});

// === Mechanism B: a route change recomputes the anchor ===

test("a client-side navigation recomputes the panel map, not only the access check", () => {
  const watch = functionBody(SIDEBAR_FILTER, "watchNavigation");
  assert.match(
    watch,
    /onNavigate:\s*[^,]*onRouteChanged/,
    "the navigation hooks report to onRouteChanged()",
  );

  const onRouteChanged = functionBody(SIDEBAR_FILTER, "onRouteChanged");
  assert.match(
    onRouteChanged,
    /applySidebarFilter\(/,
    "the anchor names the panel the document loaded with; after a route " +
      "change the newly routed denied panel is the one absent from " +
      "hass.panels, which is the missing route the anchor exists to prevent",
  );
  assert.match(
    onRouteChanged,
    /checkCurrentPanelAccess\(/,
    "and the Access Denied Filter still has to cover the panel now routed to",
  );
});

test("a route change costs one permission round trip, not one per thing it does", () => {
  const onRouteChanged = functionBody(SIDEBAR_FILTER, "onRouteChanged");
  const fetches = onRouteChanged.match(/fetchPermissions\(/g) || [];

  assert.equal(
    fetches.length,
    1,
    "both halves are told what was fetched; each fetching for itself would " +
      "double what a navigation costs, which is the shape of the defect " +
      "ADR-0007 records under the nested pushState wrappers",
  );
});

test("the panel map is only ever put on hass by the one function that marks it", () => {
  // ADR-0007: a baseline is never re-read from a map this integration
  // produced, and applyPanels() is what says which maps those are. A second
  // assignment elsewhere puts an unmarked filtered map on hass, and the next
  // reset rebaselines from it.
  //
  // Every write to a `.hass` or a `.hass.panels` is caught, not only the
  // spelling the defect happened to take: `hass.panels = x` and an assignment
  // wrapped across lines are the two that a pattern shaped like the known-bad
  // one would let past.
  const writes = [...SIDEBAR_FILTER.matchAll(/^.*\.hass(?:\.panels)?\s*=[^=].*$/gm)].map(
    ([line]) => line.trim(),
  );

  /** The two writes there are, each named for why it is allowed to exist. */
  const allowed = new Set([
    // applyPanels(), the one place a panel map goes onto hass — and the one
    // place markFiltered() is called.
    "haMain.hass = { ...haMain.hass, panels };",
    // Handing the current hass to the Access Denied element, which puts no
    // panel map anywhere.
    "accessDenied.hass = haMain.hass;",
  ]);

  assert.ok(writes.length > 0, "the filter writes to hass at least once");
  for (const line of writes) {
    assert.ok(
      allowed.has(line),
      `"${line}" writes to hass outside applyPanels(). If it puts a panel ` +
        "map there, that map is unmarked and a reset can take a baseline " +
        "from it (ADR-0007); if it does not, add it to the allowed set here " +
        "with the reason.",
    );
  }
});
