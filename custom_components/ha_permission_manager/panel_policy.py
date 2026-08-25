"""Pure panel decisions, shared by discovery and the WebSocket API.

This module deliberately imports nothing from Home Assistant. Every decision
about which panels the Permission Manager offers, reports, or honours lives
here, so there is exactly one answer to each question and it can be unit
tested offline. Reading panels off `hass` stays in discovery.py.

The frontend counterpart is frontend/permission_policy.js.
"""
from __future__ import annotations

from typing import Any, Mapping


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
