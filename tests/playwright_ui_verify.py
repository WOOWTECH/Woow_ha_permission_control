#!/usr/bin/env python3
"""Playwright UI verification for Woow HA Permission Control.

Drives a real browser against a running Home Assistant and screenshots the two
panels this integration ships, once per identity. The point of the non-admin run
is the whole point of the integration: what a regular user can and cannot see.

Usage:
  python3 tests/playwright_ui_verify.py                 # every configured identity
  python3 tests/playwright_ui_verify.py admin           # just one

Configuration (a repo-root .env is read automatically):

  HA_URL              target instance      (default http://localhost:15124)
  HA_TOKEN            admin long-lived access token
  HA_TOKEN_NONADMIN   non-admin long-lived access token; the non-admin run is
                      skipped, loudly, when this is missing

Screenshots land in tests/screenshots/<identity>/. Read-only: this script never
writes a permission.
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

HA_URL = os.environ.get("HA_URL", "http://localhost:15124").rstrip("/")
TOKENS = {
    "admin": os.environ.get("HA_TOKEN")
    or os.environ.get("HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN"),
    "nonadmin": os.environ.get("HA_TOKEN_NONADMIN"),
}

# The panels this integration ships, plus one control page.
PAGES = [
    ("sidebar", "/lovelace/0", "sidebar as this user sees it"),
    ("control-panel", "/ha-control-panel", "Control Panel — Areas tab"),
    ("permission-manager", "/ha_permission_manager", "Permission Manager (admin only)"),
]

SHOTS = REPO / "tests" / "screenshots"


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
    findings = []

    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(_auth_script(token))
    page = context.new_page()
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

    for name, path, _desc in PAGES:
        url = HA_URL + path
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            findings.append((name, "NAVIGATION FAILED", str(exc)[:120]))
            continue
        time.sleep(2.5)  # let the panel's WebSocket round-trip settle
        shot = out / f"{name}.png"
        page.screenshot(path=str(shot), full_page=False)

        # Which sidebar entries is this identity actually offered?
        items = page.evaluate(
            """() => {
                const el = document.querySelector('home-assistant')
                  ?.shadowRoot?.querySelector('home-assistant-main')
                  ?.shadowRoot?.querySelector('ha-sidebar');
                if (!el) return null;
                return Array.from(el.shadowRoot.querySelectorAll('a[href]'))
                  .map(a => a.getAttribute('href'));
            }"""
        )
        findings.append((name, "ok", f"{shot.name}; sidebar={items}"))

        if name == "control-panel":
            # The Areas tab is the default; the Labels tab is where the entity
            # filtering shows up, so capture both.
            try:
                # activeTab is a plain reactive property with no URL route, and the
                # panel sits several shadow roots deep, so walk them to find it.
                switched = page.evaluate(
                    """() => {
                        const find = (root, depth) => {
                            if (!root || depth > 12) return null;
                            for (const el of root.querySelectorAll('*')) {
                                if (el.tagName === 'HA-CONTROL-PANEL') return el;
                                if (el.shadowRoot) {
                                    const hit = find(el.shadowRoot, depth + 1);
                                    if (hit) return hit;
                                }
                            }
                            return null;
                        };
                        const panel = find(document, 0);
                        if (!panel) return false;
                        panel.activeTab = 'labels';
                        panel.requestUpdate?.();
                        return true;
                    }"""
                )
                if not switched:
                    findings.append(("control-panel-labels", "CAPTURE FAILED",
                                     "ha-control-panel not reachable in the shadow tree"))
                else:
                    time.sleep(3)
                    page.screenshot(path=str(out / "control-panel-labels.png"))
                    findings.append(("control-panel-labels", "ok", "control-panel-labels.png"))
            except Exception as exc:
                findings.append(("control-panel-labels", "CAPTURE FAILED", str(exc)[:120]))

    context.close()
    return findings, console_errors


def main():
    wanted = sys.argv[1:] or list(TOKENS)
    print("=" * 64)
    print("Woow HA Permission Control — UI verification")
    print("=" * 64)
    print(f"Target: {HA_URL}")

    exit_code = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for identity in wanted:
            token = TOKENS.get(identity)
            if not token:
                env = "HA_TOKEN" if identity == "admin" else "HA_TOKEN_NONADMIN"
                print(f"\n!! SKIPPING '{identity}': {env} is not set.")
                print("!! The non-admin run is the one that proves the Filters work.")
                exit_code = 2
                continue
            print(f"\n--- identity: {identity} ---")
            findings, console_errors = verify(identity, token, browser)
            for name, status, detail in findings:
                mark = "v" if status == "ok" else "X"
                print(f"  [{mark}] {name}: {detail}")
                if status != "ok":
                    exit_code = 1
            if console_errors:
                print(f"  console errors ({len(console_errors)}):")
                for e in console_errors[:5]:
                    print(f"    - {e[:160]}")
        browser.close()

    print(f"\nScreenshots: {SHOTS}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
