# HA Permission Manager — Services Guide / 服務指南

## Quick Reference / 速查表

| # | Service | Type | Description |
|---|---------|------|-------------|
| 1 | `ha_permission_manager.set_permission` | Write | Set single user-resource permission / 設定單筆權限 |
| 2 | `ha_permission_manager.bulk_set_permissions` | Write | Set multiple permissions at once / 批量設定權限 |
| 3 | `ha_permission_manager.remove_user_permissions` | Write | Delete all permissions for a user / 刪除用戶所有權限 |
| 4 | `ha_permission_manager.remove_resource_permissions` | Write | Delete all permissions for a resource / 刪除資源所有權限 |
| 5 | `ha_permission_manager.reset_all_permissions` | Write | Clear entire permission table / 重置所有權限 |
| 6 | `ha_permission_manager.get_permissions` | Query | Query permissions with filters / 查詢權限 |
| 7 | `ha_permission_manager.get_users` | Query | List all manageable users / 查詢用戶列表 |
| 8 | `ha_permission_manager.get_resources` | Query | List all manageable resources / 查詢資源列表 |

---

## Authentication / 認證

**All 8 services require admin authentication.** / 所有 8 個服務都需要管理員認證。

- **HA Automation / Script**: Runs as the automation owner (must be admin).
- **REST API**: Requires `Authorization: Bearer <long_lived_access_token>` header. The token owner must be an admin user.
- **Developer Tools UI**: Must be logged in as admin.

### Getting a Long-Lived Access Token / 取得長期 Token

1. Go to your HA profile page: `http://<HA_URL>/profile`
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token", give it a name
4. Copy the token (shown only once)

---

## Resource ID Format / 資源 ID 格式

All resource IDs use a prefix to indicate their type:

| Type | Prefix | Example |
|------|--------|---------|
| Panel / 面板 | `panel_` | `panel_lovelace`, `panel_config`, `panel_ha_permission_manager` |
| Area / 區域 | `area_` | `area_living_room`, `area_bedroom` |
| Label / 標籤 | `label_` | `label_outdoor`, `label_important` |

Use `get_resources` to discover all available resource IDs.

---

## Permission Levels / 權限等級

| Level | Name | Meaning |
|-------|------|---------|
| `0` | Closed / 關閉 | User cannot see this resource (hidden from sidebar, control panel, etc.) |
| `1` | View / 可見 | User can see and interact with this resource |

---

## Service Details / 服務詳情

---

### 1. `set_permission` — Set Single Permission / 設定單筆權限

Sets the permission level for one user on one resource.

#### Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `user_id` | Yes | string | HA user ID |
| `resource_id` | Yes | string | Resource ID with prefix (`panel_`/`area_`/`label_`) |
| `level` | Yes | int | `0` (Closed) or `1` (View) |

#### HA Automation YAML

```yaml
service: ha_permission_manager.set_permission
data:
  user_id: "a1b2c3d4e5f6"
  resource_id: "area_living_room"
  level: 1
```

#### REST API (curl)

```bash
curl -X POST http://localhost:8123/api/services/ha_permission_manager/set_permission \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "a1b2c3d4e5f6",
    "resource_id": "area_living_room",
    "level": 1
  }'
```

#### Python

```python
import requests

url = "http://localhost:8123/api/services/ha_permission_manager/set_permission"
headers = {
    "Authorization": "Bearer YOUR_TOKEN",
    "Content-Type": "application/json",
}
data = {
    "user_id": "a1b2c3d4e5f6",
    "resource_id": "area_living_room",
    "level": 1,
}
response = requests.post(url, headers=headers, json=data)
print(response.status_code)  # 200 on success
```

---

### 2. `bulk_set_permissions` — Bulk Set / 批量設定權限

Sets multiple permission entries in one call. Max 500 entries.

#### Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `permissions` | Yes | list | Array of `{user_id, resource_id, level}` objects |

#### HA Automation YAML

