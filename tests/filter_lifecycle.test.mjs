/**
 * Unit tests for what a Filter must undo before it runs again (issue #5).
 *
 * Run:  node --test tests/filter_lifecycle.test.mjs
 *
 * Home Assistant replaces its `home-assistant` element on logout/login, and the
 * sidebar filter re-initialises when it does. Everything below exists so that a
 * re-initialisation *replaces* what the previous run registered instead of
 * adding to it: WebSocket subscriptions are released, the navigation hooks are
 * installed once and stay installed, and the unfiltered baseline is never
 * retaken from a panel map the Filter itself produced.
 *
 * These are pure-function tests. The "connection", "history" and "document"
 * here are plain objects carrying the two or three methods the module touches,
 * which is the whole surface it has.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  createSubscriptions,
  installNavigationHooks,
  isFiltered,
  markFiltered,
  nextBaseline,
} from "../custom_components/ha_permission_manager/frontend/filter_lifecycle.js";

/**
 * A stand-in for `hass.connection`, counting what is registered against it and
 * what is still live. `subscribeEvents` resolves to an unsubscribe function,
 * which is the shape Home Assistant's own returns.
 */
const fakeConnection = () => {
  const live = new Set();
  let registered = 0;
  return {
    get registered() {
      return registered;
    },
    get live() {
      return live.size;
    },
    subscribeEvents(handler, eventType) {
      registered += 1;
      const entry = { eventType, handler };
      live.add(entry);
      return Promise.resolve(() => {
        live.delete(entry);
      });
    },
  };
};

/** The five event types the sidebar filter subscribes to, in one place. */
const SIDEBAR_EVENTS = [
  "user_updated",
  "homeassistant_auth_updated",
  "lovelace_updated",
  "permission_manager_updated",
  "core_config_updated",
];

/** Let every already-resolved promise settle. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

// === Subscriptions ===

test("release unsubscribes everything that was added", async () => {
  const subscriptions = createSubscriptions();
  const calls = [];
  for (const name of ["a", "b", "c"]) {
    subscriptions.add(Promise.resolve(() => calls.push(name)));
  }

  await subscriptions.release();

  assert.deepEqual(calls, ["a", "b", "c"]);
});

test("a re-initialisation leaves one live subscription per event, not two", async () => {
  const connection = fakeConnection();
  const subscriptions = createSubscriptions();
  const subscribeAll = () => {
    for (const eventType of SIDEBAR_EVENTS) {
      subscriptions.add(connection.subscribeEvents(() => {}, eventType));
    }
  };

  subscribeAll();
  await settle();
  assert.equal(connection.live, 5, "the first run subscribes to all five");

  await subscriptions.release();
  subscribeAll();
  await settle();

  assert.equal(
    connection.live,
    5,
    "a second run replaces the first run's subscriptions rather than " +
      "doubling the traffic and the handlers",
  );
  assert.equal(
    connection.registered,
    10,
    "both runs did subscribe — the count above is teardown, not a guard that " +
      "skipped the second run",
  );
});

test("release twice unsubscribes once", async () => {
  const subscriptions = createSubscriptions();
  let calls = 0;
  subscriptions.add(Promise.resolve(() => (calls += 1)));

  await subscriptions.release();
  await subscriptions.release();

  assert.equal(calls, 1);
});

test("a subscription added after release is not released by it", async () => {
  const subscriptions = createSubscriptions();
  let released = 0;
  let kept = 0;

  subscriptions.add(Promise.resolve(() => (released += 1)));
  const releasing = subscriptions.release();
  // The Filter's reset is synchronous and init() starts before the release
  // settles, so the new run's subscriptions land on the same set mid-release.
  subscriptions.add(Promise.resolve(() => (kept += 1)));
  await releasing;

  assert.equal(released, 1);
  assert.equal(kept, 0, "the new run's subscription survives the old run's reset");
});

test("a subscription that arrives after release is still unsubscribed", async () => {
  const subscriptions = createSubscriptions();
  let calls = 0;
  let arrive;
  subscriptions.add(new Promise((resolve) => (arrive = resolve)));

  const releasing = subscriptions.release();
  arrive(() => (calls += 1));
  await releasing;

  assert.equal(
    calls,
    1,
    "subscribeEvents is async, so a reset that beats it must not leave it live",
  );
});

test("one unsubscribe that throws does not strand the rest", async () => {
  const subscriptions = createSubscriptions();
  const calls = [];
  subscriptions.add(Promise.resolve(() => calls.push("first")));
  subscriptions.add(
    Promise.resolve(() => {
      throw new Error("connection already closed");
    }),
  );
  subscriptions.add(Promise.resolve(() => calls.push("last")));

  await subscriptions.release();

  assert.deepEqual(
    calls,
    ["first", "last"],
    "a logout closes the connection, so unsubscribing on the way out is " +
      "expected to fail sometimes",
  );
});

test("a subscription that never arrived does not stop the reset", async () => {
  const subscriptions = createSubscriptions();
  let calls = 0;
  subscriptions.add(Promise.reject(new Error("connection lost")));
  subscriptions.add(Promise.resolve(() => (calls += 1)));

  await subscriptions.release();

  assert.equal(calls, 1);
});

// === Navigation hooks ===

/** A `window` carrying only what the hooks touch, its own history and document. */
const fakeBrowser = () => {
  const pushed = [];
  const listeners = [];
  const listen = (target) => (type, handler) =>
    listeners.push({ target, type, handler });
  const history = {
    pushState(...args) {
      pushed.push({ self: this, args });
    },
  };
  return {
    pushed,
    listeners,
    history,
    scheduled: [],
    win: {
      history,
      document: { addEventListener: listen("document") },
      location: { origin: "http://ha.local" },
      addEventListener: listen("window"),
    },
    fire(type, event) {
      for (const entry of listeners) {
        if (entry.type === type) entry.handler(event);
      }
    },
  };
};

