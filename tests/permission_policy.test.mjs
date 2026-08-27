/**
 * Unit tests for the pure permission policy shared by the Filters.
 *
 * Run:  node --test tests/permission_policy.test.mjs
 *
 * These are pure-function tests: no Home Assistant, no browser, no network.
 * The scenarios are drawn from the live-instance traces in issue #4.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  ACCESS_ALLOW,
  ACCESS_DENY,
  ACCESS_REDIRECT,
  ALWAYS_VISIBLE_PANELS,
  ROUTER_FALLBACK_PANELS,
  decideInitAccess,
  filterPanels,
  isAnchoredPanel,
  isDashboardPath,
  isPermitted,
  panelIdFromPath,
  panelsEqual,
  resolveRedirectTarget,
  shouldShowDashboard,
} from "../custom_components/ha_permission_manager/frontend/permission_policy.js";

/** A panel entry shaped like the ones Home Assistant puts in hass.panels. */
const panel = (urlPath, extra = {}) => ({
  component_name: "lovelace",
  icon: null,
  title: urlPath,
  url_path: urlPath,
  config: null,
  ...extra,
});

/**
 * The live instance from issue #4: the default dashboard is served at "home",
 * there is no legacy "lovelace" overview panel, and the integration ships two
 * panels of its own.
 */
const LIVE_PANELS = {
  home: panel("home"),
  "ha-control-panel": panel("ha-control-panel", { component_name: "custom" }),
  ha_permission_manager: panel("ha_permission_manager", { component_name: "custom" }),
  config: panel("config", { component_name: "config" }),
  profile: panel("profile", { component_name: "profile" }),
  notfound: panel("notfound", { component_name: "custom", title: null }),
};

/** What get_panel_permissions returned for the non-admin in issue #4. */
const LIVE_PERMISSIONS = {
  lovelace: 1,
  "ha-control-panel": 0,
  ha_permission_manager: 0,
  config: 0,
  core_configurator: 0,
};

test("panelIdFromPath reads the first path segment", () => {
  assert.equal(panelIdFromPath("/ha-control-panel"), "ha-control-panel");
  assert.equal(panelIdFromPath("/lovelace/0"), "lovelace");
  assert.equal(panelIdFromPath("/config/areas/dashboard"), "config");
  assert.equal(panelIdFromPath("/"), null);
  assert.equal(panelIdFromPath(""), null);
});

test("isPermitted is fail-secure: only an explicit level above Closed grants", () => {
  assert.equal(isPermitted({ home: 1 }, "home"), true);
  assert.equal(isPermitted({ home: 0 }, "home"), false);
  assert.equal(isPermitted({}, "home"), false);
  assert.equal(isPermitted(undefined, "home"), false);
});

test("a permitted panel is allowed", () => {
  const decision = decideInitAccess({
    currentPanel: "ha-control-panel",
    permissions: { "ha-control-panel": 1 },
    panels: LIVE_PANELS,
    defaultPanels: ["home"],
    redirectSpent: false,
  });
  assert.equal(decision.action, ACCESS_ALLOW);
});

test("paths that are not Resources are allowed without a permission", () => {
  for (const path of ["/profile", "/auth/authorize", "/api/states", "/", "/notfound"]) {
    const decision = decideInitAccess({
      currentPanel: panelIdFromPath(path),
      permissions: {},
      panels: LIVE_PANELS,
      defaultPanels: ["home"],
      redirectSpent: false,
    });
    assert.equal(decision.action, ACCESS_ALLOW, path);
  }
});

test("a denied panel redirects to the permitted default panel", () => {
  const decision = decideInitAccess({
    currentPanel: "ha-control-panel",
    permissions: { home: 1, "ha-control-panel": 0 },
    panels: LIVE_PANELS,
    defaultPanels: ["home"],
    redirectSpent: false,
  });
  assert.equal(decision.action, ACCESS_REDIRECT);
  assert.equal(decision.target, "home");
});

