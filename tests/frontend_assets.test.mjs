/**
 * The cache-buster invariant over every frontend asset (issue #9).
 *
 * Run:  node --test tests/frontend_assets.test.mjs
 *
 * These tests read source as text rather than importing it, because the asset
 * graph spans both languages: `__init__.py` names the entry points, and the JS
 * modules name what those entry points pull in. Busting the entry points alone
 * is not enough — a browser holding a stale copy of a module an entry point
 * imports evaluates neither, so a half-busted graph is a panel that renders
 * nothing. When issue #9 wrote this rule the modules at stake were the
 * Filters, and the failure was fail-open: nothing filtered and a non-admin saw
 * every panel. The Panel Gate ended that class (#20) and the rule outlives it,
 * because the graph is still two languages wide and still only correct if one
 * version bump moves all of it.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const COMPONENT = path.join(REPO, "custom_components", "ha_permission_manager");
const FRONTEND = path.join(COMPONENT, "frontend");

const read = (...parts) => readFileSync(path.join(...parts), "utf8");

/** Pull a plain string constant out of const.py. */
const constant = (name) => {
  const match = new RegExp(`^${name} = "([^"]+)"`, "m").exec(
    read(COMPONENT, "const.py"),
  );
  assert.ok(match, `const.py defines ${name}`);
  return match[1];
};

const PANEL_VERSION = constant("PANEL_VERSION");
const FRONTEND_URL_BASE = constant("FRONTEND_URL_BASE");

/** Every .js file served out of the frontend directory. */
const MODULES = readdirSync(FRONTEND).filter((name) => name.endsWith(".js"));

/**
 * The one way a module carries its own cache buster onto what it pulls in.
 * Spelt out here so that a second, subtly different spelling is a test failure
 * rather than an asset that quietly stops being busted.
 */
const ASSET_VERSION_DECLARATION =
  "const ASSET_VERSION_QUERY = new URL(import.meta.url).search;";

/** What a first-party specifier must end with, inside a template literal. */
const BUSTER = "${ASSET_VERSION_QUERY}";

/** A backtick, named rather than written, so it can sit inside one. */
const TICK = String.fromCharCode(96);

/**
 * Quoted references to a first-party .js asset, in whichever of the two
 * spellings the frontend uses: relative (`./x.js`) or rooted at the mount
 * point (`/ha_permission_manager_frontend/x.js`). Matching only inside quotes
 * is what keeps these files' own prose about each other out of the results.
 *
 * A `../` specifier would escape this, and nothing in `frontend/` has reason
 * to reach outside itself — the directory is flat and is the whole served
 * surface. If that ever stops being true, this pattern is what to widen.
 */
const firstPartySpecifiers = (source) => {
  const base = FRONTEND_URL_BASE.replace(/[.\-]/g, "\\$&");
  const quote = `["'\\u0060]`;
  const pattern = new RegExp(
    `(${quote})((?:\\./|${base}/)[\\w./-]+\\.js)([^"'\\u0060]*)\\1`,
    "g",
  );
  return [...source.matchAll(pattern)].map((m) => ({
    quote: m[1],
    asset: m[2],
    suffix: m[3],
    text: m[0],
  }));
};

/**
 * Every string literal in `__init__.py` that names a .js file, however it is
 * written. Deliberately not scoped to the `f"{FRONTEND_URL_BASE}/…"` form:
 * a registration spelt as a bare literal URL is exactly the case that would
 * otherwise slip past unbusted.
 */
const registeredAssets = () => {
  const source = read(COMPONENT, "__init__.py");
  return [...source.matchAll(/(f?)"([^"\n]*\.js[^"\n]*)"/g)].map((m) => ({
    isFString: m[1] === "f",
    url: m[2],
    text: m[0],
  }));
};

test("manifest.json ships the version const.py busts with", () => {
  const manifest = JSON.parse(read(COMPONENT, "manifest.json"));
  assert.equal(
    manifest.version,
    PANEL_VERSION,
    "a release that bumps one and not the other serves assets under a " +
      "version nothing else in the integration knows",
  );
});

test("every asset __init__.py registers carries the panel version", () => {
  const registrations = registeredAssets();

  assert.ok(registrations.length > 0, "__init__.py registers frontend assets");
  for (const { isFString, url, text } of registrations) {
    assert.ok(
      isFString,
      `${text} names a frontend asset as a plain literal — every registration ` +
        "goes through FRONTEND_URL_BASE and PANEL_VERSION, so that one bump " +
        "moves the whole graph at once",
    );
    assert.match(
      url,
      /^\{FRONTEND_URL_BASE\}\/[\w.-]+\.js\?v=\{PANEL_VERSION\}$/,
      `${text} is not of the form ` +
        'f"{FRONTEND_URL_BASE}/<name>.js?v={PANEL_VERSION}"',
    );
  }
});

