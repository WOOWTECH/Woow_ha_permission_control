#!/usr/bin/env python3
"""Live verification for issue #16: does a denied panel still reach the browser?

The Panel Gate's whole claim is about what leaves Home Assistant, so the only
place it can be checked is a live `get_panels` over the wire. Reading the code
is not enough, and #16's own record is why: its spike expected a non-admin to
receive 4 panels and measured 5.

Six measurements, the same six the spike in #16 recorded, so this script and
that table can be read against each other:

  1. a non-administrator's `get_panels`, filtered
  2. an administrator's `get_panels`, not one key touched
  3. a grant reaching a page that is already open
  4. a revoke reaching a page that is already open
  5. disabling the integration, which lifts every restriction with no restart
  6. re-enabling it, which puts them back with no restart

3 and 4 are measured on **one non-admin connection that stays open** for the
whole run. That is the point of them: nothing about a grant is worth much if
the sidebar stays wrong until the user reloads.

Each of those two has two halves, and they belong to different issues:

  - the Gate honouring the new level when the page asks again — #18's claim,
    and part of this run's verdict;
  - `panels_updated` arriving so the page knows to ask — #19's claim, since it
    is #19 that fires the event from the Permission write paths. Measured and
    printed on every run, but only counted in the verdict under
    `--expect-push`, which is what to use once #19 has landed.

Usage:
  python3 tests/verify_issue_16.py --label v2.0.11
  python3 tests/verify_issue_16.py --label v2.0.10-before --read-only
  python3 tests/verify_issue_16.py --label v2.0.12 --expect-push

Configuration (a repo-root .env is read automatically; a git worktree walks up
to find it):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN   admin token
  HA_TOKEN            admin token, if the name above is not set
  HA_TOKEN_NONADMIN   non-admin token; falls back to .ha_nonadmin_token

**This script writes.** Measurements 3 and 4 grant and revoke one panel
Permission on the non-admin, and 5 and 6 disable and re-enable the config
entry. Both are read first and put back at the end, and the run reports whether
the restore succeeded — but point it at a throwaway instance, not a home.
`--read-only` takes measurements 1 and 2 and stops, which is what to use for a
before capture on a version that has no Gate.

Captures land in tests/reports/issue-16/<label>.json.
"""
import argparse
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from ha_session import (
    REPO,
    Session,
    load_dotenv,
    admin_token,
    nonadmin_token,
    nonadmin_user_id,
    set_level,
    stored_level,
)

# The panel the grant and the revoke are measured on. `home` is what #16's
# spike used, and it is the one panel a non-admin's sidebar is most obviously
# missing when the Gate is on.
PANEL = os.environ.get("VERIFY_PANEL", "home")
RESOURCE = f"panel_{PANEL}"

# What a refused non-administrator still receives. panel_policy holds the
# reasoning; this is the same pair, spelt for the report.
DEGRADED = {"notfound", "profile"}

# How long to wait for `panels_updated` on the open connection. Short while the
# push is a measurement rather than an expectation — until #19 lands every one
# of these waits runs out, and there are three of them.
EVENT_TIMEOUT = 6.0


class Page(Session):
    """A Session that also waits for events and reads its own report.

    `wait_for_event` is what makes this run's grant and revoke measurable on a
    connection that never closes; `reported_panels` is #17's other half. Both
    are particular to this issue, so neither is in the shared helper.
    """

    def __init__(self, socket, name):
        super().__init__(socket, name)
        self.events: list[dict] = []

    async def call(self, command: dict, keep_events=None) -> dict:
        # Events that arrive mid-command are the measurement here, so they are
        # kept rather than dropped.
        return await super().call(command, keep_events=self.events)

    async def wait_for_event(self, event_type: str, timeout: float = EVENT_TIMEOUT) -> bool:
        """Whether `event_type` arrives on this connection inside `timeout`."""
        for event in self.events:
            if event.get("event", {}).get("event_type") == event_type:
                self.events.remove(event)
                return True
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            try:
                raw = await asyncio.wait_for(
                    self.socket.recv(), timeout=max(0.1, deadline - loop.time())
                )
            except asyncio.TimeoutError:
                return False
            message = json.loads(raw)
            if message.get("type") != "event":
                continue
            if message.get("event", {}).get("event_type") == event_type:
                return True
            self.events.append(message)
        return False

    async def reported_panels(self) -> list[str]:
        """The panels this identity is *told* it may see, at a level above Closed.

        The other half of #17's one-answer guarantee. Compared against
        `panels()` it is what catches an instance with no Gate on it, which
        nothing else in this run can see.
        """
        result = await self.call({"type": "permission_manager/get_panel_permissions"})
        return sorted(
            panel_id
            for panel_id, level in result.get("permissions", {}).items()
            if level > 0
        )


