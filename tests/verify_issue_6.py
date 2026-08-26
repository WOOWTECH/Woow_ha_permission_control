#!/usr/bin/env python3
"""Live verification for issue #6: does the routing anchor hold?

`filterPanels()` keeps the panel Home Assistant is routing to in `hass.panels`
as a hidden anchor. Issue #6 reports two ways it stops holding, neither of which
was ever reproduced on an instance — both were read off the code. This points an
instrument at each.

  Mechanism A  the anchor is hidden by having no title, and two other places in
               this integration write titles onto exactly the panels that get
               anchored. Measured as: after loading a denied panel, what is
               `hass.panels[panel].title`, and is there a sidebar row for it?
               Watched over time, not once — the undoing is a later write, and a
               single reading taken too early would miss it.

  Mechanism B  the anchor names the panel the *document* loaded with. Measured
               as: drive a client-side navigation into a second denied panel the
               way Home Assistant's own `navigate()` does, then ask whether the
               map holds a route for where the browser now is.

Run it against the release before the fix and the release after, and diff the
two records. Usage:

  python3 tests/verify_issue_6.py --label v2.0.5-before
  python3 tests/verify_issue_6.py --label v2.0.6-after

Read-only: this script writes no Permission and fires no event. It needs the
non-admin to have BOTH panels below Closed, which is a store state the caller
sets up and restores.

Configuration (a repo-root .env is read automatically):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HA_TOKEN_NONADMIN   non-admin token; falls back to .ha_nonadmin_token

Screenshots and a JSON record land in tests/screenshots/issue-6/<label>/.
"""
import argparse
import base64
import json
import os
import time
import urllib.request
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
NONADMIN_TOKEN = os.environ.get("HA_TOKEN_NONADMIN") or (
    _nonadmin_file.read_text(encoding="utf-8").strip()
    if _nonadmin_file.exists()
    else None
)

SHOTS = REPO / "tests" / "screenshots" / "issue-6"

# The panel the document loads with, and the one it then navigates to. Both must
# be Closed for this user: the first is what gets anchored, the second is what
# the anchor has to follow. `ha-control-panel` is also one of the two panels the
# title writers name by id, which is what makes it the Mechanism A case.
FIRST_PANEL = "ha-control-panel"
SECOND_PANEL = "config"

# The anchor's hiding, as the two title writers would undo it.
TITLE_WRITER_PANELS = ["ha_permission_manager", "ha-control-panel"]

# Long enough for ROUTER_SETTLE_MS (150) plus a get_panel_permissions round
# trip, with room to spare. Mechanism B's repair cannot land sooner than that.
AFTER_NAVIGATION_MS = 2500

# Mechanism A is a *later* write undoing an earlier one, so the title is read
# repeatedly rather than once. sidebar-title.js polls on a 2 s cadence, so this
# window covers several of its passes.
TITLE_WATCH_MS = 9000
TITLE_SAMPLE_MS = 500

PROBE_INIT = """
(() => {
  const probe = { replaces: [], consoleErrors: [], rejections: [] };
  window.__issue6 = probe;

  // Issue #4's loop was measured this way; a redirect here would mean the
  // scenario never reached the anchor at all, so it has to be visible.
  const nativeReplace = window.location.replace.bind(window.location);
  try {
    Object.defineProperty(window.location, "replace", {
      value: function (url) {
        probe.replaces.push(String(url));
        return nativeReplace(url);
      },
      configurable: true,
    });
  } catch (err) {
    probe.replaceHookFailed = String(err);
  }

  window.addEventListener("unhandledrejection", (event) => {
    probe.rejections.push(String(event.reason && (event.reason.message || event.reason)));
  });
})();
"""

# Breadth-first search for an element by name, through shadow roots — the one
# way of finding the DOM that ADR-0005 allows.
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

