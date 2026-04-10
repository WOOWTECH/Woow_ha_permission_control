"""Constants for ha_permission_manager."""

DOMAIN = "ha_permission_manager"

# Storage versioning (for hass.helpers.storage.Store)
STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN

PERMISSION_OPTIONS = ["0", "1"]
PERMISSION_LABELS = {
    "0": "Closed",
    "1": "View",
}

# Permission levels (numeric values for comparison)
# Simplified from 4 levels to 2 levels (v1.0.0)
PERM_CLOSED = 0
PERM_VIEW = 1

# Resource type prefixes
PREFIX_AREA = "area_"
PREFIX_LABEL = "label_"
PREFIX_PANEL = "panel_"

# Self-reference resource ID (for bootstrap protection)
SELF_PANEL_ID = f"{PREFIX_PANEL}ha_permission_manager"

# Admin group ID (HA built-in)
ADMIN_GROUP_ID = "system-admin"

# Panel configuration (Permission Manager)
PANEL_TITLE = "Permission Manager"
PANEL_TITLE_ZH = "權限管理器"
PANEL_ICON = "mdi:shield-lock"
PANEL_URL = "ha_permission_manager"
PANEL_VERSION = "1.0.2"

# Control Panel configuration (unified area/label control)
CONTROL_PANEL_URL = "ha-control-panel"
CONTROL_PANEL_TITLE = "Control Panel"
CONTROL_PANEL_TITLE_ZH = "控制面板"
CONTROL_PANEL_ICON = "mdi:view-dashboard"

# Tab Configuration for Control Panel
CONTROL_PANEL_TABS = ["areas", "labels"]
DEFAULT_TAB = "areas"

# Legacy panel references (for migration/compatibility)
AREA_PANEL_URL = "area-control"
AREA_PANEL_TITLE = "Area Control"
AREA_PANEL_ICON = "mdi:floor-plan"

LABEL_PANEL_URL = "label-control"
LABEL_PANEL_TITLE = "Label Control"
LABEL_PANEL_ICON = "mdi:label"

# WebSocket Commands
WS_GET_PERMITTED_AREAS = "ha_permission_manager/get_permitted_areas"
WS_GET_PERMITTED_LABELS = "ha_permission_manager/get_permitted_labels"
WS_GET_ENTITIES_FOR_AREA = "ha_permission_manager/get_entities_for_area"
WS_GET_ENTITIES_FOR_LABEL = "ha_permission_manager/get_entities_for_label"

# Domain Configuration (for entity grouping in control panel)
DOMAIN_ICONS = {
    "light": "mdi:lightbulb",
    "switch": "mdi:toggle-switch",
    "sensor": "mdi:eye",
    "binary_sensor": "mdi:checkbox-marked-circle",
    "climate": "mdi:thermostat",
    "cover": "mdi:window-shutter",
    "fan": "mdi:fan",
    "lock": "mdi:lock",
    "media_player": "mdi:play-circle",
    "camera": "mdi:camera",
    "vacuum": "mdi:robot-vacuum",
    "automation": "mdi:robot",
    "script": "mdi:script-text",
}

DOMAIN_COLORS = {
    "light": "#FFD700",       # Gold
    "switch": "#4CAF50",      # Green
    "sensor": "#2196F3",      # Blue
    "binary_sensor": "#9C27B0",  # Purple
    "climate": "#FF5722",     # Deep Orange
    "cover": "#795548",       # Brown
    "fan": "#00BCD4",         # Cyan
    "lock": "#F44336",        # Red
    "media_player": "#E91E63",  # Pink
}
