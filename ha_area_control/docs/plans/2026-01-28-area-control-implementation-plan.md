# Area Control Panel - Home Dashboard Style Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite Area Control frontend to match native HA Home Dashboard with tall tiles, embedded controls, and hybrid home view.

**Architecture:** Single-file LitElement frontend with three main views (HomeView, AreaDetailView, DomainFilterView). Uses existing WebSocket APIs. All entity tiles share base class with domain-specific control rendering.

**Tech Stack:** LitElement (from HA), CSS-in-JS, HA WebSocket API, Material Design Icons

---

## Task 1: Setup Base Structure and Constants

**Files:**
- Replace: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Write base file structure with imports and constants**

```javascript
// Home Assistant Native Style - Area Control Panel
// Matches HA Home Dashboard design with tall tiles and embedded controls

const { LitElement, html, css } = await import(
  "/frontend_latest/frontend.js"
).catch(() => {
  return import("https://unpkg.com/lit@2.8.0/index.js?module");
});

// ============================================================================
// DESIGN TOKENS - HA Native Style
// ============================================================================

const DOMAIN_COLORS = {
  light: "#FFB300",
  switch: "#FFB300",
  input_boolean: "#FFB300",
  fan: "#009688",
  climate: "#FF9800",
  climate_cool: "#2196F3",
  cover: "#9C27B0",
  lock: "#4CAF50",
  lock_unlocked: "#F44336",
  vacuum: "#009688",
  media_player: "#673AB7",
  humidifier: "#00BCD4",
  automation: "#2196F3",
  script: "#2196F3",
  scene: "#E91E63",
  sensor: "#607D8B",
  binary_sensor: "#607D8B",
  button: "#FF9800",
  person: "#4CAF50",
  person_away: "#9E9E9E",
};

const DOMAIN_ICONS = {
  light: "mdi:lightbulb",
  switch: "mdi:toggle-switch",
  input_boolean: "mdi:toggle-switch-outline",
  fan: "mdi:fan",
  climate: "mdi:thermostat",
  cover: "mdi:window-shutter",
  lock: "mdi:lock",
  vacuum: "mdi:robot-vacuum",
  media_player: "mdi:cast",
  humidifier: "mdi:air-humidifier",
  automation: "mdi:robot",
  script: "mdi:script-text",
  scene: "mdi:palette",
  sensor: "mdi:eye",
  binary_sensor: "mdi:checkbox-marked-circle",
  button: "mdi:gesture-tap-button",
  person: "mdi:account",
};

const DOMAIN_LABELS = {
  light: "燈光",
  switch: "開關",
  input_boolean: "開關",
  fan: "風扇",
  climate: "溫控",
  cover: "窗簾",
  lock: "門鎖",
  vacuum: "掃地機",
  media_player: "媒體播放器",
  humidifier: "加濕器",
  automation: "自動化",
  script: "腳本",
  scene: "場景",
  sensor: "感測器",
  binary_sensor: "二元感測器",
  button: "按鈕",
  person: "人員",
};

// Domains that show in summary section
const SUMMARY_DOMAINS = [
  "light",
  "climate",
  "cover",
  "fan",
  "media_player",
  "lock",
  "vacuum",
  "switch",
];

// Domains that can be toggled
const TOGGLEABLE_DOMAINS = [
  "light",
  "switch",
  "input_boolean",
  "fan",
  "climate",
  "humidifier",
  "automation",
  "lock",
  "vacuum",
  "media_player",
];
```

**Step 2: Verify file saved correctly**

Run: `head -80 /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`
Expected: Shows the constants defined above

**Step 3: Commit**

```bash
cd /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): setup base structure with HA native style constants"
```

---

## Task 2: Create Base Tile Component

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add BaseTile class after constants**

```javascript
// ============================================================================
// BASE TILE COMPONENT
// ============================================================================

class BaseTile extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      entityId: { type: String, attribute: "entity-id" },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }

      .tile {
        background: var(--tile-bg, rgba(255, 255, 255, 0.05));
        border-radius: 12px;
        padding: 12px;
        min-height: 120px;
        display: flex;
        flex-direction: column;
        cursor: pointer;
        transition: background-color 0.2s ease, transform 0.1s ease;
        position: relative;
        overflow: hidden;
      }

      .tile:hover {
        background: var(--tile-bg-hover, rgba(255, 255, 255, 0.08));
      }

      .tile:active {
        transform: scale(0.98);
      }

      .tile.on {
        background: var(--tile-color-bg, rgba(255, 179, 0, 0.2));
      }

      .tile.unavailable {
        opacity: 0.5;
      }

      .tile-header {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        flex: 0 0 auto;
      }

      .tile-icon {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--icon-bg, rgba(255, 255, 255, 0.1));
        color: var(--icon-color, #9e9e9e);
        flex-shrink: 0;
      }

      .tile.on .tile-icon {
        background: var(--tile-color-bg, rgba(255, 179, 0, 0.3));
        color: var(--tile-color, #ffb300);
      }

      .tile-icon ha-icon {
        --mdc-icon-size: 20px;
      }

      .tile-info {
        flex: 1;
        min-width: 0;
      }

      .tile-name {
        font-size: 14px;
        font-weight: 500;
        color: var(--primary-text-color, #fff);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .tile-state {
        font-size: 12px;
        color: var(--secondary-text-color, rgba(255, 255, 255, 0.7));
        margin-top: 2px;
      }

      .tile-controls {
        flex: 1;
        display: flex;
        align-items: flex-end;
        padding-top: 8px;
      }
    `;
  }

  get entity() {
    return this.hass?.states?.[this.entityId];
  }

  get isOn() {
    const state = this.entity?.state;
    return state === "on" || state === "playing" || state === "open" || state === "unlocked";
  }

  get isUnavailable() {
    return this.entity?.state === "unavailable" || !this.entity;
  }

  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    const state = this.entity?.state;
    if (state === "on") return "開啟";
    if (state === "off") return "關閉";
    if (state === "unavailable") return "無法使用";
    return state;
  }

  get icon() {
    const domain = this.entityId?.split(".")[0];
    return this.entity?.attributes?.icon || DOMAIN_ICONS[domain] || "mdi:help-circle";
  }

  get tileColor() {
    const domain = this.entityId?.split(".")[0];

    // For RGB lights, use actual color
    if (domain === "light" && this.isOn) {
      const rgb = this.entity?.attributes?.rgb_color;
      if (rgb) {
        return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
      }
    }

    // Climate: use blue for cooling, orange for heating
    if (domain === "climate" && this.isOn) {
      const hvacAction = this.entity?.attributes?.hvac_action;
      if (hvacAction === "cooling") return DOMAIN_COLORS.climate_cool;
    }

    // Lock: use green for locked, red for unlocked
    if (domain === "lock") {
      return this.entity?.state === "locked"
        ? DOMAIN_COLORS.lock
        : DOMAIN_COLORS.lock_unlocked;
    }

    return DOMAIN_COLORS[domain] || "#9E9E9E";
  }

  toggle() {
    if (this.isUnavailable) return;
    const domain = this.entityId?.split(".")[0];

    if (domain === "scene" || domain === "script") {
      this.hass.callService(domain, "turn_on", { entity_id: this.entityId });
    } else if (domain === "button") {
      this.hass.callService("button", "press", { entity_id: this.entityId });
    } else if (domain === "lock") {
      const service = this.entity?.state === "locked" ? "unlock" : "lock";
      this.hass.callService("lock", service, { entity_id: this.entityId });
    } else if (TOGGLEABLE_DOMAINS.includes(domain)) {
      this.hass.callService("homeassistant", "toggle", { entity_id: this.entityId });
    }
  }

  openMoreInfo() {
    const event = new CustomEvent("hass-more-info", {
      bubbles: true,
      composed: true,
      detail: { entityId: this.entityId },
    });
    this.dispatchEvent(event);
  }

  handleClick(e) {
    e.stopPropagation();
    this.toggle();
  }

  handleLongPress(e) {
    e.preventDefault();
    this.openMoreInfo();
  }

  connectedCallback() {
    super.connectedCallback();
    this._longPressTimer = null;
    this.addEventListener("touchstart", this._handleTouchStart.bind(this));
    this.addEventListener("touchend", this._handleTouchEnd.bind(this));
    this.addEventListener("touchcancel", this._handleTouchEnd.bind(this));
  }

  _handleTouchStart(e) {
    this._longPressTimer = setTimeout(() => {
      this.openMoreInfo();
      this._longPressTimer = null;
    }, 500);
  }

  _handleTouchEnd(e) {
    if (this._longPressTimer) {
      clearTimeout(this._longPressTimer);
      this._longPressTimer = null;
    }
  }

  renderControls() {
    // Override in subclasses
    return html``;
  }

  render() {
    const entity = this.entity;
    if (!entity && !this.entityId) return html``;

    const color = this.tileColor;
    const colorRgb = this._hexToRgb(color);

    return html`
      <div
        class="tile ${this.isOn ? "on" : ""} ${this.isUnavailable ? "unavailable" : ""}"
        style="--tile-color: ${color}; --tile-color-bg: rgba(${colorRgb}, 0.2); --icon-bg: rgba(${colorRgb}, 0.1);"
        @click=${this.handleClick}
        @contextmenu=${this.handleLongPress}
      >
        <div class="tile-header">
          <div class="tile-icon">
            <ha-icon icon=${this.icon}></ha-icon>
          </div>
          <div class="tile-info">
            <div class="tile-name">${entity?.attributes?.friendly_name || this.entityId}</div>
            <div class="tile-state">${this.stateDisplay}</div>
          </div>
        </div>
        <div class="tile-controls">${this.renderControls()}</div>
      </div>
    `;
  }

  _hexToRgb(hex) {
    if (hex.startsWith("rgb")) {
      // Already rgb format
      const match = hex.match(/\d+/g);
      return match ? match.slice(0, 3).join(", ") : "255, 255, 255";
    }
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result
      ? `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`
      : "255, 255, 255";
  }
}

