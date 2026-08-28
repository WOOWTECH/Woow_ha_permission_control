"""One authenticated Home Assistant WebSocket, and the credentials to open it.

Shared by the `verify_issue_*.py` scripts. It exists because the second copy
arrived: `verify_issue_16.py` and `verify_issue_19.py` both need the same
dotenv walk, the same two tokens, the same ws:// URL and the same
request/response loop, and two copies of a login is two places for an expired
token to be diagnosed differently.

Not imported by anything in `custom_components/`. This is test-side only, and
it deliberately holds no opinion about what a run measures.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import websockets

REPO = Path(__file__).resolve().parent.parent


def find_upwards(name: str) -> Path | None:
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


def load_dotenv() -> None:
    """Read KEY=VALUE from a repo-root .env, without overriding the real env."""
    env_file = find_upwards(".env")
    if env_file is None:
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def admin_token() -> str:
    for name in ("HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN", "HA_TOKEN"):
        token = os.environ.get(name)
        if token:
            return token
    sys.exit("No admin token. Set HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN in .env")


def nonadmin_token() -> str:
    token = os.environ.get("HA_TOKEN_NONADMIN")
    if token:
        return token
    token_file = find_upwards(".ha_nonadmin_token")
    if token_file is None:
        sys.exit("No non-admin token. Set HA_TOKEN_NONADMIN or add .ha_nonadmin_token")
    return token_file.read_text(encoding="utf-8").strip()


def http_url() -> str:
    return os.environ.get("HA_URL", "http://192.168.2.6:8123").rstrip("/")


def ws_url() -> str:
    return (
        http_url().replace("http://", "ws://").replace("https://", "wss://")
        + "/api/websocket"
    )


class Session:
    """One authenticated WebSocket, kept open so a live page can be imitated."""

    def __init__(self, socket, name: str):
        self.socket = socket
        self.name = name
        self._id = 0

    @classmethod
    async def open(cls, stack, token: str, name: str) -> "Session":
        socket = await stack.enter_async_context(
            websockets.connect(ws_url(), max_size=8 * 1024 * 1024)
        )
        hello = json.loads(await socket.recv())
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected greeting: {hello}")
        await socket.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(await socket.recv())
        if auth.get("type") != "auth_ok":
            # An expired non-admin token looks exactly like a Panel Gate that
            # denied everything, or like an event that never arrived, depending
            # on what is being measured. Say which it is before anything else
            # is read.
            raise RuntimeError(f"{name}: authentication refused — expired token? {auth}")
        return cls(socket, name)

    async def call(self, command: dict, keep_events: list | None = None) -> dict:
        """Send one command and return its result.

        Events that arrive before the result are dropped, or appended to
        `keep_events` if a caller is counting them.
        """
        self._id += 1
        message_id = self._id
        await self.socket.send(json.dumps({"id": message_id, **command}))
        while True:
            message = json.loads(await self.socket.recv())
            if message.get("type") == "event":
                if keep_events is not None:
                    keep_events.append(message)
                continue
            if message.get("id") != message_id or message.get("type") != "result":
                continue
            if not message.get("success"):
                raise RuntimeError(
                    f"{self.name}: {command['type']} failed: {message.get('error')}"
                )
            return message["result"]

    async def subscribe(self, event_type: str) -> None:
        await self.call({"type": "subscribe_events", "event_type": event_type})

    async def panels(self) -> list[str]:
        return sorted(await self.call({"type": "get_panels"}))

    async def deployed_version(self) -> str | None:
        """Which build answered, read off our own panel's module URL."""
        panels = await self.call({"type": "get_panels"})
        config = (panels.get("ha_permission_manager") or {}).get("config") or {}
        module_url = config.get("module_url") or (
            config.get("_panel_custom") or {}
        ).get("module_url", "")
        return module_url.split("?v=", 1)[1] if "?v=" in module_url else None


async def nonadmin_user_id(admin: Session) -> str:
    """The non-admin's own user id, which only an administrator can list.

    `get_admin_data` returns every non-owner user; the one a run acts on is the
    single non-administrator among them. More than one is ambiguous, and the
    run says so rather than guessing whose sidebar it is about to change.
    """
    data = await admin.call({"type": "permission_manager/get_admin_data"})
    candidates = [user for user in data.get("users", []) if not user["is_admin"]]
    if len(candidates) != 1:
        sys.exit(
            f"Expected exactly one non-administrator on the target, found "
            f"{len(candidates)}. Set the account this run should act on by hand."
        )
    return candidates[0]["id"]


async def stored_level(admin: Session, user_id: str, resource_id: str) -> int:
    """The level the store currently holds, so a run can put it back."""
    data = await admin.call({"type": "permission_manager/get_admin_data"})
    return data.get("permissions", {}).get(user_id, {}).get(resource_id, 0)


async def set_level(admin: Session, user_id: str, resource_id: str, level: int) -> None:
    await admin.call({
        "type": "permission_manager/set_permission",
        "user_id": user_id,
        "resource_id": resource_id,
        "level": level,
    })
