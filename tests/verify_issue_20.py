#!/usr/bin/env python3
"""Live verification for issue #20: are the Filters gone, and did anyone notice?

Deleting code is only safe if nothing was leaning on it. Two claims have to be
measured on an instance, because neither can be read off the source:

  1. **Nothing is left to load.** The six deleted modules must 404, and the only
     asset the browser pulls out of our mount on an ordinary page must be
     `sidebar-title.js`. A file left on disk by a partial deploy still gets
     served, and `tests/frontend_assets.test.mjs` cannot see the instance.

  2. **Nobody lost a row.** The Panel Gate has decided since v2.0.11, so the
     sidebar a user sees must not move when the Filters go. If it moves, the
     Filters were still deciding something and the Gate was not the whole
     answer.

And one claim is the behaviour change #20 makes on purpose, which is worth a
record rather than an assumption:

  3. **A denied panel is `notfound`, not Access Denied.** The browser cannot
     tell "denied" from "does not exist", which is the point of deleting the
     key rather than hiding it.

Run it against the release before the deploy and the release after, and diff
the two records:

  python3 tests/verify_issue_20.py --label v2.0.12-before
  python3 tests/verify_issue_20.py --label v2.0.13-after
  python3 tests/verify_issue_20.py --compare v2.0.12-before v2.0.13-after

Configuration (a repo-root .env is read automatically; a git worktree walks up
to find it):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN   admin token
  HA_TOKEN            admin token, if the name above is not set
  HA_TOKEN_NONADMIN   non-admin token; falls back to .ha_nonadmin_token

Read-only: this script writes no Permission, fires no event and restarts
nothing. Captures land in tests/reports/issue-20/<label>.json, screenshots
beside them in tests/screenshots/issue-20/<label>/.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent


def _find_upwards(name: str) -> Path | None:
    """The nearest `name` at or above the repo root."""
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


# Read before HA_URL below, not in main(): the module-level constants are what
# every function here reads, so a .env loaded later would be loaded too late.
_load_dotenv()

HA_URL = os.environ.get("HA_URL", "http://192.168.2.6:8123").rstrip("/")
FRONTEND = "/ha_permission_manager_frontend"

# The six modules #20 deletes. Each must 404 after the deploy: a file left
# behind by a partial copy is still served, and still runs.
DELETED = (
    "ha_sidebar_filter.js",
    "ha_lovelace_filter.js",
    "ha_access_denied.js",
    "permission_policy.js",
    "filter_lifecycle.js",
    "shadow_dom.js",
)

# What must still be served: the two panels, what they import, and the one
# asset that goes on every page.
KEPT = ("ha_permission_manager.js", "ha_control_panel.js", "lit.js", "sidebar-title.js")

# A panel the non-admin is denied, measured as `notfound` rather than assumed.
# `climate` is an ordinary dashboard rather than an admin-only page, so what is
# measured is the Permission level and not Home Assistant's own require_admin.
DENIED_PANEL = "climate"


def _asset_status(name: str) -> int:
    """The HTTP status the instance answers for one frontend asset."""
    request = urllib.request.Request(f"{HA_URL}{FRONTEND}/{name}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError as error:
        return -1 if not hasattr(error, "code") else error.code


def _auth_script(token: str) -> str:
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


# Read out of the running page: the sidebar rows, whether the Access Denied
# Filter's element is anywhere in the shadow trees, and what the panel resolver
# actually resolved to. The walk is breadth-limited the way the deleted
# shadow_dom.js was — a dashboard is deep, and this only needs the top.
PAGE_PROBE = """() => {
  const seen = [];
  const walk = (root, depth) => {
    if (!root || depth > 10) return;
    for (const el of root.querySelectorAll("*")) {
      seen.push(el.localName);
      if (el.shadowRoot) walk(el.shadowRoot, depth + 1);
    }
  };
  walk(document, 0);

  const ha = document.querySelector("home-assistant");

  // What the browser was actually given. This is the claim: the Panel Gate
  // decides, so hass.panels is the sidebar, and reading it does not depend on
  // finding whichever element Home Assistant draws rows with this month.
  const panelKeys = ha && ha.hass && ha.hass.panels
    ? Object.keys(ha.hass.panels).sort()
    : null;

  // The drawn rows as well, when they can be found. An anchor is not the only
  // shape a row has had, so anything carrying an href counts.
  const sidebar = (() => {
    const main = ha && ha.shadowRoot && ha.shadowRoot.querySelector("home-assistant-main");
    const bar = main && main.shadowRoot && main.shadowRoot.querySelector("ha-sidebar");
    if (!bar || !bar.shadowRoot) return null;
    const rows = new Set();
    const dig = (root, depth) => {
      if (!root || depth > 6) return;
      for (const el of root.querySelectorAll("*")) {
        const href = el.getAttribute && el.getAttribute("href");
        if (href) rows.add(href);
        if (el.shadowRoot) dig(el.shadowRoot, depth + 1);
      }
    };
    dig(bar.shadowRoot, 0);
    return [...rows].sort();
  })();

  return {
    url: location.pathname,
    panelKeys,
    sidebar,
    accessDeniedPresent: seen.includes("ha-access-denied"),
    notfoundPresent: seen.some((n) => n && n.includes("notfound")),
    loadingOverlayPresent: !!document.getElementById("perm-loading-overlay"),
    bodyText: (document.body.innerText || "").slice(0, 200),
  };
}"""


def _capture_identity(identity: str, token: str, browser, shots: Path) -> dict:
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(_auth_script(token))
    page = context.new_page()

    console_errors: list[str] = []
    page.on(
        "console",
        lambda m: console_errors.append(m.text[:200]) if m.type == "error" else None,
    )

    # Every request the page makes into our mount, in the order it makes them.
    ours: list[str] = []
    page.on(
        "request",
        lambda r: ours.append(r.url.split("/")[-1]) if FRONTEND in r.url else None,
    )

    result: dict = {"identity": identity}

    for name, path in (("home", "/lovelace/0"), ("denied", f"/{DENIED_PANEL}")):
        ours.clear()
        try:
            page.goto(HA_URL + path, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:  # noqa: BLE001 - recorded, not raised
            result[name] = {"navigationFailed": str(exc)[:160]}
            continue
        time.sleep(4)  # the panel's WebSocket round-trip, then the render
        probe = page.evaluate(PAGE_PROBE)
        probe["requestedFromOurMount"] = sorted(set(ours))
        result[name] = probe
        page.screenshot(path=str(shots / f"{identity}-{name}.png"), full_page=False)

    result["consoleErrors"] = console_errors
    context.close()
    return result


def _deployed_version() -> str | None:
    """The version the instance is actually running, off its own manifest."""
    request = urllib.request.Request(
        f"{HA_URL}{FRONTEND}/sidebar-title.js",
        headers={"Cache-Control": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            source = response.read().decode("utf-8", "replace")
    except OSError:
        return None
    # The file names the release it belongs to in its own header prose.
    for token in ("v2.0.13", "v3.0.0", "v2.0.12"):
        if token in source:
            return token
    return "unknown"


def _report_path(label: str) -> Path:
    directory = REPO / "tests" / "reports" / "issue-20"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{label}.json"


def run_capture(label: str) -> None:
    shots = REPO / "tests" / "screenshots" / "issue-20" / label
    shots.mkdir(parents=True, exist_ok=True)

    assets = {name: _asset_status(name) for name in DELETED + KEPT}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        identities = {
            "admin": _capture_identity("admin", _admin_token(), browser, shots),
            "nonadmin": _capture_identity("nonadmin", _nonadmin_token(), browser, shots),
        }
        browser.close()

    capture = {
        "label": label,
        "assets": assets,
        "sidebarTitleSays": _deployed_version(),
        "identities": identities,
    }
    _report_path(label).write_text(
        json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
    )

    print(f"captured {label}   (sidebar-title.js says {capture['sidebarTitleSays']})")
    print("  deleted modules, served status:")
    for name in DELETED:
        print(f"    {assets[name]:>4}  {name}")
    print("  kept modules, served status:")
    for name in KEPT:
        print(f"    {assets[name]:>4}  {name}")
    for identity, data in identities.items():
        home = data.get("home", {})
        denied = data.get("denied", {})
        keys = home.get("panelKeys")
        rows = home.get("sidebar")
        print(f"  {identity}:")
        print(f"    hass.panels keys    {len(keys) if keys is not None else '?'}")
        print(f"    drawn sidebar rows  {len(rows) if rows is not None else '?'}")
        print(f"    pulled from mount   {home.get('requestedFromOurMount')}")
        print(f"    loading overlay     {home.get('loadingOverlayPresent')}")
        print(f"    on /{DENIED_PANEL}: url={denied.get('url')} "
              f"accessDenied={denied.get('accessDeniedPresent')} "
              f"notfound={denied.get('notfoundPresent')}")
        print(f"    console errors      {len(data.get('consoleErrors', []))}")


def run_compare(before_label: str, after_label: str) -> int:
    before = json.loads(_report_path(before_label).read_text(encoding="utf-8"))
    after = json.loads(_report_path(after_label).read_text(encoding="utf-8"))

    failures: list[str] = []
    print(f"{before_label}  ->  {after_label}\n")

    print("1. nothing is left to load")
    for name in DELETED:
        was, now = before["assets"][name], after["assets"][name]
        ok = now == 404
        print(f"   {'ok ' if ok else '!! '}{name:<24} {was} -> {now}")
        if not ok:
            failures.append(f"{name} still answers {now}; a deleted module is still served")
    for name in KEPT:
        was, now = before["assets"][name], after["assets"][name]
        ok = now == 200
        print(f"   {'ok ' if ok else '!! '}{name:<24} {was} -> {now}")
        if not ok:
            failures.append(f"{name} answers {now}; a kept module stopped being served")

    print("\n2. nobody lost a row")
    for identity in ("admin", "nonadmin"):
        old_home = before["identities"][identity].get("home", {})
        new_home = after["identities"][identity].get("home", {})
        old_keys = old_home.get("panelKeys")
        new_keys = new_home.get("panelKeys")
        if old_keys is None or new_keys is None:
            failures.append(f"{identity}: hass.panels could not be read on one side")
            print(f"   !! {identity}: hass.panels unreadable")
            continue
        print(f"   {identity}: hass.panels {len(old_keys)} -> {len(new_keys)}")
        if sorted(old_keys) != sorted(new_keys):
            gained = sorted(set(new_keys) - set(old_keys))
            lost = sorted(set(old_keys) - set(new_keys))
            failures.append(f"{identity} panel map changed: gained {gained}, lost {lost}")
            print(f"      !! gained {gained}")
            print(f"      !! lost   {lost}")
        else:
            print(f"      unchanged: {sorted(new_keys)}")

        old_rows, new_rows = old_home.get("sidebar"), new_home.get("sidebar")
        if old_rows is not None and new_rows is not None:
            print(f"      drawn rows {len(old_rows)} -> {len(new_rows)}")
            if sorted(old_rows) != sorted(new_rows):
                failures.append(
                    f"{identity} drawn sidebar changed: "
                    f"gained {sorted(set(new_rows) - set(old_rows))}, "
                    f"lost {sorted(set(old_rows) - set(new_rows))}"
                )

        pulled = new_home.get("requestedFromOurMount") or []
        page_assets = [n for n in pulled if n.split("?")[0].endswith(".js")]
        print(f"      pulls from our mount: {page_assets}")
        for asset in page_assets:
            if asset.split("?")[0] in DELETED:
                failures.append(f"{identity}'s page still pulls {asset}")

    print("\n3. a denied panel is notfound, not Access Denied")
    for identity in ("admin", "nonadmin"):
        old = before["identities"][identity].get("denied", {})
        new = after["identities"][identity].get("denied", {})
        print(f"   {identity}: accessDenied {old.get('accessDeniedPresent')} -> "
              f"{new.get('accessDeniedPresent')}, url {old.get('url')} -> {new.get('url')}")
        if identity == "nonadmin" and new.get("accessDeniedPresent"):
            failures.append("the Access Denied page is still rendered for a non-admin")

    print("\n4. the loading overlay is gone")
    for identity in ("admin", "nonadmin"):
        new_home = after["identities"][identity].get("home", {})
        up = new_home.get("loadingOverlayPresent")
        print(f"   {identity}: overlay present = {up}")
        if up:
            failures.append(f"{identity} still has a loading overlay on the page")

    print("\n5. console errors (the non-admin session has a known baseline)")
    for identity in ("admin", "nonadmin"):
        old = before["identities"][identity].get("consoleErrors", [])
        new = after["identities"][identity].get("consoleErrors", [])
        print(f"   {identity}: {len(old)} -> {len(new)}")
        for line in new:
            print(f"      {line[:150]}")

    if failures:
        print("\nFAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nPASS — the Filters are gone and nothing moved that should not have")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", help="capture the current instance under this label")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()

    if args.compare:
        return run_compare(*args.compare)
    if args.label:
        run_capture(args.label)
        return 0
    parser.error("pass --label or --compare")


if __name__ == "__main__":
    sys.exit(main())
