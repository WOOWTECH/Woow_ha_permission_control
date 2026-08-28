#!/usr/bin/env python3
"""Live verification for issue #12: break the frontend and see if anything moves.

Issue #12 is the fail-open failure class: the Filters decided in the browser, so
a Filter module that did not evaluate meant nothing applied the Permission
store, and a non-administrator was served every panel. Measured on v2.0.3 and
v2.0.4 by the old `tests/verify_issue_9.py`: 5 panels working, **28 panels with
one module broken**, on both releases.

#12 sets its own closing condition, and it is not an argument:

  > This issue closes when the Gate is deploy-verified, and not before, and not
  > on argument. The closing comment needs a fresh measurement in the shape of
  > tests/verify_issue_9.py: break the frontend on purpose and show that a
  > non-admin's panel list does not change, because it no longer depends on the
  > frontend at all.

So this breaks the frontend on purpose, four ways, and counts panels each time.
Breaking it is done at the network edge with a route intercept, exactly as
verify_issue_9.py did — nothing is deployed and nothing on the instance is
modified, so the same run can be repeated against any release.

  normal        every asset served as the instance serves it
  unparseable   sidebar-title.js served as text that cannot parse
  missing       sidebar-title.js served as 404
  blackout      EVERY request into our mount aborted — the strongest form,
                and the one the old failure needed: not one line of this
                integration's JavaScript runs in the page at all

The number that matters is `hass.panels`, read off the live page. Under the
Panel Gate it is the whole of what the user may see, so if it does not move
when the frontend is destroyed, the decision is provably not in the browser.

A denied panel is opened under each condition too. Fail-open would show up
there as the panel rendering rather than `notfound`.

Usage:
  python3 tests/verify_issue_12.py

Configuration (a repo-root .env is read automatically):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN   admin token
  HA_TOKEN_NONADMIN   non-admin token; falls back to .ha_nonadmin_token

Read-only: this script writes no Permission, deploys nothing and restarts
nothing. The record lands in tests/reports/issue-12/<version>.json.
"""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent


def _find_upwards(name: str) -> Path | None:
    for directory in [REPO, *REPO.parents]:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def _load_dotenv() -> None:
    env_file = _find_upwards(".env")
    if env_file is None:
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

# A panel the non-admin has at Permission level Closed. Fail-open renders it.
DENIED_PANEL = "climate"

# Not JavaScript. An asset served as this evaluates to a SyntaxError, which is
# the shape of every cause #12 lists: a bad deploy, a corrupted asset, a
# half-written file.
GIBBERISH = "this is not javascript {{{ ((( <<< \n export const"


def _admin_token() -> str:
    for name in ("HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN", "HA_TOKEN"):
        token = os.environ.get(name)
        if token:
            return token
    sys.exit("No admin token. Set HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN in .env")


def _nonadmin_token() -> str:
    token = os.environ.get("HA_TOKEN_NONADMIN")
    if token:
        return token
    fallback = _find_upwards(".ha_nonadmin_token")
    if fallback:
        return fallback.read_text(encoding="utf-8").strip()
    sys.exit("No non-admin token. Set HA_TOKEN_NONADMIN or add .ha_nonadmin_token")


def _auth_script(token: str) -> str:
    payload = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "hassUrl": HA_URL,
        "clientId": HA_URL + "/",
        "expires": int(time.time() * 1000) + 10 * 365 * 24 * 3600 * 1000,
    }
    return f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(payload))});"


PROBE = """() => {
  const seen = [];
  const walk = (r, d) => { if (!r || d > 10) return;
    for (const e of r.querySelectorAll("*")) { seen.push(e.localName); if (e.shadowRoot) walk(e.shadowRoot, d + 1); } };
  walk(document, 0);
  const ha = document.querySelector("home-assistant");
  return {
    panels: ha && ha.hass && ha.hass.panels ? Object.keys(ha.hass.panels).sort() : null,
    url: location.pathname,
    notfound: seen.some((n) => n && n.includes("notfound")),
    accessDenied: seen.includes("ha-access-denied"),
  };
}"""


