#!/usr/bin/env python3
"""Live verification for issue #8: is a deleted dashboard's Permission forgotten?

#8 was filed against one guard — `if not url_path: return` in front of the
`action == "delete"` branch — and asked, as its open question, which deletions
actually arrive without a `url_path`. Reading Home Assistant's source answers
something larger: `lovelace_updated` carries `{"url_path": ...}` and nothing
else, on 2025.7.0, on 2026.7.2 and on dev. There is no `action` key at all, so
the branch was never taken by any deletion, with a url_path or without one.

That is a claim about the payload of an event on a running instance, which is
exactly the kind of claim this repo does not take on reading alone. Three
things are measured here, in one run:

  1. **What a deletion actually says.** The event is captured off the bus, as
     it arrives, on a save and on a delete of the same dashboard. Whether it
     carries an `action`, and whether the `url_path` is there, is then a
     record rather than an argument.

  2. **Whether the panel has already gone** by the time the event is read.
     This is what the fix reads instead of `action`: Home Assistant's own
     `storage_dashboard_changed` removes the panel before the config it then
     deletes fires the event, so a url_path with no panel behind it is a
     dashboard that is gone. If the panel were still registered here, the fix
     would be reading a coin flip.

  3. **Whether the Permission row survives the dashboard.** The point of the
     issue: grant a level on the new dashboard, delete the dashboard, and ask
     the store. Before the fix the row is still there — which is the live
     reproduction #8 says it never had. After it, the row is gone.

Run it against the release before the deploy and the release after, and diff
the two records:

  python3 tests/verify_issue_8.py --label v2.0.13-before
  python3 tests/verify_issue_8.py --label v2.0.14-after

Configuration (a repo-root .env is read automatically; a git worktree walks up
to find it):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN   admin token
  HA_TOKEN            admin token, if the name above is not set

**This script writes.** It creates one dashboard, saves a config onto it,
grants one Permission on it to the non-administrator, then deletes the
dashboard and removes the Resource's rows. Everything it makes, it unmakes —
and the run reports whether it managed to. Point it at a throwaway instance,
not a home.

Captures land in tests/reports/issue-8/<label>.json.
"""
import argparse
import asyncio
import json
import sys
import time
from contextlib import AsyncExitStack

from ha_session import (
    REPO,
    Session,
    load_dotenv,
    admin_token,
    nonadmin_user_id,
    stored_level,
)

# How long to wait for the store to catch up with an event. The listener that
# does the cleanup is a task Home Assistant schedules off the bus, so it lands
# some time after the delete command returns, not before.
SETTLE = 3.0


class Listener:
    """Keeps every `lovelace_updated` that arrives on one connection."""

    def __init__(self, session: Session):
        self.session = session
        self.events: list[dict] = []
        self._task: asyncio.Task | None = None

    async def _run(self) -> None:
        while True:
            message = json.loads(await self.session.socket.recv())
            if message.get("type") != "event":
                continue
            event = message.get("event", {})
            if event.get("event_type") == "lovelace_updated":
                self.events.append(event.get("data", {}))

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def take(self) -> list[dict]:
        """The payloads seen so far, and forget them."""
        seen = list(self.events)
        self.events.clear()
        return seen


