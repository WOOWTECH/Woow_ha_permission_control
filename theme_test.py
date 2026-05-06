#!/usr/bin/env python3
"""Theme Test Runner v3 - No reload needed.
Uses frontend.set_theme service + callWS for user data.
After setting theme, navigates directly without reload.
"""
import subprocess
import json
import time
import os

PROJDIR = "/var/tmp/vibe-kanban/worktrees/1fe8-ha-permission-co/Woow_ha_permission&control"
SCREENSHOT_DIR = os.path.join(PROJDIR, "screenshots")
RESULTS_FILE = "/tmp/ha-theme-test/results.json"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

THEMES = ["Woow", "Frosted Glass", "Google Theme"]
MODES = ["light", "dark"]
PANELS = [
    ("PM", "/ha_permission_manager"),
    ("CP", "/ha-control-panel"),
    ("AC", "/area-control"),
    ("LC", "/label-control"),
]
CSS_PROPS = [
    "--sidebar-background-color",
    "--sidebar-selected-text-color",
    "--ha-card-background",
    "--primary-color",
    "--primary-text-color",
    "--primary-background-color",
    "--card-background-color",
    "--app-header-background-color",
]


def run_pw(args, timeout=30):
    cmd = ["npx", "playwright-cli"] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=PROJDIR)
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as e:
        return f"ERROR: {e}"


def eval_js(js_code, filename="tmp_eval.js"):
    """Write JS to file and evaluate via playwright-cli --raw eval."""
    filepath = os.path.join(PROJDIR, filename)
    with open(filepath, "w") as f:
        f.write(js_code)
    with open(filepath) as f:
        content = f.read()
    return run_pw(["--raw", "eval", content], timeout=20)


def set_theme_and_mode(theme, mode):
    """Set theme using callWS + callService, then wait for application."""
    safe_theme = theme.replace("'", "\\'")
    dark_val = "true" if mode == "dark" else "false"
    js = f"""() => {{
  var ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({{ error: 'no-hass' }});

  // Step 1: Set user preference (persists)
  var p1 = ha.hass.callWS({{
    type: 'frontend/set_user_data',
    key: 'core',
    value: {{
      selectedTheme: {{ theme: '{safe_theme}', dark: {dark_val} }}
    }}
  }});

  // Step 2: Set system default theme (triggers immediate CSS update)
  var p2 = ha.hass.callService('frontend', 'set_theme', {{
    name: '{safe_theme}',
    mode: '{mode}'
  }});

  return Promise.all([p1, p2]).then(function() {{
    // Wait for theme to apply
    return new Promise(function(resolve) {{
      setTimeout(function() {{
        var root = document.documentElement;
        var primary = getComputedStyle(root).getPropertyValue('--primary-color').trim();
        resolve(JSON.stringify({{ success: true, primary: primary }}));
      }}, 3000);
    }});
  }}).catch(function(e) {{
    return JSON.stringify({{ error: e.message }});
  }});
}}"""
    return eval_js(js, "set_theme_v3.js")


def get_css():
    props_json = json.dumps(CSS_PROPS)
    js = f"""() => {{
  var result = {{}};
  var root = document.documentElement;
  var ha = document.querySelector('home-assistant');
  var props = {props_json};
  for (var i = 0; i < props.length; i++) {{
    var prop = props[i];
    result[prop] = getComputedStyle(root).getPropertyValue(prop).trim()
      || (ha ? getComputedStyle(ha).getPropertyValue(prop).trim() : '') || '(not set)';
  }}
  try {{
    var sidebar = ha && ha.shadowRoot ? ha.shadowRoot.querySelector('ha-sidebar') : null;
    var menu = sidebar && sidebar.shadowRoot ? sidebar.shadowRoot.querySelector('.menu') : null;
    if (menu) result['_sidebar_actual_bg'] = getComputedStyle(menu).backgroundColor;
  }} catch(e) {{}}
  return JSON.stringify(result);
}}"""
    raw = eval_js(js, "get_css_v3.js")
    try:
        if raw.startswith('"') and raw.endswith('"'):
            raw = json.loads(raw)
        return json.loads(raw)
    except Exception:
        return {"_error": raw[:200] if raw else "empty"}


def navigate(url):
    return run_pw(["goto", url], timeout=20)


def screenshot(filepath):
    # Use relative path from PROJDIR
    relpath = os.path.relpath(filepath, PROJDIR)
    return run_pw(["screenshot", f"--filename={relpath}"])


