#!/usr/bin/env python3
"""Live verification for issue #17: did the report change what a user receives?

Issue #17 moved every rule about which panels a user may receive into
`panel_policy.visible_panel_ids()` and made `get_panel_permissions` read its
answer from there. The claim that has to be measured is that **no sidebar gains
or loses a row**: the payload changes shape, and nothing a user sees changes
with it.

Reading the Filters is not enough to know that. Issue #16's own record is the
reason — its spike expected a non-admin to receive 4 panels and measured 5, and
the difference was found by measuring, not by reading.

So this script captures, per identity, straight off the WebSocket:

  panel_ids     Home Assistant's own get_panels answer for that user
  permissions   permission_manager/get_panel_permissions
  is_admin      as that endpoint reports it

and then computes the sidebar the Filter would build, by handing the pair to
the real `filterPanels()` out of frontend/permission_policy.js — the function
that actually decides, not a restatement of it. Two runs either side of a
deploy are compared on that computed set.

The two questions only a live instance answers:

  1. Is the non-admin's sidebar set identical before and after?
  2. Is the non-admin's `permissions` map non-empty? An empty one means
     `get_registered_panels(hass)` was empty when the browser asked, which
     after #17 empties the sidebar rather than being harmless.

Usage:
  python3 tests/verify_issue_17.py --label v2.0.8-before
  python3 tests/verify_issue_17.py --compare v2.0.8-before v2.0.10-after

Configuration (a repo-root .env is read automatically; a git worktree walks up
to find it):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN   admin token
  HA_TOKEN            admin token, if the name above is not set
  HA_TOKEN_NONADMIN   non-admin token; falls back to .ha_nonadmin_token

Read-only: this script never writes a Permission and never restarts anything.
Captures land in tests/reports/issue-17/<label>.json.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import websockets

REPO = Path(__file__).resolve().parent.parent


def _find_upwards(name: str) -> Path | None:
    """The nearest `name` at or above the repo root.

    A git worktree keeps its own root, and the untracked credentials live at
    the root of the checkout it was made from. Walking up finds them from
    either place without either place having to know about the other.
    """
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
    return http_url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"


async def _capture(token: str) -> dict:
    """One identity's panels and permissions, straight off the WebSocket."""
    async with websockets.connect(_ws_url(), max_size=8 * 1024 * 1024) as socket:
        hello = json.loads(await socket.recv())
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected greeting: {hello}")

        await socket.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(await socket.recv())
        if auth.get("type") != "auth_ok":
            # An expired non-admin token looks exactly like a broken Filter
            # from the browser. Say which it is before anything else is read.
            raise RuntimeError(f"Authentication refused — expired token? {auth}")

        async def call(message_id: int, command: dict) -> dict:
            await socket.send(json.dumps({"id": message_id, **command}))
            while True:
                message = json.loads(await socket.recv())
                if message.get("id") == message_id and message.get("type") == "result":
                    if not message.get("success"):
                        raise RuntimeError(f"{command['type']} failed: {message.get('error')}")
                    return message["result"]

        panels = await call(1, {"type": "get_panels"})
        reported = await call(2, {"type": "permission_manager/get_panel_permissions"})
        everything = await call(3, {"type": "permission_manager/get_all_permissions"})

    # Our own panel carries the deployed PANEL_VERSION in the URL it loads its
    # module from, so a capture says which build produced it without being
    # told. Home Assistant nests a custom panel's registration under
    # `_panel_custom`, so the url is looked for at both depths.
    deployed_version = None
    config = (panels.get("ha_permission_manager") or {}).get("config") or {}
    module_url = config.get("module_url") or (config.get("_panel_custom") or {}).get("module_url", "")
    if module_url and "?v=" in module_url:
        deployed_version = module_url.split("?v=", 1)[1]

    return {
        "panel_ids": sorted(panels),
        "permissions": reported.get("permissions", {}),
        "is_admin": reported.get("is_admin"),
        "all_permissions_panels": everything.get("panels", {}),
        "deployed_version": deployed_version,
    }


def _sidebars(capture: dict) -> dict:
    """The sidebar each identity would see, from the real filterPanels().

    Shelling out to node is the point: the decision has to come from the
    shipped JavaScript, not from a Python restatement of it that could be
    wrong in the same direction as the change under test.
    """
    script = REPO / "tests" / "sidebar_from_capture.mjs"
    completed = subprocess.run(
        ["node", str(script)],
        input=json.dumps(capture),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        sys.exit(f"sidebar_from_capture.mjs failed:\n{completed.stderr}")
    return json.loads(completed.stdout)


def _report_path(label: str) -> Path:
    directory = REPO / "tests" / "reports" / "issue-17"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{label}.json"


def run_capture(label: str) -> None:
    identities = {
        "admin": asyncio.run(_capture(_admin_token())),
        "nonadmin": asyncio.run(_capture(_nonadmin_token())),
    }
    capture = {"label": label, "identities": identities}
    capture["sidebars"] = _sidebars(capture)

    _report_path(label).write_text(json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8")

    print(f"captured {label}")
    for identity, data in identities.items():
        print(
            f"  {identity:9} version={data['deployed_version']} is_admin={data['is_admin']} "
            f"panels={len(data['panel_ids'])} permissions={len(data['permissions'])} "
            f"sidebar={len(capture['sidebars'][identity])}"
        )
    if not identities["nonadmin"]["permissions"]:
        print("  !! the non-admin permissions map is EMPTY — get_registered_panels was empty")


def run_compare(before_label: str, after_label: str) -> int:
    before = json.loads(_report_path(before_label).read_text(encoding="utf-8"))
    after = json.loads(_report_path(after_label).read_text(encoding="utf-8"))

    failures = []
    print(f"{before_label}  ->  {after_label}\n")

    for identity in ("admin", "nonadmin"):
        old_sidebar = set(before["sidebars"][identity])
        new_sidebar = set(after["sidebars"][identity])
        old_perms = before["identities"][identity]["permissions"]
        new_perms = after["identities"][identity]["permissions"]

        print(f"{identity}:")
        print(f"  sidebar      {len(old_sidebar)} -> {len(new_sidebar)}")
        if old_sidebar != new_sidebar:
            failures.append(
                f"{identity} sidebar changed: "
                f"gained {sorted(new_sidebar - old_sidebar)}, lost {sorted(old_sidebar - new_sidebar)}"
            )
            print(f"  !! gained {sorted(new_sidebar - old_sidebar)}")
            print(f"  !! lost   {sorted(old_sidebar - new_sidebar)}")
        else:
            print(f"  sidebar      unchanged: {sorted(new_sidebar)}")

        permitted_before = {p for p, level in old_perms.items() if level > 0}
        permitted_after = {p for p, level in new_perms.items() if level > 0}
        print(f"  permitted    {sorted(permitted_before)}")
        print(f"            -> {sorted(permitted_after)}")
        gained = permitted_after - permitted_before
        lost = permitted_before - permitted_after
        if gained:
            print(f"  gained       {sorted(gained)}")
        if lost:
            print(f"  lost         {sorted(lost)}")
        print()

    nonadmin_after = after["identities"]["nonadmin"]
    if not nonadmin_after["permissions"]:
        failures.append("the non-admin permissions map is empty — get_registered_panels was empty")

    if "ha_permission_manager" not in after["sidebars"]["admin"]:
        failures.append("the Permission Manager panel is missing from the administrator's sidebar")

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS — no sidebar gained or lost a row")
    return 0


def main() -> int:
    _load_dotenv()
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
