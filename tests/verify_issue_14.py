#!/usr/bin/env python3
"""Live verification for issue #14: does every write path announce?

The issue's evidence is a table read off a live instance — listen for
`permission_manager_updated` from an administrator's connection, call each write
service over the REST API, and count what arrives. Three services delivered one
event each and two delivered none, and the two were the revocations.

This is the same instrument, pointed at the same instance, and it runs against
whatever version is deployed. Run it once before deploying and once after, and
the two records are the measurement:

  python3 tests/verify_issue_14.py --label v2.0.8
  # deploy, restart, wait for RUNNING
  python3 tests/verify_issue_14.py --label v2.0.9

Six cases, in this order, so that the destructive one is last:

  1. set_permission                on a scratch user and a scratch Resource
  2. bulk_set_permissions          two entries for the same scratch user
  3. remove_resource_permissions   the scratch Resource
  4. remove_user_permissions       the scratch user
  5. remove_user_permissions       again, on a user who now holds nothing
  6. reset_all_permissions         confirm=true

Case 5 is the one ADR-0010 argues about: a write that changed nothing still
announces. On a version that guards the save on "did it change" it is expected
to deliver nothing, and that is not a defect on that version — it is the
behaviour the ADR replaces. Read it next to case 4.

**This script writes to the Permission store, and case 6 erases it.** It reads
the whole store before it starts, prints it, and restores it through
`bulk_set_permissions` at the end. The restore is verified by reading the store
back and comparing. Nothing here is safe to point at an instance you cannot
lose — see the backup procedure in the ADR trail and take one first.

Configuration (a repo-root .env is read automatically):

  HA_URL    target instance   (default http://192.168.2.6:8123)
  HA_TOKEN, or HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN — an admin token

A JSON record lands in tests/screenshots/issue-14/<label>.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import websocket  # websocket-client

REPO = Path(__file__).resolve().parent.parent
RECORDS = REPO / "tests" / "screenshots" / "issue-14"

EVENT = "permission_manager_updated"

# A user id and a Resource id that exist only for this run. Both satisfy the
# services' id patterns, and neither collides with anything on the instance, so
# every case before the reset leaves the real Permission store alone.
SCRATCH_USER = "verify14user"
SCRATCH_RESOURCE = "area_verify14"
SCRATCH_RESOURCE_2 = "label_verify14"

# How long to wait for an announcement after a service call answers. The event
# bus is local and the fire is synchronous with the handler, so this is slack,
# not a real latency.
LISTEN_SECONDS = 2.0


def load_dotenv() -> None:
    env_file = REPO / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Listener:
    """An administrator's WebSocket connection, subscribed to the event.

    Home Assistant accepts this subscription for an administrator and refuses it
    for anyone else (#13), which is why the measurement is made from here.
    """

    def __init__(self, url: str, token: str) -> None:
        ws_url = url.replace("http://", "ws://").replace("https://", "wss://")
        self.ws = websocket.create_connection(ws_url + "/api/websocket", timeout=10)
        self.events: list[dict] = []
        self.results: dict[int, dict] = {}
        self._id = 0
        self._lock = threading.Lock()

        assert json.loads(self.ws.recv())["type"] == "auth_required"
        self.ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(self.ws.recv())
        if auth.get("type") != "auth_ok":
            raise SystemExit(f"WebSocket auth failed: {auth}")

        self._id += 1
        self.ws.send(json.dumps(
            {"id": self._id, "type": "subscribe_events", "event_type": EVENT}
        ))
        reply = json.loads(self.ws.recv())
        if not reply.get("success"):
            raise SystemExit(f"subscribe_events refused: {reply}")

        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        while True:
            try:
                message = json.loads(self.ws.recv())
            except Exception:
                return
            with self._lock:
                if message.get("type") == "event":
                    self.events.append(message["event"])
                elif message.get("type") == "result":
                    self.results[message["id"]] = message

    def take(self) -> list[dict]:
        """Every event since the last take, and reset the count."""
        with self._lock:
            taken, self.events = self.events, []
        return taken

    def command(self, payload: dict, timeout: float = 10.0) -> dict:
        """Send one WebSocket command and wait for its result."""
        with self._lock:
            self._id += 1
            message_id = self._id
        self.ws.send(json.dumps({"id": message_id, **payload}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if message_id in self.results:
                    return self.results.pop(message_id)
            time.sleep(0.05)
        raise SystemExit(f"No result for {payload.get('type')}")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def call_service(url: str, token: str, service: str, data: dict) -> int:
    """Call one service over the REST API. Returns the HTTP status."""
    request = urllib.request.Request(
        f"{url}/api/services/ha_permission_manager/{service}",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        print(f"    ! {service} -> HTTP {error.code}: {error.read()[:300]!r}")
        return error.code


def read_store(url: str, token: str) -> dict:
    """The whole Permission store, through get_permissions with no filter.

    Not `get_all_permissions` — that one is per-user and needs a user id that
    Home Assistant's auth knows, which the scratch user is not.
    """
    request = urllib.request.Request(
        f"{url}/api/services/ha_permission_manager/get_permissions"
        "?return_response",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read())
    return body.get("service_response", {}).get("permissions", {})


def run_case(
    listener: Listener,
    url: str,
    token: str,
    name: str,
    service: str,
    data: dict,
) -> dict:
    """One service call, and everything that arrived because of it."""
    listener.take()
    status = call_service(url, token, service, data)
    time.sleep(LISTEN_SECONDS)
    events = listener.take()

    record = {
        "case": name,
        "service": service,
        "data": data,
        "http": status,
        "events": len(events),
        "payloads": [event.get("data") for event in events],
    }
    mark = "ok " if events else "NONE"
    print(f"  [{mark}] {name:<34} HTTP {status}  events={len(events)}")
    for payload in record["payloads"]:
        print(f"         {json.dumps(payload, sort_keys=True)}")
    return record


def run_registry_case(listener: Listener, url: str, token: str) -> dict:
    """Delete an area that carries a Permission level, and watch for the event.

    The one write path with no service handler in front of it: Home Assistant's
    own `area_registry_updated` reaches `async_delete_resource_permissions`
    through a listener in `__init__.py`. It is the same helper the service
    calls, so it was silent for the same reason — and it is the path that
    matters most, because an area's removal is not something an administrator
    is watching a page for.

    The area is created here and deleted here. Nothing on the instance that
    existed before this run is touched.
    """
    created = listener.command({
        "type": "config/area_registry/create",
        "name": "verify14 scratch area",
    })
    area_id = created["result"]["area_id"]
    resource_id = f"area_{area_id}"
    print(f"  created area {area_id}")

    call_service(url, token, "set_permission", {
        "user_id": SCRATCH_USER,
        "resource_id": resource_id,
        "level": 1,
    })
    time.sleep(1.0)
    listener.take()

    deleted = listener.command({
        "type": "config/area_registry/delete",
        "area_id": area_id,
    })
    time.sleep(LISTEN_SECONDS)
    events = listener.take()

    record = {
        "case": "area deletion (registry listener)",
        "service": "config/area_registry/delete",
        "data": {"area_id": area_id, "resource_id": resource_id},
        "http": 200 if deleted.get("success") else 0,
        "events": len(events),
        "payloads": [event.get("data") for event in events],
    }
    mark = "ok " if events else "NONE"
    print(f"  [{mark}] {record['case']:<34} ws ok={deleted.get('success')}  events={len(events)}")
    for payload in record["payloads"]:
        print(f"         {json.dumps(payload, sort_keys=True)}")

    call_service(url, token, "remove_user_permissions", {"user_id": SCRATCH_USER})
    time.sleep(1.0)
    listener.take()
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="version under test, e.g. v2.0.9")
    parser.add_argument("--url", default=None)
    args = parser.parse_args()

    load_dotenv()
    url = (args.url or os.environ.get("HA_URL", "http://192.168.2.6:8123")).rstrip("/")
    token = (
        os.environ.get("HA_TOKEN")
        or os.environ.get("HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN")
    )
    if not token:
        raise SystemExit("No admin token. Set HA_TOKEN or put it in .env.")

    print(f"target   {url}")
    print(f"label    {args.label}")

    before = read_store(url, token)
    entries = sum(len(levels) for levels in before.values())
    print(f"store    {len(before)} users, {entries} entries — restored at the end")

    listener = Listener(url, token)
    print(f"listener subscribed to {EVENT} as administrator\n")

    cases = [
        ("set_permission", "set_permission", {
            "user_id": SCRATCH_USER,
            "resource_id": SCRATCH_RESOURCE,
            "level": 1,
        }),
        ("bulk_set_permissions", "bulk_set_permissions", {
            "permissions": [
                {"user_id": SCRATCH_USER, "resource_id": SCRATCH_RESOURCE, "level": 0},
                {"user_id": SCRATCH_USER, "resource_id": SCRATCH_RESOURCE_2, "level": 1},
            ],
        }),
        ("remove_resource_permissions", "remove_resource_permissions", {
            "resource_id": SCRATCH_RESOURCE,
        }),
        ("remove_user_permissions", "remove_user_permissions", {
            "user_id": SCRATCH_USER,
        }),
        ("remove_user_permissions (no-op)", "remove_user_permissions", {
            "user_id": SCRATCH_USER,
        }),
        ("reset_all_permissions", "reset_all_permissions", {"confirm": True}),
    ]

    results = [run_case(listener, url, token, *case) for case in cases]
    results.append(run_registry_case(listener, url, token))
    listener.close()

    print("\nrestoring the Permission store")
    restore = [
        {"user_id": user_id, "resource_id": resource_id, "level": level}
        for user_id, levels in before.items()
        for resource_id, level in levels.items()
    ]
    if restore:
        status = call_service(url, token, "bulk_set_permissions", {"permissions": restore})
        print(f"  bulk_set_permissions of {len(restore)} entries -> HTTP {status}")
    time.sleep(2.0)
    after = read_store(url, token)
    restored = after == before
    print(f"  store restored: {restored}")
    if not restored:
        print(f"  ! before={json.dumps(before, sort_keys=True)}")
        print(f"  ! after ={json.dumps(after, sort_keys=True)}")

    silent = [record["case"] for record in results if record["events"] == 0]
    print("\nsummary")
    for record in results:
        print(f"  {record['case']:<34} HTTP {record['http']}  events={record['events']}")
    print(f"  silent write paths: {silent or 'none'}")

    RECORDS.mkdir(parents=True, exist_ok=True)
    record_file = RECORDS / f"{args.label}.json"
    record_file.write_text(json.dumps({
        "label": args.label,
        "url": url,
        "event": EVENT,
        "cases": results,
        "silent": silent,
        "store_before": before,
        "store_restored": restored,
    }, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nrecord   {record_file.relative_to(REPO).as_posix()}")

    return 0 if restored else 1


if __name__ == "__main__":
    sys.exit(main())
