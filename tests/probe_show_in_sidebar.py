#!/usr/bin/env python3
"""Does this Home Assistant honour `show_in_sidebar: false`?

Issue #6 asserts it does not — "Home Assistant's `PanelInfo` has no
`show_in_sidebar` field ... So `title: null` is the whole of the hiding" — and
`anchorPanel()` in permission_policy.js was written the other way round. Both
cannot be right, and the answer decides how much of Mechanism A a user could
ever have seen.

The discriminator is a panel the user *is* permitted, which is therefore in the
sidebar to begin with. Flip one field at a time on it and watch the row:

  1. baseline          — the row is there
  2. show_in_sidebar   — set false, title untouched
  3. restore           — set true again, to show the row comes back and the
                         disappearance was the field rather than the re-render
  4. title             — set null, show_in_sidebar untouched

Read-only against the Permission store: this mutates only the browser's own
copy of `hass.panels`, in a throwaway page.

  python3 tests/probe_show_in_sidebar.py
"""
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env_file = REPO / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

HA_URL = os.environ.get("HA_URL", "http://192.168.2.6:8123").rstrip("/")
_nonadmin_file = REPO / ".ha_nonadmin_token"
TOKEN = os.environ.get("HA_TOKEN_NONADMIN") or _nonadmin_file.read_text(encoding="utf-8").strip()

# A panel this non-admin has a View level on, so it starts out in the sidebar.
PERMITTED_PANEL = "energy"

FIND = """
  const find = (name) => {
    const queue = [document.body];
    let n = 0;
    while (queue.length) {
      const node = queue.shift();
      if (!node || ++n > 20000) break;
      if (node.localName === name) return node;
      for (const list of [node.shadowRoot ? node.shadowRoot.children : null, node.children]) {
        if (!list) continue;
        for (let i = 0; i < list.length; i++) queue.push(list[i]);
      }
    }
    return null;
  };
"""

# The sidebar's own text is what a user reads, and it survives whichever element
# Home Assistant builds a row out of — which the row-by-href walk did not.
READ_SIDEBAR = """
() => {
  %s
  const root = find("ha-sidebar")?.shadowRoot;
  return root ? (root.textContent || "").trim().replace(/\\s+/g, " ") : null;
}
""" % FIND

SET_FIELD = """
({ panelId, field, value }) => {
  const haMain = document.querySelector("home-assistant");
  const panels = { ...haMain.hass.panels };
  panels[panelId] = { ...panels[panelId], [field]: value };
  haMain.hass = { ...haMain.hass, panels };
  return { [field]: haMain.hass.panels[panelId][field], title: haMain.hass.panels[panelId].title };
}
"""


def auth_script(token):
    payload = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "hassUrl": HA_URL,
        "clientId": HA_URL + "/",
        "expires": int(time.time() * 1000) + 10 * 365 * 24 * 3600 * 1000,
    }
    return f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(payload))});"


def main():
    steps = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script(auth_script(TOKEN))
        page = context.new_page()
        page.goto(f"{HA_URL}/{PERMITTED_PANEL}", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        def look(stage, applied=None):
            text = page.evaluate(READ_SIDEBAR)
            steps.append({"stage": stage, "applied": applied, "sidebarText": text})

        look("baseline")
        applied = page.evaluate(SET_FIELD, {"panelId": PERMITTED_PANEL, "field": "show_in_sidebar", "value": False})
        page.wait_for_timeout(1200)
        look("show_in_sidebar=false", applied)

        applied = page.evaluate(SET_FIELD, {"panelId": PERMITTED_PANEL, "field": "show_in_sidebar", "value": True})
        page.wait_for_timeout(1200)
        look("show_in_sidebar=true (restored)", applied)

        applied = page.evaluate(SET_FIELD, {"panelId": PERMITTED_PANEL, "field": "title", "value": None})
        page.wait_for_timeout(1200)
        look("title=null", applied)

        context.close()
        browser.close()

    baseline = steps[0]["sidebarText"] or ""
    for step in steps:
        text = step["sidebarText"] or ""
        print(f"{step['stage']:<32} {text}")
    print()

    def names_panel(text):
        # The row is identified by the panel's own title as the baseline shows it.
        return "能源" in (text or "") or "Energy" in (text or "")

    hidden_by_field = not names_panel(steps[1]["sidebarText"])
    back_after_restore = names_panel(steps[2]["sidebarText"])
    hidden_by_title = not names_panel(steps[3]["sidebarText"])

    print(f"in sidebar at baseline            {names_panel(baseline)}")
    print(f"hidden by show_in_sidebar=false   {hidden_by_field}")
    print(f"  ...and back when restored       {back_after_restore}")
    print(f"hidden by title=null              {hidden_by_title}")
    print()
    if hidden_by_field and back_after_restore:
        print("VERDICT: this Home Assistant DOES honour show_in_sidebar.")
    else:
        print("VERDICT: show_in_sidebar does nothing here; the missing title is the hiding.")

    out = REPO / "tests" / "screenshots" / "issue-6" / "show_in_sidebar.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"panel": PERMITTED_PANEL, "steps": steps}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main()
