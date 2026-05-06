#!/bin/bash
# Theme Test Runner - Uses individual playwright-cli commands
# 3 themes × 2 modes × 4 panels = 24 tests

PROJDIR="/var/tmp/vibe-kanban/worktrees/1fe8-ha-permission-co/Woow_ha_permission&control"
cd "$PROJDIR"

SCREENSHOT_DIR="/tmp/ha-theme-test/screenshots"
RESULTS_FILE="/tmp/ha-theme-test/results.json"
mkdir -p "$SCREENSHOT_DIR"

echo "[" > "$RESULTS_FILE"
FIRST=true
TEST_COUNT=0

declare -a THEMES=("Woow" "Frosted Glass" "Google Theme")
declare -a MODES=("light" "dark")
declare -a PANEL_NAMES=("PM" "CP" "AC" "LC")
declare -a PANEL_URLS=("/ha_permission_manager" "/ha-control-panel" "/area-control" "/label-control")

# Function to set theme via eval
set_theme() {
  local theme="$1"
  local dark_bool="$2"  # true or false

  npx playwright-cli eval "() => {
    const ha = document.querySelector('home-assistant');
    if (!ha || !ha.hass) return 'no-hass';
    ha.hass.connection.sendMessage({
      type: 'frontend/set_user_data',
      key: 'core',
      value: { selectedTheme: { theme: '$theme', dark: $dark_bool }, selectedLanguage: null }
    });
    return 'theme-set: $theme ($dark_bool)';
  }" 2>&1 | grep "Result:" || echo "  (theme set command sent)"
}

# Function to extract CSS values
get_css() {
  npx playwright-cli --raw eval "() => {
    const result = {};
    const root = document.documentElement;
    const ha = document.querySelector('home-assistant');
    const props = ['--sidebar-background-color','--sidebar-selected-text-color','--ha-card-background','--primary-color','--primary-text-color','--primary-background-color','--card-background-color','--app-header-background-color'];
    for (const prop of props) {
      result[prop] = getComputedStyle(root).getPropertyValue(prop).trim()
        || (ha ? getComputedStyle(ha).getPropertyValue(prop).trim() : '') || '(not set)';
    }
    try {
      const sidebar = ha?.shadowRoot?.querySelector('ha-sidebar');
      const menu = sidebar?.shadowRoot?.querySelector('.menu');
      if (menu) result['_sidebar_actual_bg'] = getComputedStyle(menu).backgroundColor;
    } catch(e) {}
    return JSON.stringify(result);
  }" 2>&1
}

echo "======================================="
echo "Starting Theme UI Tests"
echo "3 themes × 2 modes × 4 panels = 24"
echo "======================================="

for theme in "${THEMES[@]}"; do
  for mode in "${MODES[@]}"; do
    DARK_BOOL="false"
    [ "$mode" = "dark" ] && DARK_BOOL="true"

    echo ""
    echo "=== Theme: $theme | Mode: $mode ==="

    # Set theme
    set_theme "$theme" "$DARK_BOOL"
    sleep 2

    # Reload to apply
    npx playwright-cli reload 2>&1 | head -3
    sleep 4

    for i in 0 1 2 3; do
      PNAME="${PANEL_NAMES[$i]}"
      PURL="${PANEL_URLS[$i]}"
      SAFE_THEME="${theme// /_}"
      FNAME="${SAFE_THEME}_${mode}_${PNAME}.png"

      echo -n "  $PNAME: "

      # Navigate
      npx playwright-cli goto "http://localhost:15124${PURL}" 2>&1 | head -1
      sleep 3

      # Screenshot
      npx playwright-cli screenshot --filename="$SCREENSHOT_DIR/$FNAME" 2>&1 | head -1

      # Get CSS
      CSS_JSON=$(get_css)

      # Parse key values with python
      PRIMARY=$(echo "$CSS_JSON" | python3 -c "
import sys,json
try:
    d=json.loads(sys.stdin.read())
    print(d.get('--primary-color','?'))
except:
    print('?')
" 2>/dev/null)

      CARD_BG=$(echo "$CSS_JSON" | python3 -c "
import sys,json
try:
    d=json.loads(sys.stdin.read())
    v = d.get('--ha-card-background','') or d.get('--card-background-color','?')
    print(v)
except:
    print('?')
" 2>/dev/null)

      SIDEBAR_BG=$(echo "$CSS_JSON" | python3 -c "
import sys,json
try:
    d=json.loads(sys.stdin.read())
    print(d.get('--sidebar-background-color','?'))
except:
    print('?')
" 2>/dev/null)

      STATUS="OK"
      if [ "$PRIMARY" = "?" ] || [ "$PRIMARY" = "(not set)" ] || [ -z "$PRIMARY" ]; then
        STATUS="CHECK"
      fi
      echo "$STATUS | primary=$PRIMARY | card-bg=$CARD_BG | sidebar=$SIDEBAR_BG"

      # Append to results JSON
      if [ "$FIRST" = true ]; then
        FIRST=false
      else
        echo "," >> "$RESULTS_FILE"
      fi

      # Escape the CSS JSON for embedding
      ESCAPED_CSS=$(echo "$CSS_JSON" | python3 -c "
import sys,json
try:
    raw = sys.stdin.read().strip()
    d = json.loads(raw)
    print(json.dumps(d))
except:
    print('{}')
" 2>/dev/null)

      cat >> "$RESULTS_FILE" <<EOF
  {"theme":"${theme}","mode":"${mode}","panel":"${PNAME}","screenshot":"${FNAME}","css":${ESCAPED_CSS:-"{}"}}
EOF

      TEST_COUNT=$((TEST_COUNT + 1))
    done
  done
done

echo "" >> "$RESULTS_FILE"
echo "]" >> "$RESULTS_FILE"

echo ""
echo "======================================="
echo "Done. $TEST_COUNT tests completed."
echo "Screenshots: $SCREENSHOT_DIR"
echo "Results: $RESULTS_FILE"
echo "======================================="