STATE_PROBE = """
() => {
  %(find)s
  const hass = document.querySelector("home-assistant")?.hass;
  const panels = hass?.panels || {};

  // The sidebar's rows, however this Home Assistant spells them. Whether the
  // element was found at all matters as much as the rows: an empty list from a
  // sidebar that was never located says nothing about the sidebar.
  const sidebar = find("ha-sidebar");
  const rows = [];
  const root = sidebar?.shadowRoot;
  if (root) {
    for (const el of root.querySelectorAll("[href]")) {
      const href = el.getAttribute("href") || "";
      if (!href.startsWith("/")) continue;
      rows.push({ href, text: (el.textContent || "").trim().replace(/\\s+/g, " ") });
    }
  }

  const describe = (id) => {
    const panel = panels[id];
    if (!panel) return { present: false };
    return {
      present: true,
      title: panel.title === undefined ? "<undefined>" : panel.title,
      show_in_sidebar: panel.show_in_sidebar,
      // The mark v2.0.6 puts on an anchor. Absent on v2.0.5, which is the
      // point: there was nothing for a title writer to ask.
      anchored: !!panel[Symbol.for("ha_permission_manager.anchored_panel")],
    };
  };

  return {
    url: location.pathname,
    panelIds: Object.keys(panels).sort(),
    first: describe(%(first)s),
    second: describe(%(second)s),
    titleWriterPanels: %(writers)s.map((id) => ({ id, ...describe(id) })),
    sidebarRows: rows,
    sidebarFound: !!sidebar,
    sidebarHasShadowRoot: !!root,
    sidebarText: root ? (root.textContent || "").trim().replace(/\\s+/g, " ").slice(0, 300) : null,
    accessDenied: !!document.querySelector("ha-access-denied"),
    sidebarNamesFirst: rows.some((r) => r.href === "/" + %(first)s),
    sidebarNamesSecond: rows.some((r) => r.href === "/" + %(second)s),
  };
}
""" % {
    "find": FIND,
    "first": json.dumps(FIRST_PANEL),
    "second": json.dumps(SECOND_PANEL),
    "writers": json.dumps(TITLE_WRITER_PANELS),
}

# What Home Assistant's own navigate() does for an in-page route change: push
# the URL, then tell the app the location changed. No document load, which is
# the whole of Mechanism B.
CLIENT_SIDE_NAVIGATE = """
(target) => {
  history.pushState(null, "", target);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  return location.pathname;
}
"""


def _auth_script(token):
    """HA's frontend reads its session from localStorage['hassTokens']."""
    payload = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "hassUrl": HA_URL,
        "clientId": HA_URL + "/",
        "expires": int(time.time() * 1000) + 10 * 365 * 24 * 3600 * 1000,
    }
    return f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(payload))});"