async def measure(label: str) -> dict:
    url_path = f"verify-issue-8-{int(time.time())}"
    resource_id = f"panel_{url_path}"

    async with AsyncExitStack() as stack:
        admin = await Session.open(stack, admin_token(), "admin")
        # A second connection, doing nothing but listening: `call` drops the
        # events that arrive while it waits for its own result, and the event
        # this run is about arrives inside the delete call.
        bus = await Session.open(stack, admin_token(), "bus")

        capture: dict = {
            "label": label,
            "url_path": url_path,
            "resource_id": resource_id,
            "deployed_version": await admin.deployed_version(),
        }

        await bus.subscribe("lovelace_updated")
        listener = Listener(bus)
        listener.start()

        user_id = await nonadmin_user_id(admin)
        capture["user_id"] = user_id

        dashboard = await admin.call({
            "type": "lovelace/dashboards/create",
            "url_path": url_path,
            "title": "Verify issue 8",
            "require_admin": False,
            "show_in_sidebar": True,
        })
        dashboard_id = dashboard["id"]
        capture["dashboard_id"] = dashboard_id
        await asyncio.sleep(SETTLE)
        capture["panel_registered"] = url_path in await admin.call(
            {"type": "get_panels"}
        )

        await admin.call({
            "type": "permission_manager/set_permission",
            "user_id": user_id,
            "resource_id": resource_id,
            "level": 1,
        })
        await asyncio.sleep(SETTLE)
        capture["level_before_delete"] = await stored_level(
            admin, user_id, resource_id
        )

        # A save, on the granted row. It holds the other payload — what the
        # event says when the dashboard survives, which is the same shape as
        # what it says when it does not — and it is the regression the fix
        # could introduce: a save read as a deletion takes the row with it.
        listener.take()
        await admin.call({
            "type": "lovelace/config/save",
            "url_path": url_path,
            "config": {"views": [{"title": "Verify", "cards": []}]},
        })
        await asyncio.sleep(SETTLE)
        capture["save_events"] = listener.take()
        capture["level_after_save"] = await stored_level(admin, user_id, resource_id)

        await admin.call({
            "type": "lovelace/dashboards/delete",
            "dashboard_id": dashboard_id,
        })
        await asyncio.sleep(SETTLE)
        capture["delete_events"] = listener.take()
        capture["panel_gone"] = url_path not in await admin.call(
            {"type": "get_panels"}
        )
        capture["level_after_delete"] = await stored_level(
            admin, user_id, resource_id
        )

        await listener.stop()

        # Leave the store as it was found. On a build without the fix this is
        # the row the integration should have removed; on one with it, this
        # removes nothing and says so.
        await admin.call({
            "type": "call_service",
            "domain": "ha_permission_manager",
            "service": "remove_resource_permissions",
            "service_data": {"resource_id": resource_id},
        })
        await asyncio.sleep(SETTLE)
        capture["level_after_cleanup"] = await stored_level(
            admin, user_id, resource_id
        )
        dashboards = await admin.call({"type": "lovelace/dashboards/list"})
        capture["dashboard_removed"] = url_path not in {
            entry["url_path"] for entry in dashboards
        }

    return capture


def report(capture: dict) -> int:
    failures: list[str] = []
    delete_events = capture["delete_events"]

    print(f"\n{'=' * 78}")
    print(f"  issue #8 — a deleted dashboard's Permissions, "
          f"{capture['label']} (v{capture['deployed_version']})")
    print(f"{'=' * 78}\n")

    print(f"  dashboard                 : {capture['url_path']}")
    print(f"  panel registered on create: {capture['panel_registered']}")
    print(f"  panel gone after delete   : {capture['panel_gone']}")
    print(f"  payload on a save         : {capture['save_events']}")
    print(f"  payload on a delete       : {delete_events}")

    carries_action = any("action" in event for event in delete_events)
    carries_url_path = any(event.get("url_path") for event in delete_events)
    print(f"  a delete carries `action` : {carries_action}")
    print(f"  a delete carries url_path : {carries_url_path}\n")

    after_save = capture.get("level_after_save", "n/a")
    print(f"  level granted, before     : {capture['level_before_delete']}")
    print(f"  level held, after a save  : {after_save}")
    print(f"  level held, after delete  : {capture['level_after_delete']}")

    if capture["level_before_delete"] != 1:
        failures.append(
            "the grant this run depends on never landed: the store held "
            f"{capture['level_before_delete']} for {capture['resource_id']} before the "
            "deletion, so nothing was measured"
        )
    elif capture["level_after_delete"] != 0:
        failures.append(
            f"the deleted dashboard kept its Permission: {capture['resource_id']} is "
            f"still {capture['level_after_delete']} in the store. This is issue #8, "
            "reproduced."
        )

    if after_save not in (1, "n/a"):
        failures.append(
            f"an ordinary save took the Permission with it: {capture['resource_id']} "
            f"dropped to {after_save} on a save, with the dashboard still there. A "
            "save and a delete carry the same payload, and this is what telling them "
            "apart wrongly costs."
        )

    if not capture["panel_gone"]:
        failures.append(
            "the panel was still registered after the dashboard was deleted — the "
            "signal the fix reads is not there"
        )
    if not delete_events:
        failures.append("no lovelace_updated arrived on the delete at all")
    if not carries_url_path:
        failures.append(
            "the delete event carried no url_path, so no payload names the Resource"
        )

    if capture["level_after_cleanup"] != 0:
        failures.append(
            f"the store was NOT restored: {capture['resource_id']} left at "
            f"{capture['level_after_cleanup']}"
        )
    if not capture["dashboard_removed"]:
        failures.append(
            f"the dashboard {capture['url_path']} this run created was not deleted"
        )

    if failures:
        print("\n  FAIL")
        for failure in failures:
            print(f"    - {failure}")
        return 1
    print("\n  PASS — the dashboard went, and its Permission went with it")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="name for this run's capture")
    args = parser.parse_args()

    capture = asyncio.run(measure(args.label))

    directory = REPO / "tests" / "reports" / "issue-8"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{args.label}.json").write_text(
        json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
    )

    return report(capture)


if __name__ == "__main__":
    sys.exit(main())