/** Install the hooks on a fake browser, recording every navigation they report. */
const install = (browser, seen) =>
  installNavigationHooks({
    window: browser.win,
    onNavigate: () => seen.push("checked"),
    schedule: (fn, delay) => {
      browser.scheduled.push(delay);
      fn();
    },
  });

test("installing the hooks twice wraps pushState once", () => {
  const browser = fakeBrowser();
  const seen = [];

  assert.equal(install(browser, seen), true, "the first install takes");
  assert.equal(
    install(browser, seen),
    false,
    "the second reports that there was nothing to do",
  );

  browser.history.pushState({ page: 1 }, "", "/config");

  assert.equal(
    seen.length,
    1,
    "wrappers that nest rather than replace make one navigation cost N " +
      "get_panel_permissions round trips",
  );
  assert.equal(
    browser.pushed.length,
    1,
    "Home Assistant's own pushState still ran, once",
  );
});

test("a navigation is reported only after Home Assistant has already routed", () => {
  // This is the shape of what issue #6's Mechanism B fix can and cannot do.
  // The wrapper calls Home Assistant's own pushState *first* and schedules the
  // report after it, and popstate fires once the URL has already changed. So a
  // Filter told about a navigation here is being told about one that has
  // happened: it can repair hass.panels for the route the browser is now on,
  // and it cannot put the anchor there before Home Assistant's router looked.
  //
  // Closing that window means acting before the navigation, off permissions
  // already held. See ADR-0008.
  const browser = fakeBrowser();
  let alreadyPushed = null;

  installNavigationHooks({
    window: browser.win,
    onNavigate: () => {
      alreadyPushed = browser.pushed.length;
    },
    schedule: (fn) => fn(),
  });

  browser.history.pushState({ page: 1 }, "", "/config");

  assert.equal(
    alreadyPushed,
    1,
    "the report lands after the navigation it reports, not before it",
  );
});

test("the wrapper passes pushState its arguments and its receiver", () => {
  const browser = fakeBrowser();
  install(browser, []);

  browser.history.pushState({ page: 1 }, "", "/config");

  assert.deepEqual(browser.pushed[0].args, [{ page: 1 }, "", "/config"]);
  assert.equal(
    browser.pushed[0].self,
    browser.history,
    "history.pushState called on anything but history throws in a browser",
  );
});

test("a second install adds no second listener", () => {
  const browser = fakeBrowser();
  const seen = [];
  install(browser, seen);
  const afterFirst = browser.listeners.length;
  install(browser, seen);

  assert.equal(browser.listeners.length, afterFirst);
});