def assert_token_usable(token):
    """The trap: an expired token imitates a Filter defect rather than failing.

    A 401 here, or an `exp` in the past, means every screenshot below would be
    of Home Assistant's auth page. Checked before anything is measured.
    """
    request = urllib.request.Request(
        HA_URL + "/api/", headers={"Authorization": "Bearer " + token}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise SystemExit(f"non-admin token rejected: HTTP {response.status}")

    claims = token.split(".")[1]
    claims += "=" * (-len(claims) % 4)
    exp = json.loads(base64.urlsafe_b64decode(claims)).get("exp", 0)
    if exp <= time.time():
        raise SystemExit("non-admin token has expired; every result would be the auth page")
    return {"http": 200, "expires": time.strftime("%Y-%m-%d", time.gmtime(exp))}


def served_version():
    """Which release the instance is actually serving, off the frontend itself."""
    with urllib.request.urlopen(HA_URL + "/", timeout=15) as response:
        body = response.read().decode("utf-8", "replace")
    versions = sorted(
        {
            part.split("?v=")[1].split('"')[0].split("'")[0]
            for part in body.split("/ha_permission_manager_frontend/")[1:]
            if "?v=" in part
        }
    )
    return versions


def run(label):
    out = SHOTS / label
    out.mkdir(parents=True, exist_ok=True)

    record = {
        "label": label,
        "identity": "nonadmin",
        "url": HA_URL,
        "firstPanel": FIRST_PANEL,
        "secondPanel": SECOND_PANEL,
        "token": assert_token_usable(NONADMIN_TOKEN),
        "servedVersions": served_version(),
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script(_auth_script(NONADMIN_TOKEN))
        context.add_init_script(PROBE_INIT)
        page = context.new_page()

        console_errors = []
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )

        # --- Mechanism A: load a denied panel and watch the anchor's title ---
        page.goto(f"{HA_URL}/{FIRST_PANEL}", wait_until="domcontentloaded")
        page.wait_for_timeout(AFTER_NAVIGATION_MS)

        samples = []
        deadline = time.time() + TITLE_WATCH_MS / 1000
        while time.time() < deadline:
            state = page.evaluate(STATE_PROBE)
            samples.append(
                {
                    "atMs": round((TITLE_WATCH_MS / 1000 - (deadline - time.time())) * 1000),
                    "title": state["first"].get("title"),
                    "anchored": state["first"].get("anchored"),
                    # The filtered map is a handful of panels. A sample where
                    # this jumps to the instance's full count is the filtering
                    # being wiped out from under the Filter, not a title being
                    # rewritten — a different defect wearing the same symptom.
                    "panelCount": len(state["panelIds"]),
                    "sidebarNamesFirst": state["sidebarNamesFirst"],
                }
            )
            page.wait_for_timeout(TITLE_SAMPLE_MS)

        record["onLoad"] = page.evaluate(STATE_PROBE)
        record["titleSamples"] = samples
        record["titleEverRestored"] = any(
            sample["title"] not in (None, "<undefined>") for sample in samples
        )
        record["sidebarEverNamedIt"] = any(sample["sidebarNamesFirst"] for sample in samples)
        page.screenshot(path=str(out / "01-denied-panel-loaded.png"), full_page=False)

        # --- Mechanism B: navigate client-side into a second denied panel ---
        record["navigatedTo"] = page.evaluate(CLIENT_SIDE_NAVIGATE, "/" + SECOND_PANEL)
        page.wait_for_timeout(AFTER_NAVIGATION_MS)
        record["afterNavigation"] = page.evaluate(STATE_PROBE)
        page.screenshot(path=str(out / "02-after-client-side-nav.png"), full_page=False)

        record["probe"] = page.evaluate("() => window.__issue6")
        record["consoleErrors"] = console_errors
        record["consoleErrorCount"] = len(console_errors)

        context.close()
        browser.close()

    # The two questions, answered rather than left to a reader of the JSON.
    first_after = record["afterNavigation"]["first"]
    second_after = record["afterNavigation"]["second"]
    record["verdict"] = {
        "mechanismA_hidingHeld": not record["titleEverRestored"]
        and not record["sidebarEverNamedIt"],
        "mechanismB_anchorFollowedRoute": second_after["present"],
        "mechanismB_staleAnchorDropped": not first_after["present"],
    }

    (out / "record.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="e.g. v2.0.6-after")
    args = parser.parse_args()

    if not NONADMIN_TOKEN:
        raise SystemExit("no non-admin token: set HA_TOKEN_NONADMIN or .ha_nonadmin_token")

    record = run(args.label)

    print(f"label            {record['label']}")
    print(f"served           {', '.join(record['servedVersions'])}")
    print(f"token good to    {record['token']['expires']}")
    print(f"landed on        {record['onLoad']['url']}")
    print(f"location.replace {len(record['probe']['replaces'])} {record['probe']['replaces']}")
    print()
    print("Mechanism A — the hiding")
    print(f"  anchor present        {record['onLoad']['first']['present']}")
    print(f"  anchor marked         {record['onLoad']['first']['anchored']}")
    print(f"  title ever restored   {record['titleEverRestored']}")
    print(f"  sidebar ever named it {record['sidebarEverNamedIt']}")
    for sample in record["titleSamples"]:
        print(
            f"    +{sample['atMs']:>5}ms  title={sample['title']!r}"
            f"  marked={sample['anchored']}  panels={sample['panelCount']}"
        )
    print()
    print("Mechanism B — the anchor after a client-side navigation")
    print(f"  now at                {record['afterNavigation']['url']}")
    print(f"  route for it          {record['afterNavigation']['second']}")
    print(f"  stale anchor dropped  {record['verdict']['mechanismB_staleAnchorDropped']}")
    print(f"  access denied shown   {record['afterNavigation']['accessDenied']}")
    print()
    print(f"console errors   {record['consoleErrorCount']}")
    print(f"verdict          {json.dumps(record['verdict'])}")
    print(f"written          {SHOTS / record['label'] / 'record.json'}")


if __name__ == "__main__":
    main()