customElements.define("base-tile", BaseTile);
```

**Step 2: Verify BaseTile added**

Run: `grep -n "class BaseTile" /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`
Expected: Shows line number where BaseTile is defined

**Step 3: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add BaseTile component with HA native styling"
```

---

## Task 3: Create Light Tile with Brightness Slider

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add LightTile class after BaseTile**

```javascript
// ============================================================================
// LIGHT TILE - with brightness slider
// ============================================================================

class LightTile extends BaseTile {
  static get styles() {
    return [
      super.styles,
      css`
        .slider-container {
          width: 100%;
          height: 24px;
          position: relative;
        }

        .slider-track {
          width: 100%;
          height: 100%;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          overflow: hidden;
          position: relative;
        }

        .slider-fill {
          height: 100%;
          background: var(--tile-color, #ffb300);
          border-radius: 12px;
          transition: width 0.1s ease;
        }

        .slider-input {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          opacity: 0;
          cursor: pointer;
          margin: 0;
        }

        .tile.off .slider-fill {
          background: rgba(255, 255, 255, 0.3);
        }

        .brightness-value {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 11px;
          color: var(--primary-text-color, #fff);
          pointer-events: none;
        }
      `,
    ];
  }

  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    if (!this.isOn) return "關閉";
    const brightness = this.entity?.attributes?.brightness;
    if (brightness) {
      return `${Math.round((brightness / 255) * 100)}%`;
    }
    return "開啟";
  }

  get brightnessPercent() {
    const brightness = this.entity?.attributes?.brightness || 0;
    return Math.round((brightness / 255) * 100);
  }

  handleSliderChange(e) {
    e.stopPropagation();
    const value = parseInt(e.target.value);
    const brightness = Math.round((value / 100) * 255);

    if (value === 0) {
      this.hass.callService("light", "turn_off", { entity_id: this.entityId });
    } else {
      this.hass.callService("light", "turn_on", {
        entity_id: this.entityId,
        brightness: brightness,
      });
    }
  }

  handleSliderClick(e) {
    e.stopPropagation();
  }

  renderControls() {
    const percent = this.brightnessPercent;

    return html`
      <div class="slider-container" @click=${this.handleSliderClick}>
        <div class="slider-track">
          <div class="slider-fill" style="width: ${this.isOn ? percent : 0}%"></div>
        </div>
        <input
          type="range"
          class="slider-input"
          min="0"
          max="100"
          .value=${percent}
          @input=${this.handleSliderChange}
          @click=${this.handleSliderClick}
        />
        ${this.isOn ? html`<span class="brightness-value">${percent}%</span>` : ""}
      </div>
    `;
  }
}

customElements.define("light-tile", LightTile);
```

**Step 2: Verify LightTile added**

Run: `grep -n "class LightTile" /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`
Expected: Shows line number

**Step 3: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add LightTile with brightness slider"
```

---

## Task 4: Create Climate Tile with Temperature Controls

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add ClimateTile class**

```javascript
// ============================================================================
// CLIMATE TILE - with temperature +/- buttons
// ============================================================================

class ClimateTile extends BaseTile {
  static get styles() {
    return [
      super.styles,
      css`
        .climate-controls {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          gap: 8px;
        }

        .temp-button {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          color: var(--primary-text-color, #fff);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.2s ease;
        }

        .temp-button:hover {
          background: rgba(255, 255, 255, 0.2);
        }

        .temp-button:active {
          background: rgba(255, 255, 255, 0.3);
        }

        .temp-button ha-icon {
          --mdc-icon-size: 18px;
        }

        .temp-display {
          font-size: 18px;
          font-weight: 500;
          color: var(--primary-text-color, #fff);
        }

        .temp-display .unit {
          font-size: 12px;
          color: var(--secondary-text-color, rgba(255, 255, 255, 0.7));
        }
      `,
    ];
  }

  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    const state = this.entity?.state;
    if (state === "off") return "關閉";
    const currentTemp = this.entity?.attributes?.current_temperature;
    if (currentTemp) return `${currentTemp}°C`;
    return state;
  }

  get targetTemp() {
    return this.entity?.attributes?.temperature || 22;
  }

  adjustTemp(delta) {
    const newTemp = this.targetTemp + delta;
    const minTemp = this.entity?.attributes?.min_temp || 16;
    const maxTemp = this.entity?.attributes?.max_temp || 30;

    if (newTemp >= minTemp && newTemp <= maxTemp) {
      this.hass.callService("climate", "set_temperature", {
        entity_id: this.entityId,
        temperature: newTemp,
      });
    }
  }

  handleTempDown(e) {
    e.stopPropagation();
    this.adjustTemp(-0.5);
  }

  handleTempUp(e) {
    e.stopPropagation();
    this.adjustTemp(0.5);
  }

  renderControls() {
    if (!this.isOn) return html``;

    return html`
      <div class="climate-controls">
        <button class="temp-button" @click=${this.handleTempDown}>
          <ha-icon icon="mdi:minus"></ha-icon>
        </button>
        <div class="temp-display">
          ${this.targetTemp}<span class="unit">°C</span>
        </div>
        <button class="temp-button" @click=${this.handleTempUp}>
          <ha-icon icon="mdi:plus"></ha-icon>
        </button>
      </div>
    `;
  }
}

customElements.define("climate-tile", ClimateTile);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add ClimateTile with temperature controls"
```

---

## Task 5: Create Cover Tile with Up/Stop/Down Buttons

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add CoverTile class**

```javascript
// ============================================================================
// COVER TILE - with up/stop/down buttons
// ============================================================================

class CoverTile extends BaseTile {
  static get styles() {
    return [
      super.styles,
      css`
        .cover-controls {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          gap: 8px;
        }

        .cover-button {
          width: 40px;
          height: 32px;
          border-radius: 8px;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          color: var(--primary-text-color, #fff);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.2s ease;
        }

        .cover-button:hover {
          background: rgba(255, 255, 255, 0.2);
        }

        .cover-button:active {
          background: rgba(255, 255, 255, 0.3);
        }

        .cover-button ha-icon {
          --mdc-icon-size: 18px;
        }
      `,
    ];
  }

  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    const state = this.entity?.state;
    const position = this.entity?.attributes?.current_position;
    if (position !== undefined) {
      if (position === 0) return "關閉";
      if (position === 100) return "開啟";
      return `${position}%`;
    }
    if (state === "open") return "開啟";
    if (state === "closed") return "關閉";
    if (state === "opening") return "正在開啟";
    if (state === "closing") return "正在關閉";
    return state;
  }

  handleOpen(e) {
    e.stopPropagation();
    this.hass.callService("cover", "open_cover", { entity_id: this.entityId });
  }

  handleStop(e) {
    e.stopPropagation();
    this.hass.callService("cover", "stop_cover", { entity_id: this.entityId });
  }

  handleClose(e) {
    e.stopPropagation();
    this.hass.callService("cover", "close_cover", { entity_id: this.entityId });
  }

  toggle() {
    // Override toggle to do nothing - use buttons instead
  }

  renderControls() {
    return html`
      <div class="cover-controls">
        <button class="cover-button" @click=${this.handleOpen}>
          <ha-icon icon="mdi:arrow-up"></ha-icon>
        </button>
        <button class="cover-button" @click=${this.handleStop}>
          <ha-icon icon="mdi:stop"></ha-icon>
        </button>
        <button class="cover-button" @click=${this.handleClose}>
          <ha-icon icon="mdi:arrow-down"></ha-icon>
        </button>
      </div>
    `;
  }
}

