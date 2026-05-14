"""Service handlers for ha_permission_manager.

Provides 8 HA Services for programmatic permission management:
  Write: set_permission, bulk_set_permissions, remove_user_permissions,
         remove_resource_permissions, reset_all_permissions
  Query: get_permissions, get_users, get_resources (SupportsResponse)
"""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    PERM_CLOSED,
    PERM_VIEW,
    PREFIX_AREA,
    PREFIX_LABEL,
    PREFIX_PANEL,
    RESOURCE_TYPES,
    RESOURCE_TYPE_PREFIX_MAP,
    SERVICE_SET_PERMISSION,
    SERVICE_BULK_SET_PERMISSIONS,
    SERVICE_REMOVE_USER_PERMISSIONS,
    SERVICE_REMOVE_RESOURCE_PERMISSIONS,
    SERVICE_RESET_ALL_PERMISSIONS,
    SERVICE_GET_PERMISSIONS,
    SERVICE_GET_USERS,
    SERVICE_GET_RESOURCES,
)
from .discovery import discover_all_resources
from .users import discover_users

_LOGGER = logging.getLogger(__name__)

# Regex for valid resource/user IDs
_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")
_RESOURCE_ID_PATTERN = re.compile(r"^(panel_|area_|label_)[a-zA-Z0-9_\-]+$")

# Max entries in a bulk operation
_BULK_MAX = 500

# =============================================================================
# Voluptuous Schemas
# =============================================================================

_VALID_ID = vol.All(str, vol.Length(min=1, max=255))

_SCHEMA_SET_PERMISSION = vol.Schema({
    vol.Required("user_id"): _VALID_ID,
    vol.Required("resource_id"): _VALID_ID,
    vol.Required("level"): vol.All(vol.Coerce(int), vol.In([PERM_CLOSED, PERM_VIEW])),
})

_SINGLE_PERMISSION_ENTRY = vol.Schema({
    vol.Required("user_id"): _VALID_ID,
    vol.Required("resource_id"): _VALID_ID,
    vol.Required("level"): vol.All(vol.Coerce(int), vol.In([PERM_CLOSED, PERM_VIEW])),
})

_SCHEMA_BULK_SET = vol.Schema({
    vol.Required("permissions"): vol.All(
        [_SINGLE_PERMISSION_ENTRY],
        vol.Length(min=1, max=_BULK_MAX),
    ),
})

_SCHEMA_REMOVE_USER = vol.Schema({
    vol.Required("user_id"): _VALID_ID,
})

_SCHEMA_REMOVE_RESOURCE = vol.Schema({
    vol.Required("resource_id"): _VALID_ID,
})

_SCHEMA_RESET_ALL = vol.Schema({
    vol.Required("confirm"): True,
})

_SCHEMA_GET_PERMISSIONS = vol.Schema({
    vol.Optional("user_id"): _VALID_ID,
    vol.Optional("resource_type"): vol.In(RESOURCE_TYPES),
    vol.Optional("resource_id"): _VALID_ID,
})

_SCHEMA_GET_USERS = vol.Schema({})

_SCHEMA_GET_RESOURCES = vol.Schema({
    vol.Optional("type"): vol.In(RESOURCE_TYPES),
})


# =============================================================================
# Helper Functions
# =============================================================================


async def _async_validate_admin(hass: HomeAssistant, call: ServiceCall) -> None:
    """Verify the caller is an admin user.

    Raises HomeAssistantError if the caller is not admin.
    Internal/system calls (no user context) are allowed.
    """
    user_id = call.context.user_id
    if user_id is None:
        # Internal/system call (e.g., from automation without user context)
        return
    user = await hass.auth.async_get_user(user_id)
    if user is None or not user.is_admin:
        raise HomeAssistantError(
            "Admin access required. Only administrators can manage permissions. "
            "需要管理员权限。只有管理员可以管理权限。"
        )


def _validate_resource_id(resource_id: str) -> None:
    """Validate resource_id has correct prefix and format."""
    if not _RESOURCE_ID_PATTERN.match(resource_id):
        raise HomeAssistantError(
            f"Invalid resource_id: '{resource_id}'. "
            f"Must start with 'panel_', 'area_', or 'label_' followed by alphanumeric/underscore/hyphen characters. "
            f"无效的 resource_id：'{resource_id}'。必须以 'panel_'、'area_' 或 'label_' 开头。"
        )