# Each condition is (name, how to answer a request into our mount).
def _conditions():
    def normal(route):
        route.continue_()

    def unparseable(route):
        if route.request.url.split("?")[0].endswith("sidebar-title.js"):
            route.fulfill(status=200, content_type="text/javascript", body=GIBBERISH)
        else:
            route.continue_()

    def missing(route):
        if route.request.url.split("?")[0].endswith("sidebar-title.js"):
            route.fulfill(status=404, content_type="text/plain", body="gone")
        else:
            route.continue_()

    def blackout(route):
        route.abort()

    return [
        ("normal", normal),
        ("unparseable", unparseable),
        ("missing", missing),
        ("blackout", blackout),
    ]


def _settled(page, attempts: int = 12) -> dict:
    """Read the page once it has both a panel map and something rendered.

    Two separate waits, because they finish at different times. `hass.panels`
    arrives on the first WebSocket round trip; the element the router resolves
    to arrives after that, and on a denied panel only after a redirect. An
    earlier draft returned as soon as the panel map was readable and therefore
    recorded "no notfound element" on a page that was on its way to one — the
    measurement would have reported a fail-open that had not happened.

    A page that never produces a panel map is inconclusive, not passing, so
    `panels` comes back `None` rather than as a count of zero.
    """
    result = page.evaluate(PROBE)
    for _ in range(attempts):
        if result["panels"] is not None:
            break
        time.sleep(2)
        result = page.evaluate(PROBE)

    # Let the router finish resolving, then read what it actually resolved to.
    time.sleep(4)
    return page.evaluate(PROBE)


def _measure(identity: str, token: str, browser) -> dict:
    out = {}
    for name, handler in _conditions():
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script(_auth_script(token))
        context.route(f"**{FRONTEND}/**", handler)
        page = context.new_page()

        served = []
        page.on(
            "response",
            lambda r: served.append((r.url.split("/")[-1], r.status))
            if FRONTEND in r.url
            else None,
        )

        page.goto(HA_URL + "/lovelace/0", wait_until="domcontentloaded", timeout=45000)
        home = _settled(page)

        page.goto(HA_URL + f"/{DENIED_PANEL}", wait_until="domcontentloaded", timeout=45000)
        denied = _settled(page)

        out[name] = {
            "panelCount": len(home["panels"]) if home["panels"] is not None else None,
            "panels": home["panels"],
            "assetsServed": served,
            "deniedUrl": denied["url"],
            "deniedRenders": not denied["notfound"],
            "accessDenied": denied["accessDenied"],
        }
        context.close()
    return out


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        results = {
            "nonadmin": _measure("nonadmin", _nonadmin_token(), browser),
            "admin": _measure("admin", _admin_token(), browser),
        }
        browser.close()

    print(f"Broke the frontend on purpose, at {HA_URL}\n")
    failures = []

    for identity, conditions in results.items():
        baseline = conditions["normal"]["panelCount"]
        print(f"{identity}:")
        for name, data in conditions.items():
            count = data["panelCount"]
            shown = "unreadable" if count is None else str(count)
            moved = "" if count == baseline else "  <-- MOVED"
            print(
                f"  {name:<12} panels={shown:<11}"
                f" denied panel -> {data['deniedUrl']:<14}"
                f" renders={data['deniedRenders']}{moved}"
            )
            if count is None:
                failures.append(
                    f"{identity}: {name} never produced a panel map — inconclusive"
                )
            elif count != baseline:
                failures.append(
                    f"{identity}: {name} changed the panel count "
                    f"{baseline} -> {data['panelCount']} — the browser is still deciding"
                )
            if identity == "nonadmin" and data["deniedRenders"]:
                failures.append(
                    f"{identity}: {name} rendered the denied panel instead of notfound"
                )
        print()

    directory = REPO / "tests" / "reports" / "issue-12"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "v2.0.13.json").write_text(
        json.dumps(results, indent=2, sort_keys=True), encoding="utf-8"
    )

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        "PASS — the frontend was destroyed four ways and not one panel moved.\n"
        "The panel list does not depend on the frontend, which is what #12 asked for."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
