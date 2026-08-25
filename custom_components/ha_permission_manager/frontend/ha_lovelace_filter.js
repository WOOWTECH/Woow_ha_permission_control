/**
 * HA Permission Manager - Lovelace Filter
 * Hides dashboard content for users with restricted permissions
 *
 * The decision lives in permission_policy.js and the search in shadow_dom.js;
 * this file is the adapter that reads the browser and acts on it.
 *
 * v2.7.11 - Find the dashboard by looking for it, and say so when it is not
 *           found (issue #10)
 * v2.7.12 - Everything this file pulls in is busted with it (issue #9)
 */

/** This module's cache buster, carried onto everything it pulls in (ADR-0006). */
const ASSET_VERSION_QUERY = new URL(import.meta.url).search;

// See the same guard in ha_sidebar_filter.js: a Filter served without `?v=`
// imports unbusted modules, and an unfiltered dashboard looks entirely normal.
if (!ASSET_VERSION_QUERY) {
  console.warn(
    "[LovelaceFilter] Loaded with no version query, so what this file imports " +
    "cannot be cache-busted. A stale copy leaves the dashboard unfiltered."
  );
}

const { isDashboardPath, shouldShowDashboard } = await import(
  `./permission_policy.js${ASSET_VERSION_QUERY}`
);
const { findByLocalName } = await import(`./shadow_dom.js${ASSET_VERSION_QUERY}`);

