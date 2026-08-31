#!/usr/bin/env python3
"""#13 end to end: a real browser, a real Home Assistant, a real non-admin.

The other two scripts each hold one half of the claim and neither holds both:

  - `verify_issue_13.py` drives the real `ha_control_panel.js` in a real
    browser, against a **fake** `hass`. It proves the panel reacts, and proves
    nothing about Home Assistant.
  - `verify_issue_13_live.py` measures a **real** instance over the WebSocket,
    with no browser. It proves the broadcast arrives and the re-read answers,
    and proves nothing about the panel.

This is the two halves in one run, and it is the only thing that measures what
issue #13 actually says: an administrator changes a Permission, and the page a
non-administrator already has open changes, with nobody reloading anything.

What it does, as the non-admin, on the Control Panel:

  1. reads the area cards on screen;
  2. has an **administrator**, over a separate WebSocket, revoke one of them;
  3. waits, and reads the cards again - no reload, no navigation;
  4. has the administrator grant it back, and reads a third time.

The grant is not decoration. A revoke that works and a grant that does not is
a panel that only ever takes things away, and before this release the two
failed in opposite directions.

Usage:
  python3 tests/verify_issue_13_browser.py --label v2.0.15
  python3 tests/verify_issue_13_browser.py --label v2.0.15 --headed

Configuration is `tests/ha_session.py`'s: HA_URL, the admin token, and
HA_TOKEN_NONADMIN (or `.ha_nonadmin_token`).

**This script writes.** It moves one area Permission for the non-admin and puts
it back, and it checks the Permission store's bytes are unchanged at the end.

Captures land in tests/reports/issue-13/<label>-browser.json, and a screenshot
per step in tests/screenshots/issue-13/.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from playwright.async_api import async_playwright

from ha_session import (
    REPO,
    Session,
    admin_token,
    http_url,
    load_dotenv,
    nonadmin_token,
    nonadmin_user_id,
    set_level,
    stored_level,
)

CONTROL_PANEL = "/ha-control-panel"

# How long to give a change to cross: the Panel Gate debounces the broadcast,
# then the page makes a round trip of its own. Polled, so a fast answer is not
# slowed down to this.
CROSS_SECONDS = 12.0

SHOTS = REPO / "tests" / "screenshots" / "issue-13"


def auth_script(token: str, url: str) -> str:
    """Home Assistant's frontend reads its session out of localStorage."""
    payload = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "hassUrl": url,
        "clientId": url + "/",
        "expires": int(time.time() * 1000) + 10 * 365 * 24 * 3600 * 1000,
    }
    return "localStorage.setItem('hassTokens', %s);" % json.dumps(json.dumps(payload))


# Reaches into the Control Panel's shadow root for the names it is showing.
# The rendered card is the claim: `_areas` could be right while the page shows
# something else, and what #13 is about is what the user sees.
READ_CARDS = """
() => {
  const panel = document.querySelector("ha-control-panel")
    || [...document.querySelectorAll("*")].find((el) => el.localName === "ha-control-panel");
  if (!panel || !panel.shadowRoot) return null;
  return [...panel.shadowRoot.querySelectorAll("cp-area-card")]
    .map((card) => (card.area || {}).name || "")
    .sort();
}
"""


async def find_panel(page):
    """The Control Panel element, wherever Home Assistant nested it."""
    return await page.evaluate("""
      () => {
        const walk = (root) => {
          for (const el of root.querySelectorAll("*")) {
            if (el.localName === "ha-control-panel") return true;
            if (el.shadowRoot && walk(el.shadowRoot)) return true;
          }
          return false;
        };
        return walk(document);
      }
    """)


async def cards_on_screen(page):
    """The area names the page is rendering, reaching through shadow roots."""
    return await page.evaluate("""
      () => {
        const find = (root) => {
          for (const el of root.querySelectorAll("*")) {
            if (el.localName === "ha-control-panel") return el;
            if (el.shadowRoot) {
              const found = find(el.shadowRoot);
              if (found) return found;
            }
          }
          return null;
        };
        const panel = find(document);
        if (!panel || !panel.shadowRoot) return null;
        return [...panel.shadowRoot.querySelectorAll("cp-area-card")]
          .map((card) => (card.area || {}).name || "")
          .sort();
      }
    """)


async def wait_for_cards(page, predicate, seconds: float):
    """Poll the rendered cards until `predicate` holds, or time runs out."""
    deadline = time.monotonic() + seconds
    latest = await cards_on_screen(page)
    while time.monotonic() < deadline:
        if predicate(latest):
            return latest, True
        await asyncio.sleep(0.25)
        latest = await cards_on_screen(page)
    return latest, predicate(latest)


