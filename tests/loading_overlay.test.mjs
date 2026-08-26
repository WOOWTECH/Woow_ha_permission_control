/**
 * The loading overlay lets an administrator out on its own (issue #15).
 *
 * Run:  node --test tests/loading_overlay.test.mjs
 *
 * `ha_sidebar_filter.js` puts an opaque, full-viewport overlay up on every Home
 * Assistant page, synchronously, above its own imports — before anyone knows
 * who the user is. The only code that takes it down is at the end of `init()`,
 * past two dynamic imports, a permissions fetch, a filter application and five
 * subscriptions. Anything that throws on that path strands the overlay for the
 * life of the page, with no timeout, and administrators are covered by it too —
 * on every page, including the Permission Manager panel, the one screen that
 * could fix whatever caused it.
 *
 * So the release for an administrator has to sit *above* the imports and depend
 * on nothing below them. That region cannot be imported: it is the top of a
 * module whose next statement is a top-level `await import()` of assets that
 * only exist behind a running Home Assistant. So these tests do what
 * tests/frontend_assets.test.mjs and tests/routing_anchor.test.mjs do with
 * wiring a browser is needed to reach — read the shipped source as text — and
 * then go one step further: they *run* that text against a fake document, so
 * what is proved is the behaviour of the real prologue and not of a copy of it
 * living in the test.
 *
 * What is deliberately not tested here, because it is deliberately unchanged:
 * what a non-admin sees when the Filter never reports. That is issue #12's
 * question, and answering it by accident is how the current behaviour arrived.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const SIDEBAR_FILTER = readFileSync(
  new URL(
    "../custom_components/ha_permission_manager/frontend/ha_sidebar_filter.js",
    import.meta.url,
  ),
  "utf8",
);

const OVERLAY_ID = "perm-loading-overlay";
const START_MARKER = "// === IMMEDIATE LOADING OVERLAY ===";
const END_MARKER = "// === END IMMEDIATE LOADING OVERLAY ===";

/**
 * The part of the module that runs before its first `await import()`, sliced
 * out between the two markers. Everything the overlay needs in order to survive
 * an import that never resolves has to be inside this slice.
 */
const PROLOGUE = (() => {
  const start = SIDEBAR_FILTER.indexOf(START_MARKER);
  const end = SIDEBAR_FILTER.indexOf(END_MARKER);
  assert.ok(start !== -1, "ha_sidebar_filter.js marks the overlay region");
  assert.ok(end !== -1, "ha_sidebar_filter.js marks the end of the overlay region");
  assert.ok(end > start, "the overlay region ends after it begins");
  return SIDEBAR_FILTER.slice(start, end);
})();

/**
 * A document just real enough for the prologue: it appends, it finds by id, it
 * answers `home-assistant`, and it remembers what was removed.
 *
 * `hass` starts absent and the test assigns it, because the whole question is
 * what the prologue does across the window where Home Assistant has not yet
 * said who the user is.
 */
function makeBrowser({ hasBody = true } = {}) {
  const appended = [];
  const domReadyListeners = [];
  const live = () => appended.filter((el) => !el.removed);

  const state = { hass: undefined };
  const body = { appendChild: (el) => appended.push(el) };
  const warnings = [];

  const attributes = new Set();
  const documentElement = {
    setAttribute: (name) => attributes.add(name),
    hasAttribute: (name) => attributes.has(name),
  };

  const document = {
    documentElement,
    // A module script runs before DOMContentLoaded but after the parser has
    // built the body, so `hasBody` is the normal case. The other one is a body
    // that only exists once DOMContentLoaded has fired.
    body: hasBody ? body : null,
    createElement: () => ({
      id: "",
      style: {},
      removed: false,
      remove() {
        this.removed = true;
      },
    }),
    getElementById: (id) => live().find((el) => el.id === id) || null,
    querySelector: (selector) => {
      if (selector !== "home-assistant") return null;
      return state.hass === undefined ? null : { hass: state.hass };
    },
    querySelectorAll: (selector) => {
      assert.ok(selector.startsWith("#"), "only id selectors are understood here");
      return live().filter((el) => el.id === selector.slice(1));
    },
    addEventListener: (name, fn) => {
      if (name === "DOMContentLoaded") domReadyListeners.push(fn);
    },
  };

  const window = { matchMedia: () => ({ matches: false }) };

  const timers = new Map();
  let nextTimer = 1;
  const setInterval = (fn) => {
    timers.set(nextTimer, fn);
    return nextTimer++;
  };
  const clearInterval = (id) => timers.delete(id);

  return {
    state,
    /** The overlays still in the document. */
    overlays: () => live().filter((el) => el.id === OVERLAY_ID),
    /** What the prologue has said on the console. */
    warnings: () => warnings,
    /** How many polls are still scheduled. */
    polling: () => timers.size,
    /** Run every scheduled poll, `count` times. */
    tick: (count = 1) => {
      for (let i = 0; i < count; i += 1) {
        for (const fn of [...timers.values()]) fn();
      }
    },
    /** Fire DOMContentLoaded, for the case where there was no body yet. */
    domReady: () => {
      document.body = body;
      domReadyListeners.forEach((fn) => fn());
    },
    /** Evaluate the shipped prologue against this document. */
    run: () => {
      new Function(
        "document",
        "window",
        "setInterval",
        "clearInterval",
        "console",
        PROLOGUE,
      )(document, window, setInterval, clearInterval, {
        warn: (message) => warnings.push(message),
      });
    },
  };
}

