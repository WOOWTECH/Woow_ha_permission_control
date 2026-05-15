#!/usr/bin/env python3
"""REST API functional tests for ha_permission_manager services.

51 test cases across 3 groups:
  A (16): Happy path
  B (20): Edge conditions
  C (15): Error handling

Usage:
  python3 tests/test_services_api.py

Requires: HA running on localhost:15124 with admin/admin credentials.
"""
import json
import sys
import time
import requests
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================
HA_URL = "http://localhost:15124"
HA_USER = "admin"
HA_PASS = "admin"
API = f"{HA_URL}/api/services/ha_permission_manager"

# Known test users (from the HA test instance)
ADMIN_USER_ID = "ae1e8434ff2642c3931f0185eedc976b"
ELMO_USER_ID = "72f9eb5d8d0648c3801015d9dd723a32"

# =============================================================================
# Test infrastructure
# =============================================================================
results = []
token = None


def get_token():
    """Obtain a short-lived access token via HA login flow."""
    # Step 1: Initiate login flow
    flow = requests.post(
        f"{HA_URL}/auth/login_flow",
        json={
            "client_id": f"{HA_URL}/",
            "handler": ["homeassistant", None],
            "redirect_uri": f"{HA_URL}/",
        },
    ).json()
    flow_id = flow["flow_id"]

    # Step 2: Submit credentials
    result = requests.post(
        f"{HA_URL}/auth/login_flow/{flow_id}",
        json={
            "username": HA_USER,
            "password": HA_PASS,
            "client_id": f"{HA_URL}/",
        },
    ).json()
    auth_code = result["result"]

    # Step 3: Exchange for token
    token_resp = requests.post(
        f"{HA_URL}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": f"{HA_URL}/",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ).json()
    return token_resp["access_token"]


def headers(auth=True):
    """Return request headers."""
    h = {"Content-Type": "application/json"}
    if auth:
        h["Authorization"] = f"Bearer {token}"
    return h


def call_write(service, data):
    """Call a write service, return (status_code, body_text)."""
    r = requests.post(f"{API}/{service}", headers=headers(), json=data)
    return r.status_code, r.text


def call_query(service, data):
    """Call a query service with ?return_response, return (status_code, parsed_json_or_None)."""
    r = requests.post(
        f"{API}/{service}",
        headers=headers(),
        json=data,
        params={"return_response": True},
    )
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


def call_no_auth(service, data):
    """Call a service without auth header."""
    r = requests.post(f"{API}/{service}", headers=headers(auth=False), json=data)
    return r.status_code, r.text


def reset():
    """Reset all permissions to clean state."""
    call_write("reset_all_permissions", {"confirm": True})
    time.sleep(0.3)


def extract_service_response(resp_json):
    """Extract the service_response payload from HA REST API response.

    HA REST API returns: {"changed_states": [...], "service_response": {...}}
    We return the service_response dict directly.
    """
    if resp_json is None:
        return None
    return resp_json.get("service_response", resp_json)


def record(test_id, name, passed, detail=""):
    """Record a test result."""
    status = "PASS" if passed else "FAIL"
    results.append({
        "id": test_id,
        "name": name,
        "status": status,
        "detail": detail,
    })
    icon = "v" if passed else "X"
    print(f"  [{icon}] {test_id}: {name}" + (f" — {detail}" if detail and not passed else ""))


