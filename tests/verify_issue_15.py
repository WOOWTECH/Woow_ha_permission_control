#!/usr/bin/env python3
"""Live verification for issue #15: does the loading overlay let an administrator out?

The overlay is raised synchronously at the top of `ha_sidebar_filter.js`, above
its imports, before anything is known about the user. Until v2.0.7 the only
code that lifted it was at the end of `init()` — past both imports, a
permissions fetch, a filter application and five subscriptions. Anything that
threw on that path left an opaque, click-swallowing cover over the page for the
life of the page, administrators included.

So this script breaks the frontend on purpose, as the **administrator**, and
watches the overlay. Three ways of loading a page:

  control       nothing intercepted — the healthy path
  broken-link   permission_policy.js served unparseable, so `await import()`
                rejects and nothing below the imports ever runs
  broken-later  permission_policy.js served with one `export` keyword removed.
                A dynamic import of a missing name yields `undefined` rather
                than a link error, so the module evaluates and then throws
                inside applyPanels() — the exact console line issue #12
                measured on v2.0.4: `panelsEqual is not a function`

The two broken runs are the discriminator. On a healthy load the release and
`removeLoadingOverlay()` both fire, so "the overlay went" proves nothing about
which one did it. On a broken load only the release can.

The same breakage is then loaded as the **non-admin**, where the overlay is
expected to stay up on every release. Issue #15 says so explicitly: what the
overlay should do for a non-admin when a Filter never reports is #12's
question, and #15 must not answer it. That run is here to prove the answer did
not change by accident.

Usage:
  python3 tests/verify_issue_15.py --label v2.0.7-after

Configuration (a repo-root .env is read automatically):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN   admin token
  HA_TOKEN_NONADMIN   non-admin token; falls back to .ha_nonadmin_token

Read-only: this script never writes a Permission. Screenshots and result.json
land in tests/screenshots/issue-15/<label>/.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env_file = REPO / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

HA_URL = os.environ.get("HA_URL", "http://192.168.2.6:8123").rstrip("/")
FRONTEND = "/ha_permission_manager_frontend"

ADMIN_TOKEN = os.environ.get("HA_TOKEN") or os.environ.get(
    "HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN"
)

_nonadmin_file = REPO / ".ha_nonadmin_token"
NONADMIN_TOKEN = os.environ.get("HA_TOKEN_NONADMIN") or (
    _nonadmin_file.read_text(encoding="utf-8").strip()
    if _nonadmin_file.exists()
    else None
)

SHOTS = REPO / "tests" / "screenshots" / "issue-15"

# The Permission Manager panel: the screen a stranded administrator would go to
# in order to fix whatever stranded them, and therefore the page worth loading.
ADMIN_PANEL = "ha_permission_manager"

# The panel the non-admin has Closed, so their run exercises a Filter that has
# something to do rather than nothing.
NONADMIN_PANEL = "home"

# An export ha_sidebar_filter.js destructures out of the policy module.
MISSING_EXPORT = "panelsEqual"

# How long to let a page run before reading it. The release warns at 30s and
# keeps watching, so a page is watched past that: a run that stopped at 30s
# could not tell "still up" from "about to be lifted".
WATCH_MS = 40000

# Installed before any page script, so the overlay's whole life is recorded
# rather than sampled. Polling from the test cannot do this: the first sample
# lands in the gap *before* the module has created the overlay, and reads it as
# "already gone" — which is how the first version of this script reported an
# administrator released at 108 ms and still covered at the end of the run.
OVERLAY_WATCHER = """
window.__overlayLog = [];
(() => {
  const present = () => !!document.getElementById("perm-loading-overlay");
  const record = () => {
    const state = present() ? "present" : "absent";
    const log = window.__overlayLog;
    if (log.length && log[log.length - 1].state === state) return;
    log.push({ state, atMs: Math.round(performance.now()) });
  };
  // An init script runs before the parser has built documentElement, so there
  // is nothing to observe yet. Waiting a tick is enough, and is cheaper than
  // guessing which readiness event fires first.
  const start = () => {
    if (!document.documentElement) {
      setTimeout(start, 0);
      return;
    }
    record();
    new MutationObserver(record).observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  };
  start();
})();
"""

PROBE = """
() => {
  const overlay = document.getElementById("perm-loading-overlay");
  const cx = Math.floor(window.innerWidth / 2);
  const cy = Math.floor(window.innerHeight / 2);
  const atCentre = document.elementFromPoint(cx, cy);
  const hass = document.querySelector("home-assistant")?.hass;
  const panels = hass?.panels || {};
  return {
    path: location.pathname,
    hassReady: !!hass?.panels,
    isAdmin: hass?.user?.is_admin ?? null,
    panelCount: Object.keys(panels).length,
    permissionManagerOffered: Object.prototype.hasOwnProperty.call(
      panels, "ha_permission_manager"),
    overlayLog: window.__overlayLog || [],
    loadingOverlayPresent: !!overlay,
    loadingOverlayOpacity: overlay ? getComputedStyle(overlay).opacity : null,
    // The overlay is full-viewport and has no pointer-events rule, so if it is
    // what the middle of the screen hits, every click on this page hits it.
    centreIsOverlay: atCentre ? atCentre.id === "perm-loading-overlay" : null,
    releasedAttr: document.documentElement.hasAttribute(
      "data-perm-overlay-released"),
  };
}
"""


# Where a real click has to land for the overlay to be off the page in the only
# sense that matters. Issue #15's complaint is not that the page is grey — it is
# that recovery is "a hard reload with a cleared cache", or SSH. So the run ends
# by finding a sidebar link, clicking it with the mouse rather than calling
# .click() in script, and asking whether the URL moved. A script click would
# pass straight through the cover and prove nothing about hit-testing.
# Settings is `/config` on HA 2026.7.2, and it is the screen an administrator
# would head for. A non-admin has no Settings row, so any other sidebar link
# serves: the question is whether a click lands anywhere at all.
SIDEBAR_LINK = """
() => {
  const found = [];
  const queue = [document.body];
  let n = 0;
  while (queue.length) {
    const node = queue.shift();
    if (!node || ++n > 30000) break;
    if (node.localName === "a") {
      const href = node.getAttribute("href") || "";
      const box = node.getBoundingClientRect();
      if (href.startsWith("/") && href !== location.pathname && box.width && box.height) {
        found.push({
          href,
          x: Math.round(box.x + box.width / 2),
          y: Math.round(box.y + box.height / 2),
        });
      }
    }
    for (const list of [node.shadowRoot ? node.shadowRoot.children : null, node.children]) {
      if (!list) continue;
      for (let i = 0; i < list.length; i++) queue.push(list[i]);
    }
  }
  return found.find((link) => link.href === "/config") || found[0] || null;
}
"""


def unparseable_policy_body():
    """A module body no browser can parse, so `await import()` rejects."""
    return "export const broken = (((;\n"


def stale_policy_body(real_source):
    """The real module with one export withheld.

    A dynamic import destructures the namespace object, so a missing name is
    `undefined` rather than a link error: the module evaluates, and the throw
    lands later, inside applyPanels(). That is the case issue #12 measured.
    """
    pattern = re.compile(
        r"^export (function|const) " + MISSING_EXPORT + r"\b", re.MULTILINE
    )
    stale, count = pattern.subn(lambda m: f"{m.group(1)} {MISSING_EXPORT}", real_source)
    if count != 1:
        sys.exit(
            f"expected exactly one `export ... {MISSING_EXPORT}` in "
            f"permission_policy.js, found {count}"
        )
    return stale


def _auth_script(token):
    """HA's frontend reads its session from localStorage['hassTokens']."""
    payload = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "hassUrl": HA_URL,
        "clientId": HA_URL + "/",
        "expires": int(time.time() * 1000) + 10 * 365 * 24 * 3600 * 1000,
    }
    return f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(payload))});"


