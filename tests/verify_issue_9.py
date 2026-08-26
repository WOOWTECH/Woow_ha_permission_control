#!/usr/bin/env python3
"""Live verification for issue #9: does a stale shared module leave the page unfiltered?

The issue is not about an outage. It is about version skew: a browser holding an
old `permission_policy.js` while loading a fresh `ha_sidebar_filter.js`. Both
Filters live inside those modules, so if the pair does not evaluate, nothing
filters. This script makes that pairing happen on purpose, and asks the page
what it did.

The stale copy is simulated at the network edge, because a browser cache cannot
be aged on demand. One route serves an older `permission_policy.js` — the real
module with one export removed, as a release that predates that export would
have — and only ever at the **unversioned** URL:

    /ha_permission_manager_frontend/permission_policy.js      (no query)

That URL is what v2.0.3 asks for. v2.0.4 asks for `…?v=2.0.4`, so the same route
matches nothing. The difference between the two runs is the whole of the fix:
not that the new import is safer, but that the stale copy is at a URL the fresh
release never requests.

Usage:
  python3 tests/verify_issue_9.py            # measure whatever is deployed
  python3 tests/verify_issue_9.py --label v2.0.3

Configuration (a repo-root .env is read automatically):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HA_TOKEN            admin long-lived access token
  HA_TOKEN_NONADMIN   non-admin token; falls back to .ha_nonadmin_token

Read-only: this script never writes a Permission. Screenshots land in
tests/screenshots/issue-9/<label>/.
"""
import argparse
import json
import os
import re
import sys
import time
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

_nonadmin_file = REPO / ".ha_nonadmin_token"
NONADMIN_TOKEN = os.environ.get("HA_TOKEN_NONADMIN") or (
    _nonadmin_file.read_text(encoding="utf-8").strip()
    if _nonadmin_file.exists()
    else None
)

SHOTS = REPO / "tests" / "screenshots" / "issue-9"

# The Permission store on the target gives the non-admin panel_home: 0 (Closed).
# A working sidebar filter takes `home` out of hass.panels and covers the page.
DENIED_PANEL = "home"

# An export ha_sidebar_filter.js imports. Removing it is what an older
# permission_policy.js looks like from the importer's side.
MISSING_EXPORT = "panelsEqual"

PROBE = """
() => {
  const find = (name) => {
    const queue = [document.body];
    let n = 0;
    while (queue.length) {
      const node = queue.shift();
      if (!node || ++n > 20000) break;
      if (node.localName === name) return node;
      for (const list of [node.shadowRoot ? node.shadowRoot.children : null, node.children]) {
        if (!list) continue;
        for (let i = 0; i < list.length; i++) queue.push(list[i]);
      }
    }
    return null;
  };
  const hass = document.querySelector("home-assistant")?.hass;
  const panels = hass?.panels || {};
  const overlay = document.getElementById("perm-loading-overlay");
  return {
    path: location.pathname,
    hassReady: !!hass?.panels,
    panelCount: Object.keys(panels).length,
    panelIds: Object.keys(panels).sort(),
    deniedPanelStillOffered: Object.prototype.hasOwnProperty.call(panels, "home"),
    accessDeniedPresent: !!find("ha-access-denied"),
    huiRootPresent: !!find("hui-root"),
    loadingOverlayPresent: !!overlay,
    loadingOverlayOpacity: overlay ? getComputedStyle(overlay).opacity : null,
  };
}
"""


def stale_policy_body(real_source):
    """The real module as an older release would have shipped it: one export short.

    Only the `export` keyword is dropped, so the module still parses and still
    evaluates. What fails is the *link* to it — exactly what a browser reports
    when a cached module predates an export its importer now needs.
    """
    pattern = re.compile(
        r"^export (function|const) " + MISSING_EXPORT + r"\b", re.MULTILINE
    )
    stale, count = pattern.subn(
        lambda m: f"{m.group(1)} {MISSING_EXPORT}", real_source
    )
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


def run(browser, label, name, stale_body, match_any_version=False):
    """Load the denied panel as the non-admin, optionally with a stale module served.

    `stale_body` of None is the control run: nothing is intercepted.

    `match_any_version` widens the route to every `permission_policy.js` URL,
    version query or not. That is no longer the skew case — it is the module
    being broken outright, which no cache buster can prevent. It is here to
    measure what the release *does* in that case: fail silently, or visibly.
    """
    out = SHOTS / label
    out.mkdir(parents=True, exist_ok=True)

    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(_auth_script(NONADMIN_TOKEN))

    hits = []
    if stale_body is not None:
        def serve_stale(route, request):
            hits.append(request.url)
            route.fulfill(
                status=200,
                content_type="application/javascript",
                body=stale_body,
            )

        # The unversioned URL only. A release that busts its imports never asks
        # for this, so on such a release the handler is dead weight — which is
        # the measurement.
        pattern = (
            f"{HA_URL}{FRONTEND}/permission_policy.js*"
            if match_any_version
            else f"{HA_URL}{FRONTEND}/permission_policy.js"
        )
        context.route(pattern, serve_stale)

    page = context.new_page()
    console = []
    page.on("console", lambda m: console.append((m.type, m.text)))
    page.on("pageerror", lambda e: console.append(("pageerror", str(e))))

    requested = []
    page.on(
        "request",
        lambda r: requested.append(r.url) if "permission_policy.js" in r.url else None,
    )

    page.goto(f"{HA_URL}/{DENIED_PANEL}", wait_until="domcontentloaded", timeout=45000)

    # Wait for Home Assistant's own frontend to finish booting before asking
    # anything. Without this, "no panels" reads as "filtered" when it really
    # means "not loaded yet", and a broken Filter looks like a working one.
    try:
        page.wait_for_function(
            "() => !!document.querySelector('home-assistant')?.hass?.panels",
            timeout=45000,
        )
    except Exception:
        pass  # report it as hassReady: false rather than dying here
    time.sleep(8)  # let the Filters round-trip and any grace period elapse

    result = page.evaluate(PROBE)
    page.screenshot(path=str(out / f"{name}.png"))

    result["staleServed"] = hits
    result["policyRequests"] = requested
    result["errors"] = [t for kind, t in console if kind in ("error", "pageerror")]
    result["filterWarnings"] = [
        t for kind, t in console if "[SidebarFilter]" in t or "[LovelaceFilter]" in t
    ]
    context.close()
    return result