def _validate_user_id(user_id: str) -> None:
    """Validate user_id format."""
    if not _ID_PATTERN.match(user_id):
        raise HomeAssistantError(
            f"Invalid user_id: '{user_id}'. "
            f"Must contain only alphanumeric, underscore, or hyphen characters. "
            f"无效的 user_id：'{user_id}'。只能包含字母、数字、下划线或连字号。"
        )


def _get_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Get domain data, raising error if integration not loaded."""
    domain_data = hass.data.get(DOMAIN)
    if domain_data is None:
        raise HomeAssistantError(
            "Permission Manager is not loaded. "
            "权限管理器未加载。"
        )
    return domain_data


# =============================================================================
# Write Service Handlers
# =============================================================================


async def async_handle_set_permission(call: ServiceCall) -> None:
    """Handle set_permission service call.

    Sets the permission level for a specific user on a specific resource.
    """
    hass = call.hass
    await _async_validate_admin(hass, call)

    user_id = call.data["user_id"]
    resource_id = call.data["resource_id"]
    level = call.data["level"]

    _validate_user_id(user_id)
    _validate_resource_id(resource_id)

    # Import here to avoid circular imports
    from . import async_set_permission

    await async_set_permission(hass, user_id, resource_id, level)

    _LOGGER.info(
        "Service set_permission: user=%s, resource=%s, level=%d",
        user_id, resource_id, level,
    )


async def async_handle_bulk_set_permissions(call: ServiceCall) -> None:
    """Handle bulk_set_permissions service call.

    Sets multiple permission entries in one call.
    Fires permission_manager_updated event once after all entries are applied.
    """
    hass = call.hass
    await _async_validate_admin(hass, call)

    permissions_list = call.data["permissions"]

    # Validate all entries first before applying any
    for entry in permissions_list:
        _validate_user_id(entry["user_id"])
        _validate_resource_id(entry["resource_id"])

    # Apply all permissions
    from . import async_save_permissions

    domain_data = _get_domain_data(hass)
    permissions = domain_data.setdefault("permissions", {})

    for entry in permissions_list:
        uid = entry["user_id"]
        rid = entry["resource_id"]
        lvl = entry["level"]

        if uid not in permissions:
            permissions[uid] = {}
        permissions[uid][rid] = lvl

    # Save once (batched) and fire event once
    await async_save_permissions(hass)

    hass.bus.async_fire("permission_manager_updated", {
        "action": "bulk_set",
        "count": len(permissions_list),
    })

    _LOGGER.info(
        "Service bulk_set_permissions: applied %d entries",
        len(permissions_list),
    )


async def async_handle_remove_user_permissions(call: ServiceCall) -> None:
    """Handle remove_user_permissions service call.

    Deletes all permissions for a specific user.
    """
    hass = call.hass
    await _async_validate_admin(hass, call)

    user_id = call.data["user_id"]
    _validate_user_id(user_id)

    from . import async_delete_user_permissions

    await async_delete_user_permissions(hass, user_id)

    _LOGGER.info("Service remove_user_permissions: user=%s", user_id)


async def async_handle_remove_resource_permissions(call: ServiceCall) -> None:
    """Handle remove_resource_permissions service call.

    Deletes all permissions for a specific resource across all users.
    """
    hass = call.hass
    await _async_validate_admin(hass, call)

    resource_id = call.data["resource_id"]
    _validate_resource_id(resource_id)

    from . import async_delete_resource_permissions

    await async_delete_resource_permissions(hass, resource_id)

    _LOGGER.info("Service remove_resource_permissions: resource=%s", resource_id)


async def async_handle_reset_all_permissions(call: ServiceCall) -> None:
    """Handle reset_all_permissions service call.

    Clears the entire permission table. Requires confirm=true.
    """
    hass = call.hass
    await _async_validate_admin(hass, call)

    # confirm is already validated by schema to be True
    from . import async_save_permissions

    domain_data = _get_domain_data(hass)
    domain_data["permissions"] = {}

    await async_save_permissions(hass)

    hass.bus.async_fire("permission_manager_updated", {
        "action": "reset_all",
    })

    _LOGGER.warning("Service reset_all_permissions: all permissions cleared")


# =============================================================================
# Query Service Handlers (SupportsResponse)
# =============================================================================


async def async_handle_get_permissions(call: ServiceCall) -> ServiceResponse:
    """Handle get_permissions service call.

    Returns permissions filtered by optional user_id, resource_type, resource_id.
    """
    hass = call.hass
    await _async_validate_admin(hass, call)

    from . import async_get_all_permissions, async_get_user_permissions

    user_id = call.data.get("user_id")
    resource_type = call.data.get("resource_type")
    resource_id = call.data.get("resource_id")

    # Start with all or single-user permissions
    if user_id:
        _validate_user_id(user_id)
        raw_perms = {user_id: async_get_user_permissions(hass, user_id)}
    else:
        raw_perms = dict(async_get_all_permissions(hass))

    # Filter by resource_type if specified
    if resource_type:
        prefix = RESOURCE_TYPE_PREFIX_MAP[resource_type]
        filtered = {}
        for uid, user_perms in raw_perms.items():
            type_filtered = {
                rid: lvl for rid, lvl in user_perms.items()
                if rid.startswith(prefix)
            }
            if type_filtered:
                filtered[uid] = type_filtered
        raw_perms = filtered

    # Filter by specific resource_id if specified
    if resource_id:
        _validate_resource_id(resource_id)
        filtered = {}
        for uid, user_perms in raw_perms.items():
            if resource_id in user_perms:
                filtered[uid] = {resource_id: user_perms[resource_id]}
        raw_perms = filtered

    return {"permissions": raw_perms}


async def async_handle_get_users(call: ServiceCall) -> ServiceResponse:
    """Handle get_users service call.

    Returns all manageable (non-system) users.
    """
    hass = call.hass
    await _async_validate_admin(hass, call)

    users = await discover_users(hass)

    return {
        "users": [
            {
                "id": user.id,
                "name": user.name,
                "is_admin": user.is_admin,
            }
            for user in users
        ]
    }


async def async_handle_get_resources(call: ServiceCall) -> ServiceResponse:
    """Handle get_resources service call.

    Returns all manageable resources, optionally filtered by type.
    """
    hass = call.hass
    await _async_validate_admin(hass, call)

    resource_type = call.data.get("type")

    all_resources = discover_all_resources(hass)

    result = []

    if resource_type:
        # Return only the requested type
        type_key = resource_type + "s"  # "panel" -> "panels", "area" -> "areas"
        for resource in all_resources.get(type_key, []):
            result.append({
                "id": resource.id,
                "name": resource.name,
                "type": resource.type,
            })
    else:
        # Return all types
        for type_key in ("panels", "areas", "labels"):
            for resource in all_resources.get(type_key, []):
                result.append({
                    "id": resource.id,
                    "name": resource.name,
                    "type": resource.type,
                })

    return {"resources": result}


# =============================================================================
# Service Registration
# =============================================================================


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all permission manager services."""

    # Write services (no response)
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PERMISSION,
        async_handle_set_permission,
        schema=_SCHEMA_SET_PERMISSION,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_BULK_SET_PERMISSIONS,
        async_handle_bulk_set_permissions,
        schema=_SCHEMA_BULK_SET,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_USER_PERMISSIONS,
        async_handle_remove_user_permissions,
        schema=_SCHEMA_REMOVE_USER,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_RESOURCE_PERMISSIONS,
        async_handle_remove_resource_permissions,
        schema=_SCHEMA_REMOVE_RESOURCE,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_ALL_PERMISSIONS,
        async_handle_reset_all_permissions,
        schema=_SCHEMA_RESET_ALL,
    )

    # Query services (with SupportsResponse)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PERMISSIONS,
        async_handle_get_permissions,
        schema=_SCHEMA_GET_PERMISSIONS,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_USERS,
        async_handle_get_users,
        schema=_SCHEMA_GET_USERS,
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_RESOURCES,
        async_handle_get_resources,
        schema=_SCHEMA_GET_RESOURCES,
        supports_response=SupportsResponse.ONLY,
    )

    _LOGGER.info("Registered %d permission manager services", 8)


def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister all permission manager services."""
    for service_name in (
        SERVICE_SET_PERMISSION,
        SERVICE_BULK_SET_PERMISSIONS,
        SERVICE_REMOVE_USER_PERMISSIONS,
        SERVICE_REMOVE_RESOURCE_PERMISSIONS,
        SERVICE_RESET_ALL_PERMISSIONS,
        SERVICE_GET_PERMISSIONS,
        SERVICE_GET_USERS,
        SERVICE_GET_RESOURCES,
    ):
        hass.services.async_remove(DOMAIN, service_name)

    _LOGGER.info("Unregistered permission manager services")