customElements.define("cover-tile", CoverTile);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add CoverTile with up/stop/down buttons"
```

---

## Task 6: Create Fan Tile with Speed Slider

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add FanTile class**

```javascript
// ============================================================================
// FAN TILE - with speed slider
// ============================================================================

class FanTile extends BaseTile {
  static get styles() {
    return [
      super.styles,
      css`
        .slider-container {
          width: 100%;
          height: 24px;
          position: relative;
        }

        .slider-track {
          width: 100%;
          height: 100%;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          overflow: hidden;
        }

        .slider-fill {
          height: 100%;
          background: var(--tile-color, #009688);
          border-radius: 12px;
          transition: width 0.1s ease;
        }

        .slider-input {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          opacity: 0;
          cursor: pointer;
          margin: 0;
        }

        .speed-value {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 11px;
          color: var(--primary-text-color, #fff);
          pointer-events: none;
        }

        .tile-icon.spinning ha-icon {
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `,
    ];
  }

  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    if (!this.isOn) return "關閉";
    const percentage = this.entity?.attributes?.percentage;
    if (percentage) return `${percentage}%`;
    return "開啟";
  }

  get speedPercent() {
    return this.entity?.attributes?.percentage || 0;
  }

  handleSliderChange(e) {
    e.stopPropagation();
    const value = parseInt(e.target.value);

    if (value === 0) {
      this.hass.callService("fan", "turn_off", { entity_id: this.entityId });
    } else {
      this.hass.callService("fan", "set_percentage", {
        entity_id: this.entityId,
        percentage: value,
      });
    }
  }

  handleSliderClick(e) {
    e.stopPropagation();
  }

  render() {
    const entity = this.entity;
    if (!entity && !this.entityId) return html``;

    const color = this.tileColor;
    const colorRgb = this._hexToRgb(color);

    return html`
      <div
        class="tile ${this.isOn ? "on" : ""} ${this.isUnavailable ? "unavailable" : ""}"
        style="--tile-color: ${color}; --tile-color-bg: rgba(${colorRgb}, 0.2); --icon-bg: rgba(${colorRgb}, 0.1);"
        @click=${this.handleClick}
        @contextmenu=${this.handleLongPress}
      >
        <div class="tile-header">
          <div class="tile-icon ${this.isOn ? "spinning" : ""}">
            <ha-icon icon=${this.icon}></ha-icon>
          </div>
          <div class="tile-info">
            <div class="tile-name">${entity?.attributes?.friendly_name || this.entityId}</div>
            <div class="tile-state">${this.stateDisplay}</div>
          </div>
        </div>
        <div class="tile-controls">${this.renderControls()}</div>
      </div>
    `;
  }

  renderControls() {
    const percent = this.speedPercent;

    return html`
      <div class="slider-container" @click=${this.handleSliderClick}>
        <div class="slider-track">
          <div class="slider-fill" style="width: ${this.isOn ? percent : 0}%"></div>
        </div>
        <input
          type="range"
          class="slider-input"
          min="0"
          max="100"
          .value=${percent}
          @input=${this.handleSliderChange}
          @click=${this.handleSliderClick}
        />
        ${this.isOn ? html`<span class="speed-value">${percent}%</span>` : ""}
      </div>
    `;
  }
}

