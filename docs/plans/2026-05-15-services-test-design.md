# HA Permission Manager Services — Test Design

## Overview

Comprehensive test suite for the 8 new HA Services, covering functional correctness,
edge conditions, error handling, and UI presentation verification.

## Test Architecture

### Layer 1: REST API Functional Tests (Python)
- 51 test cases via HA REST API (`requests` library)
- Groups: A (happy path, 16), B (edge conditions, 20), C (error handling, 15)
- Output: `tests/test-results.json`

### Layer 2: Playwright CLI UI Verification
- Developer Tools: 8 Service form screenshots
- Permission Manager panel: before/after permission change screenshots
- Output: `tests/screenshots/`

## Test Cases

### Group A: Happy Path (16)
A1-A5: get_users, get_resources (all + 3 type filters)
A6-A7: set_permission (level=1, level=0 override)
A8-A12: get_permissions (no filter, user_id, resource_type, resource_id, combo)
A13: bulk_set_permissions (3 entries)
A14: remove_resource_permissions
A15: remove_user_permissions
A16: reset_all_permissions

### Group B: Edge Conditions (20)
B1-B2: Non-existent user_id / resource_id (valid format)
B3: Level boundary (0 and 1)
B4-B6: Empty table queries, non-existent filters
B7-B8: Bulk min=1, duplicate entries
B9-B11: Idempotent removes/reset on empty
B12: Rapid consecutive calls (10x)
B13-B14: Resource prefix validation, admin user inclusion
B15: Bulk mixed types
B16-B17: Atomic set+get, type filter after bulk
B18: Triple filter combination
B19: Toggle permission 0→1→0
B20: Bulk with mixed users

### Group C: Error Handling (15)
C1-C3: Missing required fields
C4-C5: Level out of range (2, -1)
C6-C7: Invalid resource_id format
C8-C9: Bulk empty array, incomplete entry
C10-C11: Reset without confirm / confirm=false
C12-C13: Invalid type values
C14: No auth header (401)
C15: Oversized user_id (300 chars)