```yaml
service: ha_permission_manager.bulk_set_permissions
data:
  permissions:
    - user_id: "a1b2c3d4e5f6"
      resource_id: "area_living_room"
      level: 1
    - user_id: "a1b2c3d4e5f6"
      resource_id: "area_bedroom"
      level: 1
    - user_id: "a1b2c3d4e5f6"
      resource_id: "panel_lovelace"
      level: 1
    - user_id: "a1b2c3d4e5f6"
      resource_id: "label_outdoor"
      level: 0
```

#### REST API (curl)

```bash
curl -X POST http://localhost:8123/api/services/ha_permission_manager/bulk_set_permissions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "permissions": [
      {"user_id": "a1b2c3", "resource_id": "area_living_room", "level": 1},
      {"user_id": "a1b2c3", "resource_id": "area_bedroom", "level": 1},
      {"user_id": "a1b2c3", "resource_id": "panel_lovelace", "level": 1}
    ]
  }'
```

#### Python

```python
data = {
    "permissions": [
        {"user_id": "a1b2c3", "resource_id": "area_living_room", "level": 1},
        {"user_id": "a1b2c3", "resource_id": "area_bedroom", "level": 1},
        {"user_id": "a1b2c3", "resource_id": "panel_lovelace", "level": 1},
    ]
}
response = requests.post(url_prefix + "bulk_set_permissions", headers=headers, json=data)
```

---

### 3. `remove_user_permissions` — Remove User / 刪除用戶權限

Deletes all permissions for a specific user.

#### Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `user_id` | Yes | string | HA user ID |

#### HA Automation YAML

```yaml
service: ha_permission_manager.remove_user_permissions
data:
  user_id: "a1b2c3d4e5f6"
```

#### REST API (curl)

```bash
curl -X POST http://localhost:8123/api/services/ha_permission_manager/remove_user_permissions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "a1b2c3d4e5f6"}'
```

---

### 4. `remove_resource_permissions` — Remove Resource / 刪除資源權限

Deletes all permissions for a specific resource across all users.

#### Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `resource_id` | Yes | string | Resource ID with prefix |

#### HA Automation YAML

```yaml
service: ha_permission_manager.remove_resource_permissions
data:
  resource_id: "area_living_room"
```

#### REST API (curl)

```bash
curl -X POST http://localhost:8123/api/services/ha_permission_manager/remove_resource_permissions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resource_id": "area_living_room"}'
```

---

### 5. `reset_all_permissions` — Reset All / 重置所有權限

Clears the entire permission table. **This action cannot be undone.**

#### Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `confirm` | Yes | boolean | Must be `true` (safety lock) |

#### HA Automation YAML

```yaml
service: ha_permission_manager.reset_all_permissions
data:
  confirm: true
```

#### REST API (curl)

```bash
curl -X POST http://localhost:8123/api/services/ha_permission_manager/reset_all_permissions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

---

### 6. `get_permissions` — Query Permissions / 查詢權限

Returns permissions with optional filters. **This service returns data.**

#### Parameters (all optional)

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `user_id` | No | string | Filter by user |
| `resource_type` | No | string | Filter by type: `panel`, `area`, `label` |
| `resource_id` | No | string | Filter by specific resource |

Omit all parameters to get the complete permission table.

#### HA Automation YAML (with response_variable)

```yaml
service: ha_permission_manager.get_permissions
data:
  user_id: "a1b2c3d4e5f6"
  resource_type: "area"
response_variable: perms
```

After this, `perms` contains:
```json
{
  "permissions": {
    "a1b2c3d4e5f6": {
      "area_living_room": 1,
      "area_bedroom": 0
    }
  }
}
```

#### REST API (curl) — Returns JSON response

> **Important**: For query services (get_*), add `?return_response` to the URL to receive JSON data.
> 查詢類服務需在 URL 後加上 `?return_response` 才能獲取 JSON 數據。

```bash
# Get all permissions
curl -X POST "http://localhost:8123/api/services/ha_permission_manager/get_permissions?return_response" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'

# Filter by user
curl -X POST "http://localhost:8123/api/services/ha_permission_manager/get_permissions?return_response" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "a1b2c3d4e5f6"}'