async def measure(label: str, headed: bool) -> dict:
    url = http_url()
    async with AsyncExitStack() as stack:
        admin = await Session.open(stack, admin_token(), "admin")
        user_id = await nonadmin_user_id(admin)

        capture: dict = {
            "label": label,
            "deployed_version": await admin.deployed_version(),
            "url": url,
        }

        # Which area to move. It has to be one the non-admin already has, so
        # the revoke is a card leaving the screen rather than nothing changing.
        granted = await admin.call({"type": "permission_manager/get_admin_data"})
        permissions = granted.get("permissions", {}).get(user_id, {})
        areas = sorted(
            resource for resource, level in permissions.items()
            if resource.startswith("area_") and level == 1
        )
        if not areas:
            sys.exit(
                "The non-administrator has no area with View permission, so a "
                "revoke would change nothing on screen. Grant one and re-run."
            )
        resource = areas[0]
        area_id = resource[len("area_"):]
        capture["resource"] = resource
        capture["restore_level"] = await stored_level(admin, user_id, resource)

        store_before = None
        SHOTS.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=not headed)
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900}
            )
            await context.add_init_script(auth_script(nonadmin_token(), url))
            page = await context.new_page()
            console_errors: list[str] = []
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" else None)

            await page.goto(url + CONTROL_PANEL, wait_until="domcontentloaded",
                            timeout=45000)
            # The panel loads its own data after the frontend hands it a hass.
            await asyncio.sleep(6)
            capture["panel_found"] = await find_panel(page)

            before = await cards_on_screen(page)
            capture["before"] = before
            await page.screenshot(path=str(SHOTS / f"{label}-1-before.png"))
            if not before:
                capture["error"] = (
                    "No area cards rendered as the non-admin. Nothing can be "
                    "measured leaving a screen that is already empty."
                )
                await browser.close()
                return capture

            # The name the card carries, looked up from the registry so the
            # assertion is about this area and not about a count.
            registry = await admin.call({"type": "config/area_registry/list"})
            target = next(
                (row["name"] for row in registry if row["area_id"] == area_id), None
            )
            capture["target_area"] = target

            # 1. The administrator revokes, on a connection of their own.
            await set_level(admin, user_id, resource, 0)
            gone, ok_gone = await wait_for_cards(
                page, lambda names: names is not None and target not in names,
                CROSS_SECONDS,
            )
            capture["after_revoke"] = gone
            capture["revoke_reached_the_page"] = ok_gone
            await page.screenshot(path=str(SHOTS / f"{label}-2-revoked.png"))

            # 2. And grants it back.
            await set_level(admin, user_id, resource, 1)
            back, ok_back = await wait_for_cards(
                page, lambda names: names is not None and target in names,
                CROSS_SECONDS,
            )
            capture["after_grant"] = back
            capture["grant_reached_the_page"] = ok_back
            await page.screenshot(path=str(SHOTS / f"{label}-3-granted.png"))

            capture["reloads"] = await page.evaluate(
                "() => performance.getEntriesByType('navigation').length"
            )
            capture["console_errors"] = console_errors
            await browser.close()

        # Put the store back the way it was found.
        await set_level(admin, user_id, resource, capture["restore_level"])
        capture["restored_level"] = await stored_level(admin, user_id, resource)

    return capture


def report(capture: dict) -> int:
    failures: list[str] = []
    print("\n" + "=" * 78)
    print("  issue #13 end to end - %s (v%s) on %s"
          % (capture["label"], capture["deployed_version"], capture["url"]))
    print("=" * 78 + "\n")

    if capture.get("error"):
        print("  " + capture["error"])
        return 1

    print("  the Control Panel rendered   : %s" % capture["panel_found"])
    print("  the area moved               : %s (%s)"
          % (capture["target_area"], capture["resource"]))
    print()
    print("  on screen before             : %s" % capture["before"])
    print("  after the administrator revoked: %s   %s"
          % (capture["after_revoke"],
             "ok" if capture["revoke_reached_the_page"] else "STALE"))
    print("  after granting it back       : %s   %s"
          % (capture["after_grant"],
             "ok" if capture["grant_reached_the_page"] else "STALE"))
    print()
    print("  page loads for the whole run : %d (1 = never reloaded)"
          % capture["reloads"])
    print("  console errors               : %d" % len(capture["console_errors"]))
    for message in capture["console_errors"]:
        print("    %s" % message)

    if not capture["panel_found"]:
        failures.append("the Control Panel did not render for the non-admin at all")
    if not capture["revoke_reached_the_page"]:
        failures.append(
            "the revoked area %r was still on screen after %.0fs - a Permission "
            "the administrator took away, still offered"
            % (capture["target_area"], CROSS_SECONDS)
        )
    if not capture["grant_reached_the_page"]:
        failures.append(
            "the re-granted area %r never came back - the page only ever loses "
            "things" % (capture["target_area"],)
        )
    if capture["reloads"] != 1:
        failures.append(
            "the page loaded %d times: this run only proves anything if nothing "
            "reloaded" % capture["reloads"]
        )
    # From v2.0.13 the baseline is zero, for both identities.
    if capture["console_errors"]:
        failures.append(
            "%d console error(s) on a v2.0.13+ page, where the baseline is zero"
            % len(capture["console_errors"])
        )
    if capture["restored_level"] != capture["restore_level"]:
        failures.append(
            "the Permission store was NOT restored: %s left at %s, was %s"
            % (capture["resource"], capture["restored_level"],
               capture["restore_level"])
        )

    print()
    if failures:
        print("  FAIL")
        for failure in failures:
            print("    - %s" % failure)
        return 1
    print("  PASS - an administrator's revoke and grant both reached a page the\n"
          "         non-administrator already had open, and nothing reloaded.")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="name for this run's capture")
    parser.add_argument("--headed", action="store_true", help="watch it happen")
    args = parser.parse_args()

    capture = asyncio.run(measure(args.label, args.headed))

    directory = REPO / "tests" / "reports" / "issue-13"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ("%s-browser.json" % args.label)).write_text(
        json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report(capture)


if __name__ == "__main__":
    sys.exit(main())