test("with every panel Closed there is no redirect, only a denial", () => {
  const decision = decideInitAccess({
    currentPanel: "ha-control-panel",
    permissions: { home: 0, "ha-control-panel": 0, config: 0 },
    panels: LIVE_PANELS,
    defaultPanels: ["home"],
    redirectSpent: false,
  });
  assert.equal(decision.action, ACCESS_DENY);
});

test("a destination Home Assistant does not serve is never used", () => {
  // The regression from issue #4: "lovelace" holds View, but this instance has
  // no lovelace panel, so Home Assistant reroutes /lovelace to /home.
  assert.equal(
    resolveRedirectTarget({
      permissions: LIVE_PERMISSIONS,
      panels: LIVE_PANELS,
      currentPanel: "ha-control-panel",
      defaultPanels: [],
    }),
    null
  );
});

test("the reroute case denies instead of bouncing off a phantom destination", () => {
  const decision = decideInitAccess({
    currentPanel: "ha-control-panel",
    permissions: LIVE_PERMISSIONS,
    panels: LIVE_PANELS,
    defaultPanels: [], // hass.defaultPanel was undefined on the live instance
    redirectSpent: false,
  });
  assert.equal(decision.action, ACCESS_DENY);
});

test("a spent redirect is never spent twice", () => {
  const decision = decideInitAccess({
    currentPanel: "ha-control-panel",
    permissions: { home: 1, "ha-control-panel": 0 },
    panels: LIVE_PANELS,
    defaultPanels: ["home"],
    redirectSpent: true,
  });
  assert.equal(decision.action, ACCESS_DENY);
});

test("the destination is never the panel already being denied", () => {
  const decision = decideInitAccess({
    currentPanel: "home",
    permissions: { home: 0 },
    panels: LIVE_PANELS,
    defaultPanels: ["home"],
    redirectSpent: false,
  });
  assert.equal(decision.action, ACCESS_DENY);
});

test("the reported loop terminates after at most one redirect", () => {
  // Replays the live trace: every init-time redirect to /lovelace is rewritten
  // by Home Assistant to /home before the filter finishes initialising.
  const rewriteLikeHomeAssistant = (target) =>
    LIVE_PANELS[target] ? target : "home";

  let currentPanel = "ha-control-panel";
  let redirectSpent = false;
  let redirects = 0;
  let settled = null;

  for (let load = 0; load < 20; load++) {
    const decision = decideInitAccess({
      currentPanel,
      permissions: LIVE_PERMISSIONS,
      panels: LIVE_PANELS,
      defaultPanels: [],
      redirectSpent,
    });
    if (decision.action !== ACCESS_REDIRECT) {
      settled = decision.action;
      break;
    }
    redirects++;
    redirectSpent = true;
    currentPanel = rewriteLikeHomeAssistant(decision.target);
  }

  assert.ok(redirects <= 1, `expected at most one redirect, got ${redirects}`);
  assert.equal(settled, ACCESS_DENY);
});

test("no arrangement of permissions and routing can loop", () => {
  // Exhaustive sweep: for every subset of granted panels and every rewrite
  // target Home Assistant might pick, the browsing session settles.
  const ids = Object.keys(LIVE_PANELS);
  const rewriteTargets = [...ids, "home", "lovelace"];

  for (let mask = 0; mask < 1 << ids.length; mask++) {
    const permissions = {};
    ids.forEach((id, i) => {
      permissions[id] = mask & (1 << i) ? 1 : 0;
    });
    for (const rewriteTo of rewriteTargets) {
      let currentPanel = "ha-control-panel";
      let redirectSpent = false;
      let redirects = 0;
      let settled = false;
      for (let load = 0; load < 10; load++) {
        const decision = decideInitAccess({
          currentPanel,
          permissions,
          panels: LIVE_PANELS,
          defaultPanels: ["home"],
          redirectSpent,
        });
        if (decision.action !== ACCESS_REDIRECT) {
          settled = true;
          break;
        }
        redirects++;
        redirectSpent = true;
        currentPanel = rewriteTo; // worst case: HA sends them anywhere at all
      }
      assert.ok(settled, `did not settle: mask=${mask} rewriteTo=${rewriteTo}`);
      assert.ok(redirects <= 1, `looped: mask=${mask} rewriteTo=${rewriteTo}`);
    }
  }
});