test("popstate reports a navigation", () => {
  const browser = fakeBrowser();
  const seen = [];
  install(browser, seen);

  browser.fire("popstate", {});

  assert.equal(seen.length, 1);
});

test("a click on a same-origin link reports a navigation", () => {
  const browser = fakeBrowser();
  const seen = [];
  install(browser, seen);
  const link = { href: "http://ha.local/config" };

  browser.fire("click", { target: { closest: () => link } });

  assert.equal(seen.length, 1);
  assert.deepEqual(
    browser.scheduled,
    [150],
    "the check waits for Home Assistant's router to land",
  );
});

test("a click that leaves Home Assistant reports nothing", () => {
  const browser = fakeBrowser();
  const seen = [];
  install(browser, seen);

  browser.fire("click", {
    target: { closest: () => ({ href: "https://example.com/" }) },
  });
  browser.fire("click", { target: { closest: () => null } });

  assert.equal(seen.length, 0);
});

// === The unfiltered baseline ===

/** A panel entry shaped like the ones Home Assistant puts in hass.panels. */
const panel = (urlPath) => ({
  component_name: "lovelace",
  icon: null,
  title: urlPath,
  url_path: urlPath,
  config: null,
});

/** What Home Assistant offers a user before this integration touches it. */
const unfiltered = () => ({
  home: panel("home"),
  "ha-control-panel": panel("ha-control-panel"),
  "developer-tools": panel("developer-tools"),
});

test("the first baseline is taken from Home Assistant's own map", () => {
  const candidate = unfiltered();

  const baseline = nextBaseline({ current: null, candidate, stale: true });

  assert.deepEqual(Object.keys(baseline).sort(), [
    "developer-tools",
    "ha-control-panel",
    "home",
  ]);
});

test("the baseline is a copy, so Home Assistant mutating its map cannot reach it", () => {
  const candidate = unfiltered();

  const baseline = nextBaseline({ current: null, candidate, stale: true });
  delete candidate.home;
  candidate["ha-control-panel"].title = null;

  assert.ok(baseline.home, "the panel Home Assistant dropped is still in the baseline");
  assert.equal(baseline["ha-control-panel"].title, "ha-control-panel");
});

test("a baseline that is current is not retaken", () => {
  const current = unfiltered();

  const baseline = nextBaseline({
    current,
    candidate: { home: panel("home") },
    stale: false,
  });

  assert.equal(baseline, current);
});

test("a reset takes a fresh baseline from a map the Filter did not produce", () => {
  const current = unfiltered();
  const candidate = { ...unfiltered(), weather: panel("weather") };

  const baseline = nextBaseline({ current, candidate, stale: true });

  assert.ok(baseline.weather, "a dashboard added while logged out is picked up");
});

test("a reset refuses a map the Filter produced and keeps the baseline it has", () => {
  const current = unfiltered();
  const filtered = markFiltered({ "ha-control-panel": panel("ha-control-panel") });

  const baseline = nextBaseline({ current, candidate: filtered, stale: true });

  assert.equal(
    baseline,
    current,
    "rebaselining from the filtered map bakes the filtering in: every panel " +
      "the user has no View level on is gone for the rest of the session, and " +
      "granting one back cannot bring it up again without a full reload",
  );
});

test("a copy of a filtered map is not itself marked", () => {
  const filtered = markFiltered({ home: panel("home"), weather: panel("weather") });
  const copy = { ...filtered };

  assert.equal(
    isFiltered(copy),
    false,
    "object spread copies own enumerable symbol keys like any other, so a " +
      "mark left enumerable would ride every { ...panels } Home Assistant " +
      "takes, and no map derived from a filtered one could be read as a " +
      "baseline again",
  );

  const baseline = nextBaseline({ current: null, candidate: copy, stale: true });

  assert.ok(baseline?.home, "a copy is a map this Filter did not produce");
  assert.equal(isFiltered(baseline), false);
});

test("with no baseline yet, a filtered map yields no baseline at all", () => {
  const baseline = nextBaseline({
    current: null,
    candidate: markFiltered({ home: panel("home") }),
    stale: true,
  });

  assert.equal(
    baseline,
    null,
    "the caller reports having no baseline rather than filtering against a " +
      "filtered one",
  );
});