# Filter by resource type
curl -X POST "http://localhost:8123/api/services/ha_permission_manager/get_permissions?return_response" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resource_type": "area"}'

# Filter by specific resource
curl -X POST "http://localhost:8123/api/services/ha_permission_manager/get_permissions?return_response" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resource_id": "area_living_room"}'
```

#### Response Format

```json
{
  "service_response": {
    "ha_permission_manager.get_permissions": {
      "permissions": {
        "user_id_1": {
          "area_living_room": 1,
          "panel_lovelace": 0,
          "label_outdoor": 1
        },
        "user_id_2": {
          "area_living_room": 1
        }
      }
    }
  }
}
```

#### Python

```python
data = {"user_id": "a1b2c3"}
response = requests.post(
    url_prefix + "get_permissions",
    headers=headers,
    json=data,
    params={"return_response": True},
)
permissions = response.json()
print(permissions)
```

---

### 7. `get_users` — List Users / 查詢用戶

Returns all manageable (non-system) HA users. **This service returns data.**

#### Parameters

None.

#### HA Automation YAML

```yaml
service: ha_permission_manager.get_users
data: {}
response_variable: users_result
```

#### REST API (curl)

```bash
curl -X POST "http://localhost:8123/api/services/ha_permission_manager/get_users?return_response" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### Response Format

```json
{
  "service_response": {
    "ha_permission_manager.get_users": {
      "users": [
        {
          "id": "a1b2c3d4e5f6",
          "name": "John",
          "is_admin": false
        },
        {
          "id": "d4e5f6a1b2c3",
          "name": "Jane",
          "is_admin": true
        }
      ]
    }
  }
}
```

---

### 8. `get_resources` — List Resources / 查詢資源

Returns all manageable resources. **This service returns data.**

#### Parameters (all optional)

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `type` | No | string | Filter: `panel`, `area`, `label` |

#### HA Automation YAML

```yaml
# Get all resources
service: ha_permission_manager.get_resources
data: {}
response_variable: resources_result

# Get only areas
service: ha_permission_manager.get_resources
data:
  type: "area"
response_variable: areas_result
```

#### REST API (curl)

```bash
# Get all resources
curl -X POST "http://localhost:8123/api/services/ha_permission_manager/get_resources?return_response" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'

# Get only panels
curl -X POST "http://localhost:8123/api/services/ha_permission_manager/get_resources?return_response" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "panel"}'
```

#### Response Format

```json
{
  "service_response": {
    "ha_permission_manager.get_resources": {
      "resources": [
        {"id": "panel_lovelace", "name": "Dashboard", "type": "panel"},
        {"id": "panel_config", "name": "Settings", "type": "panel"},
        {"id": "area_living_room", "name": "Living Room", "type": "area"},
        {"id": "area_bedroom", "name": "Bedroom", "type": "area"},
        {"id": "label_outdoor", "name": "Outdoor", "type": "label"}
      ]
    }
  }
}
```

---

## Common Recipes / 常見使用場景

### Recipe 1: Onboard a New User / 新用戶開通權限

```yaml
# Step 1: Get available users and resources
service: ha_permission_manager.get_users
data: {}
response_variable: users

service: ha_permission_manager.get_resources
data: {}
response_variable: resources

# Step 2: Grant access to specific areas and panels
service: ha_permission_manager.bulk_set_permissions
data:
  permissions:
    - user_id: "NEW_USER_ID"
      resource_id: "panel_lovelace"
      level: 1
    - user_id: "NEW_USER_ID"
      resource_id: "area_living_room"
      level: 1
    - user_id: "NEW_USER_ID"
      resource_id: "area_kitchen"
      level: 1
    - user_id: "NEW_USER_ID"
      resource_id: "label_common"
      level: 1
```

### Recipe 2: Offboard a User / 用戶離開

```yaml
service: ha_permission_manager.remove_user_permissions
data:
  user_id: "DEPARTING_USER_ID"
```