test("filterPanels keeps what is granted and drops what is not", () => {
  const { panels } = filterPanels({
    panels: LIVE_PANELS,
    permissions: { home: 1, "ha-control-panel": 1 },
    currentPanel: "home",
  });
  assert.deepEqual(Object.keys(panels).sort(), [
    "ha-control-panel",
    "home",
    "notfound",
    "profile",
  ]);
});

test("filterPanels never removes the panel Home Assistant is routing to", () => {
  // Removing the routed panel is what made the frontend throw
  // "Cannot read properties of undefined (reading 'url_path')".
  const { panels } = filterPanels({
    panels: LIVE_PANELS,
    permissions: LIVE_PERMISSIONS,
    currentPanel: "ha-control-panel",
  });
  assert.ok(panels["ha-control-panel"], "routed panel must stay routable");
  assert.equal(panels["ha-control-panel"].show_in_sidebar, false);
  assert.equal(panels["ha-control-panel"].title, null);
});

test("an anchor says it is one, so nothing re-titles it back into view", () => {
  // The missing title IS the hiding, and two other places in this integration
  // write titles onto these very panels (issue #6, Mechanism A). They ask
  // this, so that "hidden" has one owner rather than three opinions.
  const { panels } = filterPanels({
    panels: LIVE_PANELS,
    permissions: { home: 1 },
    currentPanel: "ha-control-panel",
  });

  assert.equal(isAnchoredPanel(panels["ha-control-panel"]), true);
  assert.equal(
    isAnchoredPanel(panels.home),
    false,
    "a panel kept because the user has a View level on it is an ordinary " +
      "panel, and its title is the sidebar's to show and this integration's " +
      "to translate",
  );
});

test("the anchor mark is invisible to everything Home Assistant does with a panel", () => {
  const { panels } = filterPanels({
    panels: LIVE_PANELS,
    permissions: {},
    currentPanel: "ha-control-panel",
  });
  const anchor = panels["ha-control-panel"];

  const plain = { ...LIVE_PANELS["ha-control-panel"], title: null, show_in_sidebar: false };

  assert.deepEqual(
    Object.keys(anchor),
    Object.keys(plain),
    "Home Assistant enumerates a panel's keys and serialises it; the mark " +
      "must be neither a key nor a field",
  );
  assert.deepEqual(
    Object.getOwnPropertyNames(anchor),
    Object.getOwnPropertyNames(plain),
    "and it must not be a non-enumerable string key either",
  );
  assert.equal(
    JSON.stringify(anchor),
    JSON.stringify(plain),
    "panelsEqual() compares serialised maps, so a mark that serialised " +
      "would make every re-filter look like a change",
  );
});

test("nothing is anchored until filterPanels says so", () => {
  assert.equal(isAnchoredPanel(LIVE_PANELS["ha-control-panel"]), false);
  assert.equal(isAnchoredPanel({ title: null }), false, "a panel Home Assistant itself left untitled is not an anchor");
  assert.equal(isAnchoredPanel(undefined), false);
  assert.equal(isAnchoredPanel(null), false);
});

test("an anchor never carries the name of a panel the user was denied", () => {
  // Both hiding rules are set, because a Home Assistant version that honours
  // only one of them would otherwise leave the name on screen.
  for (const currentPanel of ["home", "ha-control-panel"]) {
    const { panels } = filterPanels({
      panels: LIVE_PANELS,
      permissions: {},
      currentPanel,
    });
    assert.equal(panels[currentPanel].title, null, currentPanel);
    assert.equal(panels[currentPanel].show_in_sidebar, false, currentPanel);
  }
});

test("filterPanels adds nothing beyond the routed panel when all are Closed", () => {
  // v2.0.0 showed a sidebar with no panels in it; that must not change.
  const { panels, anchored } = filterPanels({
    panels: LIVE_PANELS,
    permissions: {},
    currentPanel: "ha-control-panel",
  });
  assert.deepEqual(anchored, ["ha-control-panel"]);
  assert.deepEqual(Object.keys(panels).sort(), [
    "ha-control-panel",
    "notfound",
    "profile",
  ]);
  assert.equal(panels["ha-control-panel"].show_in_sidebar, false);
  assert.equal(panels["ha-control-panel"].title, null);
});