(function() {
  "use strict";

  // Loading overlay is owned by ha_sidebar_filter.js — do not create here.
  // This prevents the race condition where duplicate overlays cause permanent UI blocking.

  /**
   * The element Home Assistant renders a dashboard into, whichever panel is
   * hosting it. This is the only Home Assistant element name this Filter still
   * knows, and not finding it is reported rather than shrugged off.
   *
   * A list of one, because the next rename should be a name added here rather
   * than a traversal rewritten — that is the whole lesson of issue #10. Its
   * counterpart is DASHBOARD_COMPONENT_NAMES in permission_policy.js, which
   * names the same concept in Home Assistant's other vocabulary; a rename that
   * reaches one usually reaches the other.
   */
  const DASHBOARD_ROOTS = ["hui-root"];

  /** The Access Denied Filter's element, which already replaces a denied page. */
  const ACCESS_DENIED_ROOT = "ha-access-denied";

  /** How long a denied dashboard may stay unhidden before that is a defect. */
  const UNREACHABLE_GRACE_MS = 3000;

  /** Floor on how often DOM mutations may re-run the filter. */
  const CHECK_THROTTLE_MS = 150;

  // State
  let permissions = null;
  let isAdmin = false;
  let initialized = false;
  let contentHidden = false;
  let hiddenRoot = null;
  let lastPath = null;
  let unreachableSince = null;
  let unreachableReportedPath = null;
  let unreachableTimer = null;
  let checkTimer = null;
  let lastCheck = 0;

  /**
   * Wait for Home Assistant frontend to be ready
   */
  function waitForHass(maxWait = 15000) {
    return new Promise((resolve) => {
      const start = Date.now();

      function check() {
        const haMain = document.querySelector("home-assistant");
        if (haMain && haMain.hass && haMain.hass.user) {
          resolve(haMain.hass);
          return;
        }

        if (Date.now() - start > maxWait) {
          console.warn("[LovelaceFilter] Timeout waiting for hass");
          resolve(null);
          return;
        }

        setTimeout(check, 100);
      }

      check();
    });
  }

  /**
   * Fetch all permissions from WebSocket API
   */
  async function fetchAllPermissions() {
    try {
      const hass = await waitForHass();
      if (!hass) return null;

      const result = await hass.callWS({
        type: "permission_manager/get_all_permissions",
      });

      isAdmin = result.is_admin || false;
      permissions = result;

      return result;
    } catch (err) {
      console.error("[LovelaceFilter] Failed to fetch permissions:", err);
      return null;
    }
  }

  /**
   * Check if user should see lovelace content
   * Returns TRUE if content should be VISIBLE
   *
   * The decision itself lives in permission_policy.js, so this Filter and the
   * sidebar filter resolve the routed panel the same way and cannot disagree
   * about which Permission governs the dashboard.
   */
  function shouldShowContent() {
    return shouldShowDashboard({
      permissions,
      isAdmin,
      pathname: window.location.pathname,
    });
  }

  /**
   * The dashboard on screen, wherever Home Assistant has put it.
   *
   * Not a path through the element hierarchy: that hierarchy is not an API.
   * Between releases `partial-panel-resolver` lost its shadow root and the
   * default dashboard moved from `ha-panel-lovelace` to `ha-panel-home`, and a
   * spelt-out walk answered "nothing here" to both — silently, for a whole
   * release (issue #10).
   */
  function findDashboardRoot() {
    return findByLocalName(document.body, DASHBOARD_ROOTS);
  }

  /**
   * Apply the filter to whatever is on screen.
   *
   * There is deliberately no list of paths that carry a dashboard either. Home
   * Assistant serves the default one at /home here and served it at /lovelace
   * before; the Permission store says whether to hide, and the page itself
   * says whether there is a dashboard to hide.
   */
  function applyDashboardFilter() {
    const path = window.location.pathname;
    if (path !== lastPath) {
      lastPath = path;
      clearUnreachable();
    }

    if (shouldShowContent()) {
      removeContentHiding();
      return;
    }

    // Searched every time rather than short-circuiting on the element already
    // hidden: at 30 nodes and 0.02ms on a live dashboard the search is cheaper
    // than the reasoning about when a remembered element goes stale.
    const dashboardRoot = findDashboardRoot();
    if (!dashboardRoot) {
      reportUnreachableDashboard(path);
      return;
    }

    // Hide the dashboard element itself rather than parts of its insides. Its
    // `#view` and `.toolbar` are Home Assistant's internals in exactly the way
    // the traversal was, and the message below stands in for the whole page.
    dashboardRoot.style.display = "none";
    hiddenRoot = dashboardRoot;
    clearUnreachable();
    showNoAccessMessage();
    contentHidden = true;
  }

  /**
   * Report a denied dashboard this Filter failed to hide.
   *
   * A decision of "hide" that hides nothing is a defect, not a no-op — the
   * whole of issue #10 is that the old traversal returned early without a
   * word. Two things keep this from crying wolf: a grace period, because a
   * dashboard that has not rendered yet is not a missing one, and the routed
   * panel having to be one that renders a dashboard at all.
   */
  function reportUnreachableDashboard(path) {
    const now = Date.now();

    if (unreachableSince === null) {
      unreachableSince = now;
      // DOM mutations may stop before the grace period is up. Come back once.
      if (unreachableTimer === null) {
        unreachableTimer = setTimeout(() => {
          unreachableTimer = null;
          applyDashboardFilter();
        }, UNREACHABLE_GRACE_MS + 100);
      }
      return;
    }

    if (now - unreachableSince < UNREACHABLE_GRACE_MS) return;
    if (unreachableReportedPath === path) return;
    if (!isDashboardPath({ panels: currentPanels(), pathname: path })) return;

    unreachableReportedPath = path;
    console.warn(
      "[LovelaceFilter] " + path + " is denied for this user, but no <" +
        DASHBOARD_ROOTS.join(">, <") + "> was found on the page, so its content " +
        "has not been hidden. Home Assistant's element names have most likely " +
        "changed; until this Filter is taught the new one, the Access Denied " +
        "overlay is the only layer covering this page.",
    );
  }

  /**
   * The panel map this browser holds, as the sidebar filter has left it.
   *
   * `home-assistant` and its `hass` are Home Assistant's one documented entry
   * point — waitForHass() above reads the same two — so this is not the kind
   * of hierarchy walk findDashboardRoot() exists to avoid. Naming it keeps
   * that distinction visible.
   *
   * Note what the sidebar filter has left: filterPanels() drops the panels
   * this user is denied and keeps only the routed one, as an anchor. So this
   * map answers for the page the browser loaded, and can be missing the panel
   * after a client-side navigation — the gap issue #6 owns.
   */
  function currentPanels() {
    return document.querySelector("home-assistant")?.hass?.panels;
  }

  /** Forget an unhidden dashboard, so the next one is reported on its own merits. */
  function clearUnreachable() {
    unreachableSince = null;
    unreachableReportedPath = null;
    if (unreachableTimer !== null) {
      clearTimeout(unreachableTimer);
      unreachableTimer = null;
    }
  }

  /**
   * Put the "no access" message over the page, once, and only when nothing
   * else is already saying it.
   *
   * The Access Denied Filter replaces a denied page outright, and it gets
   * there first on any full page load. Painting this message on top of it is
   * two answers to one question — which is what happened the moment issue #10
   * was fixed, because the broken traversal had meant this never ran on the
   * default dashboard at all. The message earns its place only where the
   * overlay does not run, such as a client-side navigation into a denied
   * dashboard (issue #6, Mechanism B).
   */
  function showNoAccessMessage() {
    const existing = document.getElementById("perm-manager-no-access-msg");

    if (findByLocalName(document.body, ACCESS_DENIED_ROOT)) {
      if (existing) existing.remove();
      return;
    }

    if (existing) return;

    const messageContainer = document.createElement("div");
    messageContainer.id = "perm-manager-no-access-msg";
    messageContainer.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      text-align: center;
      font-size: 18px;
      color: var(--secondary-text-color, #666);
      z-index: 1000;
      padding: 20px;
    `;

    // Build DOM structure safely without innerHTML (security fix)
    const iconWrapper = document.createElement("div");
    iconWrapper.style.marginBottom = "10px";
    const icon = document.createElement("ha-icon");
    icon.setAttribute("icon", "mdi:shield-lock");
    icon.style.cssText = "--mdc-icon-size: 48px;";
    iconWrapper.appendChild(icon);

    const titleDiv = document.createElement("div");
    titleDiv.textContent = "無可用內容";

    const subtitleDiv = document.createElement("div");
    subtitleDiv.style.cssText = "font-size: 14px; margin-top: 8px;";
    subtitleDiv.textContent = "請聯繫管理員獲取訪問權限";

    messageContainer.appendChild(iconWrapper);
    messageContainer.appendChild(titleDiv);
    messageContainer.appendChild(subtitleDiv);

    document.body.appendChild(messageContainer);
  }

  /**
   * Remove content hiding
   */
  function removeContentHiding() {
    clearUnreachable();
    if (!contentHidden) return;

    const msg = document.getElementById("perm-manager-no-access-msg");
    if (msg) msg.remove();

    // Restore the element that was hidden, rather than going looking for it
    // again: whatever Home Assistant has re-rendered since, this is the one
    // whose style this Filter changed.
    if (hiddenRoot) {
      hiddenRoot.style.display = "";
      hiddenRoot = null;
    }

    contentHidden = false;
  }

  /**
   * Run the filter, at most every CHECK_THROTTLE_MS.
   *
   * A rendered dashboard mutates constantly and the filter searches the shadow
   * tree, so the observer below hands its work to this rather than doing it.
   */
  function scheduleFilterCheck() {
    if (checkTimer !== null) return;
    const wait = Math.max(0, CHECK_THROTTLE_MS - (Date.now() - lastCheck));
    checkTimer = setTimeout(() => {
      checkTimer = null;
      lastCheck = Date.now();
      applyDashboardFilter();
    }, wait);
  }

  /**
   * Subscribe to permission changes via event bus (replaces 5-second polling)
   */
  let lastPermHash = null;

  async function subscribeToPermissionChanges() {
    const hass = await waitForHass();
    if (!hass || !hass.connection) return;

    hass.connection.subscribeEvents(async () => {
      const result = await fetchAllPermissions();
      if (!result) return;
      const newHash = JSON.stringify(result);
      if (newHash !== lastPermHash) {
        lastPermHash = newHash;
        applyDashboardFilter();
      }
    }, "permission_manager_updated");
  }

  /**
   * Initialize
   */
  async function init() {
    if (initialized) return;
    initialized = true;

    await fetchAllPermissions();
    lastPermHash = JSON.stringify(permissions);
    applyDashboardFilter();
    await subscribeToPermissionChanges();

    // Watch for navigation. scheduleFilterCheck() runs immediately when the
    // last check is already older than the throttle, which after a navigation
    // it almost always is.
    window.addEventListener("popstate", scheduleFilterCheck);

    // Observe DOM changes to catch when a dashboard renders (replaces 1-second polling)
    const observer = new MutationObserver(scheduleFilterCheck);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // Start when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Debug object removed for security - do not expose internal state in production
})();
