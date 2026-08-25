/**
 * HA Permission Manager - Permission policy
 *
 * Every panel-level decision the Filters make, as pure functions: no DOM, no
 * hass, no side effects. The Filters read the browser and talk to Home
 * Assistant; this module decides. That split is what lets the decisions be
 * unit tested (tests/permission_policy.test.mjs) instead of only observed in a
 * live browser.
 *
 * Loaded as an ES module — Home Assistant pulls the Filters in with import().
 */

/** The only two Permission levels that exist are 0 Closed and 1 View. */
export const PERM_DENY = 0;

/** First path segments that are not a Resource and are always reachable. */
export const EXEMPT_SEGMENTS = Object.freeze([
  "local",
  "api",
  "auth",
  "static",
  "frontend_latest",
  "frontend_es5",
  "_my_redirect",
  "profile",
]);

/** Panels a non-admin keeps whatever the Permission store says. */
export const ALWAYS_VISIBLE_PANELS = Object.freeze(["profile"]);

/**
 * Panels kept for routing only. Home Assistant resolves its default panel as
 * `panels[default] ?? panels.home ?? panels.notfound` and throws reading
 * `.url_path` off the result when all three are missing — which is what
 * filtering did to it. "notfound" is in Home Assistant's own FIXED_PANELS, so
 * it is never listed in the sidebar and keeping it costs nothing visible.
 */
export const ROUTER_FALLBACK_PANELS = Object.freeze(["notfound"]);

/**
 * Where Home Assistant sends a browser when it has no panel for the URL,
 * most likely first.
 *
 * This list is the heart of issue #4. Home Assistant's own default is "home",
 * and it rewrites /lovelace to /home whenever the instance has no legacy
 * overview dashboard. A redirect aimed at a panel Home Assistant does not
 * serve is therefore not a redirect at all — it is a bounce, and bounces are
 * what produced the replace() loop.
 */
export const DEFAULT_PANEL_FALLBACKS = Object.freeze(["home", "lovelace"]);

/** Outcomes of decideInitAccess(). */
export const ACCESS_ALLOW = "allow";
export const ACCESS_REDIRECT = "redirect";
export const ACCESS_DENY = "deny";

/**
 * The panel id in a URL path, or null when the path names no panel.
 *
 * @param {string} pathname e.g. "/lovelace/0"
 * @returns {string|null} e.g. "lovelace"
 */
export function panelIdFromPath(pathname) {
  const match = /^\/([^/]+)/.exec(pathname || "");
  return match ? match[1] : null;
}

/**
 * True for paths that carry no Permission, so are never denied.
 *
 * The router fallbacks count: they are Home Assistant's own "nowhere to go"
 * pages, not a Resource anyone grants, and denying a page we deliberately keep
 * routable would only put an Access Denied Filter over a 404.
 */
export function isExemptPanel(panelId) {
  return (
    panelId === null ||
    EXEMPT_SEGMENTS.includes(panelId) ||
    ROUTER_FALLBACK_PANELS.includes(panelId)
  );
}

/**
 * Fail-secure read of the Permission store: only an explicit level above
 * Closed grants. Absent means denied.
 */
export function isPermitted(permissions, panelId) {
  const level = (permissions || {})[panelId];
  return level !== undefined && level > PERM_DENY;
}

/**
 * Ordered destinations to consider, caller's preferences first.
 *
 * @param {string[]} [defaultPanels] panel ids read from hass, best first
 */
function destinationCandidates(defaultPanels) {
  return [...(defaultPanels || []), ...DEFAULT_PANEL_FALLBACKS];
}

/**
 * The one panel a denied user may be sent to, or null when there is none.
 *
 * A destination only qualifies when Home Assistant actually serves it — a
 * panel id that is not in hass.panels gets rewritten by Home Assistant's
 * router the moment the document loads, which lands the user somewhere the
 * caller never chose.
 *
 * @returns {string|null}
 */