test("filterPanels adds no anchor when the current panel is granted", () => {
  const { panels, anchored } = filterPanels({
    panels: LIVE_PANELS,
    permissions: { home: 1 },
    currentPanel: "home",
  });
  assert.deepEqual(anchored, []);
  assert.equal(panels.home.title, "home");
  assert.equal(panels.home.show_in_sidebar, undefined);
});

test("the map built for one path holds no route for another", () => {
  // Why the panel map has to be recomputed on a route change (issue #6,
  // Mechanism B) rather than only re-checked for access. The anchor is the
  // only reason a denied panel is routable at all, and it is built for one
  // path — so the map that made /ha-control-panel routable is a map on which
  // /config is exactly as missing as it ever was.
  const atControlPanel = filterPanels({
    panels: LIVE_PANELS,
    permissions: {},
    currentPanel: "ha-control-panel",
  }).panels;
  const atConfig = filterPanels({
    panels: LIVE_PANELS,
    permissions: {},
    currentPanel: "config",
  }).panels;

  assert.ok(atControlPanel["ha-control-panel"], "routable where it was built");
  assert.ok(
    !atControlPanel.config,
    "and not routable at the panel the browser navigates to next — which is " +
      "the missing route the anchor exists to prevent",
  );
  assert.ok(atConfig.config, "recomputing at the new path restores it");
  assert.equal(
    panelsEqual(atControlPanel, atConfig),
    false,
    "so a navigation is a real change to hass.panels, not a no-op " +
      "applyPanels() would skip",
  );
});

test("filterPanels is deterministic, so re-applying it does not churn hass", () => {
  const args = {
    panels: LIVE_PANELS,
    permissions: LIVE_PERMISSIONS,
    currentPanel: "ha-control-panel",
  };
  assert.deepEqual(filterPanels(args).panels, filterPanels(args).panels);
});

test("filterPanels keeps Home Assistant's router fallback panel", () => {
  // getDefaultPanel() ends at panels.notfound; without it, Home Assistant
  // throws reading .url_path off undefined on every route change.
  const { panels } = filterPanels({
    panels: LIVE_PANELS,
    permissions: {},
    currentPanel: "ha-control-panel",
  });
  assert.ok(panels.notfound, "notfound must stay routable");
});

test("filterPanels leaves the source panels untouched", () => {
  const before = JSON.parse(JSON.stringify(LIVE_PANELS));
  filterPanels({
    panels: LIVE_PANELS,
    permissions: LIVE_PERMISSIONS,
    currentPanel: "ha-control-panel",
  });
  assert.deepEqual(LIVE_PANELS, before);
});

test("panelsEqual sees through a fresh object with the same content", () => {
  // filterPanels returns new objects every call. Without this, hass would be
  // replaced on every event and Home Assistant would rebuild the page each
  // time — the rebuild that makes its router read `route.path` off undefined.
  const args = {
    panels: LIVE_PANELS,
    permissions: LIVE_PERMISSIONS,
    currentPanel: "ha-control-panel",
  };
  assert.equal(panelsEqual(filterPanels(args).panels, filterPanels(args).panels), true);
});

test("panelsEqual reports a real change", () => {
  const before = filterPanels({
    panels: LIVE_PANELS,
    permissions: {},
    currentPanel: "ha-control-panel",
  }).panels;
  const after = filterPanels({
    panels: LIVE_PANELS,
    permissions: { home: 1 },
    currentPanel: "ha-control-panel",
  }).panels;
  assert.equal(panelsEqual(before, after), false);
});

test("panelsEqual sees the anchor appearing on an otherwise identical map", () => {
  const granted = filterPanels({
    panels: LIVE_PANELS,
    permissions: { "ha-control-panel": 1 },
    currentPanel: "ha-control-panel",
  }).panels;
  const anchored = filterPanels({
    panels: LIVE_PANELS,
    permissions: {},
    currentPanel: "ha-control-panel",
  }).panels;
  assert.equal(panelsEqual(granted, anchored), false);
});