def set_color_scheme(mode):
    """Emulate dark or light color scheme via playwright-cli run-code.
    Uses pre-written emulate_dark.js / emulate_light.js files.
    """
    filename = f"emulate_{mode}.js"
    return run_pw(["run-code", f"--filename={filename}"], timeout=15)


# ============================================================
print("=" * 60)
print("Theme UI Test v3: 3 themes x 2 modes x 4 panels = 24")
print("No reload — theme applied via service call + user data")
print("=" * 60)

results = []

for theme in THEMES:
    for mode in MODES:
        print(f"\n--- Theme: {theme} | Mode: {mode} ---")

        # Emulate color scheme for dark/light mode
        set_color_scheme(mode)
        time.sleep(1)

        # Set theme (no reload needed)
        r = set_theme_and_mode(theme, mode)
        try:
            parsed = json.loads(json.loads(r)) if r.startswith('"') else json.loads(r)
            print(f"  Set result: {parsed}")
        except Exception:
            print(f"  Set result: {r}")

        # Navigate to first panel (acts as soft-refresh for theme application)
        navigate("http://localhost:15124/lovelace/0")
        time.sleep(2)

        for pname, purl in PANELS:
            safe_theme = theme.replace(" ", "_")
            fname = f"{safe_theme}_{mode}_{pname}.png"
            fpath = os.path.join(SCREENSHOT_DIR, fname)

            navigate(f"http://localhost:15124{purl}")
            time.sleep(3)

            screenshot(fpath)

            css = get_css()

            result = {
                "theme": theme,
                "mode": mode,
                "panel": pname,
                "screenshot": fname,
                "css": css,
            }
            results.append(result)

            primary = css.get("--primary-color", "?")
            card_bg = css.get("--ha-card-background", "") or css.get("--card-background-color", "?")
            sidebar_bg = css.get("--sidebar-background-color", "?")
            bg_color = css.get("--primary-background-color", "?")
            status = "OK" if primary and primary not in ("(not set)", "?", "#009ac7") else "CHECK"
            print(f"  {pname}: {status} | primary={primary} | card-bg={card_bg} | sidebar={sidebar_bg} | bg={bg_color}")

# Reset to default
print("\nResetting to default theme...")
eval_js("""() => {
  var ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return 'no-hass';
  ha.hass.callService('frontend', 'set_theme', { name: 'default' });
  ha.hass.callWS({
    type: 'frontend/set_user_data',
    key: 'core',
    value: { selectedTheme: { theme: '' } }
  });
  return 'reset';
}""", "reset_theme.js")

# Write results
with open(RESULTS_FILE, "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\n{'=' * 60}")
print(f"Done. {len(results)} tests completed.")
print(f"Screenshots: {SCREENSHOT_DIR}")
print(f"Results: {RESULTS_FILE}")
print(f"{'=' * 60}")

# Summary table
print(f"\n{'Theme':<20} {'Mode':<6} {'Panel':<4} {'Primary':<20} {'Card BG':<25} {'St'}")
print("-" * 85)
prev_key = ""
for r in results:
    css = r["css"]
    primary = css.get("--primary-color", "?")
    card_bg = css.get("--ha-card-background", "") or css.get("--card-background-color", "?")
    key = f"{r['theme']}_{r['mode']}"
    # Check if theme values are non-default
    is_default = primary in ("#009ac7", "(not set)", "?", "")
    status = "PASS" if not is_default else "FAIL"
    if key != prev_key:
        print(f"{r['theme']:<20} {r['mode']:<6} {r['panel']:<4} {primary:<20} {card_bg:<25} {status}")
        prev_key = key
    else:
        print(f"{'':20} {'':6} {r['panel']:<4} {primary:<20} {card_bg:<25} {status}")

# Check dark vs light differentiation
print("\n--- Dark/Light Mode Differentiation ---")
for theme in THEMES:
    light_vals = [r for r in results if r["theme"] == theme and r["mode"] == "light"]
    dark_vals = [r for r in results if r["theme"] == theme and r["mode"] == "dark"]
    if light_vals and dark_vals:
        lp = light_vals[0]["css"].get("--primary-color", "?")
        dp = dark_vals[0]["css"].get("--primary-color", "?")
        lb = light_vals[0]["css"].get("--primary-background-color", "?")
        db = dark_vals[0]["css"].get("--primary-background-color", "?")
        diff = "DIFFERENT" if (lp != dp or lb != db) else "SAME"
        print(f"  {theme}: light primary={lp}, dark primary={dp} | light bg={lb}, dark bg={db} -> {diff}")