def instance_state():
    """What Home Assistant says it is doing, so nothing is measured mid-startup."""
    req = urllib.request.Request(
        f"{HA_URL}/api/config", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def served_versions():
    """The cache-buster queries the instance is handing out right now."""
    with urllib.request.urlopen(f"{HA_URL}/", timeout=15) as response:
        html = response.read().decode("utf-8", "replace")
    return sorted(set(re.findall(r"/ha_permission_manager_frontend/[^\"']+", html)))


def run(browser, label, name, token, panel, policy_body):
    """Load one page, break the policy module or not, and watch the overlay.

    `policy_body` of None is the control run: nothing is intercepted.
    """
    out = SHOTS / label
    out.mkdir(parents=True, exist_ok=True)

    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(_auth_script(token))
    context.add_init_script(OVERLAY_WATCHER)

    served = []
    if policy_body is not None:
        def serve_broken(route, request):
            served.append(request.url)
            route.fulfill(
                status=200,
                content_type="application/javascript",
                body=policy_body,
            )

        # Every spelling of the URL, with a version query or without: this is
        # the module being broken outright, which no cache buster prevents.
        context.route(f"{HA_URL}{FRONTEND}/permission_policy.js*", serve_broken)

    page = context.new_page()
    console = []
    page.on("console", lambda m: console.append((m.type, m.text)))
    page.on("pageerror", lambda e: console.append(("pageerror", str(e))))

    page.goto(f"{HA_URL}/{panel}", wait_until="domcontentloaded", timeout=45000)

    # Wait for Home Assistant's own frontend before reading anything about
    # panels. Without this, "no panels" reads as "filtered" when it means "not
    # loaded yet" — and on a covered page it takes longer than a healthy one.
    try:
        page.wait_for_function(
            "() => !!document.querySelector('home-assistant')?.hass?.panels",
            timeout=45000,
        )
    except Exception:
        pass  # reported as hassReady: false rather than dying here

    # Every run is watched for the same length of time, past the release's own
    # 30-second warning, so "still up" means the same thing in each of them.
    time.sleep(WATCH_MS / 1000)

    result = page.evaluate(PROBE)

    # The overlay's life, read off the log the watcher kept.
    appeared = next((e for e in result["overlayLog"] if e["state"] == "present"), None)
    released = None
    if appeared:
        released = next(
            (
                e
                for e in result["overlayLog"]
                if e["state"] == "absent" and e["atMs"] >= appeared["atMs"]
            ),
            None,
        )
    result["overlayAppearedAtMs"] = appeared["atMs"] if appeared else None
    result["releasedAfterMs"] = (
        released["atMs"] - appeared["atMs"] if appeared and released else None
    )
    page.screenshot(path=str(out / f"{name}.png"))

    # Can this user leave the page by clicking, or is SSH the only way out?
    target = page.evaluate(SIDEBAR_LINK)
    before_path = result["path"]
    after_path = before_path
    if target:
        page.mouse.click(target["x"], target["y"])
        time.sleep(3)
        after_path = page.evaluate("() => location.pathname")
    result["sidebarLink"] = target["href"] if target else None
    result["sidebarLinkFound"] = bool(target)
    result["pathAfterClick"] = after_path
    # Aimed at, not merely "the path changed": Home Assistant settles /home to
    # /home/overview by itself, and a swallowed click on a covered page reads as
    # a successful navigation if that is all you check.
    result["clickNavigated"] = bool(target) and after_path.startswith(target["href"])

    page.screenshot(path=str(out / f"{name}-after-click.png"))

    result["run"] = name
    result["panel"] = panel
    result["brokenPolicyServed"] = served
    result["errors"] = [t for kind, t in console if kind in ("error", "pageerror")]
    result["filterWarnings"] = [
        t for kind, t in console if "[SidebarFilter]" in t or "[LovelaceFilter]" in t
    ]
    context.close()
    return result


def line(result):
    overlay = "UP" if result["loadingOverlayPresent"] else "gone"
    when = (
        f"{result['releasedAfterMs']} ms"
        if result["releasedAfterMs"] is not None
        else f"never (watched {WATCH_MS // 1000}s)"
    )
    return overlay, when


def report(label, runs, state, assets):
    print(f"\n{'=' * 78}\n  issue #15  —  {label}\n{'=' * 78}")
    print(f"  instance     : {HA_URL}  HA {state.get('version')}  state={state.get('state')}")
    for asset in assets:
        print(f"  serving      : {asset}")

    for result in runs:
        overlay, when = line(result)
        print(f"\n  {result['run']}  (/{result['panel']})")
        print(f"    broken policy served         : {bool(result['brokenPolicyServed'])}")
        print(f"    hass ready / is_admin        : {result['hassReady']} / {result['isAdmin']}")
        print(f"    panels offered               : {result['panelCount']}")
        print(f"    overlay                      : {overlay}, opacity {result['loadingOverlayOpacity']}")
        print(f"    overlay raised at            : {result['overlayAppearedAtMs']} ms")
        print(f"    overlay lifted after         : {when}")
        print(f"    centre of screen is overlay  : {result['centreIsOverlay']}")
        print(f"    release recorded on document : {result['releasedAttr']}")
        aimed = result.get("sidebarLink") or "(no link found)"
        landed = result["pathAfterClick"]
        print(f"    a click aimed at {aimed:16}: "
              f"{'landed, now at ' + landed if result['clickNavigated'] else 'swallowed, still at ' + landed}")
        for warning in result["filterWarnings"][:3]:
            print(f"    Filter says                  : {warning[:92]}")
        for error in result["errors"][:3]:
            print(f"    console error                : {error[:92]}")

    admin_broken = [
        r for r in runs if r["run"].startswith("admin-broken")
    ]
    nonadmin_broken = [r for r in runs if r["run"].startswith("nonadmin-broken")]

    print(f"\n  VERDICT")
    stranded = [r for r in admin_broken if r["loadingOverlayPresent"]]
    navigated = [r for r in admin_broken if r["clickNavigated"]]
    if stranded:
        print(f"    -> ADMINISTRATOR STRANDED in {len(stranded)}/{len(admin_broken)} broken runs.")
        print("       The overlay is up with no timeout and swallows every click.")
    elif admin_broken:
        print(f"    -> administrator released in all {len(admin_broken)} broken runs,")
        print("       without any code below the imports having run.")
    print(f"    clicked away in {len(navigated)}/{len(admin_broken)} broken runs"
          " — the recovery issue #15 says costs a hard reload or SSH.")

    for result in nonadmin_broken:
        if result["loadingOverlayPresent"]:
            print("    -> non-admin still covered, as before. #12's question is untouched.")
        else:
            print("    -> NON-ADMIN RELEASED TOO. That is #12's question answered by")
            print("       accident, which #15 forbids. Investigate before shipping.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="e.g. v2.0.7-after")
    args = parser.parse_args()

    if not ADMIN_TOKEN:
        sys.exit("no admin token: set HA_TOKEN or HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN")
    if not NONADMIN_TOKEN:
        sys.exit("no non-admin token: set HA_TOKEN_NONADMIN or .ha_nonadmin_token")

    state = instance_state()
    if state.get("state") != "RUNNING":
        sys.exit(
            f"Home Assistant reports state={state.get('state')!r}. A page loaded "
            "before startup finishes reads fail-open and is worthless as evidence."
        )
    assets = served_versions()

    policy = (
        REPO / "custom_components" / "ha_permission_manager" / "frontend"
        / "permission_policy.js"
    ).read_text(encoding="utf-8")
    stale = stale_policy_body(policy)
    unparseable = unparseable_policy_body()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        runs = [
            run(browser, args.label, "admin-control", ADMIN_TOKEN, ADMIN_PANEL, None),
            run(browser, args.label, "admin-broken-link", ADMIN_TOKEN, ADMIN_PANEL, unparseable),
            run(browser, args.label, "admin-broken-later", ADMIN_TOKEN, ADMIN_PANEL, stale),
            run(browser, args.label, "nonadmin-control", NONADMIN_TOKEN, NONADMIN_PANEL, None),
            run(browser, args.label, "nonadmin-broken-later", NONADMIN_TOKEN, NONADMIN_PANEL, stale),
        ]
        browser.close()

    report(args.label, runs, state, assets)

    out = SHOTS / args.label
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(
        json.dumps(
            {
                "label": args.label,
                "instance": HA_URL,
                "haVersion": state.get("version"),
                "servedAssets": assets,
                "runs": runs,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n  written: {out / 'result.json'}")


if __name__ == "__main__":
    main()
