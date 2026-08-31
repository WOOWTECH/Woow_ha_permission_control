#!/usr/bin/env python3
"""Does an open Control Panel notice an area or label Permission change? (#13)

The panel half of #13 is done: #19 measured, on a real instance, that
`panels_updated` reaches a **non-administrator's** connection. What is left is
the Control Panel's own data - areas and labels - which no event re-reads.

This drives the shipped `ha_control_panel.js` in a real browser against a fake
`hass` that answers the four WebSocket commands the panel actually calls. No
Home Assistant is involved, which is the point: the question is not whether the
backend answers correctly - `verify_issue_13_live.py` checks that against the
real instance - but whether an **already-rendered page** ever asks again.

Five admin actions, each one a change a user would expect to see:

  1. an area revoked  - two areas, one taken away. Does the card disappear?
  2. an area granted  - no areas, one given. Does a card appear?
  3. an area renamed  - one area kept but renamed, so a count cannot mask it.
  4. a label revoked  - the same revoke on the Labels tab.
  5. a kept area whose contents changed - the case that separates a re-read of
     the lists from a re-read that also drops the per-resource entity caches.

Each one fires `panels_updated` at the page the way Home Assistant would, and
*also* replaces the `hass` object, because Home Assistant replaces it on every
state change and a refetch that rides on that churn is not the same as one that
rides on the broadcast.

Then five checks on how the re-read behaves, all of them from the code review
of the first fix, and every one confirmed red against a copy of the panel
carrying the one defect it is written for (see VERIFY_FRONTEND below):

  - two broadcasts one round trip apart, which is what a debounced burst of
    Permission writes actually produces;
  - what the page shows *during* a re-read, which matters because the Panels
    broadcast is global and reaches pages the change is nothing to do with;
  - a re-read that fails against a page somebody is using;
  - the open area being the one revoked;
  - a subscription Home Assistant refuses, which must not be retried on every
    state change;

and the idle traffic count, which is what the old `_areas.length === 0` load
guard got wrong.

Usage:
  python3 tests/verify_issue_13.py --label v2.0.14

Read-only and offline: it writes to no Home Assistant and needs none running.
Captures land in tests/reports/issue-13/<label>.json.

  VERIFY_FRONTEND   a frontend directory to serve instead of the real one, for
                    running these checks against a deliberately broken copy
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent

# The frontend directory to serve. Overridable so a mutated copy can be run
# against these checks: a check that has never gone red proves nothing, and
# every check below was confirmed red against a copy carrying the one defect
# it is written for.
FRONTEND = Path(
    os.environ.get(
        "VERIFY_FRONTEND",
        REPO / "custom_components" / "ha_permission_manager" / "frontend",
    )
)

# Where the integration mounts its assets. `ha_control_panel.js` pulls lit in
# from this absolute path, so the harness has to serve it from there too.
MOUNT = "/ha_permission_manager_frontend"

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>issue 13 harness</title></head>
<body><div id="root"></div>
<script type="module">
  await import("MOUNT_PATH/ha_control_panel.js?v=harness");
  window.__ready = true;
</script>
</body></html>
""".replace("MOUNT_PATH", MOUNT)


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the frontend directory at the mount point, and one HTML page."""

    def do_GET(self):  # noqa: N802 - http.server's spelling
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith(MOUNT + "/"):
            return str(FRONTEND / path[len(MOUNT) + 1:])
        return str(FRONTEND / path.lstrip("/"))

    def log_message(self, *args):
        pass


# The fake Home Assistant. One `connection` object shared across every `hass`
# assignment, because that is how Home Assistant does it: the frontend hands
# the panel a new `hass` on every state change and the same live connection.
HARNESS_JS = """
() => {
  // `delayMs` is what makes the overlap measurable: a real backend answers
  // after a round trip, and two reads that overlap are the case the panel gets
  // wrong. `fail` makes every command reject, for the refresh-failure check.
  window.__backend = {
    areas: [], labels: [], areaEntities: {}, labelEntities: {},
    delayMs: 0, fail: false,
  };
  window.__calls = [];
  window.__subs = {};

  window.__subscribeAttempts = 0;
  window.__subscribeFails = false;

  window.__connection = {
    subscribeEvents: (callback, eventType) => {
      window.__subscribeAttempts += 1;
      if (window.__subscribeFails) {
        return Promise.reject(new Error("unauthorized"));
      }
      (window.__subs[eventType] = window.__subs[eventType] || []).push(callback);
      return Promise.resolve(() => {});
    },
    subscribeMessage: (callback, message) => {
      const key = message && message.type;
      (window.__subs[key] = window.__subs[key] || []).push(callback);
      return Promise.resolve(() => {});
    },
  };

  window.__makeHass = () => ({
    language: "en",
    states: {},
    themes: { darkMode: false },
    user: { id: "nonadmin", name: "nonadmin", is_admin: false },
    localize: (key) => key,
    connection: window.__connection,
    callService: async () => {},
    callWS: async (msg) => {
      window.__calls.push(msg.type);
      const backend = window.__backend;
      if (backend.fail) throw new Error("Connection lost");
      // The answer is settled when the request arrives, not when it lands.
      // That is what a backend does, and it is the whole of the overlap: a
      // read issued before a change carries the state from before it.
      let answer;
      switch (msg.type) {
        case "area_control/get_permitted_areas":
          answer = { areas: JSON.parse(JSON.stringify(backend.areas)) };
          break;
        case "label_control/get_permitted_labels":
          answer = { labels: JSON.parse(JSON.stringify(backend.labels)) };
          break;
        case "area_control/get_area_entities":
          answer = { entities: backend.areaEntities[msg.area_id] || {} };
          break;
        case "label_control/get_label_entities":
          answer = { entities: backend.labelEntities[msg.label_id] || {} };
          break;
        default:
          throw new Error("unexpected command: " + msg.type);
      }
      answer = JSON.parse(JSON.stringify(answer));
      const delay = backend.delayMs;
      if (delay > 0) {
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
      return answer;
    },
  });

  // What Home Assistant does when the Panel Gate broadcasts: every open page
  // hears `panels_updated`. Returns how many listeners there were to hear it.
  window.__broadcast = () => {
    const listeners = window.__subs["panels_updated"] || [];
    for (const callback of listeners) {
      callback({ event_type: "panels_updated", data: {}, origin: "LOCAL" });
    }
    return listeners.length;
  };

  // And separately, on every state change, hands the panel a new `hass`.
  window.__churn = () => {
    document.querySelector("ha-control-panel").hass = window.__makeHass();
  };

  window.__mount = () => {
    const panel = document.createElement("ha-control-panel");
    panel.hass = window.__makeHass();
    panel.narrow = false;
    panel.panel = { config: {} };
    document.getElementById("root").appendChild(panel);
  };

  window.__names = (tag) => {
    const panel = document.querySelector("ha-control-panel");
    if (!panel || !panel.shadowRoot) return null;
    return [...panel.shadowRoot.querySelectorAll(tag)].map((card) => {
      const thing = card.area || card.label || {};
      return thing.name || "";
    });
  };
}
"""

AREA_A = {"id": "kitchen", "name": "Kitchen", "icon": None,
          "entity_count": 0, "permission_level": 1}
AREA_B = {"id": "garage", "name": "Garage", "icon": None,
          "entity_count": 0, "permission_level": 1}
LABEL_A = {"id": "downstairs", "name": "Downstairs", "icon": None, "color": None,
           "entity_count": 0, "permission_level": 1}
LABEL_B = {"id": "upstairs", "name": "Upstairs", "icon": None, "color": None,
           "entity_count": 0, "permission_level": 1}

# How long to let the page react. Generous: the panel's fetches are a single
# await against an in-page fake, so anything that was going to happen has
# happened long before this.
REACT_MS = 1200


def scenario(page, name: str, *, before: dict, after: dict, tag: str) -> dict:
    """One admin action against an already-rendered page.

    `before` and `after` are backend states. The page is mounted on `before`,
    then the store moves to `after` and the broadcast goes out - with no
    reload, which is the whole question.
    """
    page.reload()
    page.wait_for_function("() => window.__ready === true")
    page.evaluate(HARNESS_JS)
    page.evaluate("(state) => Object.assign(window.__backend, state)", before)
    page.evaluate("() => window.__mount()")
    if tag == "cp-label-card":
        page.evaluate("() => { document.querySelector('ha-control-panel')"
                      ".activeTab = 'labels'; }")
    page.wait_for_timeout(REACT_MS)

    names_before = page.evaluate("(tag) => window.__names(tag)", tag)
    page.evaluate("() => { window.__calls.length = 0; }")

    # The administrator writes. Nothing tells the page directly - only the two
    # channels Home Assistant actually has.
    page.evaluate("(state) => Object.assign(window.__backend, state)", after)
    heard = page.evaluate("() => window.__broadcast()")
    page.evaluate("() => window.__churn()")
    page.wait_for_timeout(REACT_MS)

    key = "areas" if tag == "cp-area-card" else "labels"
    # Which list the page went back and asked for. A bare count is not enough:
    # the page re-reads whichever list is *empty* on every `hass` it is handed,
    # so a run can show traffic without any of it being about the change.
    calls = page.evaluate("() => window.__calls.slice()")
    return {
        "scenario": name,
        "tag": tag,
        "subscribers_for_panels_updated": heard,
        "names_before": names_before,
        "names_after": page.evaluate("(tag) => window.__names(tag)", tag),
        "reread_areas": "area_control/get_permitted_areas" in calls,
        "reread_labels": "label_control/get_permitted_labels" in calls,
        "calls_after_write": calls,
        "expected_names": [item["name"] for item in after[key]],
    }


def entity_staleness(page) -> dict:
    """A kept area whose *contents* changed.

    This is the scenario that separates a shallow fix from a correct one. The
    panel caches an area's entities under `_areaEntities[areaId]` and returns
    early whenever the key exists, so re-fetching the area *list* on the
    broadcast leaves every surviving area holding the entities it was born
    with. An area the user keeps, with a device taken out of it, would still
    offer the device.
    """
    page.reload()
    page.wait_for_function("() => window.__ready === true")
    page.evaluate(HARNESS_JS)
    page.evaluate("(state) => Object.assign(window.__backend, state)", {
        "areas": [AREA_A],
        "labels": [],
        "areaEntities": {"kitchen": {"light": ["light.ceiling", "light.lamp"]}},
    })
    page.evaluate("() => window.__mount()")
    page.wait_for_timeout(REACT_MS)

    read = ("() => { const card = document.querySelector('ha-control-panel')"
            ".shadowRoot.querySelector('cp-area-card');"
            "return card ? (card.areaEntities.light || []) : null; }")
    before = page.evaluate(read)

    # The lamp leaves the area - or its Permission goes. Either way the area
    # itself is still granted, so the area list is unchanged.
    page.evaluate("() => { window.__backend.areaEntities.kitchen = "
                  "{ light: ['light.ceiling'] }; }")
    page.evaluate("() => window.__broadcast()")
    page.evaluate("() => window.__churn()")
    page.wait_for_timeout(REACT_MS)

    return {
        "before": before,
        "after": page.evaluate(read),
        "expected": ["light.ceiling"],
    }


AREA_LIGHTS = ("() => { const card = document.querySelector('ha-control-panel')"
               ".shadowRoot.querySelector('cp-area-card');"
               "return card ? (card.areaEntities.light || []) : null; }")


def _mount(page, state: dict) -> None:
    page.reload()
    page.wait_for_function("() => window.__ready === true")
    page.evaluate(HARNESS_JS)
    page.evaluate("(state) => Object.assign(window.__backend, state)", state)
    page.evaluate("() => window.__mount()")
    page.wait_for_timeout(REACT_MS)


def overlapping_reads(page) -> dict:
    """Two broadcasts, one round trip apart, on a slow connection.

    A burst of Permission writes is what the Panel Gate's debounce is for, and
    what it produces is broadcasts about a second apart - so two reads of this
    panel's own data overlap routinely. If the older read is allowed to finish
    into the same state the newer one is filling, it writes the entities from
    before the change and the newer read then finds the id already there and
    does not ask for it. The area keeps its old contents until some later,
    unrelated broadcast happens to land.

    The timing is chosen so the overlap is certain rather than likely: with a
    round trip of D, the older read's entity request goes out at D and lands at
    2D, and the second broadcast at 1.5D clears nothing but starts a read whose
    list does not land until 2.5D - after the older write.
    """
    delay = 200
    _mount(page, {
        "areas": [AREA_A],
        "labels": [],
        "areaEntities": {"kitchen": {"light": ["light.ceiling", "light.lamp"]}},
        "delayMs": 0,
    })
    page.evaluate("(ms) => { window.__backend.delayMs = ms; }", delay)

    page.evaluate("() => window.__broadcast()")           # read one starts
    page.wait_for_timeout(int(delay * 1.25))              # its entity request is out
    page.evaluate("() => { window.__backend.areaEntities.kitchen = "
                  "{ light: ['light.ceiling'] }; }")      # the change it will miss
    page.wait_for_timeout(int(delay * 0.25))
    page.evaluate("() => window.__broadcast()")           # read two starts

    page.evaluate("(ms) => { window.__backend.delayMs = ms; }", 0)
    page.wait_for_timeout(delay * 8)
    return {"after": page.evaluate(AREA_LIGHTS), "expected": ["light.ceiling"]}


def no_blanking(page) -> dict:
    """What the page shows *during* a re-read.

    The Panels broadcast is global: every open page hears every Permission
    write on the instance, plus whatever Home Assistant fires it for itself.
    A re-read that empties the entity map before it refills it drops every
    summary count to zero for a round trip, on all of those pages, for changes
    that have nothing to do with the user reading them.
    """
    _mount(page, {
        "areas": [AREA_A],
        "labels": [],
        "areaEntities": {"kitchen": {"light": ["light.ceiling", "light.lamp"]}},
        "delayMs": 0,
    })
    page.evaluate("() => { window.__backend.delayMs = 400; }")
    page.evaluate("() => window.__broadcast()")
    page.wait_for_timeout(200)  # mid-flight
    midway = page.evaluate(AREA_LIGHTS)
    page.evaluate("() => { window.__backend.delayMs = 0; }")
    page.wait_for_timeout(REACT_MS)
    return {
        "midway": midway,
        "after": page.evaluate(AREA_LIGHTS),
        "expected": ["light.ceiling", "light.lamp"],
    }


def failed_refresh(page) -> dict:
    """A re-read that fails against a page someone is using.

    Before the panel re-read on its own, a failed read only ever happened at
    startup, where there was nothing to lose. Now one bad round trip arrives
    unasked, and it must not take a working page away from the user and
    replace it with an error screen.
    """
    _mount(page, {"areas": [AREA_A, AREA_B], "labels": [], "delayMs": 0})
    page.evaluate("() => { window.__backend.fail = true; }")
    page.evaluate("() => window.__broadcast()")
    page.wait_for_timeout(REACT_MS)
    return {
        "names": page.evaluate("(tag) => window.__names(tag)", "cp-area-card"),
        "expected_names": [AREA_A["name"], AREA_B["name"]],
        "error_screen": page.evaluate(
            "() => !!document.querySelector('ha-control-panel')"
            ".shadowRoot.querySelector('.error-container')"
        ),
    }


def revoked_while_open(page) -> dict:
    """The area on screen is the one taken away.

    Unreachable until the panel re-read its lists, and the worst-looking
    failure of the lot: the detail view keeps the name of a Resource this user
    no longer has, on the panel whose whole job is to not show it.
    """
    _mount(page, {"areas": [AREA_A, AREA_B], "labels": [], "delayMs": 0})
    page.evaluate("() => { const panel = document.querySelector('ha-control-panel');"
                  "panel._view = 'area'; panel._selectedAreaId = 'garage'; }")
    page.wait_for_timeout(200)
    page.evaluate("() => { window.__backend.areas = "
                  "window.__backend.areas.filter((a) => a.id !== 'garage'); }")
    page.evaluate("() => window.__broadcast()")
    page.wait_for_timeout(REACT_MS)
    return {
        "view": page.evaluate(
            "() => document.querySelector('ha-control-panel')._view"
        ),
        "expected_view": "home",
    }


def refused_subscription(page, *, churns: int) -> dict:
    """A subscription Home Assistant will not grant.

    `updated()` runs on every state change, so an attempt that is retried there
    is a round trip and a console error per state change for the life of the
    page. One attempt per connection is the whole of the rule; a reconnect
    hands over a new connection object and earns a new attempt.
    """
    page.reload()
    page.wait_for_function("() => window.__ready === true")
    page.evaluate(HARNESS_JS)
    page.evaluate("() => { window.__subscribeFails = true; }")
    page.evaluate("(state) => Object.assign(window.__backend, state)",
                  {"areas": [AREA_A], "labels": []})
    page.evaluate("() => window.__mount()")
    page.wait_for_timeout(REACT_MS)
    for _ in range(churns):
        page.evaluate("() => window.__churn()")
        page.wait_for_timeout(60)
    page.wait_for_timeout(REACT_MS)
    return {
        "churns": churns,
        "attempts": page.evaluate("() => window.__subscribeAttempts"),
    }


def churn_storm(page, *, areas: list, churns: int) -> dict:
    """How much traffic does an idle page make just by being handed a `hass`?

    Home Assistant replaces `hass` on every state change - dozens a minute on a
    live instance. The panel's "have I loaded yet?" guard is `length === 0`,
    which a user with nothing granted never leaves, so this measures the cost
    of that guard from both sides of it.
    """
    page.reload()
    page.wait_for_function("() => window.__ready === true")
    page.evaluate(HARNESS_JS)
    page.evaluate("(state) => Object.assign(window.__backend, state)",
                  {"areas": areas, "labels": []})
    page.evaluate("() => window.__mount()")
    page.wait_for_timeout(REACT_MS)

    page.evaluate("() => { window.__calls.length = 0; }")
    for _ in range(churns):
        page.evaluate("() => window.__churn()")
        page.wait_for_timeout(60)
    page.wait_for_timeout(REACT_MS)

    calls = page.evaluate("() => window.__calls.slice()")
    return {
        "granted_areas": len(areas),
        "churns": churns,
        "calls": len(calls),
        "call_types": sorted(set(calls)),
    }


def measure(label: str, port: int) -> dict:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:%d/" % port)

        results = [
            scenario(
                page, "an area revoked",
                before={"areas": [AREA_A, AREA_B], "labels": []},
                after={"areas": [AREA_A], "labels": []},
                tag="cp-area-card",
            ),
            scenario(
                page, "an area granted",
                before={"areas": [], "labels": []},
                after={"areas": [AREA_A], "labels": []},
                tag="cp-area-card",
            ),
            scenario(
                page, "an area renamed",
                before={"areas": [AREA_A], "labels": []},
                after={"areas": [dict(AREA_A, name="Scullery")], "labels": []},
                tag="cp-area-card",
            ),
            scenario(
                page, "a label revoked",
                before={"areas": [], "labels": [LABEL_A, LABEL_B]},
                after={"areas": [], "labels": [LABEL_A]},
                tag="cp-label-card",
            ),
        ]
        entities = entity_staleness(page)
        overlap = overlapping_reads(page)
        blanking = no_blanking(page)
        failure = failed_refresh(page)
        revoked = revoked_while_open(page)
        refused = refused_subscription(page, churns=10)
        storms = [
            churn_storm(page, areas=[AREA_A], churns=10),
            churn_storm(page, areas=[], churns=10),
        ]
        browser.close()

    return {
        "label": label,
        "page_errors": errors,
        "scenarios": results,
        "entity_staleness": entities,
        "overlapping_reads": overlap,
        "no_blanking": blanking,
        "failed_refresh": failure,
        "revoked_while_open": revoked,
        "refused_subscription": refused,
        "churn_storms": storms,
    }


def report(capture: dict) -> int:
    failures: list[str] = []
    print("\n" + "=" * 78)
    print("  issue #13 - does an open Control Panel re-read?  %s" % capture["label"])
    print("=" * 78 + "\n")

    for result in capture["scenarios"]:
        got = result["names_after"]
        want = result["expected_names"]
        verdict = "ok" if got == want else "STALE"
        print("  %-18s %s -> %s" % (result["scenario"], result["names_before"], got))
        print("  %-18s wanted %s   [listeners: %d, re-read areas: %s / labels: %s]"
              "  %s\n" % (
                  "", want, result["subscribers_for_panels_updated"],
                  result["reread_areas"], result["reread_labels"], verdict,
              ))
        if got != want:
            failures.append(
                "%s: the page still shows %s, wanted %s"
                % (result["scenario"], got, want)
            )

    entities = capture["entity_staleness"]
    print("  a kept area whose contents changed:")
    print("    %s -> %s   wanted %s\n"
          % (entities["before"], entities["after"], entities["expected"]))
    if entities["after"] != entities["expected"]:
        failures.append(
            "a kept area still offers %s, wanted %s - the per-area entity cache "
            "never expires, so re-reading the area list alone is not enough"
            % (entities["after"], entities["expected"])
        )

    overlap = capture["overlapping_reads"]
    print("  two broadcasts one round trip apart:")
    print("    %s   wanted %s\n" % (overlap["after"], overlap["expected"]))
    if overlap["after"] != overlap["expected"]:
        failures.append(
            "two overlapping re-reads left the area holding %s, wanted %s - the "
            "older read finished into the newer read's state"
            % (overlap["after"], overlap["expected"])
        )

    blanking = capture["no_blanking"]
    print("  a re-read in progress:")
    print("    midway %s, after %s   wanted %s throughout\n"
          % (blanking["midway"], blanking["after"], blanking["expected"]))
    if blanking["midway"] != blanking["expected"]:
        failures.append(
            "a re-read in progress showed %s, wanted %s - the page blanks its own "
            "counts on a broadcast meant for somebody else"
            % (blanking["midway"], blanking["expected"])
        )
    if blanking["after"] != blanking["expected"]:
        failures.append(
            "after an unchanged re-read the page shows %s, wanted %s"
            % (blanking["after"], blanking["expected"])
        )

    failure_case = capture["failed_refresh"]
    print("  a re-read that fails:")
    print("    kept %s, error screen: %s   wanted %s and False\n"
          % (failure_case["names"], failure_case["error_screen"],
             failure_case["expected_names"]))
    if failure_case["names"] != failure_case["expected_names"]:
        failures.append(
            "a failed re-read threw away the areas already on screen: %s, wanted %s"
            % (failure_case["names"], failure_case["expected_names"])
        )
    if failure_case["error_screen"]:
        failures.append(
            "a failed re-read replaced a working page with the error screen"
        )

    revoked = capture["revoked_while_open"]
    print("  the open area is the one revoked:")
    print("    view %r   wanted %r\n" % (revoked["view"], revoked["expected_view"]))
    if revoked["view"] != revoked["expected_view"]:
        failures.append(
            "after the open area was revoked the panel stayed on %r - it goes on "
            "naming a Resource the user no longer has" % (revoked["view"],)
        )

    refused = capture["refused_subscription"]
    print("  a subscription Home Assistant refuses:")
    print("    %d attempt(s) over %d state changes   wanted 1"
          % (refused["attempts"], refused["churns"]))
    print()
    if refused["attempts"] != 1:
        failures.append(
            "a refused subscription was attempted %d times over %d state changes - "
            "one round trip and one console error each, for the life of the page"
            % (refused["attempts"], refused["churns"])
        )

    print("  an idle page, handed a fresh hass 10 times:")
    for storm in capture["churn_storms"]:
        print("    %d area(s) granted -> %d WebSocket call(s)  %s"
              % (storm["granted_areas"], storm["calls"], storm["call_types"]))
    print()
    for storm in capture["churn_storms"]:
        if storm["calls"] > storm["churns"]:
            failures.append(
                "an idle page with %d area(s) granted made %d WebSocket calls for "
                "%d state changes - the load guard is polling, not caching"
                % (storm["granted_areas"], storm["calls"], storm["churns"])
            )

    if capture["page_errors"]:
        failures.append("page errors: %s" % capture["page_errors"])

    if failures:
        print("  FAIL")
        for failure in failures:
            print("    - %s" % failure)
        return 1
    print("  PASS - every change reached the open page without a reload")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="name for this run's capture")
    args = parser.parse_args()

    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Handler))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        capture = measure(args.label, port)
    finally:
        server.shutdown()

    directory = REPO / "tests" / "reports" / "issue-13"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ("%s.json" % args.label)).write_text(
        json.dumps(capture, indent=2, sort_keys=True), encoding="utf-8"
    )
    return report(capture)


if __name__ == "__main__":
    sys.exit(main())
