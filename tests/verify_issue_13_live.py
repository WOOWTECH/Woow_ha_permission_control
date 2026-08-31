#!/usr/bin/env python3
"""The premise the #13 fix rests on, measured on a real instance.

`tests/verify_issue_13.py` shows the Control Panel never re-reads. The fix is
to make it re-read when the Panels broadcast arrives - which is only worth
building if two things are true of a **non-administrator's own connection**,
and neither can be checked offline:

  1. `panels_updated` arrives when an *area* or *label* Permission is written.
     #19 measured this for a `panel_*` write. Areas and labels go through the
     same store and the same debouncer, but "the same code path" is an
     argument, not a measurement, and this issue is about areas and labels.

  2. `get_permitted_areas` / `get_permitted_labels`, re-asked on that same
     connection with no reload, return the new answer. If the backend caches
     per-connection, or reads a snapshot taken at connect, then re-reading on
     the broadcast changes nothing and the fix has to go somewhere else.

Usage:
  python3 tests/verify_issue_13_live.py --label v2.0.14

Configuration is `tests/ha_session.py`'s: a repo-root .env supplies HA_URL, the
admin token and HA_TOKEN_NONADMIN (or .ha_nonadmin_token).

**This script writes.** It creates one area and one label, grants and revokes
them on the non-admin, and deletes both again. Nothing of the user's is
touched, but point it at a throwaway instance.

Captures land in tests/reports/issue-13/<label>-live.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from contextlib import AsyncExitStack

from ha_session import (
    REPO,
    Session,
    admin_token,
    load_dotenv,
    nonadmin_token,
    nonadmin_user_id,
)

# Long enough for the Panel Gate's debounce to have run and the broadcast to
# have crossed the wire. Deliberately not read from panel_gate.py: this run is
# not measuring the debounce - #19 does that - it is only waiting it out.
SETTLE = 4.0


async def wait_for_broadcast(page: Session, seconds: float) -> bool:
    """True if `panels_updated` reached this connection within `seconds`."""
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        try:
            raw = await asyncio.wait_for(page.socket.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            return False
        message = json.loads(raw)
        if message.get("type") != "event":
            continue
        if message.get("event", {}).get("event_type") == "panels_updated":
            return True


async def measure(label: str) -> dict:
    async with AsyncExitStack() as stack:
        admin = await Session.open(stack, admin_token(), "admin")
        page = await Session.open(stack, nonadmin_token(), "nonadmin")

        capture: dict = {
            "label": label,
            "deployed_version": await admin.deployed_version(),
        }

        await page.subscribe("panels_updated")
        user_id = await nonadmin_user_id(admin)

        stamp = int(time.time())
        area = await admin.call({
            "type": "config/area_registry/create",
            "name": f"verify-issue-13-{stamp}",
        })
        area_id = area["area_id"]
        label_row = await admin.call({
            "type": "config/label_registry/create",
            "name": f"verify-issue-13-{stamp}",
        })
        label_id = label_row["label_id"]
        capture["area_id"] = area_id
        capture["label_id"] = label_id

        async def permitted(kind: str) -> list[str]:
            if kind == "area":
                result = await page.call({"type": "area_control/get_permitted_areas"})
                return sorted(row["id"] for row in result["areas"])
            result = await page.call({"type": "label_control/get_permitted_labels"})
            return sorted(row["id"] for row in result["labels"])

        async def write(resource_id: str, level: int) -> None:
            await admin.call({
                "type": "permission_manager/set_permission",
                "user_id": user_id,
                "resource_id": resource_id,
                "level": level,
            })

        try:
            steps = []
            for kind, resource_id, target_id in (
                ("area", f"area_{area_id}", area_id),
                ("label", f"label_{label_id}", label_id),
            ):
                for action, level, should_be_present in (
                    ("grant", 1, True),
                    ("revoke", 0, False),
                ):
                    before = await permitted(kind)
                    await write(resource_id, level)
                    heard = await wait_for_broadcast(page, SETTLE)
                    after = await permitted(kind)
                    steps.append({
                        "kind": kind,
                        "action": action,
                        "broadcast_reached_nonadmin": heard,
                        "present_before": target_id in before,
                        "present_after": target_id in after,
                        "should_be_present_after": should_be_present,
                    })
            capture["steps"] = steps
        finally:
            await admin.call(
                {"type": "config/area_registry/delete", "area_id": area_id}
            )
            await admin.call(
                {"type": "config/label_registry/delete", "label_id": label_id}
            )
            areas = await admin.call({"type": "config/area_registry/list"})
            labels = await admin.call({"type": "config/label_registry/list"})
            capture["area_gone"] = area_id not in {a["area_id"] for a in areas}
            capture["label_gone"] = label_id not in {a["label_id"] for a in labels}

    return capture


def report(capture: dict) -> int:
    failures: list[str] = []
    print("\n" + "=" * 78)
    print("  issue #13 premise - live, %s (v%s)"
          % (capture["label"], capture["deployed_version"]))
    print("=" * 78 + "\n")

    for step in capture["steps"]:
        reread_ok = step["present_after"] == step["should_be_present_after"]
        print("  %-6s %-7s  broadcast reached non-admin: %-5s   "
              "re-read gave the new answer: %s"
              % (step["kind"], step["action"],
                 step["broadcast_reached_nonadmin"], reread_ok))
        if not step["broadcast_reached_nonadmin"]:
            failures.append(
                "a %s %s fired no panels_updated the non-admin could hear - the "
                "Control Panel has nothing to listen to" % (step["kind"], step["action"])
            )
        if not reread_ok:
            failures.append(
                "after a %s %s the non-admin re-read on the same connection and got "
                "the old answer - re-reading on the broadcast would not fix #13"
                % (step["kind"], step["action"])
            )

    if not capture.get("area_gone"):
        failures.append("the area %s this run created was not deleted" % capture["area_id"])
    if not capture.get("label_gone"):
        failures.append("the label %s this run created was not deleted" % capture["label_id"])

    print()
    if failures:
        print("  FAIL")
        for failure in failures:
            print("    - %s" % failure)
        return 1
    print("  PASS - the signal reaches the non-admin and a re-read on the same\n"
          "         connection returns the new answer. The gap is the frontend's.")
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="name for this run's capture")
    args = parser.parse_args()

    capture = asyncio.run(measure(args.label))

    directory = REPO / "tests" / "reports" / "issue-13"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ("%s-live.json" % args.label)).write_text(
        json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report(capture)


if __name__ == "__main__":
    sys.exit(main())