customElements.define("fan-tile", FanTile);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add FanTile with speed slider and spinning animation"
```

---

## Task 7: Create Media Player Tile

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add MediaPlayerTile class**

```javascript
// ============================================================================
// MEDIA PLAYER TILE - with playback controls
// ============================================================================

class MediaPlayerTile extends BaseTile {
  static get styles() {
    return [
      super.styles,
      css`
        .media-controls {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          gap: 4px;
        }

        .media-button {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          color: var(--primary-text-color, #fff);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.2s ease;
        }

        .media-button:hover {
          background: rgba(255, 255, 255, 0.2);
        }

        .media-button.play-pause {
          width: 44px;
          height: 44px;
          background: var(--tile-color, #673ab7);
        }

        .media-button.play-pause:hover {
          opacity: 0.9;
        }

        .media-button ha-icon {
          --mdc-icon-size: 18px;
        }

        .media-button.play-pause ha-icon {
          --mdc-icon-size: 22px;
        }
      `,
    ];
  }

  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    const state = this.entity?.state;
    if (state === "playing") return "播放中";
    if (state === "paused") return "暫停";
    if (state === "idle") return "閒置";
    if (state === "off") return "關閉";
    return state;
  }

  get isPlaying() {
    return this.entity?.state === "playing";
  }

  handlePrev(e) {
    e.stopPropagation();
    this.hass.callService("media_player", "media_previous_track", {
      entity_id: this.entityId,
    });
  }

  handlePlayPause(e) {
    e.stopPropagation();
    this.hass.callService("media_player", "media_play_pause", {
      entity_id: this.entityId,
    });
  }

  handleNext(e) {
    e.stopPropagation();
    this.hass.callService("media_player", "media_next_track", {
      entity_id: this.entityId,
    });
  }

  toggle() {
    this.hass.callService("media_player", "media_play_pause", {
      entity_id: this.entityId,
    });
  }

  renderControls() {
    return html`
      <div class="media-controls">
        <button class="media-button" @click=${this.handlePrev}>
          <ha-icon icon="mdi:skip-previous"></ha-icon>
        </button>
        <button class="media-button play-pause" @click=${this.handlePlayPause}>
          <ha-icon icon=${this.isPlaying ? "mdi:pause" : "mdi:play"}></ha-icon>
        </button>
        <button class="media-button" @click=${this.handleNext}>
          <ha-icon icon="mdi:skip-next"></ha-icon>
        </button>
      </div>
    `;
  }
}

customElements.define("media-player-tile", MediaPlayerTile);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add MediaPlayerTile with playback controls"
```

---

## Task 8: Create Lock Tile

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add LockTile class**

```javascript
// ============================================================================
// LOCK TILE - with lock/unlock buttons
// ============================================================================

class LockTile extends BaseTile {
  static get styles() {
    return [
      super.styles,
      css`
        .lock-controls {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          gap: 8px;
        }

        .lock-button {
          flex: 1;
          height: 36px;
          border-radius: 18px;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          color: var(--primary-text-color, #fff);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          font-size: 12px;
          transition: background 0.2s ease;
        }

        .lock-button:hover {
          background: rgba(255, 255, 255, 0.2);
        }

        .lock-button.active {
          background: var(--tile-color, #4caf50);
          color: #fff;
        }

        .lock-button ha-icon {
          --mdc-icon-size: 16px;
        }
      `,
    ];
  }

  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    const state = this.entity?.state;
    if (state === "locked") return "已鎖定";
    if (state === "unlocked") return "已解鎖";
    if (state === "locking") return "鎖定中";
    if (state === "unlocking") return "解鎖中";
    return state;
  }

  get isLocked() {
    return this.entity?.state === "locked";
  }

  handleLock(e) {
    e.stopPropagation();
    this.hass.callService("lock", "lock", { entity_id: this.entityId });
  }

  handleUnlock(e) {
    e.stopPropagation();
    this.hass.callService("lock", "unlock", { entity_id: this.entityId });
  }

  renderControls() {
    return html`
      <div class="lock-controls">
        <button
          class="lock-button ${this.isLocked ? "active" : ""}"
          @click=${this.handleLock}
        >
          <ha-icon icon="mdi:lock"></ha-icon>
          鎖定
        </button>
        <button
          class="lock-button ${!this.isLocked ? "active" : ""}"
          @click=${this.handleUnlock}
        >
          <ha-icon icon="mdi:lock-open"></ha-icon>
          解鎖
        </button>
      </div>
    `;
  }
}

customElements.define("lock-tile", LockTile);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add LockTile with lock/unlock buttons"
```

---

## Task 9: Create Vacuum Tile

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add VacuumTile class**

```javascript
// ============================================================================
// VACUUM TILE - with start/pause/return buttons
// ============================================================================

class VacuumTile extends BaseTile {
  static get styles() {
    return [
      super.styles,
      css`
        .vacuum-controls {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          gap: 8px;
        }

        .vacuum-button {
          width: 40px;
          height: 32px;
          border-radius: 8px;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          color: var(--primary-text-color, #fff);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.2s ease;
        }

        .vacuum-button:hover {
          background: rgba(255, 255, 255, 0.2);
        }

        .vacuum-button.active {
          background: var(--tile-color, #009688);
        }

        .vacuum-button ha-icon {
          --mdc-icon-size: 18px;
        }
      `,
    ];
  }

  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    const state = this.entity?.state;
    if (state === "cleaning") return "清掃中";
    if (state === "docked") return "充電中";
    if (state === "returning") return "返回中";
    if (state === "paused") return "暫停";
    if (state === "idle") return "閒置";
    if (state === "error") return "錯誤";
    return state;
  }

  get isCleaning() {
    return this.entity?.state === "cleaning";
  }

  handleStart(e) {
    e.stopPropagation();
    this.hass.callService("vacuum", "start", { entity_id: this.entityId });
  }

  handlePause(e) {
    e.stopPropagation();
    this.hass.callService("vacuum", "pause", { entity_id: this.entityId });
  }

  handleReturn(e) {
    e.stopPropagation();
    this.hass.callService("vacuum", "return_to_base", { entity_id: this.entityId });
  }

  renderControls() {
    return html`
      <div class="vacuum-controls">
        <button
          class="vacuum-button ${this.isCleaning ? "active" : ""}"
          @click=${this.handleStart}
        >
          <ha-icon icon="mdi:play"></ha-icon>
        </button>
        <button class="vacuum-button" @click=${this.handlePause}>
          <ha-icon icon="mdi:pause"></ha-icon>
        </button>
        <button class="vacuum-button" @click=${this.handleReturn}>
          <ha-icon icon="mdi:home"></ha-icon>
        </button>
      </div>
    `;
  }
}

customElements.define("vacuum-tile", VacuumTile);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add VacuumTile with start/pause/return buttons"
```

---

## Task 10: Create Scene Tile

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add SceneTile class**

```javascript
// ============================================================================
// SCENE TILE - with last triggered time
// ============================================================================

