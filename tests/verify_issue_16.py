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

import websockets

REPO = Path(__file__).resolve().parent.parent

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


def _find_upwards(name: str) -> Path | None:
    """The nearest `name` at or above the repo root — see verify_issue_17.py."""
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
    token_file = _find_upwards(".ha_nonadmin_token")
    if token_file is None:
        sys.exit("No non-admin token. Set HA_TOKEN_NONADMIN or add .ha_nonadmin_token")
    return token_file.read_text(encoding="utf-8").strip()


def _ws_url() -> str:
    http_url = os.environ.get("HA_URL", "http://192.168.2.6:8123").rstrip("/")
    return (
        http_url.replace("http://", "ws://").replace("https://", "wss://")
        + "/api/websocket"
    )


class Session:
    """One authenticated WebSocket, kept open so a live page can be imitated."""

    def __init__(self, socket, name: str):
        self.socket = socket
        self.name = name
        self._id = 0
        self.events: list[dict] = []

    @classmethod
    async def open(cls, stack, token: str, name: str) -> "Session":
        socket = await stack.enter_async_context(
            websockets.connect(_ws_url(), max_size=8 * 1024 * 1024)
        )
        hello = json.loads(await socket.recv())
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected greeting: {hello}")
        await socket.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(await socket.recv())
        if auth.get("type") != "auth_ok":
            # An expired non-admin token looks exactly like a working Gate from
            # out here: no panels, and nothing saying why. Say which it is.
            raise RuntimeError(f"{name}: authentication refused — expired token? {auth}")
        return cls(socket, name)

    async def call(self, command: dict) -> dict:
        """One command, with every event that arrives ahead of its result kept."""
        self._id += 1
        message_id = self._id
        await self.socket.send(json.dumps({"id": message_id, **command}))
        while True:
            message = json.loads(await self.socket.recv())
            if message.get("type") == "event":
                self.events.append(message)
                continue
            if message.get("id") != message_id or message.get("type") != "result":
                continue
            if not message.get("success"):
                raise RuntimeError(f"{self.name}: {command['type']} failed: {message.get('error')}")
            return message["result"]

    async def subscribe(self, event_type: str) -> None:
        await self.call({"type": "subscribe_events", "event_type": event_type})

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

    async def panels(self) -> list[str]:
        return sorted(await self.call({"type": "get_panels"}))


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


async def _stored_level(admin: Session, user_id: str) -> int:
    """The level the store currently holds, so the run can put it back."""
    data = await admin.call({"type": "permission_manager/get_admin_data"})
    return data.get("permissions", {}).get(user_id, {}).get(RESOURCE, 0)


async def _set_level(admin: Session, user_id: str, level: int) -> None:
    await admin.call({
        "type": "permission_manager/set_permission",
        "user_id": user_id,
        "resource_id": RESOURCE,
        "level": level,
    })


async def _deployed_version(admin: Session) -> str | None:
    """Which build answered, read off our own panel's module URL."""
    panels = await admin.call({"type": "get_panels"})
    config = (panels.get("ha_permission_manager") or {}).get("config") or {}
    module_url = config.get("module_url") or (config.get("_panel_custom") or {}).get(
        "module_url", ""
    )
    return module_url.split("?v=", 1)[1] if "?v=" in module_url else None


async def _nonadmin_user_id(admin: Session) -> str:
    """The non-admin's own user id, which only the administrator can list.

    `get_admin_data` returns every non-owner user; the one this run acts on is
    the single non-administrator among them. More than one is ambiguous and the
    run says so rather than guessing which sidebar it is about to change.
    """
    data = await admin.call({"type": "permission_manager/get_admin_data"})
    candidates = [user for user in data.get("users", []) if not user["is_admin"]]
    if len(candidates) != 1:
        sys.exit(
            f"Expected exactly one non-administrator on the target, found "
            f"{len(candidates)}. Set the account this run should act on by hand."
        )
    return candidates[0]["id"]


async def measure(label: str, read_only: bool) -> dict:
    async with AsyncExitStack() as stack:
        admin = await Session.open(stack, _admin_token(), "admin")
        # The page that stays open for the whole run. Subscribed before
        # anything is written, because the events it must receive are the
        # measurement.
        page = await Session.open(stack, _nonadmin_token(), "nonadmin")
        await page.subscribe("panels_updated")

        capture: dict = {
            "label": label,
            "panel": PANEL,
            "deployed_version": await _deployed_version(admin),
            "admin_panels": await admin.panels(),
            "nonadmin_panels": await page.panels(),
            "read_only": read_only,
        }
        if read_only:
            return capture

        user_id = await _nonadmin_user_id(admin)
        entry_id = await _entry_id(admin)
        restore_level = await _stored_level(admin, user_id)
        capture["user_id_tail"] = user_id[-6:]
        capture["restore_level"] = restore_level

        # 3. a grant, on a page that is already open
        await _set_level(admin, user_id, 0)
        await page.wait_for_event("panels_updated")
        capture["nonadmin_before_grant"] = await page.panels()

        await _set_level(admin, user_id, 1)
        capture["grant_event"] = await page.wait_for_event("panels_updated")
        capture["nonadmin_after_grant"] = await page.panels()

        # 4. a revoke, on the same connection
        await _set_level(admin, user_id, 0)
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
        await _set_level(admin, user_id, restore_level)
        capture["restored_level"] = await _stored_level(admin, user_id)

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
    if nonadmin >= admin_panels:
        failures.append("the non-admin receives everything the administrator does: nothing is gated")

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
    print("\n  PASS — a denied panel never reached the browser, and the live "
          "updates arrived")
    return 0


def main() -> int:
    _load_dotenv()
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
