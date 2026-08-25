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

import {
  ACCESS_ALLOW,
  ACCESS_DENY,
  ACCESS_REDIRECT,
  decideInitAccess,
  filterPanels,
  isPermitted,
  panelIdFromPath,
  panelsEqual,
  resolveRedirectTarget,
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