class SceneTile extends BaseTile {
  static get styles() {
    return [
      super.styles,
      css`
        .scene-info {
          width: 100%;
          text-align: center;
          font-size: 11px;
          color: var(--secondary-text-color, rgba(255, 255, 255, 0.5));
        }
      `,
    ];
  }

  get stateDisplay() {
    return "";  // Don't show state for scenes
  }

  get lastTriggered() {
    const lastChanged = this.entity?.last_changed;
    if (!lastChanged) return "";

    const date = new Date(lastChanged);
    const now = new Date();
    const diff = now - date;

    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return "剛剛";
    if (minutes < 60) return `${minutes} 分鐘前`;
    if (hours < 24) return `${hours} 小時前`;
    return `${days} 天前`;
  }

  toggle() {
    this.hass.callService("scene", "turn_on", { entity_id: this.entityId });
  }

  renderControls() {
    const lastTriggered = this.lastTriggered;
    if (!lastTriggered) return html``;

    return html`
      <div class="scene-info">${lastTriggered}</div>
    `;
  }
}

customElements.define("scene-tile", SceneTile);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add SceneTile with last triggered time"
```

---

## Task 11: Create Simple Tiles (Switch, Sensor, Button)

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add SwitchTile, SensorTile, ButtonTile classes**

```javascript
// ============================================================================
// SWITCH TILE - simple toggle
// ============================================================================

class SwitchTile extends BaseTile {
  // Uses base implementation - no extra controls needed
}

customElements.define("switch-tile", SwitchTile);

// ============================================================================
// SENSOR TILE - display only
// ============================================================================

class SensorTile extends BaseTile {
  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    const state = this.entity?.state;
    const unit = this.entity?.attributes?.unit_of_measurement;
    return unit ? `${state} ${unit}` : state;
  }

  toggle() {
    // Sensors don't toggle, open more-info instead
    this.openMoreInfo();
  }
}

customElements.define("sensor-tile", SensorTile);

// ============================================================================
// BINARY SENSOR TILE - display only
// ============================================================================

class BinarySensorTile extends BaseTile {
  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    const state = this.entity?.state;
    const deviceClass = this.entity?.attributes?.device_class;

    if (deviceClass === "door") return state === "on" ? "開啟" : "關閉";
    if (deviceClass === "window") return state === "on" ? "開啟" : "關閉";
    if (deviceClass === "motion") return state === "on" ? "偵測到" : "無動作";
    if (deviceClass === "occupancy") return state === "on" ? "有人" : "無人";

    return state === "on" ? "開啟" : "關閉";
  }

  toggle() {
    this.openMoreInfo();
  }
}

customElements.define("binary-sensor-tile", BinarySensorTile);

// ============================================================================
// BUTTON TILE - press action
// ============================================================================

class ButtonTile extends BaseTile {
  get stateDisplay() {
    return "";  // Buttons don't have meaningful state
  }

  toggle() {
    this.hass.callService("button", "press", { entity_id: this.entityId });
  }
}

customElements.define("button-tile", ButtonTile);

// ============================================================================
// SCRIPT TILE - with last triggered
// ============================================================================

class ScriptTile extends SceneTile {
  toggle() {
    this.hass.callService("script", "turn_on", { entity_id: this.entityId });
  }
}

customElements.define("script-tile", ScriptTile);

// ============================================================================
// AUTOMATION TILE
// ============================================================================

class AutomationTile extends SceneTile {
  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    return this.entity?.state === "on" ? "啟用" : "停用";
  }
}

customElements.define("automation-tile", AutomationTile);

// ============================================================================
// HUMIDIFIER TILE - with humidity slider
// ============================================================================

class HumidifierTile extends BaseTile {
  static get styles() {
    return [
      super.styles,
      css`
        .slider-container {
          width: 100%;
          height: 24px;
          position: relative;
        }

        .slider-track {
          width: 100%;
          height: 100%;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          overflow: hidden;
        }

        .slider-fill {
          height: 100%;
          background: var(--tile-color, #00bcd4);
          border-radius: 12px;
          transition: width 0.1s ease;
        }

        .slider-input {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          opacity: 0;
          cursor: pointer;
          margin: 0;
        }

        .humidity-value {
          position: absolute;
          right: 8px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 11px;
          color: var(--primary-text-color, #fff);
          pointer-events: none;
        }
      `,
    ];
  }

  get stateDisplay() {
    if (this.isUnavailable) return "無法使用";
    if (!this.isOn) return "關閉";
    const humidity = this.entity?.attributes?.humidity;
    if (humidity) return `${humidity}%`;
    return "開啟";
  }

  get humidityPercent() {
    return this.entity?.attributes?.humidity || 0;
  }

  handleSliderChange(e) {
    e.stopPropagation();
    const value = parseInt(e.target.value);

    this.hass.callService("humidifier", "set_humidity", {
      entity_id: this.entityId,
      humidity: value,
    });
  }

  handleSliderClick(e) {
    e.stopPropagation();
  }

  renderControls() {
    if (!this.isOn) return html``;

    const percent = this.humidityPercent;

    return html`
      <div class="slider-container" @click=${this.handleSliderClick}>
        <div class="slider-track">
          <div class="slider-fill" style="width: ${percent}%"></div>
        </div>
        <input
          type="range"
          class="slider-input"
          min="0"
          max="100"
          .value=${percent}
          @input=${this.handleSliderChange}
          @click=${this.handleSliderClick}
        />
        <span class="humidity-value">${percent}%</span>
      </div>
    `;
  }
}

customElements.define("humidifier-tile", HumidifierTile);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add Switch, Sensor, Button, Script, Automation, Humidifier tiles"
```

---

## Task 12: Create Tile Factory Function

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add tile factory function**

```javascript
// ============================================================================
// TILE FACTORY
// ============================================================================

function createTileElement(entityId) {
  const domain = entityId.split(".")[0];

  const tileMap = {
    light: "light-tile",
    climate: "climate-tile",
    cover: "cover-tile",
    fan: "fan-tile",
    media_player: "media-player-tile",
    lock: "lock-tile",
    vacuum: "vacuum-tile",
    scene: "scene-tile",
    script: "script-tile",
    automation: "automation-tile",
    switch: "switch-tile",
    input_boolean: "switch-tile",
    sensor: "sensor-tile",
    binary_sensor: "binary-sensor-tile",
    button: "button-tile",
    humidifier: "humidifier-tile",
  };

  const tagName = tileMap[domain] || "base-tile";
  return tagName;
}
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add tile factory function"
```

---

## Task 13: Create Domain Section Component

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add DomainSection component**

```javascript
// ============================================================================
// DOMAIN SECTION COMPONENT
// ============================================================================