# =============================================================================
# Group A: Happy Path (16 tests)
# =============================================================================
def run_group_a():
    print("\n=== Group A: Happy Path (16 tests) ===")
    reset()

    # A1: get_users returns user list
    code, resp = call_query("get_users", {})
    data = extract_service_response(resp)
    users = data.get("users", []) if data else []
    user_ids = [u["id"] for u in users]
    passed = code == 200 and len(users) >= 2 and ELMO_USER_ID in user_ids
    record("A1", "get_users returns user list", passed,
           f"got {len(users)} users" if not passed else "")

    # A2: get_resources returns all types
    code, resp = call_query("get_resources", {})
    data = extract_service_response(resp)
    resources = data.get("resources", []) if data else []
    types_found = set(r["type"] for r in resources)
    passed = code == 200 and types_found == {"panel", "area", "label"}
    record("A2", "get_resources returns all types", passed,
           f"types={types_found}" if not passed else "")

    # A3: get_resources type=panel
    code, resp = call_query("get_resources", {"type": "panel"})
    data = extract_service_response(resp)
    resources = data.get("resources", []) if data else []
    passed = code == 200 and all(r["type"] == "panel" for r in resources) and len(resources) > 0
    record("A3", "get_resources type=panel", passed)

    # A4: get_resources type=area
    code, resp = call_query("get_resources", {"type": "area"})
    data = extract_service_response(resp)
    resources = data.get("resources", []) if data else []
    passed = code == 200 and all(r["type"] == "area" for r in resources) and len(resources) > 0
    record("A4", "get_resources type=area", passed)

    # A5: get_resources type=label
    code, resp = call_query("get_resources", {"type": "label"})
    data = extract_service_response(resp)
    resources = data.get("resources", []) if data else []
    passed = code == 200 and all(r["type"] == "label" for r in resources) and len(resources) > 0
    record("A5", "get_resources type=label", passed)

    # A6: set_permission level=1
    code, _ = call_write("set_permission", {
        "user_id": ELMO_USER_ID,
        "resource_id": "area_living_room",
        "level": 1,
    })
    passed = code == 200
    record("A6", "set_permission level=1", passed, f"HTTP {code}" if not passed else "")

    # A7: set_permission level=0 (override)
    code, _ = call_write("set_permission", {
        "user_id": ELMO_USER_ID,
        "resource_id": "area_living_room",
        "level": 0,
    })
    # Verify the override
    _, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID, "resource_id": "area_living_room"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    user_perms = perms.get(ELMO_USER_ID, {})
    passed = code == 200 and user_perms.get("area_living_room") == 0
    record("A7", "set_permission level=0 override", passed)

    # A8: get_permissions no filter (full table)
    # First set some data
    call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_kitchen", "level": 1})
    code, resp = call_query("get_permissions", {})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    passed = code == 200 and ELMO_USER_ID in perms
    record("A8", "get_permissions no filter", passed)

    # A9: get_permissions user_id filter
    code, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    passed = code == 200 and len(perms) == 1 and ELMO_USER_ID in perms
    record("A9", "get_permissions user_id filter", passed)

    # A10: get_permissions resource_type filter
    code, resp = call_query("get_permissions", {"resource_type": "area"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    # All resource keys should start with area_
    all_area = True
    for uid, rmap in perms.items():
        for rid in rmap:
            if not rid.startswith("area_"):
                all_area = False
    passed = code == 200 and all_area
    record("A10", "get_permissions resource_type filter", passed)

    # A11: get_permissions resource_id filter
    code, resp = call_query("get_permissions", {"resource_id": "area_kitchen"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    # Should only contain area_kitchen
    all_kitchen = True
    for uid, rmap in perms.items():
        if list(rmap.keys()) != ["area_kitchen"]:
            all_kitchen = False
    passed = code == 200 and all_kitchen and len(perms) > 0
    record("A11", "get_permissions resource_id filter", passed)

    # A12: get_permissions combo filter (user_id + resource_type)
    call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "panel_lovelace", "level": 1})
    code, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID, "resource_type": "panel"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    user_perms = perms.get(ELMO_USER_ID, {})
    passed = code == 200 and "panel_lovelace" in user_perms and "area_kitchen" not in user_perms
    record("A12", "get_permissions combo filter", passed)

    # A13: bulk_set_permissions
    reset()
    code, _ = call_write("bulk_set_permissions", {
        "permissions": [
            {"user_id": ELMO_USER_ID, "resource_id": "area_living_room", "level": 1},
            {"user_id": ELMO_USER_ID, "resource_id": "area_bedroom", "level": 1},
            {"user_id": ELMO_USER_ID, "resource_id": "panel_lovelace", "level": 0},
        ]
    })
    _, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    passed = (code == 200
              and perms.get("area_living_room") == 1
              and perms.get("area_bedroom") == 1
              and perms.get("panel_lovelace") == 0)
    record("A13", "bulk_set_permissions 3 entries", passed)

    # A14: remove_resource_permissions
    code, _ = call_write("remove_resource_permissions", {"resource_id": "area_bedroom"})
    _, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    passed = code == 200 and "area_bedroom" not in perms and "area_living_room" in perms
    record("A14", "remove_resource_permissions", passed)

    # A15: remove_user_permissions
    code, _ = call_write("remove_user_permissions", {"user_id": ELMO_USER_ID})
    _, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    passed = code == 200 and len(perms) == 0
    record("A15", "remove_user_permissions", passed)

    # A16: reset_all_permissions
    call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_kitchen", "level": 1})
    code, _ = call_write("reset_all_permissions", {"confirm": True})
    _, resp = call_query("get_permissions", {})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    passed = code == 200 and len(perms) == 0
    record("A16", "reset_all_permissions", passed)


# =============================================================================
# Group B: Edge Conditions (20 tests)
# =============================================================================
def run_group_b():
    print("\n=== Group B: Edge Conditions (20 tests) ===")
    reset()

    # B1: set_permission with non-existent user_id (valid format, should succeed)
    code, _ = call_write("set_permission", {
        "user_id": "nonexistent_user_12345",
        "resource_id": "area_living_room",
        "level": 1,
    })
    passed = code == 200
    record("B1", "set_permission non-existent user_id (valid format)", passed, f"HTTP {code}")

    # B2: set_permission with non-existent resource_id (valid format)
    code, _ = call_write("set_permission", {
        "user_id": ELMO_USER_ID,
        "resource_id": "area_nonexistent_room",
        "level": 1,
    })
    passed = code == 200
    record("B2", "set_permission non-existent resource_id (valid format)", passed, f"HTTP {code}")

    # B3: set_permission level boundary (0 and 1)
    code0, _ = call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_kitchen", "level": 0})
    code1, _ = call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_kitchen", "level": 1})
    passed = code0 == 200 and code1 == 200
    record("B3", "set_permission level boundary 0 and 1", passed)

    # B4: get_permissions on empty table
    reset()
    code, resp = call_query("get_permissions", {})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    passed = code == 200 and len(perms) == 0
    record("B4", "get_permissions on empty table", passed)

    # B5: get_permissions non-existent user_id (returns empty)
    code, resp = call_query("get_permissions", {"user_id": "nonexistent_xyz"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    user_perms = perms.get("nonexistent_xyz", {})
    passed = code == 200 and len(user_perms) == 0
    record("B5", "get_permissions non-existent user_id", passed)

    # B6: get_permissions non-existent resource_id (returns empty)
    call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_living_room", "level": 1})
    code, resp = call_query("get_permissions", {"resource_id": "area_nonexistent_xyz"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    passed = code == 200 and len(perms) == 0
    record("B6", "get_permissions non-existent resource_id", passed)

    # B7: bulk_set_permissions with only 1 entry (minimum)
    reset()
    code, _ = call_write("bulk_set_permissions", {
        "permissions": [{"user_id": ELMO_USER_ID, "resource_id": "area_bedroom", "level": 1}]
    })
    passed = code == 200
    record("B7", "bulk_set_permissions 1 entry (min)", passed)

    # B8: bulk_set_permissions duplicate entries (last value wins)
    reset()
    code, _ = call_write("bulk_set_permissions", {
        "permissions": [
            {"user_id": ELMO_USER_ID, "resource_id": "area_kitchen", "level": 0},
            {"user_id": ELMO_USER_ID, "resource_id": "area_kitchen", "level": 1},
        ]
    })
    _, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID, "resource_id": "area_kitchen"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    passed = code == 200 and perms.get("area_kitchen") == 1
    record("B8", "bulk_set duplicate entries (last wins)", passed,
           f"got {perms.get('area_kitchen')}" if not passed else "")

    # B9: remove_user_permissions non-existent user (idempotent)
    code, _ = call_write("remove_user_permissions", {"user_id": "nonexistent_user_999"})
    passed = code == 200
    record("B9", "remove_user_permissions non-existent (idempotent)", passed)

    # B10: remove_resource_permissions non-existent resource (idempotent)
    code, _ = call_write("remove_resource_permissions", {"resource_id": "area_nonexistent_room"})
    passed = code == 200
    record("B10", "remove_resource_permissions non-existent (idempotent)", passed)

    # B11: reset_all on already empty table (idempotent)
    reset()
    code, _ = call_write("reset_all_permissions", {"confirm": True})
    passed = code == 200
    record("B11", "reset_all on empty table (idempotent)", passed)

    # B12: rapid consecutive calls (10x set_permission)
    reset()
    all_ok = True
    for i in range(10):
        c, _ = call_write("set_permission", {
            "user_id": ELMO_USER_ID,
            "resource_id": f"area_rapid_test_{i}",
            "level": 1,
        })
        if c != 200:
            all_ok = False
    # Verify all 10 were stored
    time.sleep(0.5)  # Wait for batched save
    _, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    rapid_count = sum(1 for k in perms if k.startswith("area_rapid_test_"))
    passed = all_ok and rapid_count == 10
    record("B12", "rapid consecutive 10x set_permission", passed,
           f"stored={rapid_count}/10" if not passed else "")

    # B13: get_resources — all resource IDs have correct prefix
    _, resp = call_query("get_resources", {})
    data = extract_service_response(resp)
    resources = data.get("resources", []) if data else []
    all_prefixed = all(
        (r["id"].startswith("panel_") and r["type"] == "panel")
        or (r["id"].startswith("area_") and r["type"] == "area")
        or (r["id"].startswith("label_") and r["type"] == "label")
        for r in resources
    )
    passed = all_prefixed and len(resources) > 0
    record("B13", "get_resources all IDs have correct prefix", passed)

    # B14: get_users includes admin user with is_admin=true
    _, resp = call_query("get_users", {})
    data = extract_service_response(resp)
    users = data.get("users", []) if data else []
    admin_found = any(u["id"] == ADMIN_USER_ID and u["is_admin"] is True for u in users)
    elmo_found = any(u["id"] == ELMO_USER_ID and u["is_admin"] is False for u in users)
    passed = admin_found and elmo_found
    record("B14", "get_users admin flag correctness", passed)

    # B15: bulk_set mixed types (panel_ + area_ + label_)
    reset()
    code, _ = call_write("bulk_set_permissions", {
        "permissions": [
            {"user_id": ELMO_USER_ID, "resource_id": "panel_lovelace", "level": 1},
            {"user_id": ELMO_USER_ID, "resource_id": "area_living_room", "level": 1},
            {"user_id": ELMO_USER_ID, "resource_id": "label_zi_dong_hua", "level": 0},
        ]
    })
    _, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    passed = (code == 200
              and perms.get("panel_lovelace") == 1
              and perms.get("area_living_room") == 1
              and perms.get("label_zi_dong_hua") == 0)
    record("B15", "bulk_set mixed types (panel+area+label)", passed)

    # B16: set_permission then immediate get (atomicity)
    reset()
    call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_bedroom", "level": 1})
    code, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID, "resource_id": "area_bedroom"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    passed = code == 200 and perms.get("area_bedroom") == 1
    record("B16", "set then immediate get (atomicity)", passed)

    # B17: bulk_set then resource_type filter
    reset()
    call_write("bulk_set_permissions", {
        "permissions": [
            {"user_id": ELMO_USER_ID, "resource_id": "area_kitchen", "level": 1},
            {"user_id": ELMO_USER_ID, "resource_id": "panel_config", "level": 1},
            {"user_id": ELMO_USER_ID, "resource_id": "label_zi_dong_hua", "level": 1},
        ]
    })
    _, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID, "resource_type": "label"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    passed = list(perms.keys()) == ["label_zi_dong_hua"] and perms["label_zi_dong_hua"] == 1
    record("B17", "bulk_set then resource_type filter", passed)

    # B18: triple filter (user_id + resource_type + resource_id)
    code, resp = call_query("get_permissions", {
        "user_id": ELMO_USER_ID,
        "resource_type": "area",
        "resource_id": "area_kitchen",
    })
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    passed = code == 200 and perms == {"area_kitchen": 1}
    record("B18", "triple filter combination", passed)

    # B19: toggle permission 0→1→0
    reset()
    call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_bedroom", "level": 0})
    call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_bedroom", "level": 1})
    call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_bedroom", "level": 0})
    _, resp = call_query("get_permissions", {"user_id": ELMO_USER_ID, "resource_id": "area_bedroom"})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}).get(ELMO_USER_ID, {}) if data else {}
    passed = perms.get("area_bedroom") == 0
    record("B19", "toggle permission 0→1→0", passed)

    # B20: bulk_set with mixed users
    reset()
    code, _ = call_write("bulk_set_permissions", {
        "permissions": [
            {"user_id": ELMO_USER_ID, "resource_id": "area_living_room", "level": 1},
            {"user_id": ADMIN_USER_ID, "resource_id": "area_living_room", "level": 1},
            {"user_id": ELMO_USER_ID, "resource_id": "area_bedroom", "level": 0},
        ]
    })
    _, resp = call_query("get_permissions", {})
    data = extract_service_response(resp)
    perms = data.get("permissions", {}) if data else {}
    elmo_ok = perms.get(ELMO_USER_ID, {}).get("area_living_room") == 1
    admin_ok = perms.get(ADMIN_USER_ID, {}).get("area_living_room") == 1
    passed = code == 200 and elmo_ok and admin_ok
    record("B20", "bulk_set with mixed users", passed)


# =============================================================================
# Group C: Error Handling (15 tests)
# =============================================================================
def run_group_c():
    print("\n=== Group C: Error Handling (15 tests) ===")
    reset()

    # C1: set_permission missing user_id
    code, _ = call_write("set_permission", {"resource_id": "area_living_room", "level": 1})
    passed = code == 400
    record("C1", "set_permission missing user_id → 400", passed, f"HTTP {code}")

    # C2: set_permission missing resource_id
    code, _ = call_write("set_permission", {"user_id": ELMO_USER_ID, "level": 1})
    passed = code == 400
    record("C2", "set_permission missing resource_id → 400", passed, f"HTTP {code}")

    # C3: set_permission missing level
    code, _ = call_write("set_permission", {"user_id": ELMO_USER_ID, "resource_id": "area_living_room"})
    passed = code == 400
    record("C3", "set_permission missing level → 400", passed, f"HTTP {code}")

    # C4: set_permission level=2 (out of range)
    code, _ = call_write("set_permission", {
        "user_id": ELMO_USER_ID, "resource_id": "area_living_room", "level": 2
    })
    passed = code == 400
    record("C4", "set_permission level=2 → 400", passed, f"HTTP {code}")

    # C5: set_permission level=-1 (out of range)
    code, _ = call_write("set_permission", {
        "user_id": ELMO_USER_ID, "resource_id": "area_living_room", "level": -1
    })
    passed = code == 400
    record("C5", "set_permission level=-1 → 400", passed, f"HTTP {code}")

    # C6: set_permission resource_id without prefix
    code, body = call_write("set_permission", {
        "user_id": ELMO_USER_ID, "resource_id": "living_room", "level": 1
    })
    passed = code == 400 or code == 500  # Schema validation or handler validation
    record("C6", "set_permission no prefix → error", passed, f"HTTP {code}")

    # C7: set_permission resource_id with special chars
    code, _ = call_write("set_permission", {
        "user_id": ELMO_USER_ID, "resource_id": "area_living room!", "level": 1
    })
    passed = code == 400 or code == 500
    record("C7", "set_permission special chars → error", passed, f"HTTP {code}")

    # C8: bulk_set_permissions empty array
    code, _ = call_write("bulk_set_permissions", {"permissions": []})
    passed = code == 400
    record("C8", "bulk_set empty array → 400", passed, f"HTTP {code}")

    # C9: bulk_set_permissions incomplete entry (missing level)
    code, _ = call_write("bulk_set_permissions", {
        "permissions": [{"user_id": ELMO_USER_ID, "resource_id": "area_living_room"}]
    })
    passed = code == 400
    record("C9", "bulk_set incomplete entry → 400", passed, f"HTTP {code}")

    # C10: reset_all_permissions confirm=false
    code, _ = call_write("reset_all_permissions", {"confirm": False})
    passed = code == 400
    record("C10", "reset_all confirm=false → 400", passed, f"HTTP {code}")

    # C11: reset_all_permissions no confirm field
    code, _ = call_write("reset_all_permissions", {})
    passed = code == 400
    record("C11", "reset_all no confirm → 400", passed, f"HTTP {code}")

    # C12: get_resources type="invalid"
    code, _ = call_query("get_resources", {"type": "invalid"})
    passed = code == 400
    record("C12", "get_resources type=invalid → 400", passed, f"HTTP {code}")

    # C13: get_permissions resource_type="invalid"
    code, _ = call_query("get_permissions", {"resource_type": "invalid"})
    passed = code == 400
    record("C13", "get_permissions resource_type=invalid → 400", passed, f"HTTP {code}")

    # C14: no Authorization header → 401
    code, _ = call_no_auth("set_permission", {
        "user_id": ELMO_USER_ID, "resource_id": "area_living_room", "level": 1
    })
    passed = code == 401
    record("C14", "no auth header → 401", passed, f"HTTP {code}")

    # C15: oversized user_id (300 chars)
    long_id = "a" * 300
    code, _ = call_write("set_permission", {
        "user_id": long_id, "resource_id": "area_living_room", "level": 1
    })
    passed = code == 400
    record("C15", "oversized user_id (300 chars) → 400", passed, f"HTTP {code}")


# =============================================================================
# Main
# =============================================================================
def main():
    global token

    print("=" * 60)
    print("HA Permission Manager — Services API Test Suite")
    print("=" * 60)
    print(f"Target: {HA_URL}")

    # Get auth token
    print("\nAuthenticating...", end=" ")
    try:
        token = get_token()
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

    # Run test groups
    run_group_a()
    run_group_b()
    run_group_c()

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{total} PASS, {failed} FAIL")
    print("=" * 60)

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  {r['id']}: {r['name']} — {r['detail']}")

    # Save results to JSON
    output_dir = Path(__file__).parent
    output_file = output_dir / "test-results.json"
    with open(output_file, "w") as f:
        json.dump({
            "total": total,
            "passed": passed,
            "failed": failed,
            "results": results,
        }, f, indent=2)
    print(f"\nResults saved to {output_file}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