test("no map is filtered until it is said to be", () => {
  assert.equal(isFiltered(unfiltered()), false);
  assert.equal(isFiltered(null), false);
  assert.equal(isFiltered(markFiltered(unfiltered())), true);
});

test("marking a map returns it, so it can be marked on the way past", () => {
  const panels = unfiltered();
  assert.equal(markFiltered(panels), panels);
});

// === The Filters' own wiring ===
//
// Everything above tests the module. What it cannot reach is the adapter that
// uses it: a sixth subscribeEvents call added later without subscriptions.add,
// or a resetState() that stops releasing, regresses issue #5 silently and no
// test above would notice. Reaching that code needs a browser and a Home
// Assistant, so these read it as text instead — the same way
// frontend_assets.test.mjs holds the cache-buster rule.

const source = (name) =>
  readFileSync(
    new URL(`../custom_components/ha_permission_manager/frontend/${name}`, import.meta.url),
    "utf8",
  );

const LIFECYCLE = source("filter_lifecycle.js");
const SIDEBAR_FILTER = source("ha_sidebar_filter.js");
const SIDEBAR_TITLE = source("sidebar-title.js");

test("every event the sidebar filter subscribes to is held", () => {
  // Everything on the same line before the call, which is where the holding
  // goes: `subscriptions.add(hass.connection.subscribeEvents(…`.
  const calls = [...SIDEBAR_FILTER.matchAll(/^(.*?)\w+\.subscribeEvents\(/gm)];

  assert.equal(
    calls.length,
    SIDEBAR_EVENTS.length,
    `the sidebar filter makes ${calls.length} subscribeEvents calls; this ` +
      `test and ADR-0007 both say ${SIDEBAR_EVENTS.length}`,
  );
  for (const [, before] of calls) {
    assert.match(
      before,
      /subscriptions\.add\(/,
      `a subscribeEvents call reached as "${before.trim()}…" is not held, so ` +
        "a reset cannot release it and the next run adds a second copy",
    );
  }
});

test("resetting the sidebar filter releases what it holds", () => {
  const resetState = /function resetState\(\)\s*\{([^}]*)\}/.exec(SIDEBAR_FILTER);

  assert.ok(resetState, "ha_sidebar_filter.js defines resetState()");
  assert.match(resetState[1], /subscriptions\.release\(\)/);
});

test("the sidebar filter hooks navigation only through this module", () => {
  assert.match(SIDEBAR_FILTER, /installNavigationHooks\(/);

  for (const forbidden of [
    /addEventListener\(\s*["']popstate["']/,
    /addEventListener\(\s*["']click["']/,
    /history\.pushState\s*=/,
  ]) {
    assert.doesNotMatch(
      SIDEBAR_FILTER,
      forbidden,
      "hooks placed here are placed once per run, and the run happens again " +
        "on every logout/login — installNavigationHooks() is what makes that " +
        "once per document",
    );
  }
});

test("the title script hands the mark on with every map it copies", () => {
  // sidebar-title.js replaces hass.panels with a copy, because ha-sidebar
  // memoises on the identity of that map. Object.assign copies own enumerable
  // properties and the mark is deliberately neither enumerable nor a string
  // key, so a plain copy strips it — and the sidebar filter is then free to
  // re-read its unfiltered baseline out of a map it produced itself. That is
  // this decision's contamination, reintroduced from a file it does not cover.
  //
  // The script is a classic one loaded by add_extra_js_url, so it cannot
  // import markFiltered(); the global symbol registry is the contract, and the
  // string has to be the same one.
  const mark = /Symbol\.for\("(ha_permission_manager\.filtered_panels)"\)/;
  const declared = mark.exec(LIFECYCLE);
  assert.ok(declared, "filter_lifecycle.js marks a map with a registered symbol");

  assert.ok(
    SIDEBAR_TITLE.includes(`Symbol.for("${declared[1]}")`),
    "sidebar-title.js reads the same mark this module writes",
  );

  assert.doesNotMatch(
    SIDEBAR_TITLE,
    /panels:\s*Object\.assign\(\{\},/,
    "a bare Object.assign of the panel map drops the mark; the copy that goes " +
      "on hass has to carry it",
  );
});