class DomainSection extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      domain: { type: String },
      entities: { type: Array },
      expanded: { type: Boolean },
    };
  }

  constructor() {
    super();
    this.expanded = true;
  }

  static get styles() {
    return css`
      :host {
        display: block;
        margin-bottom: 16px;
      }

      .section-header {
        display: flex;
        align-items: center;
        padding: 8px 4px;
        cursor: pointer;
        user-select: none;
      }

      .section-header:hover {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 8px;
      }

      .section-icon {
        width: 24px;
        height: 24px;
        margin-right: 8px;
        color: var(--primary-text-color, #fff);
      }

      .section-icon ha-icon {
        --mdc-icon-size: 20px;
      }

      .section-title {
        flex: 1;
        font-size: 14px;
        font-weight: 500;
        color: var(--primary-text-color, #fff);
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .section-count {
        font-size: 12px;
        color: var(--secondary-text-color, rgba(255, 255, 255, 0.7));
        margin-right: 8px;
        background: rgba(255, 255, 255, 0.1);
        padding: 2px 8px;
        border-radius: 10px;
      }

      .section-arrow {
        color: var(--secondary-text-color, rgba(255, 255, 255, 0.7));
        transition: transform 0.2s ease;
      }

      .section-arrow.collapsed {
        transform: rotate(-90deg);
      }

      .section-arrow ha-icon {
        --mdc-icon-size: 20px;
      }

      .tiles-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 8px;
        padding-top: 8px;
      }

      @media (min-width: 600px) {
        .tiles-grid {
          grid-template-columns: repeat(3, 1fr);
        }
      }

      @media (min-width: 1024px) {
        .tiles-grid {
          grid-template-columns: repeat(4, 1fr);
        }
      }

      .tiles-grid.collapsed {
        display: none;
      }
    `;
  }

  toggleExpanded() {
    this.expanded = !this.expanded;
  }

  render() {
    const icon = DOMAIN_ICONS[this.domain] || "mdi:help-circle";
    const label = DOMAIN_LABELS[this.domain] || this.domain;
    const count = this.entities?.length || 0;

    return html`
      <div class="section-header" @click=${this.toggleExpanded}>
        <div class="section-icon">
          <ha-icon icon=${icon}></ha-icon>
        </div>
        <div class="section-title">${label}</div>
        <div class="section-count">${count}</div>
        <div class="section-arrow ${this.expanded ? "" : "collapsed"}">
          <ha-icon icon="mdi:chevron-down"></ha-icon>
        </div>
      </div>
      <div class="tiles-grid ${this.expanded ? "" : "collapsed"}">
        ${this.entities?.map((entityId) => {
          const tagName = createTileElement(entityId);
          return html`
            <${tagName}
              .hass=${this.hass}
              entity-id=${entityId}
            ></${tagName}>
          `;
        })}
      </div>
    `;
  }
}

customElements.define("domain-section", DomainSection);
```

**Step 2: Fix dynamic tag rendering (LitElement doesn't support dynamic tags directly)**

Replace the render method's tiles section with:

```javascript
  render() {
    const icon = DOMAIN_ICONS[this.domain] || "mdi:help-circle";
    const label = DOMAIN_LABELS[this.domain] || this.domain;
    const count = this.entities?.length || 0;

    return html`
      <div class="section-header" @click=${this.toggleExpanded}>
        <div class="section-icon">
          <ha-icon icon=${icon}></ha-icon>
        </div>
        <div class="section-title">${label}</div>
        <div class="section-count">${count}</div>
        <div class="section-arrow ${this.expanded ? "" : "collapsed"}">
          <ha-icon icon="mdi:chevron-down"></ha-icon>
        </div>
      </div>
      <div class="tiles-grid ${this.expanded ? "" : "collapsed"}">
        ${this.entities?.map((entityId) => this.renderTile(entityId))}
      </div>
    `;
  }

  renderTile(entityId) {
    const domain = entityId.split(".")[0];

    switch (domain) {
      case "light":
        return html`<light-tile .hass=${this.hass} entity-id=${entityId}></light-tile>`;
      case "climate":
        return html`<climate-tile .hass=${this.hass} entity-id=${entityId}></climate-tile>`;
      case "cover":
        return html`<cover-tile .hass=${this.hass} entity-id=${entityId}></cover-tile>`;
      case "fan":
        return html`<fan-tile .hass=${this.hass} entity-id=${entityId}></fan-tile>`;
      case "media_player":
        return html`<media-player-tile .hass=${this.hass} entity-id=${entityId}></media-player-tile>`;
      case "lock":
        return html`<lock-tile .hass=${this.hass} entity-id=${entityId}></lock-tile>`;
      case "vacuum":
        return html`<vacuum-tile .hass=${this.hass} entity-id=${entityId}></vacuum-tile>`;
      case "scene":
        return html`<scene-tile .hass=${this.hass} entity-id=${entityId}></scene-tile>`;
      case "script":
        return html`<script-tile .hass=${this.hass} entity-id=${entityId}></script-tile>`;
      case "automation":
        return html`<automation-tile .hass=${this.hass} entity-id=${entityId}></automation-tile>`;
      case "switch":
      case "input_boolean":
        return html`<switch-tile .hass=${this.hass} entity-id=${entityId}></switch-tile>`;
      case "sensor":
        return html`<sensor-tile .hass=${this.hass} entity-id=${entityId}></sensor-tile>`;
      case "binary_sensor":
        return html`<binary-sensor-tile .hass=${this.hass} entity-id=${entityId}></binary-sensor-tile>`;
      case "button":
        return html`<button-tile .hass=${this.hass} entity-id=${entityId}></button-tile>`;
      case "humidifier":
        return html`<humidifier-tile .hass=${this.hass} entity-id=${entityId}></humidifier-tile>`;
      default:
        return html`<base-tile .hass=${this.hass} entity-id=${entityId}></base-tile>`;
    }
  }
```

**Step 3: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add DomainSection component with collapsible grid"
```

---

## Task 14: Create Domain Summary Component

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add DomainSummary component**

```javascript
// ============================================================================
// DOMAIN SUMMARY COMPONENT
// ============================================================================

class DomainSummary extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      domain: { type: String },
      count: { type: Number },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }

      .summary-tile {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 16px;
        cursor: pointer;
        transition: background 0.2s ease;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 8px;
      }

      .summary-tile:hover {
        background: rgba(255, 255, 255, 0.08);
      }

      .summary-tile.active {
        background: var(--tile-color-bg, rgba(255, 179, 0, 0.2));
      }

      .summary-icon {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(255, 255, 255, 0.1);
        color: var(--secondary-text-color, rgba(255, 255, 255, 0.7));
      }

      .summary-tile.active .summary-icon {
        background: var(--tile-color-bg, rgba(255, 179, 0, 0.3));
        color: var(--tile-color, #ffb300);
      }

      .summary-icon ha-icon {
        --mdc-icon-size: 24px;
      }

      .summary-label {
        font-size: 12px;
        color: var(--primary-text-color, #fff);
        text-align: center;
      }

      .summary-count {
        font-size: 11px;
        color: var(--secondary-text-color, rgba(255, 255, 255, 0.7));
      }
    `;
  }

  get isActive() {
    return this.count > 0;
  }

  handleClick() {
    this.dispatchEvent(
      new CustomEvent("domain-selected", {
        bubbles: true,
        composed: true,
        detail: { domain: this.domain },
      })
    );
  }

  render() {
    const icon = DOMAIN_ICONS[this.domain] || "mdi:help-circle";
    const label = DOMAIN_LABELS[this.domain] || this.domain;
    const color = DOMAIN_COLORS[this.domain] || "#9E9E9E";
    const colorRgb = this._hexToRgb(color);

    return html`
      <div
        class="summary-tile ${this.isActive ? "active" : ""}"
        style="--tile-color: ${color}; --tile-color-bg: rgba(${colorRgb}, 0.2);"
        @click=${this.handleClick}
      >
        <div class="summary-icon">
          <ha-icon icon=${icon}></ha-icon>
        </div>
        <div class="summary-label">${label}</div>
        <div class="summary-count">${this.count} 開啟</div>
      </div>
    `;
  }

  _hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result
      ? `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`
      : "255, 255, 255";
  }
}

