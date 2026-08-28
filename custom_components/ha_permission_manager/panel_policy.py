"""Pure panel decisions, shared by discovery and the WebSocket API.

This module deliberately imports nothing from Home Assistant. Every decision
about which panels the Permission Manager offers, reports, or honours lives
here, so there is exactly one answer to each question and it can be unit
tested offline. Reading panels off `hass` stays in discovery.py.

The frontend counterpart is frontend/permission_policy.js.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .const import PERM_CLOSED, PREFIX_PANEL


def _panel_attr(panel: Any, name: str) -> Any:
    """Read one attribute off a panel, which may be a dict or an object."""
    if isinstance(panel, dict):
        return panel.get(name)
    return getattr(panel, name, None)


def is_unroutable_panel(panel: Any) -> bool:
    """Whether Home Assistant registers this panel but never routes to it.

    Home Assistant keeps a stub `lovelace` panel on instances that have no
    legacy overview dashboard. Its own ha-panel-lovelace does:

        const confMode = this.panel.config?.mode;
        if (!confMode) navigate("/home", {replace: true});

    so opening that panel sends the browser straight to the real default
    dashboard. A Permission level on it can never be honoured. The test is
    deliberately word-for-word Home Assistant's own, so the two cannot drift.
    """
    if _panel_attr(panel, "component_name") != "lovelace":
        return False
    config = _panel_attr(panel, "config")
    if not isinstance(config, dict):
        return True
    return not config.get("mode")


def unroutable_panel_ids(panels: Mapping[str, Any]) -> set[str]:
    """Panel ids that Home Assistant registers but never routes to."""
    return {
        panel_id
        for panel_id, panel in panels.items()
        if is_unroutable_panel(panel)
    }


# Panels Home Assistant ships for administrators only. A Permission level on
# one of them would be meaningless, so the matrix has never offered them.
ADMIN_ONLY_PANELS = frozenset({"developer-tools", "config", "profile"})

# Panels a non-administrator keeps whatever the Permission store says: their
# own account page, which is no Resource and which the Permission Manager
# panel has never offered a level on.
#
# This and ROUTER_FALLBACK_PANELS below are the Python counterparts of
# ALWAYS_VISIBLE_PANELS and ROUTER_FALLBACK_PANELS in
# frontend/permission_policy.js, and they have to hold the same panel ids: two
# layers that disagree about which panels need no Permission would deny in one
# place what they allow in the other. Nothing makes them agree at runtime — one
# is Python and one is JavaScript — so tests/permission_policy.test.mjs reads
# both files and fails if the lists ever part company.
ALWAYS_VISIBLE_PANELS = frozenset({"profile"})

# Panels kept for routing only. Home Assistant resolves its default panel as
# `panels[default] ?? panels.home ?? panels.notfound` and throws reading
# `.url_path` off the result when all three are gone — which is what filtering
# did to it. `notfound` is in Home Assistant's own FIXED_PANELS, so it never
# appears in a sidebar and keeping it costs nothing visible.
ROUTER_FALLBACK_PANELS = frozenset({"notfound"})

# The two above, together: the panels that need no Permission level. Named
# because it is also the whole of what a non-administrator receives when the
# Panel Gate is running and cannot answer — the degraded set is exactly "every
# panel that needs no Permission, and nothing that does", rather than a second
# list that could come to disagree with this one.
PANELS_WITHOUT_PERMISSION = ALWAYS_VISIBLE_PANELS | ROUTER_FALLBACK_PANELS


def admin_panel_resources(panels: Mapping[str, Any]) -> list[dict[str, str]]:
    """The panel Resources the permission matrix offers an administrator.

    The single source of the matrix's panel list. It excludes the panels
    Home Assistant keeps for administrators, and the panels it registers but
    never routes to — offering one of those would give the administrator a
    toggle that saves a level get_panel_permissions then drops.
    """
    unroutable = unroutable_panel_ids(panels)

    resources: list[dict[str, str]] = []
    for panel_id, panel in panels.items():
        if panel_id in ADMIN_ONLY_PANELS or panel_id in unroutable:
            continue

        title = _panel_attr(panel, "title")
        if not title:
            config = _panel_attr(panel, "config")
            if isinstance(config, dict):
                title = config.get("title")
        resources.append({
            "id": panel_id,
            "name": str(title or panel_id),
            "type": "panel",
        })
    return resources


def visible_panel_ids(
    panel_ids: Iterable[str],
    panels: Mapping[str, Any],
    user_permissions: Mapping[str, int] | None,
    is_admin: bool,
) -> set[str]:
    """The panel ids this user may receive. The whole decision, as a set.

    The one answer to "which panels may this user see", so that the Panel Gate
    deciding and get_panel_permissions reporting cannot drift apart. They did
    on the Gate's first spike run: a non-admin came back with the stub
    `lovelace` panel, because the Gate's own rule honoured a store row that
    get_panel_permissions has always dropped.

    The answer is a subset of `panel_ids`, never more: the caller says which
    panels are on the table — for the Gate, the panels Home Assistant itself
    computed for this user — and nothing here adds one back.

    :param panel_ids: the panel ids on offer to this user.
    :param panels: the registered panels, read for the unroutable verdict.
    :param user_permissions: this user's Permission store rows, keyed by
        Resource id (`panel_*`), as _get_user_permissions returns them.
    :param is_admin: an administrator is never filtered.
    """
    offered = set(panel_ids)
    if is_admin:
        return offered

    unroutable = unroutable_panel_ids(panels or {})
    permissions = user_permissions or {}

    visible: set[str] = set()
    for panel_id in offered:
        # A level on a panel Home Assistant never routes to can never be
        # honoured, so it is refused ahead of everything the store says. The
        # row itself is left alone: it comes back to life if the panel does.
        if panel_id in unroutable:
            continue
        if panel_id in PANELS_WITHOUT_PERMISSION:
            visible.add(panel_id)
            continue
        # Fail-secure: only an explicit level above Closed grants. Absent,
        # like Closed, is a refusal.
        if permissions.get(f"{PREFIX_PANEL}{panel_id}", PERM_CLOSED) > PERM_CLOSED:
            visible.add(panel_id)
    return visible
