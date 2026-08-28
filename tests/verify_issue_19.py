#!/usr/bin/env python3
"""Live verification for issue #19: does a Permission write reach a live page?

The Panel Gate decides what a browser receives. This is what tells the browser
to ask again. Two claims, and neither can be checked offline:

  1. `panels_updated` reaches a **non-administrator's** connection. The whole
     point: Home Assistant refuses that user's subscription to
     `permission_manager_updated` (#13), so if this does not arrive, a
     revocation reaches the user it is about only when they reload.

  2. A burst of writes collapses. The debounce is Home Assistant's `Debouncer`
     at 1.0 s with the leading edge first, so N writes in quick succession
     should produce far fewer than N broadcasts — and at least one, promptly.
     tests/test_panel_gate.py deliberately does not test this: it stubs the
     Debouncer, because reimplementing a timer to check a timer only proves the
     reimplementation right.

Three paths are measured, because they fail differently:

  - a grant and a revoke through `permission_manager/set_permission`;
  - a burst of single writes, which is the case the debounce is actually for;
  - an **area deletion**, which reaches the store through the registry listener
     with no service handler in front of it. #19's own comment calls this the
     path most worth having the event on, because nobody is watching a page at
     that moment. The area is created by this script and deleted again.

Usage:
  python3 tests/verify_issue_19.py --label v2.0.12
  python3 tests/verify_issue_19.py --label v2.0.12 --burst 8

Configuration (a repo-root .env is read automatically; a git worktree walks up
to find it):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN   admin token
  HA_TOKEN            admin token, if the name above is not set
  HA_TOKEN_NONADMIN   non-admin token; falls back to .ha_nonadmin_token

**This script writes.** It grants and revokes one panel Permission on the
non-admin, and it creates and deletes one area. Both are read first and put
back, and the run reports whether the restore succeeded — but point it at a
throwaway instance, not a home.

Captures land in tests/reports/issue-19/<label>.json.
"""
import argparse
import asyncio
import json
import os
import sys
import time
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

PANEL = os.environ.get("VERIFY_PANEL", "home")
RESOURCE = f"panel_{PANEL}"

# The debounce this run is measuring, from panel_gate.PANELS_UPDATED_COOLDOWN.
# Read rather than restated so a change to the cooldown moves the wait with it.
COOLDOWN = float(
    (REPO / "custom_components" / "ha_permission_manager" / "panel_gate.py")
    .read_text(encoding="utf-8")
    .split("PANELS_UPDATED_COOLDOWN = ", 1)[1]
    .split("\n", 1)[0]
)

# How long to keep listening after a write. Two cooldowns plus a margin, so a
# trailing broadcast has landed and any second one would have too.
SETTLE = COOLDOWN * 2 + 1.5


class Listener:
    """Counts `panels_updated` on one connection, with arrival times."""

    def __init__(self, session: Session):
        self.session = session
        self.times: list[float] = []
        self._task: asyncio.Task | None = None
        self._started = 0.0

    async def _run(self) -> None:
        while True:
            message = json.loads(await self.session.socket.recv())
            if message.get("type") != "event":
                continue
            if message.get("event", {}).get("event_type") == "panels_updated":
                self.times.append(time.monotonic() - self._started)

    def start(self) -> None:
        self._started = time.monotonic()
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def reset(self) -> None:
        self.times.clear()
        self._started = time.monotonic()

    def seen(self) -> list[float]:
        """Arrival times since the last reset, in seconds, rounded."""
        return [round(t, 2) for t in self.times]


async def measure(label: str, burst: int) -> dict:
    async with AsyncExitStack() as stack:
        admin = await Session.open(stack, admin_token(), "admin")
        page = await Session.open(stack, nonadmin_token(), "nonadmin")

        capture: dict = {
            "label": label,
            "cooldown": COOLDOWN,
            "burst_size": burst,
            "deployed_version": await admin.deployed_version(),
        }

        # Premise first: is a non-admin even allowed to hear this?
        try:
            await page.subscribe("panels_updated")
            capture["nonadmin_may_subscribe"] = True
        except RuntimeError as error:
            capture["nonadmin_may_subscribe"] = False
            capture["subscribe_error"] = str(error)
            return capture

        user_id = await nonadmin_user_id(admin)
        restore_level = await stored_level(admin, user_id, RESOURCE)
        capture["restore_level"] = restore_level

        listener = Listener(page)
        listener.start()

        # 1. one grant
        await set_level(admin, user_id, RESOURCE, 0)
        await asyncio.sleep(SETTLE)
        listener.reset()
        await set_level(admin, user_id, RESOURCE, 1)
        await asyncio.sleep(SETTLE)
        capture["grant"] = listener.seen()

        # 2. one revoke
        listener.reset()
        await set_level(admin, user_id, RESOURCE, 0)
        await asyncio.sleep(SETTLE)
        capture["revoke"] = listener.seen()

        # 3. a burst of separate writes — the case the debounce is for
        listener.reset()
        burst_started = time.monotonic()
        for index in range(burst):
            await set_level(admin, user_id, RESOURCE, index % 2)
        # How long the writes themselves took. If that is longer than the
        # cooldown they were never one burst, and there was nothing to collapse.
        capture["burst_seconds"] = round(time.monotonic() - burst_started, 2)
        await asyncio.sleep(SETTLE)
        capture["burst"] = listener.seen()

        # 4. the registry-listener path: an area deletion with no service
        #    handler in front of it. Created here so nothing of the user's is
        #    touched, granted on so the deletion has a Permission to remove.
        area = await admin.call({
            "type": "config/area_registry/create",
            "name": f"verify-issue-19-{int(time.time())}",
        })
        area_id = area["area_id"]
        capture["area_id"] = area_id
        await admin.call({
            "type": "permission_manager/set_permission",
            "user_id": user_id,
            "resource_id": f"area_{area_id}",
            "level": 1,
        })
        await asyncio.sleep(SETTLE)

        listener.reset()
        await admin.call({"type": "config/area_registry/delete", "area_id": area_id})
        await asyncio.sleep(SETTLE)
        capture["area_deletion"] = listener.seen()

        areas = await admin.call({"type": "config/area_registry/list"})
        capture["area_gone"] = area_id not in {a["area_id"] for a in areas}

        await listener.stop()

        # Put the store back the way it was found.
        await set_level(admin, user_id, RESOURCE, restore_level)
        capture["restored_level"] = await stored_level(admin, user_id, RESOURCE)

    return capture