customElements.define("domain-summary", DomainSummary);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add DomainSummary component for home view"
```

---

## Task 15: Create Area Card Component

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add AreaCard component**

```javascript
// ============================================================================
// AREA CARD COMPONENT
// ============================================================================

class AreaCard extends LitElement {
  static get properties() {
    return {
      area: { type: Object },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }

      .area-card {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 16px;
        cursor: pointer;
        transition: background 0.2s ease, transform 0.1s ease;
      }

      .area-card:hover {
        background: rgba(255, 255, 255, 0.08);
      }

      .area-card:active {
        transform: scale(0.98);
      }

      .area-icon {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(33, 150, 243, 0.2);
        color: #2196f3;
        margin-bottom: 12px;
      }

      .area-icon ha-icon {
        --mdc-icon-size: 24px;
      }

      .area-name {
        font-size: 14px;
        font-weight: 500;
        color: var(--primary-text-color, #fff);
        margin-bottom: 4px;
      }

      .area-count {
        font-size: 12px;
        color: var(--secondary-text-color, rgba(255, 255, 255, 0.7));
      }
    `;
  }

  handleClick() {
    this.dispatchEvent(
      new CustomEvent("area-selected", {
        bubbles: true,
        composed: true,
        detail: { areaId: this.area.id },
      })
    );
  }

  render() {
    const icon = this.area.icon || "mdi:home";
    const name = this.area.name || this.area.id;
    const count = this.area.entity_count || 0;

    return html`
      <div class="area-card" @click=${this.handleClick}>
        <div class="area-icon">
          <ha-icon icon=${icon}></ha-icon>
        </div>
        <div class="area-name">${name}</div>
        <div class="area-count">${count} entities</div>
      </div>
    `;
  }
}

customElements.define("area-card", AreaCard);
```

**Step 2: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add AreaCard component for home view"
```

---

## Task 16: Create Main Panel Component

**Files:**
- Modify: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Add main HaAreaControlPanel component**

```javascript
// ============================================================================
// MAIN PANEL COMPONENT
// ============================================================================

class HaAreaControlPanel extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      narrow: { type: Boolean },
      panel: { type: Object },
      // Internal state
      _view: { type: String },
      _selectedAreaId: { type: String },
      _selectedDomain: { type: String },
      _areas: { type: Array },
      _areaEntities: { type: Object },
      _loading: { type: Boolean },
    };
  }

  constructor() {
    super();
    this._view = "home";
    this._selectedAreaId = null;
    this._selectedDomain = null;
    this._areas = [];
    this._areaEntities = {};
    this._loading = true;
  }

  static get styles() {
    return css`
      :host {
        display: block;
        height: 100%;
        background: var(--primary-background-color, #111);
        --primary-text-color: #fff;
        --secondary-text-color: rgba(255, 255, 255, 0.7);
      }

      .panel-container {
        height: 100%;
        display: flex;
        flex-direction: column;
      }

      /* Header */
      .header {
        background: var(--app-header-background-color, #1976d2);
        color: var(--app-header-text-color, #fff);
        padding: 16px;
        display: flex;
        align-items: center;
        gap: 16px;
        flex-shrink: 0;
      }

      .header-back {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        border: none;
        background: transparent;
        color: inherit;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .header-back:hover {
        background: rgba(255, 255, 255, 0.1);
      }

      .header-back ha-icon {
        --mdc-icon-size: 24px;
      }

      .header-title {
        font-size: 20px;
        font-weight: 400;
        flex: 1;
      }

      /* Content */
      .content {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
      }

      /* Home View */
      .summary-section {
        margin-bottom: 24px;
      }

      .section-label {
        font-size: 12px;
        font-weight: 500;
        color: var(--secondary-text-color);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 12px;
      }

      .summary-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
      }

      @media (max-width: 599px) {
        .summary-grid {
          grid-template-columns: repeat(3, 1fr);
        }
      }

      .areas-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 8px;
      }

      @media (min-width: 600px) {
        .areas-grid {
          grid-template-columns: repeat(3, 1fr);
        }
      }

      @media (min-width: 1024px) {
        .areas-grid {
          grid-template-columns: repeat(4, 1fr);
        }
      }

      /* Loading */
      .loading {
        display: flex;
        align-items: center;
        justify-content: center;
        height: 200px;
        color: var(--secondary-text-color);
      }
    `;
  }

  connectedCallback() {
    super.connectedCallback();
    this._loadAreas();
  }

  async _loadAreas() {
    this._loading = true;
    try {
      const result = await this.hass.callWS({
        type: "area_control/get_permitted_areas",
      });
      this._areas = result.areas || [];
    } catch (err) {
      console.error("Failed to load areas:", err);
      this._areas = [];
    }
    this._loading = false;
  }

  async _loadAreaEntities(areaId) {
    if (this._areaEntities[areaId]) return;

    try {
      const result = await this.hass.callWS({
        type: "area_control/get_area_entities",
        area_id: areaId,
      });
      this._areaEntities = {
        ...this._areaEntities,
        [areaId]: result.entities || {},
      };
      this.requestUpdate();
    } catch (err) {
      console.error("Failed to load area entities:", err);
    }
  }

  _getDomainCounts() {
    const counts = {};

    for (const domain of SUMMARY_DOMAINS) {
      counts[domain] = 0;
    }

    // Count entities in "on" state across all areas
    for (const areaId of Object.keys(this._areaEntities)) {
      const entities = this._areaEntities[areaId];
      for (const [domain, entityIds] of Object.entries(entities)) {
        if (!SUMMARY_DOMAINS.includes(domain)) continue;

        for (const entityId of entityIds) {
          const state = this.hass?.states?.[entityId];
          if (state && (state.state === "on" || state.state === "playing" || state.state === "open")) {
            counts[domain] = (counts[domain] || 0) + 1;
          }
        }
      }
    }

    return counts;
  }

  _handleAreaSelected(e) {
    const areaId = e.detail.areaId;
    this._selectedAreaId = areaId;
    this._view = "area";
    this._loadAreaEntities(areaId);
  }

