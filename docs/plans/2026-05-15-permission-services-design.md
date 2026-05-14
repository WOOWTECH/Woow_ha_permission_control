# HA Permission Manager — Services Design

## Overview

Add 8 HA Services to `ha_permission_manager` so that **all** permission management features are accessible via `call_service` / REST API / WebSocket, enabling automation, external systems, and AI agents to manage permissions programmatically.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Granularity | Fine-grained (one operation per service) | Matches HA native style; clearer intent for AI agents |
| Query returns | `SupportsResponse` (HA 2023.7+) | REST API returns JSON directly; single API covers all |
| Batch support | Single + Bulk both provided | Simple cases stay simple; bulk for AI/script scenarios |
| Resource discovery | `get_users` + `get_resources` (with type filter) | Clean separation; fewer services than full split |
| Reset/cleanup | user + resource + reset_all | Covers lifecycle needs; reset_all has safety confirm |
| Documentation | `services.yaml` descriptions + `docs/services-guide.md` | HA UI visible + detailed guide with AI agent examples |

## Service Inventory (8 Services)

### Write Services (5)

#### 1. `set_permission`
- **Purpose**: Set permission level for one user on one resource
- **Auth**: Admin only
- **Parameters**:
  - `user_id` (required, string) — HA user ID
  - `resource_id` (required, string) — Resource ID with prefix (`panel_`/`area_`/`label_`)
  - `level` (required, int) — 0=Closed, 1=View
- **Events**: Fires `permission_manager_updated`
- **Response**: None

#### 2. `bulk_set_permissions`
- **Purpose**: Set multiple permission entries in one call
- **Auth**: Admin only
- **Parameters**:
  - `permissions` (required, list) — Array of objects, each with:
    - `user_id` (required, string)
    - `resource_id` (required, string)
    - `level` (required, int)
- **Events**: Fires `permission_manager_updated` once after all applied
- **Response**: None

#### 3. `remove_user_permissions`
- **Purpose**: Delete all permissions for a specific user
- **Auth**: Admin only
- **Parameters**:
  - `user_id` (required, string)
- **Events**: Fires `permission_manager_updated`
- **Response**: None

#### 4. `remove_resource_permissions`
- **Purpose**: Delete all permissions for a specific resource (across all users)
- **Auth**: Admin only
- **Parameters**:
  - `resource_id` (required, string)
- **Events**: Fires `permission_manager_updated`
- **Response**: None

#### 5. `reset_all_permissions`
- **Purpose**: Clear the entire permission table (dangerous)
- **Auth**: Admin only
- **Parameters**:
  - `confirm` (required, boolean) — Must be `true` to proceed
- **Events**: Fires `permission_manager_updated`
- **Response**: None

### Query Services (3, with SupportsResponse)

#### 6. `get_permissions`
- **Purpose**: Query permissions with optional filters
- **Auth**: Admin only
- **Parameters** (all optional):
  - `user_id` (string) — Filter by user
  - `resource_type` (string) — Filter by type: `panel`/`area`/`label`
  - `resource_id` (string) — Filter by specific resource
- **Response**:
```json
{
  "permissions": {
    "user_id_1": {
      "area_living_room": 1,
      "panel_lovelace": 0
    }
  }
}
```

#### 7. `get_users`
- **Purpose**: Return all manageable (non-system, non-owner) users
- **Auth**: Admin only
- **Parameters**: None
- **Response**:
```json
{
  "users": [
    {"id": "abc123", "name": "John", "is_admin": false},
    {"id": "def456", "name": "Jane", "is_admin": true}
  ]
}
```

#### 8. `get_resources`
- **Purpose**: Return all manageable resources
- **Auth**: Admin only
- **Parameters** (all optional):
  - `type` (string) — Filter: `panel`/`area`/`label`
- **Response**:
```json
{
  "resources": [
    {"id": "area_living_room", "name": "Living Room", "type": "area"},
    {"id": "panel_lovelace", "name": "Dashboard", "type": "panel"}
  ]
}
```

## Technical Architecture

### File Changes

```
ha_permission_manager/
  __init__.py          # MODIFY: register services in async_setup_entry, unregister in async_unload_entry
  services.py          # NEW: all 8 service handler functions
  services.yaml        # NEW: service definitions with descriptions, parameters, selectors
  const.py             # MODIFY: add service name constants
  websocket_api.py     # NO CHANGE: existing WebSocket API preserved
  discovery.py         # NO CHANGE: reuse existing discover_* functions
  users.py             # NO CHANGE: reuse existing discover_users function
```

### Implementation Details

1. **Service Registration**: In `async_setup_entry()`, call `async_register_services(hass)` from new `services.py`
2. **Service Unregistration**: In `async_unload_entry()`, call `hass.services.async_remove()` for each service
3. **Admin Check**: All handlers verify caller is admin via `call.context.user_id` + `auth.async_get_user()`
4. **Input Validation**: Voluptuous schemas matching existing regex patterns (`^[a-zA-Z0-9_-]+$`)
5. **Data Access**: Reuse existing `async_get_permission()`, `async_set_permission()`, etc. from `__init__.py`
6. **Resource Discovery**: Reuse `discover_users()`, `discover_panels()`, `discover_areas()`, `discover_labels()` from `discovery.py` and `users.py`
7. **Event Firing**: Write operations fire `permission_manager_updated` event (consistent with WebSocket API)
8. **Batched Saves**: `bulk_set_permissions` calls `async_save_permissions()` once after all entries applied
9. **SupportsResponse**: Query services registered with `supports_response=SupportsResponse.ONLY`

### Security

- All 8 services require admin authentication
- `reset_all_permissions` requires explicit `confirm: true` parameter
- Input validation with regex + length limits
- Non-admin callers receive `Unauthorized` error
- Resource ID prefix validation (`panel_`/`area_`/`label_`)

## Documentation Deliverables

1. **`services.yaml`**: Bilingual (EN/ZH) name, description, field descriptions, examples, selectors
2. **`docs/services-guide.md`**: Complete guide including:
   - Quick reference table
   - Authentication requirements
   - Each service: description + all 3 example formats (curl, YAML automation, Python)
   - AI agent structured reference with JSON schemas
   - Common workflow recipes (onboard user, offboard user, audit permissions, bulk configure)
   - Error code reference table
