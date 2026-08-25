"""Resource discovery for ha_permission_manager."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import label_registry as lr

from .const import (
    PREFIX_AREA,
    PREFIX_LABEL,
    PREFIX_PANEL,
    SELF_PANEL_ID,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass
class Resource:
    """Represents a protectable resource."""
    id: str
    name: str
    type: str  # "area" | "label" | "panel"


def discover_areas(hass: HomeAssistant) -> list[Resource]:
    """Discover all areas."""
    registry = ar.async_get(hass)
    resources = []
    for area in registry.async_list_areas():
        resources.append(
            Resource(
                id=f"{PREFIX_AREA}{area.id}",
                name=area.name,
                type="area",
            )
        )
    _LOGGER.debug("Discovered %d areas", len(resources))
    return resources


def discover_labels(hass: HomeAssistant) -> list[Resource]:
    """Discover all labels."""
    registry = lr.async_get(hass)
    resources = []
    for label in registry.async_list_labels():
        resources.append(
            Resource(
                id=f"{PREFIX_LABEL}{label.label_id}",
                name=label.name,
                type="label",
            )
        )
    _LOGGER.debug("Discovered %d labels", len(resources))
    return resources


def get_registered_panels(hass: HomeAssistant) -> dict:
    """Return the panels Home Assistant has registered, whatever it keeps them in."""
    # Method 1: frontend_panels (modern HA)
    if "frontend_panels" in hass.data:
        return hass.data["frontend_panels"]

    # Method 2: frontend -> panels
    if "frontend" in hass.data:
        frontend_data = hass.data["frontend"]
        if isinstance(frontend_data, dict):
            return frontend_data.get("panels", {})
        if hasattr(frontend_data, "panels"):
            return frontend_data.panels or {}

    return {}


def _panel_attr(panel: Any, name: str) -> Any:
    """Read one attribute off a panel, which may be a dict or an object."""
    if isinstance(panel, dict):
        return panel.get(name)
    return getattr(panel, name, None)


def _is_unroutable_panel(panel: Any) -> bool:
    """Whether Home Assistant registers this panel but never routes to it.

    Home Assistant keeps a stub `lovelace` panel on instances that have no
    legacy overview dashboard. Its own ha-panel-lovelace does:

        const confMode = this.panel.config?.mode;
        if (!confMode) navigate("/home", {replace: true});

    so opening that panel sends the browser straight to the real default
    dashboard. A Permission level on it can never be honoured, which is why it
    is not offered as a Resource and not reported to the Filters. The test is
    deliberately word-for-word Home Assistant's own, so the two cannot drift.
    """
    if _panel_attr(panel, "component_name") != "lovelace":
        return False
    config = _panel_attr(panel, "config")
    if not isinstance(config, dict):
        return True
    return not config.get("mode")


def unroutable_panel_ids(hass: HomeAssistant) -> set[str]:
    """Panel ids that Home Assistant registers but never routes to."""
    return {
        panel_id
        for panel_id, panel in get_registered_panels(hass).items()
        if _is_unroutable_panel(panel)
    }


def discover_panels(hass: HomeAssistant) -> list[Resource]:
    """Discover all sidebar panels."""
    resources = []

    panels = get_registered_panels(hass)
    unroutable = unroutable_panel_ids(hass)

    _LOGGER.debug("Found panels data: %s", list(panels.keys()) if panels else "None")
    if unroutable:
        _LOGGER.debug("Skipping panels Home Assistant does not route to: %s", unroutable)

    for panel_id, panel in panels.items():
        # Skip our own panel (we'll add it manually)
        if panel_id == "ha_permission_manager":
            continue

        # Never offer a Resource whose Permission level cannot be honoured
        if panel_id in unroutable:
            continue

        # Get panel title
        title = panel_id
        if isinstance(panel, dict):
            title = panel.get("title") or panel.get("sidebar_title") or panel_id
        elif hasattr(panel, "title"):
            title = panel.title or panel_id
        elif hasattr(panel, "sidebar_title"):
            title = panel.sidebar_title or panel_id

        resources.append(
            Resource(
                id=f"{PREFIX_PANEL}{panel_id}",
                name=str(title),
                type="panel",
            )
        )

    # Always add self-reference
    resources.append(
        Resource(
            id=SELF_PANEL_ID,
            name="Permission Manager",
            type="panel",
        )
    )

    _LOGGER.debug("Discovered %d panels (including self)", len(resources))
    return resources


def discover_all_resources(hass: HomeAssistant) -> dict[str, list[Resource]]:
    """Discover all protectable resources grouped by type."""
    return {
        "areas": discover_areas(hass),
        "labels": discover_labels(hass),
        "panels": discover_panels(hass),
    }