  _handleDomainSelected(e) {
    const domain = e.detail.domain;
    this._selectedDomain = domain;
    this._view = "domain";
  }

  _handleBack() {
    this._view = "home";
    this._selectedAreaId = null;
    this._selectedDomain = null;
  }

  _getSelectedArea() {
    return this._areas.find((a) => a.id === this._selectedAreaId);
  }

  render() {
    return html`
      <div class="panel-container">
        ${this._renderHeader()}
        <div class="content">
          ${this._loading
            ? html`<div class="loading">載入中...</div>`
            : this._renderView()}
        </div>
      </div>
    `;
  }

  _renderHeader() {
    let title = "Area Control";
    let showBack = false;

    if (this._view === "area") {
      const area = this._getSelectedArea();
      title = area?.name || "Area";
      showBack = true;
    } else if (this._view === "domain") {
      title = DOMAIN_LABELS[this._selectedDomain] || this._selectedDomain;
      showBack = true;
    }

    return html`
      <div class="header">
        ${showBack
          ? html`
              <button class="header-back" @click=${this._handleBack}>
                <ha-icon icon="mdi:arrow-left"></ha-icon>
              </button>
            `
          : html`<ha-icon icon="mdi:view-dashboard"></ha-icon>`}
        <div class="header-title">${title}</div>
      </div>
    `;
  }

  _renderView() {
    switch (this._view) {
      case "home":
        return this._renderHomeView();
      case "area":
        return this._renderAreaView();
      case "domain":
        return this._renderDomainView();
      default:
        return this._renderHomeView();
    }
  }

  _renderHomeView() {
    // Load all area entities for counting
    for (const area of this._areas) {
      this._loadAreaEntities(area.id);
    }

    const counts = this._getDomainCounts();
    const activeDomains = SUMMARY_DOMAINS.filter((d) => counts[d] > 0 || true);

    return html`
      <div class="summary-section">
        <div class="section-label">摘要</div>
        <div class="summary-grid">
          ${activeDomains.map(
            (domain) => html`
              <domain-summary
                .hass=${this.hass}
                .domain=${domain}
                .count=${counts[domain] || 0}
                @domain-selected=${this._handleDomainSelected}
              ></domain-summary>
            `
          )}
        </div>
      </div>

      <div class="areas-section">
        <div class="section-label">分區</div>
        <div class="areas-grid">
          ${this._areas.map(
            (area) => html`
              <area-card
                .area=${area}
                @area-selected=${this._handleAreaSelected}
              ></area-card>
            `
          )}
        </div>
      </div>
    `;
  }

  _renderAreaView() {
    const entities = this._areaEntities[this._selectedAreaId] || {};
    const domains = Object.keys(entities).sort((a, b) => {
      // Sort by priority: lights first, then climate, etc.
      const priority = ["light", "climate", "cover", "fan", "media_player", "scene"];
      const aIdx = priority.indexOf(a);
      const bIdx = priority.indexOf(b);
      if (aIdx === -1 && bIdx === -1) return a.localeCompare(b);
      if (aIdx === -1) return 1;
      if (bIdx === -1) return -1;
      return aIdx - bIdx;
    });

    return html`
      ${domains.map(
        (domain) => html`
          <domain-section
            .hass=${this.hass}
            .domain=${domain}
            .entities=${entities[domain]}
          ></domain-section>
        `
      )}
    `;
  }

  _renderDomainView() {
    // Collect all entities of selected domain across all areas
    const allEntities = [];
    for (const areaId of Object.keys(this._areaEntities)) {
      const entities = this._areaEntities[areaId];
      if (entities[this._selectedDomain]) {
        allEntities.push(...entities[this._selectedDomain]);
      }
    }

    return html`
      <domain-section
        .hass=${this.hass}
        .domain=${this._selectedDomain}
        .entities=${allEntities}
      ></domain-section>
    `;
  }
}

customElements.define("ha-area-control-panel", HaAreaControlPanel);
```

**Step 2: Verify main panel component**

Run: `grep -n "class HaAreaControlPanel" /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`
Expected: Shows line number

**Step 3: Commit**

```bash
git add frontend/ha-area-control-panel.js
git commit -m "feat(area-control): add main HaAreaControlPanel with three views"
```

---

## Task 17: Final Integration and Testing

**Files:**
- Test: `/home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`

**Step 1: Verify complete file structure**

Run: `wc -l /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js`
Expected: Approximately 1500-2000 lines

**Step 2: Check for syntax errors**

Run: `node --check /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js 2>&1 || echo "Note: Top-level await requires ES modules"`

**Step 3: Copy to HA config for testing**

Run: `cp /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/ha_area_control/frontend/ha-area-control-panel.js /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/config/custom_components/ha_area_control/frontend/`

**Step 4: Restart Home Assistant**

Run: `pkill -f "hass -c" && sleep 2 && cd /home/woowtech-ai-coder/Desktop/ha_custom_components_latest/config && nohup /home/woowtech-ai-coder/.local/bin/hass -c . > /tmp/ha.log 2>&1 &`

**Step 5: Wait for HA to start**

Run: `for i in {1..20}; do sleep 5; code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8123 2>/dev/null); if [ "$code" = "200" ]; then echo "HA ready"; break; fi; done`

**Step 6: Final commit**

```bash
git add .
git commit -m "feat(area-control): complete Home Dashboard style rewrite

- Hybrid home view with domain summary + areas grid
- Tall tiles with embedded controls for all domains
- Light: brightness slider
- Climate: temperature +/- buttons
- Cover: up/stop/down buttons
- Fan: speed slider with spinning animation
- Media player: playback controls
- Lock: lock/unlock buttons
- Vacuum: start/pause/return buttons
- Scene/Script: last triggered time
- Responsive layout: 2/3/4 columns
- Long press for more-info dialog
- RGB light actual color support"
```

---

## Summary of Files

| File | Purpose |
|------|---------|
| `frontend/ha-area-control-panel.js` | Complete frontend rewrite with HA native style |

## Component Hierarchy

```
HaAreaControlPanel (main)
├── HomeView
│   ├── DomainSummary (per SUMMARY_DOMAIN)
│   └── AreaCard (per area)
├── AreaDetailView
│   └── DomainSection (per domain)
│       └── *Tile (per entity)
└── DomainFilterView
    └── DomainSection
        └── *Tile (per entity)

Tile Components:
├── BaseTile (base class)
├── LightTile (brightness slider)
├── ClimateTile (temp +/- buttons)
├── CoverTile (up/stop/down)
├── FanTile (speed slider)
├── MediaPlayerTile (prev/play/next)
├── LockTile (lock/unlock)
├── VacuumTile (start/pause/return)
├── SceneTile (last triggered)
├── ScriptTile (extends SceneTile)
├── AutomationTile (extends SceneTile)
├── SwitchTile (simple toggle)
├── SensorTile (display only)
├── BinarySensorTile (display only)
├── ButtonTile (press action)
└── HumidifierTile (humidity slider)
```

---

**End of Implementation Plan**
