/**
 * HA Permission Manager - Filter lifecycle
 *
 * What a Filter must undo before it runs again (issue #5, ADR-0007).
 *
 * Home Assistant replaces its `home-assistant` element on logout/login, and a
 * Filter that watches for that re-initialises when it happens. Re-initialising
 * used to register a second copy of everything — five WebSocket subscriptions,
 * two DOM listeners and a wrapper around `history.pushState` — with no teardown
 * anywhere, so the registrations accumulated for the life of the tab.
 *
 * The three answers here differ, because the three registrations do:
 *
 * - A WebSocket subscription belongs to a connection that a logout closes, so
 *   it has to be made again — and therefore released again. `createSubscriptions`
 *   holds the unsubscribe function each one resolves to.
 * - The navigation hooks sit on `window`, `document` and `history`, none of
 *   which the re-initialisation replaces. So they are installed once and stay,
 *   and `installNavigationHooks` is a no-op every time after the first.
 * - The unfiltered baseline is not a registration at all, but it leaks on the
 *   same path: a reset re-derives it from `hass.panels`, which by then is the
 *   map the Filter itself produced. `markFiltered` says which map that is, and
 *   `nextBaseline` refuses to take a baseline from one.
 *
 * Unlike permission_policy.js, this module is not pure: it hooks the objects it
 * is handed, and it reaches for two globals — `setTimeout` as the default
 * scheduler, and `console` to report an unsubscribe that failed. It touches no
 * DOM and no hass of its own, which is what lets
 * tests/filter_lifecycle.test.mjs drive all of it without a browser.
 *
 * Loaded as an ES module — Home Assistant pulls the Filters in with import().
 */

/**
 * The set of WebSocket subscriptions one run of a Filter holds.
 *
 * `subscribeEvents` resolves to an unsubscribe function rather than returning
 * one, so what is held is the promise. Everything below follows from that: a
 * reset that beats the subscription still has to unsubscribe it, and a
 * subscription that never arrived must not stop the reset.
 */
export function createSubscriptions() {
  /** Promises of an unsubscribe function, or of null when there is none. */
  let held = [];

  /**
   * Swallow a rejection here rather than at release time, so a subscription
   * that fails is not an unhandled rejection while nothing is awaiting it.
   */
  const settled = (subscription) =>
    Promise.resolve(subscription).then(
      (unsubscribe) => (typeof unsubscribe === "function" ? unsubscribe : null),
      (err) => {
        console.debug("[FilterLifecycle] Subscription never arrived:", err);
        return null;
      },
    );

  return {
    /**
     * Hold a subscription: whatever `subscribeEvents` returned, or a bare
     * unsubscribe function.
     */
    add(subscription) {
      held.push(settled(subscription));
    },

    /**
     * Unsubscribe everything held, and hold nothing afterwards.
     *
     * The list is taken synchronously so that the run which follows this reset
     * — init() starts long before these promises settle — registers onto an
     * empty set rather than into the one being released.
     */
    release() {
      const releasing = held;
      held = [];
      return Promise.all(
        releasing.map(async (pending) => {
          const unsubscribe = await pending;
          if (!unsubscribe) return;
          try {
            await unsubscribe();
          } catch (err) {
            // A logout closes the connection before anything gets to leave it
            // tidily. That is ordinary, and it must not strand the rest.
            console.debug("[FilterLifecycle] Unsubscribe failed:", err);
          }
        }),
      );
    },
  };
}

/** Whether this `history` object already carries the hooks. */
const NAVIGATION_HOOKS = Symbol.for("ha_permission_manager.navigation_hooks");

/**
 * How long to let Home Assistant's router settle before reading the URL.
 * `pushState` returns before the page it names has resolved, and the check it
 * schedules reads `location.pathname`.
 */
const ROUTER_SETTLE_MS = 150;

/**
 * Report client-side navigations to `onNavigate`, hooking `window` once.
 *
 * Returns true when the hooks were installed, false when they were already
 * there. Installing twice is the defect this exists to prevent: the second
 * wrapper captures the first as "the original", so the wrappers nest rather
 * than replace, and one `pushState` then costs one permission round trip per
 * re-initialisation the tab has seen.
 *
 * The window carries its own `document` and `history`, so it is the only thing
 * to hand over; `schedule` is `setTimeout` unless a test says otherwise.
 */
export function installNavigationHooks({
  window: win,
  onNavigate,
  schedule = setTimeout,
}) {
  const history = win.history;
  if (history[NAVIGATION_HOOKS]) return false;
  history[NAVIGATION_HOOKS] = true;

  const doc = win.document;
  const check = () => schedule(() => onNavigate(), ROUTER_SETTLE_MS);

  // The back button resolves before it fires, so this one needs no wait.
  win.addEventListener("popstate", () => onNavigate());

  doc.addEventListener("click", (event) => {
    const link = event.target?.closest?.("a");
    if (link && link.href && link.href.startsWith(win.location.origin)) {
      check();
    }
  });

  const pushState = history.pushState;
  history.pushState = function (...args) {
    pushState.apply(this, args);
    check();
  };

  return true;
}

/** Whether a panel map is one this integration produced. */
const FILTERED = Symbol.for("ha_permission_manager.filtered_panels");

/**
 * Record that this panel map is the Filter's own output, and return it.
 *
 * A symbol key is what makes this safe to hang on a map that goes on to `hass`:
 * Home Assistant iterates the panels with `Object.keys` and serialises them,
 * and neither sees a symbol.
 *
 * Non-enumerable as well, and that part is load-bearing rather than tidy. A
 * symbol key is copied by object spread like any other own enumerable
 * property, so a mark left enumerable would ride every `{ ...panels }` — Home
 * Assistant's own included — and no map derived from a filtered one could ever
 * be read as a baseline again. Non-enumerable, the mark says what it means:
 * *this object* is the one the Filter produced.
 */
export function markFiltered(panels) {
  if (!panels || typeof panels !== "object") return panels;
  try {
    Object.defineProperty(panels, FILTERED, {
      value: true,
      enumerable: false,
      configurable: true,
    });
  } catch (err) {
    // Only a frozen map can refuse, and every map marked here is one this
    // integration has just built. Losing the mark costs a re-read of the
    // baseline; throwing here would cost the filtering.
    console.debug("[FilterLifecycle] Panel map could not be marked:", err);
  }
  return panels;
}

/** Whether this panel map is one the Filter produced. */
export function isFiltered(panels) {
  return Boolean(panels && typeof panels === "object" && panels[FILTERED]);
}

/**
 * The unfiltered baseline to filter against, given what is held and what Home
 * Assistant is currently offering.
 *
 * Returns `current` by identity when the baseline stands, a fresh copy when one
 * is taken, and null when there is no baseline to be had yet. The caller tells
 * the two apart by identity, and so knows without asking twice whether the
 * candidate was refused.
 *
 * `stale` is set by a reset: the panel map may have changed while the tab was
 * logged out, so the baseline is re-derived. What it must never be re-derived
 * from is the filtered map — a baseline missing every panel the user has no
 * View level on cannot bring one back when a Permission level is granted, and
 * nothing short of a full page reload fixes it for the rest of the session.
 */
export function nextBaseline({ current = null, candidate = null, stale = false }) {
  if (current && !stale) return current;
  if (!candidate || typeof candidate !== "object") return current;
  if (isFiltered(candidate)) return current;

  // A deep copy, so that Home Assistant mutating its own map afterwards cannot
  // reach the baseline. It drops the mark above with everything else symbol-
  // keyed, which is why a baseline is never itself filtered.
  return JSON.parse(JSON.stringify(candidate));
}