### Recipe 3: Lock Down a Sensitive Area / 限制敏感區域

```yaml
# Remove access for all users, then selectively grant
service: ha_permission_manager.remove_resource_permissions
data:
  resource_id: "area_server_room"

# Grant access only to specific users
service: ha_permission_manager.set_permission
data:
  user_id: "TRUSTED_USER_ID"
  resource_id: "area_server_room"
  level: 1
```

### Recipe 4: Audit Current Permissions / 審計當前權限

```yaml
# Get complete permission table
service: ha_permission_manager.get_permissions
data: {}
response_variable: all_perms

# Check specific user's area permissions
service: ha_permission_manager.get_permissions
data:
  user_id: "TARGET_USER_ID"
  resource_type: "area"
response_variable: user_area_perms
```

### Recipe 5: Time-Based Access (Automation) / 時段權限（自動化）

```yaml
# Grant access at 8 AM
automation:
  trigger:
    - platform: time
      at: "08:00:00"
  action:
    - service: ha_permission_manager.set_permission
      data:
        user_id: "WORKER_USER_ID"
        resource_id: "area_office"
        level: 1

# Revoke access at 6 PM
automation:
  trigger:
    - platform: time
      at: "18:00:00"
  action:
    - service: ha_permission_manager.set_permission
      data:
        user_id: "WORKER_USER_ID"
        resource_id: "area_office"
        level: 0
```

---

## AI Agent Reference / AI 代理參考

This section provides structured information for AI agents (Claude, GPT, etc.)
to programmatically manage HA permissions via REST API.

### Base URL Pattern

```
POST http://<HA_HOST>:<HA_PORT>/api/services/ha_permission_manager/<service_name>
```

### Required Headers

```json
{
  "Authorization": "Bearer <LONG_LIVED_ACCESS_TOKEN>",
  "Content-Type": "application/json"
}
```

### Recommended Workflow for AI Agents

```
Step 1: Discover users
  POST .../get_users?return_response  body: {}
  → Extract user IDs and names

Step 2: Discover resources
  POST .../get_resources?return_response  body: {}
  → Extract resource IDs (with prefixes)

Step 3: Check current permissions (optional)
  POST .../get_permissions?return_response  body: {"user_id": "<id>"}
  → See what's already configured

Step 4: Apply changes
  POST .../set_permission  body: {"user_id": "<id>", "resource_id": "<id>", "level": 0|1}
  or
  POST .../bulk_set_permissions  body: {"permissions": [...]}
```

> **Note for REST API**: Query services require `?return_response` as a URL query parameter,
> NOT in the JSON body. Write services do not need this parameter.

### Service Input/Output JSON Schema

#### Write Services (no response body)

```jsonc
// set_permission
{"user_id": "string", "resource_id": "string", "level": 0|1}

// bulk_set_permissions
{"permissions": [{"user_id": "string", "resource_id": "string", "level": 0|1}, ...]}

// remove_user_permissions
{"user_id": "string"}

// remove_resource_permissions
{"resource_id": "string"}

// reset_all_permissions
{"confirm": true}
```

#### Query Services (returns JSON — add `?return_response` to URL query string)

```jsonc
// get_permissions (all params optional)
// URL: POST .../get_permissions?return_response
// Body:
{"user_id": "string?", "resource_type": "panel|area|label?", "resource_id": "string?"}
// Response:
{"service_response": {"permissions": {"<user_id>": {"<resource_id>": 0|1, ...}, ...}}}

// get_users (no params)
// URL: POST .../get_users?return_response
// Body:
{}
// Response:
{"service_response": {"users": [{"id": "string", "name": "string", "is_admin": true|false}, ...]}}

// get_resources (type param optional)
// URL: POST .../get_resources?return_response
// Body:
{"type": "panel|area|label?"}
// Response:
{"service_response": {"resources": [{"id": "string", "name": "string", "type": "panel|area|label"}, ...]}}
```

### Error Responses