test("a user granted only the default dashboard sees its content", () => {
  // The migration CHANGELOG v2.0.1 documents: the stub `lovelace` panel is no
  // longer a Resource, so the default dashboard is granted as `panel_home`.
  // That grant has to actually reach the dashboard content.
  const permissions = { panels: { home: 1 } };

  assert.equal(
    shouldShowDashboard({ permissions, isAdmin: false, pathname: "/home" }),
    true,
  );
});

test("a dashboard added by hand is honoured by the level on its own panel", () => {
  // The rule this replaced looked for a permission key containing "lovelace",
  // so a dashboard at /dashboard-kitchen was hidden however it was granted.
  const permissions = { panels: { "dashboard-kitchen": 1 } };

  assert.equal(
    shouldShowDashboard({ permissions, isAdmin: false, pathname: "/dashboard-kitchen" }),
    true,
  );
});

test("a level on a panel the user is not on does not unlock the dashboard", () => {
  // The store row for the stub panel survives the upgrade untouched. It must
  // not be read as a grant on the dashboard the user was rerouted to.
  const permissions = { panels: { lovelace: 1 } };

  assert.equal(
    shouldShowDashboard({ permissions, isAdmin: false, pathname: "/home" }),
    false,
  );
});

test("a denied dashboard stays hidden", () => {
  const permissions = { panels: { home: 0 } };

  assert.equal(
    shouldShowDashboard({ permissions, isAdmin: false, pathname: "/home" }),
    false,
  );
});

test("shouldShowDashboard is fail-secure before the Permission store loads", () => {
  assert.equal(
    shouldShowDashboard({ permissions: null, isAdmin: false, pathname: "/home" }),
    false,
  );
});

test("an admin sees dashboard content whatever the store says", () => {
  const permissions = { panels: { home: 0 } };

  assert.equal(
    shouldShowDashboard({ permissions, isAdmin: true, pathname: "/home" }),
    true,
  );
});

/**
 * isDashboardPath — issue #10.
 *
 * The component names are the ones 192.168.2.6 (HA 2026.7.2) actually reports:
 * the default dashboard is `home`/`home`, a dashboard added by hand is
 * `lovelace`, and this integration's own panels are `custom`.
 */

test("the default dashboard panel is a dashboard", () => {
  assert.equal(
    isDashboardPath({ panels: { home: panel("home", { component_name: "home" }) }, pathname: "/home" }),
    true,
  );
});

test("a dashboard added by hand is a dashboard", () => {
  assert.equal(
    isDashboardPath({
      panels: { "dashboard-kitchen": panel("dashboard-kitchen", { component_name: "lovelace" }) },
      pathname: "/dashboard-kitchen/0",
    }),
    true,
  );
});

test("a panel that renders no dashboard is not one", () => {
  const panels = {
    config: panel("config", { component_name: "config" }),
    "ha-control-panel": panel("ha-control-panel", { component_name: "custom" }),
  };
  assert.equal(isDashboardPath({ panels, pathname: "/config/areas" }), false);
  assert.equal(isDashboardPath({ panels, pathname: "/ha-control-panel" }), false);
});

test("a panel this browser's map does not hold answers no, so nothing is claimed about it", () => {
  // The sidebar filter replaces hass.panels with a filtered map, so a denied
  // panel can be missing entirely. Saying "not a dashboard" here only silences
  // a diagnostic; it never decides whether content is hidden.
  assert.equal(isDashboardPath({ panels: LIVE_PANELS, pathname: "/dashboard-kitchen" }), false);
  assert.equal(isDashboardPath({ panels: null, pathname: "/home" }), false);
});

test("a path that names no panel is treated as the dashboard still being resolved", () => {
  assert.equal(isDashboardPath({ panels: LIVE_PANELS, pathname: "/" }), true);
  assert.equal(isDashboardPath({ panels: null, pathname: "" }), true);
});