def report(label, control, stale):
    print(f"\n{'=' * 78}\n  {label}  —  non-admin, /{DENIED_PANEL} (Closed)\n{'=' * 78}")

    for name, r in (("control (nothing intercepted)", control), ("stale module served", stale)):
        print(f"\n  {name}")
        print(f"    permission_policy.js requested : {r['policyRequests'] or ['(none)']}")
        print(f"    stale copy actually served     : {r['staleServed'] or '(never — route did not match)'}")
        print(f"    Home Assistant frontend ready  : {r['hassReady']}")
        print(f"    panels in hass.panels          : {r['panelCount']}")
        print(f"    denied panel still offered     : {r['deniedPanelStillOffered']}")
        print(f"    Access Denied Filter on screen : {r['accessDeniedPresent']}")
        print(f"    dashboard (hui-root) present   : {r['huiRootPresent']}")
        print(f"    loading overlay still up       : {r['loadingOverlayPresent']} (opacity {r['loadingOverlayOpacity']})")
        if r["filterWarnings"]:
            for w in r["filterWarnings"][:4]:
                print(f"    Filter says                    : {w[:96]}")
        if r["errors"]:
            for e in r["errors"][:4]:
                print(f"    console error                  : {e[:96]}")

    # "Filtered" means the Filter actually removed panels, judged against the
    # control run rather than against zero — an unbooted frontend also has no
    # panels, and that is not the same thing at all.
    extra = sorted(set(stale["panelIds"]) - set(control["panelIds"]))
    covered = stale["accessDeniedPresent"] or stale["loadingOverlayPresent"]

    print(f"\n  VERDICT with a stale module present:")
    print(f"    the stale copy was used        : {bool(stale['staleServed'])}")
    print(f"    Home Assistant frontend ready  : {stale['hassReady']}")
    print(f"    panels the control run hid     : {len(extra)}  {extra[:8]}")
    print(f"    the page was covered           : {covered}")

    if not stale["hassReady"]:
        print("    -> INCONCLUSIVE: the frontend never booted; nothing to judge.")
    elif extra and not covered:
        print(f"    -> FAILS OPEN: {len(extra)} panels the Filter should have hidden are")
        print("       offered, the page is not covered, and nothing says so.")
    elif extra and covered:
        print("    -> fails visibly: not filtered, but the page is covered, so the")
        print("       failure is a blocked page rather than a silent one.")
    else:
        print("    -> filtered normally: the stale copy never reached this release.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="current", help="name for this run's screenshots")
    args = parser.parse_args()

    if not NONADMIN_TOKEN:
        sys.exit("no non-admin token: set HA_TOKEN_NONADMIN or .ha_nonadmin_token")

    real = Path(
        REPO / "custom_components" / "ha_permission_manager" / "frontend" / "permission_policy.js"
    ).read_text(encoding="utf-8")
    stale_body = stale_policy_body(real)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        control = run(browser, args.label, "control", None)
        stale = run(browser, args.label, "stale-module", stale_body)
        broken = run(browser, args.label, "broken-module", stale_body, match_any_version=True)
        browser.close()

    report(args.label, control, stale)

    print(f"\n  BESIDES THE SKEW — the module broken at whatever URL this release asks for:")
    print(f"    (no cache buster can prevent this; the question is only whether it shows)")
    print(f"    the broken copy was used       : {bool(broken['staleServed'])}")
    print(f"    Home Assistant frontend ready  : {broken['hassReady']}")
    leaked = sorted(set(broken["panelIds"]) - set(control["panelIds"]))
    print(f"    panels the control run hid     : {len(leaked)}  {leaked[:8]}")
    print(f"    Access Denied Filter on screen : {broken['accessDeniedPresent']}")
    print(f"    loading overlay still up       : {broken['loadingOverlayPresent']} (opacity {broken['loadingOverlayOpacity']})")
    if leaked and not broken["loadingOverlayPresent"]:
        print("    -> still fails open, and silently. This is the part issue #9")
        print("       leaves open, and it is not fixed here.")
    elif leaked and broken["loadingOverlayPresent"]:
        print("    -> fails open behind a stuck overlay: the panels are offered, but")
        print("       the page is covered, so somebody notices.")
    else:
        print("    -> no panels leaked.")

    (SHOTS / args.label / "result.json").write_text(
        json.dumps({"control": control, "stale": stale, "broken": broken}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
