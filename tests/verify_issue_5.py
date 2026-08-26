#!/usr/bin/env python3
"""Live verification for issue #5: does a re-initialisation register everything twice?

The issue describes an accumulation the tab never sheds — five WebSocket
subscriptions and a nest of `history.pushState` wrappers, one set per
re-initialisation, for the life of the tab. Two instruments, both pointed at the
same number: how many copies of the Filter are live.

  subscriptions  `hass.connection.subscribeEvents` is wrapped before the Filter
                 runs, so every subscription it makes is recorded with what
                 became of it — resolved, rejected, or unsubscribed. The Filter
                 is not simulated; it is watched making its own calls.
  nesting        one `history.pushState`, then count the 150 ms timers it
                 schedules. Each surviving wrapper schedules one
                 `checkCurrentPanelAccess()`, so the count is the nesting depth.
                 For a non-admin each of those also costs one
                 `get_panel_permissions` round trip, counted off the WebSocket.

What is simulated, and the only thing that is: the re-initialisation itself. In
the wild Home Assistant replaces its `home-assistant` element on logout/login
and the Filter's own MutationObserver reacts. Driving a real logout needs the
non-admin's password, which this repo does not hold, so the element is replaced
directly — a second `home-assistant` inserted ahead of the first, carrying the
same `hass`. The observer's condition is `document.querySelector("home-assistant")
!== currentHaElement`, and that is exactly what this makes true. Everything
after it is the deployed Filter doing whatever it does.

Usage:
  python3 tests/verify_issue_5.py --label v2.0.4 --identity nonadmin
  python3 tests/verify_issue_5.py --label v2.0.5 --identity admin

Read-only: this script writes no Permission and fires no event.

Configuration (a repo-root .env is read automatically):

  HA_URL              target instance      (default http://192.168.2.6:8123)
  HA_TOKEN, or HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN — admin token
  HA_TOKEN_NONADMIN   non-admin token; falls back to .ha_nonadmin_token

Screenshots and a JSON record land in tests/screenshots/issue-5/<label>/.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
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

ADMIN_TOKEN = (
    os.environ.get("HA_TOKEN")
    or os.environ.get("HOMEASSISTANT-LONG-LIVED-ACCESS-TOKEN")
)

_nonadmin_file = REPO / ".ha_nonadmin_token"
NONADMIN_TOKEN = os.environ.get("HA_TOKEN_NONADMIN") or (
    _nonadmin_file.read_text(encoding="utf-8").strip()
    if _nonadmin_file.exists()
    else None
)

SHOTS = REPO / "tests" / "screenshots" / "issue-5"

# The non-admin this instance tests with, and a panel the store leaves open to
# them, so the page under test is an ordinary one rather than Access Denied.
NONADMIN_USER_ID = "9eafc87fb1d44f8fb0677e428fcea9aa"
PERMITTED_PANEL = "ha-control-panel"   # panel_ha-control-panel: 1 (View)

# The five the sidebar filter subscribes to. Three of them nothing else on the
# page subscribes to, which is what makes them clean to attribute: the lovelace
# filter takes only permission_manager_updated, and core_config_updated is one
# Home Assistant's own frontend also uses.
SIDEBAR_EVENTS = [
    "user_updated",
    "homeassistant_auth_updated",
    "lovelace_updated",
    "permission_manager_updated",
    "core_config_updated",
]
SIDEBAR_ONLY_EVENTS = [
    "user_updated",
    "homeassistant_auth_updated",
    "lovelace_updated",
]

CHECK_DELAY_MS = 150

# Installed before any page script: a counter on the timers a navigation check
# is scheduled with, and a wrapper around subscribeEvents that records what
# became of every subscription. The wrapper is fitted to hass.connection the
# moment it exists — the Filter waits for `hass` and then makes a round trip
# before it subscribes, so a 25 ms poll is there long before it is needed.
PROBE_INIT = """
(() => {
  const probe = { timers: 0, subs: [], haAtDomContentLoaded: null };
  window.__issue5 = probe;

  const nativeSetTimeout = window.setTimeout;
  window.setTimeout = function (fn, delay, ...rest) {
    if (delay === %(delay)d) probe.timers += 1;
    return nativeSetTimeout.call(this, fn, delay, ...rest);
  };

  document.addEventListener("DOMContentLoaded", () => {
    probe.haAtDomContentLoaded = !!document.querySelector("home-assistant");
  });

  const fit = (connection) => {
    if (connection.__issue5Wrapped) return;
    connection.__issue5Wrapped = true;
    const original = connection.subscribeEvents.bind(connection);
    connection.subscribeEvents = function (handler, eventType) {
      const record = { eventType, state: "pending", unsubscribed: false };
      probe.subs.push(record);
      return original(handler, eventType).then(
        (unsubscribe) => {
          record.state = "live";
          return function () {
            record.unsubscribed = true;
            record.state = "released";
            return unsubscribe();
          };
        },
        (err) => {
          record.state = "rejected";
          record.error = String((err && (err.message || err.code)) || err);
          throw err;
        },
      );
    };
  };

  nativeSetTimeout.call(window, function poll() {
    const connection = document.querySelector("home-assistant")?.hass?.connection;
    if (connection) fit(connection);
    nativeSetTimeout.call(window, poll, 25);
  }, 25);
})();
""" % {"delay": CHECK_DELAY_MS}

# Replace the `home-assistant` element, which is the condition the Filter's own
# MutationObserver watches for. The decoy carries the real element's `hass`
# through, so everything the Filter reads off it is the live object.
REINIT = """
() => {
  const real = document.querySelector("home-assistant");
  const decoy = document.createElement("home-assistant");
  Object.defineProperty(decoy, "hass", {
    get: () => real.hass,
    set: (value) => { real.hass = value; },
    configurable: true,
  });
  real.parentNode.insertBefore(decoy, real);
  return {
    decoyIsNowFirst: document.querySelector("home-assistant") === decoy,
    decoyCarriesHass: !!decoy.hass?.panels,
  };
}
"""

PANELS_PROBE = """
() => {
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
  const hass = document.querySelector("home-assistant")?.hass;
  const panels = hass?.panels || {};
  return {
    path: location.pathname,
    hassReady: !!hass?.panels,
    panelCount: Object.keys(panels).length,
    panelIds: Object.keys(panels).sort(),
    accessDeniedPresent: !!find("ha-access-denied"),
  };
}
"""


def api(method, path, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{HA_URL}{path}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def assert_token(name, token):
    """A token that has expired imitates a Filter defect; check before trusting."""
    if not token:
        sys.exit(f"no {name} token available")
    status, _ = api("GET", "/api/", token)
    if status != 200:
        sys.exit(f"{name} token is not accepted: GET /api/ answered {status}")
    claims = token.split(".")
    if len(claims) == 3:
        raw = claims[1] + "=" * (-len(claims[1]) % 4)
        exp = json.loads(base64.urlsafe_b64decode(raw)).get("exp")
        if exp:
            left = (exp - time.time()) / 60
            if left < 10:
                sys.exit(f"{name} token expires in {left:.1f} min — mint a fresh one")
            return f"accepted, {left / 60 / 24:.0f} days left"
    return "accepted"


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


def tally(subs):
    """Per event type: how many subscriptions were made, and how many are live."""
    out = {}
    for record in subs:
        event_type = record["eventType"]
        if event_type not in SIDEBAR_EVENTS:
            continue
        seen = out.setdefault(
            event_type, {"made": 0, "live": 0, "rejected": 0, "released": 0}
        )
        seen["made"] += 1
        if record["state"] == "live":
            seen["live"] += 1
        elif record["state"] == "rejected":
            seen["rejected"] += 1
        elif record["state"] == "released":
            seen["released"] += 1
    return out


def run(label, identity):
    out = SHOTS / label
    out.mkdir(parents=True, exist_ok=True)
    record = {
        "label": label,
        "identity": identity,
        "url": HA_URL,
        "panel": PERMITTED_PANEL,
        "tokens": {
            "admin": assert_token("admin", ADMIN_TOKEN),
            "non-admin": assert_token("non-admin", NONADMIN_TOKEN),
        },
    }
    token = ADMIN_TOKEN if identity == "admin" else NONADMIN_TOKEN

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script(_auth_script(token))
        context.add_init_script(PROBE_INIT)
        page = context.new_page()

        console = []
        page.on("console", lambda m: console.append((m.type, m.text)))
        page.on("pageerror", lambda e: console.append(("pageerror", str(e))))

        fetches = []
        page.on(
            "websocket",
            lambda ws: ws.on(
                "framesent",
                lambda payload: fetches.append(time.time())
                if "get_panel_permissions" in str(payload) else None,
            ),
        )

        page.goto(
            f"{HA_URL}/{PERMITTED_PANEL}", wait_until="domcontentloaded", timeout=45000
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if page.evaluate(
                "() => !!document.querySelector('home-assistant')?.hass?.panels"
            ):
                break
            page.wait_for_timeout(250)
        page.wait_for_timeout(6000)

        probe = lambda: page.evaluate("() => window.__issue5")  # noqa: E731
        counters = lambda: (probe()["timers"], len(fetches))    # noqa: E731

        first = probe()
        record["first_run"] = {
            "ha_present_at_dom_content_loaded": first["haAtDomContentLoaded"],
            "subscriptions": tally(first["subs"]),
        }
        record["panels_after_first_run"] = page.evaluate(PANELS_PROBE)
        page.screenshot(path=str(out / f"01-{identity}-first-run.png"))

        # --- control: what the page does when nothing is asked of it ---
        t0, w0 = counters()
        page.wait_for_timeout(2000)
        t1, w1 = counters()
        record["control_window"] = {
            "timers_at_check_delay": t1 - t0,
            "get_panel_permissions": w1 - w0,
            "note": "2s with no navigation, to price the background rate",
        }

        # --- nesting, before any re-initialisation ---
        page.evaluate("() => history.pushState({}, '', location.pathname)")
        page.wait_for_timeout(2500)
        t2, w2 = counters()
        record["pushState_before_reinit"] = {
            "timers_at_check_delay": t2 - t1,
            "get_panel_permissions": w2 - w1,
        }

        # --- the re-initialisation ---
        record["reinit"] = page.evaluate(REINIT)
        page.wait_for_timeout(8000)
        after = probe()
        record["after_reinit"] = {
            "subscriptions": tally(after["subs"]),
            "panels": page.evaluate(PANELS_PROBE),
        }
        page.screenshot(path=str(out / f"02-{identity}-after-reinit.png"))

        # --- nesting, after one re-initialisation ---
        t3, w3 = counters()
        page.evaluate("() => history.pushState({}, '', location.pathname)")
        page.wait_for_timeout(2500)
        t4, w4 = counters()
        record["pushState_after_reinit"] = {
            "timers_at_check_delay": t4 - t3,
            "get_panel_permissions": w4 - w3,
        }

        record["console"] = [
            {"type": t, "text": x[:200]}
            for t, x in console
            if t in ("error", "warning", "pageerror")
        ]
        browser.close()

    verdict(record)
    (out / f"record-{identity}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    print(json.dumps(record, indent=2))
    return record


def verdict(record):
    """State the two numbers the issue is about, and whether they held."""
    live_now = {
        event: counts["live"]
        for event, counts in record["after_reinit"]["subscriptions"].items()
        if event in SIDEBAR_ONLY_EVENTS
    }
    nesting = record["pushState_after_reinit"]["timers_at_check_delay"]
    record["verdict"] = {
        "live_subscriptions_after_one_reinit": live_now,
        "expected": "1 of each — a re-initialisation replaces, not adds",
        "pushState_checks_after_one_reinit": nesting,
        "expected_checks": 1,
        "holds": all(n <= 1 for n in live_now.values()) and nesting <= 1,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="unlabelled", help="release under test")
    parser.add_argument(
        "--identity", choices=["admin", "nonadmin"], default="nonadmin"
    )
    args = parser.parse_args()
    run(args.label, args.identity)


if __name__ == "__main__":
    main()