async def _entry_id(admin: Session) -> str:
    entries = await admin.call({"type": "config_entries/get", "domain": "ha_permission_manager"})
    if not entries:
        sys.exit("No ha_permission_manager config entry on the target instance")
    return entries[0]["entry_id"]


async def _set_entry_disabled(admin: Session, entry_id: str, disabled: bool) -> None:
    await admin.call({
        "type": "config_entries/disable",
        "entry_id": entry_id,
        "disabled_by": "user" if disabled else None,
    })


async def measure(label: str, read_only: bool) -> dict:
    async with AsyncExitStack() as stack:
        admin = await Session.open(stack, admin_token(), "admin")
        # The page that stays open for the whole run. Subscribed before
        # anything is written, because the events it must receive are the
        # measurement.
        page = await Page.open(stack, nonadmin_token(), "nonadmin")
        await page.subscribe("panels_updated")

        capture: dict = {
            "label": label,
            "panel": PANEL,
            "deployed_version": await admin.deployed_version(),
            "admin_panels": await admin.panels(),
            "nonadmin_panels": await page.panels(),
            "nonadmin_reported": await page.reported_panels(),
            "read_only": read_only,
        }
        if read_only:
            return capture

        user_id = await nonadmin_user_id(admin)
        entry_id = await _entry_id(admin)
        restore_level = await stored_level(admin, user_id, RESOURCE)
        capture["user_id_tail"] = user_id[-6:]
        capture["restore_level"] = restore_level

        # 3. a grant, on a page that is already open
        await set_level(admin, user_id, RESOURCE, 0)
        await page.wait_for_event("panels_updated")
        capture["nonadmin_before_grant"] = await page.panels()

        await set_level(admin, user_id, RESOURCE, 1)
        capture["grant_event"] = await page.wait_for_event("panels_updated")
        capture["nonadmin_after_grant"] = await page.panels()

        # 4. a revoke, on the same connection
        await set_level(admin, user_id, RESOURCE, 0)
        capture["revoke_event"] = await page.wait_for_event("panels_updated")
        capture["nonadmin_after_revoke"] = await page.panels()

        # 5 and 6. the integration off, and back on, with no restart
        await _set_entry_disabled(admin, entry_id, True)
        await asyncio.sleep(2)
        capture["nonadmin_disabled"] = await page.panels()
        capture["admin_disabled"] = await admin.panels()

        await _set_entry_disabled(admin, entry_id, False)
        await asyncio.sleep(4)
        capture["nonadmin_reenabled"] = await page.panels()

        # Put the store back the way it was found.
        await set_level(admin, user_id, RESOURCE, restore_level)
        capture["restored_level"] = await stored_level(admin, user_id, RESOURCE)

    return capture