/**
 * A page Home Assistant keeps routable but nobody grants — found by running
 * the Filter against 192.168.2.6 for issue #10.
 *
 * A client-side navigation to a denied panel lands on `notfound`, because the
 * sidebar filter has taken that panel out of hass.panels. Hiding content there
 * puts "no content available" over Home Assistant's own 404. isExemptPanel()
 * already says these carry no Permission; shouldShowDashboard has to agree.
 */

test("a router fallback page carries no Permission, so its content is not hidden", () => {
  const denied = { panels: { home: 0 } };
  assert.equal(
    shouldShowDashboard({ permissions: denied, isAdmin: false, pathname: "/notfound/0" }),
    true,
  );
});

test("a path that is not a Resource is not hidden either", () => {
  const denied = { panels: {} };
  assert.equal(shouldShowDashboard({ permissions: denied, isAdmin: false, pathname: "/profile" }), true);
  assert.equal(shouldShowDashboard({ permissions: denied, isAdmin: false, pathname: "/auth/authorize" }), true);
});

test("the exemption does not reach a path that names no panel", () => {
  // "/" before Home Assistant rewrites it to whichever dashboard it serves.
  // Fail-secure wins here: the panel is unknown, not known to be exempt.
  assert.equal(shouldShowDashboard({ permissions: { panels: {} }, isAdmin: false, pathname: "/" }), false);
});

test("the exemption does not reach a real dashboard", () => {
  assert.equal(
    shouldShowDashboard({ permissions: { panels: { home: 0 } }, isAdmin: false, pathname: "/home" }),
    false,
  );
});

// =============================================================================
// The two panels that need no Permission, spelt in two languages
// =============================================================================
//
// ALWAYS_VISIBLE_PANELS and ROUTER_FALLBACK_PANELS exist twice: here, for the
// Filters, and in custom_components/ha_permission_manager/panel_policy.py, for
// the Panel Gate and for what get_panel_permissions reports. Nothing makes the
// two agree at runtime — one is JavaScript and one is Python — and a panel
// that needs no Permission in one layer and does in the other is denied in one
// place and allowed in the other.
//
// So the Python file is read as text, the way tests/console_vocabulary.test.mjs
// and tests/frontend_assets.test.mjs read the sources they hold to a spelling.
// Importing it is not on offer here, and running a Python test against the
// JavaScript is not on offer there.

const PANEL_POLICY_PY = fileURLToPath(
  new URL("../custom_components/ha_permission_manager/panel_policy.py", import.meta.url),
);

/**
 * The panel ids in one of panel_policy.py's frozensets, read out of the source.
 *
 * Deliberately not a Python parser: one anchored regex for the assignment, one
 * for the quoted ids inside it, neither able to match past the literal it
 * starts on. Spelling the frozenset any other way fails the test rather than
 * quietly matching nothing, which is the failure this is here to prevent.
 */
function pythonPanelIds(name) {
  const source = readFileSync(PANEL_POLICY_PY, "utf8");
  const assignment = new RegExp(`^${name} = frozenset\\(\\{([^}]*)\\}\\)`, "m").exec(source);
  assert.ok(assignment, `${name} is not a frozenset literal in panel_policy.py`);
  return [...assignment[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]).sort();
}

test("both layers keep the same panels visible without a Permission", () => {
  assert.deepEqual(pythonPanelIds("ALWAYS_VISIBLE_PANELS"), [...ALWAYS_VISIBLE_PANELS].sort());
});

test("both layers keep the same panels for the router to fall back through", () => {
  assert.deepEqual(pythonPanelIds("ROUTER_FALLBACK_PANELS"), [...ROUTER_FALLBACK_PANELS].sort());
});

test("the reader would notice if either list emptied itself out", () => {
  // A regex that matched a renamed or restructured constant and returned
  // nothing would pass both tests above against an empty JS list. Neither list
  // is allowed to be empty, so a silent no-match cannot look like agreement.
  assert.ok(pythonPanelIds("ALWAYS_VISIBLE_PANELS").length > 0);
  assert.ok(pythonPanelIds("ROUTER_FALLBACK_PANELS").length > 0);
});
