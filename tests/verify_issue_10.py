#!/usr/bin/env python3
"""Live verification for issue #10: does the lovelace filter hide a denied Dashboard?

Drives a real browser against a running Home Assistant, once per identity, and
asks the page the questions the issue asks:

  - Is there a `hui-root` on this page, and is it hidden?
  - Is the Access Denied Filter covering the page as well?
  - Is exactly one "no access" message on screen, rather than two?
  - Did the Filter warn that it decided to hide and then hid nothing?

Usage:
  python3 tests/verify_issue_10.py

Configuration (a repo-root .env is read automatically):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HA_TOKEN            admin long-lived access token
  HA_TOKEN_NONADMIN   non-admin long-lived access token; falls back to the
                      contents of .ha_nonadmin_token at the repo root

Read-only: this script never writes a Permission. Screenshots land in
tests/screenshots/issue-10/<identity>/.
"""
import json
import os
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

_nonadmin_file = REPO / ".ha_nonadmin_token"
TOKENS = {
    "admin": os.environ.get("HA_TOKEN")
    or os.environ.get("HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN"),
    "nonadmin": os.environ.get("HA_TOKEN_NONADMIN")
    or (_nonadmin_file.read_text(encoding="utf-8").strip() if _nonadmin_file.exists() else None),
}

SHOTS = REPO / "tests" / "screenshots" / "issue-10"

# The permission store on the target gives the non-admin panel_home: 0 (Closed),
# panel_ha-control-panel: 1 and panel_energy: 1.
PAGES = [
    ("home", "/home", "the default Dashboard, Closed for the non-admin"),
    ("control-panel", "/ha-control-panel", "a permitted panel that is not a Dashboard"),
    ("energy", "/energy", "a permitted panel that renders no hui-root"),
]

# One question set, asked of whatever is on screen.
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
  const huiRoot = find("hui-root");
  const denied = find("ha-access-denied");
  const msg = document.getElementById("perm-manager-no-access-msg");
  const panelId = location.pathname.split("/")[1] || null;
  const panels = document.querySelector("home-assistant")?.hass?.panels || {};
  return {
    path: location.pathname,
    componentName: panelId ? (panels[panelId]?.component_name ?? null) : null,
    huiRootPresent: !!huiRoot,
    huiRootDisplay: huiRoot ? getComputedStyle(huiRoot).display : null,
    accessDeniedPresent: !!denied,
    noAccessMessagePresent: !!msg,
    loadingOverlayPresent: !!document.getElementById("perm-loading-overlay"),
  };
}
"""


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


def verify(identity, token, browser):
    out = SHOTS / identity
    out.mkdir(parents=True, exist_ok=True)

    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(_auth_script(token))
    page = context.new_page()

    console = []
    page.on("console", lambda m: console.append((m.type, m.text)))
    page.on("pageerror", lambda e: console.append(("pageerror", str(e))))

    rows = []
    for name, path, desc in PAGES:
        del console[:]
        page.goto(HA_URL + path, wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)  # let the Filters round-trip and the grace period elapse
        result = page.evaluate(PROBE)
        page.screenshot(path=str(out / f"{name}.png"))

        errors = [t for kind, t in console if kind in ("error", "pageerror")]
        filter_warnings = [t for kind, t in console if "[LovelaceFilter]" in t]
        rows.append((name, desc, result, errors, filter_warnings))

    # Issue #6 Mechanism B: a client-side navigation into the denied Dashboard,
    # which is the case this Filter exists to cover.
    del console[:]
    page.goto(HA_URL + "/ha-control-panel", wait_until="domcontentloaded", timeout=45000)
    time.sleep(4)
    page.evaluate(
        """() => { history.pushState(null, "", "/home");
                   window.dispatchEvent(new PopStateEvent("popstate"));
                   window.dispatchEvent(new CustomEvent("location-changed", {bubbles: true, composed: true})); }"""
    )
    time.sleep(5)
    nav = page.evaluate(PROBE)
    page.screenshot(path=str(out / "client-side-nav-to-home.png"))
    nav_errors = [t for kind, t in console if kind in ("error", "pageerror")]

    context.close()
    return rows, (nav, nav_errors)


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    missing = [i for i, t in TOKENS.items() if not t]
    if missing:
        print(f"!! no token for: {', '.join(missing)} — those runs are skipped")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for identity, token in TOKENS.items():
            if not token:
                continue
            print("=" * 78)
            print(f"IDENTITY: {identity}")
            print("=" * 78)
            rows, (nav, nav_errors) = verify(identity, token, browser)
            for name, desc, r, errors, warnings in rows:
                print(f"\n  {name}  ({desc})")
                print(f"    path                  {r['path']}  component={r['componentName']!r}")
                print(f"    hui-root present      {r['huiRootPresent']}   display={r['huiRootDisplay']!r}")
                print(f"    Access Denied Filter  {r['accessDeniedPresent']}")
                print(f"    no-access message     {r['noAccessMessagePresent']}")
                print(f"    loading overlay stuck {r['loadingOverlayPresent']}")
                print(f"    console errors        {len(errors)}  {errors[:3]}")
                print(f"    LovelaceFilter says   {warnings if warnings else 'nothing'}")
            print("\n  client-side navigation to /home (issue #6 Mechanism B)")
            print(f"    path                  {nav['path']}  component={nav['componentName']!r}")
            print(f"    hui-root present      {nav['huiRootPresent']}   display={nav['huiRootDisplay']!r}")
            print(f"    Access Denied Filter  {nav['accessDeniedPresent']}")
            print(f"    no-access message     {nav['noAccessMessagePresent']}")
            print(f"    console errors        {len(nav_errors)}  {nav_errors[:3]}")
        browser.close()

    print(f"\nScreenshots: {SHOTS}")


main()