def report(capture: dict) -> int:
    failures: list[str] = []
    burst = capture["burst_size"]

    print(f"\n{'=' * 78}")
    print(f"  issue #19 — panels_updated from every Permission write, "
          f"{capture['label']} (v{capture['deployed_version']})")
    print(f"{'=' * 78}\n")

    print(f"  a non-admin may subscribe : {capture['nonadmin_may_subscribe']}")
    if not capture["nonadmin_may_subscribe"]:
        print(f"    {capture.get('subscribe_error')}")
        failures.append(
            "Home Assistant refused the non-admin's subscription to panels_updated. "
            "The premise of #19 does not hold on this instance."
        )
        return _verdict(failures)

    print(f"  debounce cooldown         : {capture['cooldown']}s\n")
    rows = [
        ("one grant", "grant", 1),
        ("one revoke", "revoke", 1),
        (f"a burst of {burst} writes", "burst", burst),
        ("an area deletion", "area_deletion", 1),
    ]
    for name, key, writes in rows:
        times = capture[key]
        print(f"  {name:24} {writes:2d} write(s) -> {len(times)} event(s)  at {times}s")

    for name, key, _writes in rows:
        if not capture[key]:
            failures.append(f"no panels_updated reached the non-admin on {name}")

    # The debounce, bounded from both sides. Fewer than `burst` is not enough
    # on its own: a debouncer that fires the leading edge and drops the
    # trailing one gives exactly 1 event for 6 writes, and that is the worst
    # failure of the lot — the *last* write of a burst is the one that never
    # reaches the page, and the last write is as likely as not a revocation.
    burst_events = len(capture["burst"])
    burst_seconds = capture["burst_seconds"]
    print(f"\n  the {burst} writes took {burst_seconds}s to send "
          f"(they must fit inside {capture['cooldown']}s to be one burst)")

    if burst_seconds > capture["cooldown"]:
        # Not a failure of the code. The instance was too slow for the writes
        # to be a burst at all, so there was nothing to collapse.
        print("  !! too slow to be a burst — the debounce claim is not tested by "
              "this run")
    elif burst_events >= burst:
        failures.append(
            f"the burst was not debounced: {burst} writes produced {burst_events} "
            f"events. A write path is firing directly instead of through the debouncer."
        )
    elif burst_events < 2:
        failures.append(
            f"the burst produced {burst_events} event(s): the leading edge went out "
            f"and nothing followed it. The last write of the burst never reached the "
            f"page, which for a revocation means access that looks revoked and is not."
        )
    elif capture["burst"][-1] < burst_seconds:
        failures.append(
            f"the last broadcast of the burst landed at {capture['burst'][-1]}s, before "
            f"the last write went out at {burst_seconds}s — nothing announced the "
            f"final write"
        )

    # The leading edge. Compared against half a cooldown, not a whole one: a
    # debouncer with `immediate=False` delivers at about exactly the cooldown,
    # and a rounded 1.0 is not greater than 1.0.
    if capture["grant"] and capture["grant"][0] > capture["cooldown"] / 2:
        failures.append(
            f"the first event after a grant took {capture['grant'][0]}s, more than half "
            f"the {capture['cooldown']}s cooldown — the leading edge is not immediate"
        )

    if not capture.get("area_gone"):
        failures.append(f"the area {capture.get('area_id')} this run created was not deleted")
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
    print("\n  PASS — every write reached the non-admin's own connection, and a "
          "burst collapsed")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="name for this run's capture")
    parser.add_argument(
        "--burst", type=int, default=6, help="writes to send back-to-back (default 6)"
    )
    args = parser.parse_args()

    capture = asyncio.run(measure(args.label, args.burst))

    directory = REPO / "tests" / "reports" / "issue-19"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{args.label}.json").write_text(
        json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
    )

    return report(capture)


if __name__ == "__main__":
    sys.exit(main())