test("every registered asset is a file the frontend directory actually serves", () => {
  for (const { url, text } of registeredAssets()) {
    const name = url.replace("{FRONTEND_URL_BASE}/", "").split("?")[0];
    assert.ok(
      MODULES.includes(name),
      `${text} registers ${name}, which is not in frontend/ — a registration ` +
        "of an asset that 404s takes the module graph down with it",
    );
  }
});

test("no frontend module pulls in a first-party asset unbusted", () => {
  for (const name of MODULES) {
    for (const ref of firstPartySpecifiers(read(FRONTEND, name))) {
      assert.equal(
        ref.suffix,
        BUSTER,
        `${name} reaches ${ref.asset} as ${ref.text} — a specifier cannot ` +
          "read PANEL_VERSION, so it carries the buster its own URL already " +
          `has: ${ref.asset}${BUSTER}`,
      );
      assert.equal(
        ref.quote,
        TICK,
        `${name} reaches ${ref.asset} with ${ref.quote} quotes — ` +
          `${BUSTER} only interpolates inside a template literal`,
      );
    }
  }
});

test("a module that pulls in a first-party asset declares the buster once", () => {
  for (const name of MODULES) {
    const source = read(FRONTEND, name);
    const uses = firstPartySpecifiers(source).length;
    const declarations = source.split(ASSET_VERSION_DECLARATION).length - 1;

    if (uses === 0) {
      assert.equal(
        declarations,
        0,
        `${name} declares ASSET_VERSION_QUERY but pulls in nothing first-party`,
      );
      continue;
    }
    assert.equal(
      declarations,
      1,
      `${name} pulls in ${uses} first-party asset(s), so it declares the ` +
        `buster exactly once, as: ${ASSET_VERSION_DECLARATION}`,
    );
  }
});

test("every frontend module is reached by a registration or another module", () => {
  const registered = new Set(
    registeredAssets().map((r) =>
      r.url.replace("{FRONTEND_URL_BASE}/", "").split("?")[0],
    ),
  );
  const imported = new Set(
    MODULES.flatMap((name) =>
      firstPartySpecifiers(read(FRONTEND, name)).map((ref) =>
        path.posix.basename(ref.asset),
      ),
    ),
  );

  for (const name of MODULES) {
    assert.ok(
      registered.has(name) || imported.has(name),
      `frontend/${name} is neither registered by __init__.py nor imported by ` +
        "another module — either it is dead, or it is reached by a spelling " +
        "this check cannot see, and an asset nothing here can see is an asset " +
        "nothing here can keep busted",
    );
  }
});

/**
 * Every `add_extra_js_url()` call in the integration, wherever it is written.
 *
 * Recursive and across every Python module, not just `__init__.py`, for the
 * reason tests/test_permission_store.py walks the package rather than one
 * file: the registration that matters is the one added somewhere nobody
 * thought to look. A call whose argument is not a string literal comes back
 * with a null url rather than being skipped, so "registered from a variable"
 * fails the test below instead of passing through it.
 */
const injectedAssets = () => {
  const modules = readdirSync(COMPONENT, { recursive: true }).filter((name) =>
    String(name).endsWith(".py"),
  );

  return modules.flatMap((name) => {
    const source = read(COMPONENT, String(name));
    return [...source.matchAll(/add_extra_js_url\(/g)].map((call) => {
      // To the end of the call. No frontend URL contains a parenthesis, so the
      // first one closes it, and a call with no literal before it is exactly
      // the case this must not skip.
      const args = source.slice(call.index, source.indexOf(")", call.index));
      const literal = /f?"([^"\n]*\.js[^"\n]*)"/.exec(args);
      return {
        module: String(name),
        url: literal ? literal[1] : null,
        text: args.trim(),
      };
    });
  });
};

/**
 * The whole of what this integration injects into a page it does not own.
 *
 * Until v3.0.0 that was two Filters as well: ~2,400 lines deciding in the
 * browser what the Panel Gate now decides before the panel map leaves Home
 * Assistant. The decision has one owner (ADR-0011), so a second registration
 * here is either a new Filter or an old one coming back — and either way it is
 * the failure class issue #16 closed, where a user's access depends on
 * JavaScript that may not run.
 *
 * `sidebar-title.js` is not one of those: it retitles two panels this repo
 * ships, and an untranslated title is a cosmetic loss, not an unfiltered page.
 */
test("the only asset injected into every page is the sidebar title translator", () => {
  const injected = injectedAssets();

  for (const { module, url, text } of injected) {
    assert.ok(
      url,
      `${module} calls add_extra_js_url with no .js literal in it — ` +
        `${text} — so what lands on every page cannot be read from here`,
    );
  }

  assert.deepEqual(
    injected.map(({ url }) => url.replace("{FRONTEND_URL_BASE}/", "").split("?")[0]),
    ["sidebar-title.js"],
    "an asset injected on every page decides something in the browser, and " +
      "since v3.0.0 nothing about access is decided there",
  );
});