def report(capture: dict, expect_push: bool) -> int:
    admin_panels = set(capture["admin_panels"])
    nonadmin = set(capture["nonadmin_panels"])
    failures: list[str] = []

    print(f"\n{'=' * 78}")
    print(f"  issue #16 — Panel Gate, {capture['label']} (v{capture['deployed_version']})")
    print(f"{'=' * 78}\n")
    print(f"  administrator get_panels : {len(admin_panels)}")
    print(f"  non-admin     get_panels : {len(nonadmin)}  {sorted(nonadmin)}")

    if "ha_permission_manager" not in admin_panels:
        failures.append("the Permission Manager panel is missing from the administrator's list")
    if not DEGRADED <= nonadmin:
        failures.append(
            f"the non-admin is missing {sorted(DEGRADED - nonadmin)} — the router has no fallback"
        )
    # The teeth of a read-only run, and #17's guarantee turned into a
    # measurement: the Gate deciding and get_panel_permissions reporting are
    # the same function, so for a non-administrator the panels they receive and
    # the panels they are reported to be permitted must be the same set.
    #
    # It is also the only check here that fails on an instance with no Gate at
    # all — and the first version of this script did not have it, so a v2.0.9
    # instance handing a non-admin all 28 panels was reported as a PASS. The
    # comparison against the administrator's list cannot catch that: Home
    # Assistant filters its own admin-only panels, so a non-admin is never a
    # superset of an administrator however wide open the instance is.
    reported = set(capture["nonadmin_reported"])
    print(f"  non-admin     reported   : {len(reported)}  {sorted(reported)}")
    if nonadmin != reported:
        failures.append(
            f"the non-admin receives {len(nonadmin)} panels but is reported permitted "
            f"{len(reported)}: receives-but-not-permitted "
            f"{sorted(nonadmin - reported)}, permitted-but-not-received "
            f"{sorted(reported - nonadmin)}. Either the Gate is not running or it "
            f"and get_panel_permissions have parted company."
        )

    if capture["read_only"]:
        print("\n  read-only run: the grant, the revoke and the disable cycle were skipped.")
        return _verdict(failures)

    granted = set(capture["nonadmin_after_grant"])
    before_grant = set(capture["nonadmin_before_grant"])
    revoked = set(capture["nonadmin_after_revoke"])
    disabled = set(capture["nonadmin_disabled"])
    reenabled = set(capture["nonadmin_reenabled"])
    panel = capture["panel"]

    print(f"\n  on one non-admin connection that never closed, for `{panel}`:")
    print(f"    before the grant         : {len(before_grant)}  {panel} present: {panel in before_grant}")
    print(f"    panels_updated arrived   : {capture['grant_event']}")
    print(f"    after the grant          : {len(granted)}  {panel} present: {panel in granted}")
    print(f"    panels_updated arrived   : {capture['revoke_event']}")
    print(f"    after the revoke         : {len(revoked)}  {panel} present: {panel in revoked}")

    # The administrator's answer, measured rather than read off the code.
    # Disabling removes our own two panels along with the Gate, so an
    # administrator who was never filtered has exactly those two fewer panels
    # and not one key besides. #16's spike recorded the same subtraction.
    admin_disabled = set(capture["admin_disabled"])
    ours = {"ha_permission_manager", "ha-control-panel"}
    untouched = admin_disabled == admin_panels - ours

    print(f"\n  the integration disabled, no restart:")
    print(f"    non-admin get_panels     : {len(disabled)}  gated: {disabled != admin_disabled}")
    print(f"    admin     get_panels     : {len(admin_disabled)}  "
          f"(was {len(admin_panels)}, less our own {sorted(ours)})")
    print(f"    the admin was never filtered : {untouched}")
    print(f"    re-enabled               : {len(reenabled)}")

    if panel in before_grant:
        failures.append(f"`{panel}` was already offered at Closed — the Gate is not filtering it")
    if panel not in granted:
        failures.append(f"the grant did not reach the open connection: `{panel}` never appeared")
    if panel in revoked:
        failures.append(f"the revoke did not reach the open connection: `{panel}` is still offered")

    # The push half. #19 fires `panels_updated` from the Permission write
    # paths; until it lands these two are expected to be False, and saying so
    # is more use than a red run everybody learns to ignore.
    for arrived, what in (
        (capture["grant_event"], "grant"),
        (capture["revoke_event"], "revoke"),
    ):
        if arrived:
            continue
        message = f"no panels_updated reached the open non-admin connection on the {what}"
        if expect_push:
            failures.append(message)
        else:
            print(f"    (#19 has not landed: {message})")
    if not untouched:
        failures.append(
            "the administrator's list was not left alone: with the Gate off it gains "
            f"{sorted(admin_disabled - (admin_panels - ours))} and loses "
            f"{sorted((admin_panels - ours) - admin_disabled)} against the Gate's "
            "own answer less our two panels"
        )
    if disabled <= nonadmin:
        failures.append(
            "disabling the integration did not lift the restrictions — the Gate was not handed back"
        )
    if reenabled != nonadmin:
        failures.append(
            f"re-enabling did not restore the gated list: {sorted(reenabled)} "
            f"against {sorted(nonadmin)}"
        )
    if capture["restored_level"] != capture["restore_level"]:
        failures.append(
            f"the Permission store was NOT restored: `{RESOURCE}` left at "
            f"{capture['restored_level']}, was {capture['restore_level']}"
        )

    return _verdict(failures)


def _verdict(failures: list[str]) -> int:
    if failures:
        print("\n  FAIL")
        for failure in failures:
            print(f"    - {failure}")
        return 1
    # Deliberately says only what was checked. It used to claim "and the live
    # updates arrived", which was false on every run until #19 lands — the
    # push is measured and printed, and only counted under --expect-push.
    print("\n  PASS — a denied panel never reached the browser, and what the "
          "Gate sends is what it reports")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="name for this run's capture")
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="measurements 1 and 2 only; writes nothing and disables nothing",
    )
    parser.add_argument(
        "--expect-push",
        action="store_true",
        help="count a missing panels_updated as a failure — use once #19 has landed",
    )
    args = parser.parse_args()

    capture = asyncio.run(measure(args.label, args.read_only))

    directory = REPO / "tests" / "reports" / "issue-16"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{args.label}.json").write_text(
        json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
    )

    return report(capture, args.expect_push)


if __name__ == "__main__":
    sys.exit(main())
