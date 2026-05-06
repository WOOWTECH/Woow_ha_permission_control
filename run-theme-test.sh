#!/bin/bash
# Theme Test Orchestrator
# Runs 3 themes × 2 modes × 4 panels = 24 tests via playwright-cli

set -e
cd "/var/tmp/vibe-kanban/worktrees/1fe8-ha-permission-co/Woow_ha_permission&control"

SCREENSHOT_DIR="/tmp/ha-theme-test/screenshots"
RESULTS_FILE="/tmp/ha-theme-test/results.json"
mkdir -p "$SCREENSHOT_DIR"

# Initialize results array
echo "[" > "$RESULTS_FILE"
FIRST=true

THEMES=("Woow" "Frosted Glass" "Google Theme")
MODES=("light" "dark")
PANEL_NAMES=("PM" "CP" "AC" "LC")
PANEL_URLS=("/ha_permission_manager" "/ha-control-panel" "/area-control" "/label-control")

CSS_PROPS='["--sidebar-background-color","--sidebar-selected-text-color","--ha-card-background","--primary-color","--primary-text-color","--primary-background-color","--card-background-color","--app-header-background-color"]'

for theme in "${THEMES[@]}"; do
  for mode in "${MODES[@]}"; do
    echo ""
    echo "=== Setting theme: $theme | mode: $mode ==="

    # Set theme via eval
    DARK_VAL="false"
    if [ "$mode" = "dark" ]; then
      DARK_VAL="true"
    fi

    npx playwright-cli eval "async () => {
      const ha = document.querySelector('home-assistant');
      if (!ha || !ha.hass) return 'no-hass';
      const conn = ha.hass.connection;
      await conn.sendMessage({
        type: 'frontend/set_user_data',
        key: 'core',
        value: { selectedTheme: { theme: '${theme}', dark: ${DARK_VAL} }, selectedLanguage: null }
      });
      return 'theme-set';
    }" 2>&1 | grep -E "Result|Error" || true

    sleep 2

    # Reload page to ensure theme fully applied
    npx playwright-cli reload 2>&1 | head -3
    sleep 4

    for i in 0 1 2 3; do
      PNAME="${PANEL_NAMES[$i]}"
      PURL="${PANEL_URLS[$i]}"
      FNAME="${theme// /_}_${mode}_${PNAME}.png"

      echo "  Testing: $PNAME ($PURL)"

      # Navigate to panel
      npx playwright-cli goto "http://localhost:15124${PURL}" 2>&1 | head -3
      sleep 3

      # Screenshot
      npx playwright-cli screenshot --filename="$SCREENSHOT_DIR/$FNAME" 2>&1 | head -2

      # Extract CSS values
      CSS_JSON=$(npx playwright-cli --raw eval "(props) => {
        const result = {};
        const root = document.documentElement;
        const ha = document.querySelector('home-assistant');
        for (const prop of props) {
          const val = getComputedStyle(root).getPropertyValue(prop).trim()
            || (ha ? getComputedStyle(ha).getPropertyValue(prop).trim() : '');
          result[prop] = val || '(not set)';
        }
        try {
          if (ha && ha.shadowRoot) {
            const sidebar = ha.shadowRoot.querySelector('ha-sidebar');
            if (sidebar && sidebar.shadowRoot) {
              const menu = sidebar.shadowRoot.querySelector('.menu');
              if (menu) result['_sidebar_actual_bg'] = getComputedStyle(menu).backgroundColor;
            }
          }
        } catch(e) {}
        return JSON.stringify(result);
      }" "$CSS_PROPS" 2>&1)

      # Write result entry
      if [ "$FIRST" = true ]; then
        FIRST=false
      else
        echo "," >> "$RESULTS_FILE"
      fi

      cat >> "$RESULTS_FILE" <<JSONEOF
  {
    "theme": "${theme}",
    "mode": "${mode}",
    "panel": "${PNAME}",
    "screenshot": "${FNAME}",
    "css_raw": ${CSS_JSON:-"{}"}
  }
JSONEOF

      PRIMARY=$(echo "$CSS_JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('--primary-color','?'))" 2>/dev/null || echo "?")
      CARD_BG=$(echo "$CSS_JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('--ha-card-background','') or d.get('--card-background-color','?'))" 2>/dev/null || echo "?")

      STATUS="OK"
      if [ "$PRIMARY" = "?" ] || [ "$PRIMARY" = "(not set)" ]; then
        STATUS="CHECK"
      fi
      echo "    $STATUS | primary=$PRIMARY | card-bg=$CARD_BG"
    done
  done
done

echo "" >> "$RESULTS_FILE"
echo "]" >> "$RESULTS_FILE"

echo ""
echo "=== Done. 24 tests completed. ==="
echo "Screenshots: $SCREENSHOT_DIR"
echo "Results: $RESULTS_FILE"