| HTTP Status | Error | Cause |
|-------------|-------|-------|
| 401 | Unauthorized | Missing or invalid Bearer token |
| 400 | Bad Request | Invalid parameters (wrong type, missing required field) |
| 400 | HomeAssistantError | Admin access required (non-admin token used) |
| 400 | HomeAssistantError | Invalid resource_id format (missing prefix) |
| 400 | HomeAssistantError | Permission Manager not loaded |
| 500 | Internal Server Error | Unexpected server error |

### Complete curl Examples for AI Agents

```bash
# Set HA URL and token
HA_URL="http://localhost:8123"
TOKEN="your_long_lived_access_token"
API="${HA_URL}/api/services/ha_permission_manager"

# 1. List all users
curl -s -X POST "${API}/get_users?return_response" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# 2. List all resources
curl -s -X POST "${API}/get_resources?return_response" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# 3. List only areas
curl -s -X POST "${API}/get_resources?return_response" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"type": "area"}' | python3 -m json.tool

# 4. Get all permissions
curl -s -X POST "${API}/get_permissions?return_response" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool

# 5. Get permissions for a specific user
curl -s -X POST "${API}/get_permissions?return_response" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "USER_ID_HERE"}' | python3 -m json.tool

# 6. Set a single permission
curl -s -X POST "${API}/set_permission" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "USER_ID", "resource_id": "area_living_room", "level": 1}'

# 7. Bulk set permissions
curl -s -X POST "${API}/bulk_set_permissions" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "permissions": [
      {"user_id": "USER_ID", "resource_id": "area_living_room", "level": 1},
      {"user_id": "USER_ID", "resource_id": "panel_lovelace", "level": 1},
      {"user_id": "USER_ID", "resource_id": "label_common", "level": 1}
    ]
  }'

# 8. Remove a user's permissions
curl -s -X POST "${API}/remove_user_permissions" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "USER_ID"}'

# 9. Remove a resource's permissions
curl -s -X POST "${API}/remove_resource_permissions" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"resource_id": "area_living_room"}'

# 10. Reset all permissions (DANGEROUS)
curl -s -X POST "${API}/reset_all_permissions" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

---

## Events / 事件

All write operations fire a `permission_manager_updated` event on the HA event
bus. Nothing this integration ships listens for it — the Permission Manager
panel updates its own state as it writes, and since v3.0.0 there is no frontend
Filter to re-apply. It is there for your automations, and for whoever is reading
a trace.

Home Assistant refuses this subscription to a non-administrator (issue #13), so
every write also fires `panels_updated`, which is the event that carries a
Permission change to the user it is about. That one has no payload at all.

Until v2.0.9 the two removals did not, despite what this table said (issue #14).
They do now, and so does every other write path — including the registry
listeners that remove permissions when a user, area, label or dashboard is
deleted. A write announces whether or not the store ended up different.

**The event data is diagnostic, not a contract** (ADR-0010). It says "the
permission store has been written to, re-read it" and nothing more. Read it in a
trace; do not branch on it. Fetch the store with `get_all_permissions` instead.

| Service | Event Data |
|---------|------------|
| `set_permission` | `{"action": "set", "user_id": "...", "resource_id": "...", "level": 0\|1}` |
| `bulk_set_permissions` | `{"action": "bulk_set", "count": N}` |
| `remove_user_permissions` | `{"action": "remove_user", "user_id": "...", "count": N}` |
| `remove_resource_permissions` | `{"action": "remove_resource", "resource_id": "...", "count": N}` |
| `reset_all_permissions` | `{"action": "reset_all", "count": N}` |

`count` is what the write touched: Resources dropped for `remove_user`, users
affected for `remove_resource` and `reset_all`, entries applied for `bulk_set`.

---

## Version History / 版本歷史

| Version | Date | Changes |
|---------|------|---------|
| 1.1.0 | 2026-05-15 | Added 8 HA Services (set_permission, bulk_set_permissions, remove_user_permissions, remove_resource_permissions, reset_all_permissions, get_permissions, get_users, get_resources) |
| 1.0.2 | — | Initial release with WebSocket API only |
