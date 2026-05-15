#!/usr/bin/env python3
"""Playwright UI verification for HA Permission Manager services.

Takes screenshots of:
1. Developer Tools > Services — each of the 8 services
2. Permission Manager panel — before/after permission changes via API

Usage:
  python3 tests/playwright_ui_verify.py
"""
import time
import json
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

HA_URL = "http://localhost:15124"
HA_USER = "admin"
HA_PASS = "admin"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

ELMO_USER_ID = "72f9eb5d8d0648c3801015d9dd723a32"

# 8 services to screenshot in Developer Tools
SERVICES = [
    "set_permission",
    "bulk_set_permissions",
    "remove_user_permissions",
    "remove_resource_permissions",
    "reset_all_permissions",
    "get_permissions",
    "get_users",
    "get_resources",
]


def get_token():
    """Obtain auth token via HA login flow."""
    flow = requests.post(
        f"{HA_URL}/auth/login_flow",
        json={"client_id": f"{HA_URL}/", "handler": ["homeassistant", None], "redirect_uri": f"{HA_URL}/"},
    ).json()
    result = requests.post(
        f"{HA_URL}/auth/login_flow/{flow['flow_id']}",
        json={"username": HA_USER, "password": HA_PASS, "client_id": f"{HA_URL}/"},
    ).json()
    token_resp = requests.post(
        f"{HA_URL}/auth/token",
        data={"grant_type": "authorization_code", "code": result["result"], "client_id": f"{HA_URL}/"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ).json()
    return token_resp["access_token"]


def call_write(token, service, data):
    return requests.post(
        f"{HA_URL}/api/services/ha_permission_manager/{service}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=data,
    )


def login_browser(page):
    """Login to HA via browser.

    HA trusted network auth: radio button user selection + 'Log in' button.
    """
    page.goto(f"{HA_URL}/")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # Trusted network auth: Admin radio is pre-selected, just click Log in
    try:
        # Ensure Admin radio is selected (it should be by default)
        admin_radio = page.locator(f'input[type="radio"][value="{ADMIN_USER_ID}"]')
        if admin_radio.count() > 0:
            admin_radio.check(force=True)
            time.sleep(0.5)

        # Click the Log in button
        page.locator("text=Log in").first.click()
    except Exception:
        # Fallback: click any submit-like button
        page.locator("ha-button, mwc-button, button").first.click()

    page.wait_for_load_state("networkidle")
    time.sleep(4)


def screenshot_developer_tools_services(page):
    """Navigate to Developer Tools > Actions and screenshot each service.

    HA 2025+ uses "Actions" tab (formerly "Services"). The service picker
    is deep in shadow DOM. We use JavaScript to traverse shadow roots and
    set the service value directly.
    """
    print("\n--- Developer Tools: Service Forms ---")

    for svc in SERVICES:
        full_name = f"ha_permission_manager.{svc}"
        print(f"  Screenshotting: {full_name}...", end=" ")

        try:
            # Navigate fresh to Developer Tools > Actions (Services)
            page.goto(f"{HA_URL}/developer-tools/action")
            page.wait_for_load_state("networkidle")
            time.sleep(3)

            # Deep shadow DOM traversal to find and set the service picker
            success = page.evaluate(f"""() => {{
                // Helper to traverse shadow DOMs
                function queryShadow(root, selector) {{
                    if (!root) return null;
                    let el = root.querySelector(selector);
                    if (el) return el;
                    // Check shadow roots of children
                    const allEls = root.querySelectorAll('*');
                    for (const child of allEls) {{
                        if (child.shadowRoot) {{
                            el = queryShadow(child.shadowRoot, selector);
                            if (el) return el;
                        }}
                    }}
                    return null;
                }}

                // Find ha-service-picker or ha-action-picker in shadow DOM
                let picker = queryShadow(document, 'ha-service-picker');
                if (!picker) picker = queryShadow(document, 'ha-action-picker');

                if (picker) {{
                    picker.value = '{full_name}';
                    picker.dispatchEvent(new CustomEvent('value-changed', {{
                        detail: {{ value: '{full_name}' }},
                        bubbles: true,
                        composed: true
                    }}));
                    return 'picker-set';
                }}

                // Fallback: try to find the service control
                let control = queryShadow(document, 'ha-service-control');
                if (!control) control = queryShadow(document, 'ha-action-control');
                if (control) {{
                    control.value = {{ action: '{full_name}', data: {{}} }};
                    control.dispatchEvent(new CustomEvent('value-changed', {{
                        detail: {{ value: {{ action: '{full_name}', data: {{}} }} }},
                        bubbles: true,
                        composed: true
                    }}));
                    return 'control-set';
                }}

                return 'not-found';
            }}""")

            time.sleep(3)

            # Take screenshot
            fname = f"devtools_svc_{svc}.png"
            page.screenshot(path=str(SCREENSHOTS_DIR / fname), full_page=True)
            print(f"OK ({success}) -> {fname}")
        except Exception as e:
            fname = f"devtools_svc_{svc}.png"
            page.screenshot(path=str(SCREENSHOTS_DIR / fname), full_page=True)
            print(f"PARTIAL -> {fname}: {e}")


def screenshot_permission_manager_panel(page, token):
    """Screenshot Permission Manager panel before/after API changes."""
    print("\n--- Permission Manager Panel ---")

    # 1. Reset permissions first
    call_write(token, "reset_all_permissions", {"confirm": True})
    time.sleep(0.5)

    # 2. Navigate to Permission Manager panel
    page.goto(f"{HA_URL}/ha_permission_manager")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # Screenshot empty state
    page.screenshot(path=str(SCREENSHOTS_DIR / "panel_empty.png"), full_page=True)
    print("  Screenshotted: panel_empty.png (no permissions set)")

    # 3. Set a single permission via API
    call_write(token, "set_permission", {
        "user_id": ELMO_USER_ID,
        "resource_id": "area_living_room",
        "level": 1,
    })
    time.sleep(0.5)

    # Reload panel
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    page.screenshot(path=str(SCREENSHOTS_DIR / "panel_after_set.png"), full_page=True)
    print("  Screenshotted: panel_after_set.png (1 permission set)")

    # 4. Bulk set more permissions
    call_write(token, "bulk_set_permissions", {
        "permissions": [
            {"user_id": ELMO_USER_ID, "resource_id": "area_bedroom", "level": 1},
            {"user_id": ELMO_USER_ID, "resource_id": "panel_lovelace", "level": 1},
            {"user_id": ELMO_USER_ID, "resource_id": "label_zi_dong_hua", "level": 0},
        ]
    })
    time.sleep(0.5)

    # Reload panel
    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    page.screenshot(path=str(SCREENSHOTS_DIR / "panel_after_bulk.png"), full_page=True)
    print("  Screenshotted: panel_after_bulk.png (4 permissions after bulk set)")

    # 5. Remove one resource permission
    call_write(token, "remove_resource_permissions", {"resource_id": "area_bedroom"})
    time.sleep(0.5)

    page.reload()
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    page.screenshot(path=str(SCREENSHOTS_DIR / "panel_after_remove.png"), full_page=True)
    print("  Screenshotted: panel_after_remove.png (after remove_resource_permissions)")


def main():
    print("=" * 60)
    print("HA Permission Manager — Playwright UI Verification")
    print("=" * 60)

    # Get API token
    print("\nObtaining API token...", end=" ")
    token = get_token()
    print("OK")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )
        page = context.new_page()

        # Login
        print("Logging into HA...", end=" ")
        login_browser(page)
        print("OK")

        # Take initial screenshot
        page.screenshot(path=str(SCREENSHOTS_DIR / "ha_logged_in.png"), full_page=True)
        print("  Screenshotted: ha_logged_in.png")

        # Developer Tools screenshots
        screenshot_developer_tools_services(page)

        # Permission Manager panel screenshots
        screenshot_permission_manager_panel(page, token)

        browser.close()

    # List screenshots
    screenshots = sorted(SCREENSHOTS_DIR.glob("*.png"))
    print(f"\n{'='*60}")
    print(f"Total screenshots: {len(screenshots)}")
    for s in screenshots:
        print(f"  {s.name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