export function resolveRedirectTarget({
  permissions,
  panels,
  currentPanel,
  defaultPanels,
}) {
  const seen = new Set();
  for (const candidate of destinationCandidates(defaultPanels)) {
    if (!candidate || seen.has(candidate)) continue;
    seen.add(candidate);
    if (candidate === currentPanel) continue;
    if (!panels || !panels[candidate]) continue;
    if (!isPermitted(permissions, candidate)) continue;
    return candidate;
  }
  return null;
}

/**
 * What to do about the panel the browser has just loaded.
 *
 * @param {object} args
 * @param {string|null} args.currentPanel panel id from the URL
 * @param {Record<string, number>} args.permissions from get_panel_permissions
 * @param {Record<string, object>} args.panels hass.panels, unfiltered
 * @param {string[]} [args.defaultPanels] default panel ids read from hass
 * @param {boolean} args.redirectSpent this session already redirected once
 * @returns {{action: string, target?: string, reason: string}}
 */
export function decideInitAccess({
  currentPanel,
  permissions,
  panels,
  defaultPanels,
  redirectSpent,
}) {
  if (isExemptPanel(currentPanel)) {
    return { action: ACCESS_ALLOW, reason: "exempt-path" };
  }
  if (isPermitted(permissions, currentPanel)) {
    return { action: ACCESS_ALLOW, reason: "permitted" };
  }
  // The redirect is self-limiting. Home Assistant may rewrite the URL after a
  // redirect lands, and a second redirect from the rewritten page is exactly
  // the loop in issue #4, so one browsing session gets one redirect. It is
  // handed back only once a page settles somewhere the user is permitted.
  if (redirectSpent) {
    return { action: ACCESS_DENY, reason: "redirect-already-spent" };
  }
  const target = resolveRedirectTarget({
    permissions,
    panels,
    currentPanel,
    defaultPanels,
  });
  if (!target) {
    return { action: ACCESS_DENY, reason: "no-reachable-destination" };
  }
  return { action: ACCESS_REDIRECT, target, reason: "denied-panel" };
}

/**
 * Whether two panel maps say the same thing.
 *
 * Replacing hass.panels makes Home Assistant rebuild the page element, and a
 * rebuild during an in-flight route change is what makes its router read
 * `route.path` off undefined. So the Filters only replace the map when the map
 * actually changed. filterPanels() builds its result in a fixed order, so a
 * serialised comparison is stable.
 */
export function panelsEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * A panel kept in hass.panels for routing only, hidden from the sidebar.
 *
 * Home Assistant hides a panel when `show_in_sidebar === false` OR when it has
 * no title. Both are set: relying on either alone leaves the panel's name on
 * screen wherever that version checks only the other one. The one place Home
 * Assistant shows a panel regardless is its own default, which then renders as
 * a nameless row — a worse look than a name, but not the name of a panel this
 * user was denied.
 */
function anchorPanel(panel) {
  return { ...panel, title: null, show_in_sidebar: false };
}

/**
 * The panels a non-admin's sidebar should hold.
 *
 * Two things survive without a Permission, and neither is visible because of
 * it. Home Assistant's router reads hass.panels to resolve the current URL, and
 * a miss sends the browser to the default panel — a redirect nobody asked for —
 * so the routed panel stays as a hidden anchor. And it falls back through
 * ROUTER_FALLBACK_PANELS when it resolves that default, so those stay too.
 * The Access Denied Filter still covers their content.
 *
 * Nothing else is added. A user with every panel Closed sees a sidebar with no
 * panels in it, exactly as before.
 *
 * @param {object} args
 * @param {Record<string, object>} args.panels hass.panels, unfiltered
 * @param {Record<string, number>} args.permissions from get_panel_permissions
 * @param {string|null} args.currentPanel panel id from the URL
 * @returns {{panels: Record<string, object>, anchored: string[]}}
 */