// === The release is where it has to be ===

test("the overlay and its release both run before the first import", () => {
  const firstImport = SIDEBAR_FILTER.indexOf("await import(");
  assert.ok(firstImport !== -1, "the module pulls its policy in dynamically");
  assert.ok(
    SIDEBAR_FILTER.indexOf(END_MARKER) < firstImport,
    "an import that never resolves is the failure the release exists to " +
      "survive, so all of it has to be above the first one",
  );
});

test("the release calls nothing defined below the imports", () => {
  assert.doesNotMatch(
    PROLOGUE,
    /removeLoadingOverlay\(/,
    "removeLoadingOverlay() lives inside the IIFE below the imports; reaching " +
      "for it here would make the release depend on the code it is a backstop for",
  );
});

// === What it does in a browser ===

test("the overlay goes up on a page that has none", () => {
  const browser = makeBrowser();
  browser.run();
  assert.equal(browser.overlays().length, 1);
});

test("a second module does not add a second overlay", () => {
  const browser = makeBrowser();
  browser.run();
  browser.run();
  assert.equal(browser.overlays().length, 1);
});

test("an administrator is let out without the code below the imports running", () => {
  const browser = makeBrowser();
  browser.run();

  // Home Assistant has not said who this is yet: the overlay stays.
  browser.tick(5);
  assert.equal(browser.overlays().length, 1, "nobody is known yet");

  browser.state.hass = { user: { id: "u1", is_admin: true } };
  browser.tick();

  assert.equal(browser.overlays().length, 0, "an administrator is never filtered");
  assert.equal(browser.polling(), 0, "and there is nothing left to watch for");
});

test("a half-built hass does not count as knowing who the user is", () => {
  const browser = makeBrowser();
  browser.run();

  browser.state.hass = {};
  browser.tick(3);
  assert.equal(browser.overlays().length, 1, "no user yet is not a non-admin");
  assert.equal(browser.polling(), 1, "so it keeps watching");

  browser.state.hass = { user: { id: "u1", is_admin: true } };
  browser.tick();
  assert.equal(browser.overlays().length, 0);
});

test("a non-admin is left exactly as they were — that is issue #12's call", () => {
  const browser = makeBrowser();
  browser.run();

  browser.state.hass = { user: { id: "u2", is_admin: false } };
  browser.tick(3);

  assert.equal(browser.overlays().length, 1, "the overlay is not this ticket's to lift");
  assert.equal(browser.polling(), 0, "who this is will not change without a reload");
});

test("a hass that is slow to arrive is still waited for, and said out loud", () => {
  // There is no deadline that is both short enough to help and long enough to
  // be safe: waitForHass() starts its own 15-second clock only once both
  // imports have resolved, so anything this could give up on is a load that
  // might still be healthy — and giving up would strand the administrator this
  // is here to free.
  const browser = makeBrowser();
  browser.run();

  browser.tick(400); // 40s at a 100ms poll

  assert.equal(browser.polling(), 1, "the watch is still up");
  assert.equal(browser.warnings().length, 1, "and it has said so, once");
  assert.match(browser.warnings()[0], /SidebarFilter/);

  browser.state.hass = { user: { id: "u1", is_admin: true } };
  browser.tick();

  assert.equal(browser.overlays().length, 0, "and it still lets them out");
  assert.equal(browser.warnings().length, 1, "without repeating itself");
});

test("a second copy of this file cannot re-cover a released administrator", () => {
  // Two cache-buster queries on one page are two modules and one document. If
  // the release were remembered in a variable, the second module's overlay —
  // still pending on DOMContentLoaded, so invisible to the first module's
  // removal — would land on top of the administrator just freed.
  const first = makeBrowser({ hasBody: false });
  first.run();
  first.run();

  first.state.hass = { user: { id: "u1", is_admin: true } };
  first.tick();
  first.domReady();

  assert.equal(first.overlays().length, 0);
});

test("a document with no body yet still gets both the overlay and the release", () => {
  const browser = makeBrowser({ hasBody: false });
  browser.run();
  browser.domReady();

  assert.equal(browser.overlays().length, 1, "the overlay waits for the body");

  browser.state.hass = { user: { id: "u1", is_admin: true } };
  browser.tick();

  assert.equal(browser.overlays().length, 0);
});

test("an overlay still waiting for a body is not put up after the release", () => {
  // The release removes the overlays it can see. An append pending on
  // DOMContentLoaded is one it cannot, and it would land afterwards — an
  // administrator stranded by the very code meant to let them out.
  const browser = makeBrowser({ hasBody: false });
  browser.run();

  browser.state.hass = { user: { id: "u1", is_admin: true } };
  browser.tick();
  browser.domReady();

  assert.equal(browser.overlays().length, 0);
});