export function filterPanels({ panels, permissions, currentPanel }) {
  const filtered = {};
  for (const [panelId, panel] of Object.entries(panels || {})) {
    if (
      ALWAYS_VISIBLE_PANELS.includes(panelId) ||
      ROUTER_FALLBACK_PANELS.includes(panelId) ||
      isPermitted(permissions, panelId)
    ) {
      filtered[panelId] = panel;
    }
  }

  const anchored = [];
  if (
    !isExemptPanel(currentPanel) &&
    !filtered[currentPanel] &&
    panels &&
    panels[currentPanel]
  ) {
    filtered[currentPanel] = anchorPanel(panels[currentPanel]);
    anchored.push(currentPanel);
  }

  return { panels: filtered, anchored };
}

/**
 * Whether the dashboard content on this path may be shown.
 *
 * The Permission that governs a dashboard is the one on the panel Home
 * Assistant is routing to — `home` on an instance with no legacy overview,
 * `lovelace` on one that has, `dashboard-kitchen` for a dashboard added by
 * hand. Reading it off the path is what keeps this Filter saying the same
 * thing as the sidebar filter, which resolves the very same panel id the very
 * same way.
 *
 * Fail-secure: with no Permission store loaded, or no explicit level above
 * Closed on the routed panel, the content stays hidden.
 *
 * @param {{panels?: Object}|null} permissions get_all_permissions result
 * @param {boolean} isAdmin
 * @param {string} pathname e.g. "/home"
 * @returns {boolean} true when the content may be VISIBLE
 */
export function shouldShowDashboard({ permissions, isAdmin, pathname }) {
  if (isAdmin) return true;
  if (!permissions) return false;
  return isPermitted(permissions.panels, panelIdFromPath(pathname));
}

/**
 * Component names Home Assistant gives a panel that renders a dashboard.
 *
 * `lovelace` is a dashboard added by hand; `home` is the default dashboard on
 * an instance with no legacy overview. Both were read off 192.168.2.6 running
 * HA 2026.7.2.
 *
 * This is the one list here that names Home Assistant's own vocabulary, so it
 * is the one that will go stale. It is deliberately kept out of every decision
 * about hiding: a name missing from this list costs a diagnostic, never a
 * Permission.
 */
export const DASHBOARD_COMPONENT_NAMES = Object.freeze(["lovelace", "home"]);

/**
 * Whether the panel this path routes to is one that renders a dashboard.
 *
 * Used only to tell "this dashboard should have been hidden and was not" —
 * a defect worth reporting — from "there is no dashboard on this page", which
 * is the ordinary case on every other panel.
 *
 * Answers "yes" for a path that names no panel: the browser is on "/" and Home
 * Assistant has not yet rewritten it to whichever dashboard it serves. Answers
 * "no" for a panel the given map does not hold, because the Filters run
 * against a `hass.panels` the sidebar filter has already filtered, and a panel
 * missing from it is a panel nothing can be claimed about.
 *
 * That last case is a known limit of the diagnostic, not of the hiding.
 * filterPanels() keeps the routed panel as an anchor, so the map answers for
 * the page the browser loaded; after a client-side navigation the anchor is
 * stale (issue #6, Mechanism B) and this quietly answers "no", which costs a
 * warning that would have been earned. It never costs a Permission: whether
 * content is hidden is decided by shouldShowDashboard() alone.
 *
 * @param {object} args
 * @param {Record<string, object>|null} args.panels hass.panels as this browser has it
 * @param {string} args.pathname e.g. "/home"
 * @returns {boolean}
 */
export function isDashboardPath({ panels, pathname }) {
  const panelId = panelIdFromPath(pathname);
  if (panelId === null) return true;
  const panel = (panels || {})[panelId];
  if (!panel) return false;
  return DASHBOARD_COMPONENT_NAMES.includes(panel.component_name);
}
