# Area Control Panel - Home Dashboard Style Redesign

**Date:** 2026-01-28
**Status:** Draft
**Author:** Claude + User

---

## 1. Overview

### Goal
Rewrite the Area Control frontend to match the native Home Assistant Home Dashboard visual style and interaction experience.

### Key Design Decisions
- **Hybrid Home View**: Summary section (domain aggregates) + Areas grid; clicking summary tiles filters by domain across all areas
- **Tall Tile Cards**: All entity cards use 2-row height with embedded controls
- **Full Domain Support**: Support all common domains with appropriate controls
- **Native HA Integration**: Long press opens native more-info dialog

---

## 2. View Architecture

```
Home View (/)
├── Domain Summary Section
│   ├── Lights tile (e.g., "3 lights on")
│   ├── Climate tile (e.g., "2 climate on")
│   ├── Covers tile
│   ├── Media Players tile
│   ├── Fans tile
│   └── ...other domains with active entities
│   └── [Click] → Filter view showing all entities of that domain
│
└── Areas Grid
    ├── Area Card (icon + name + entity count)
    └── [Click] → Area Detail View

Area Detail View (/area/{area_id})
├── Header
│   ├── Back button (←)
│   └── Area name
│
└── Domain Sections (collapsible)
    ├── Lights Section
    │   ├── Section header ("燈光" + count + expand arrow)
    │   └── Entity tiles grid
    ├── Climate Section
    ├── Covers Section
    ├── Scenes Section
    └── ...other domains

Domain Filter View (/domain/{domain})
├── Header
│   ├── Back button (←)
│   └── Domain name (e.g., "所有燈光")
│
└── Entity tiles grid (all entities of domain across all areas)
```

---

## 3. Tile Card Design

### 3.1 Card Structure

All cards use a unified tall (2-row) structure:

```
┌─────────────────────────────────────┐
│  [icon]  Entity Name                │  ← Top section: icon + name + state
│          State (關閉 / 50% / 22°C)  │
├─────────────────────────────────────┤
│                                     │  ← Bottom section: control element
│  [====== Control Element ======]    │
│                                     │
└─────────────────────────────────────┘
```

### 3.2 Domain-Specific Controls

| Domain | Icon | Control Element | Tap Action |
|--------|------|-----------------|------------|
| **light** | `mdi:lightbulb` | Horizontal brightness slider | Toggle on/off |
| **switch** | `mdi:toggle-switch` | Empty (full tap area) | Toggle on/off |
| **input_boolean** | `mdi:toggle-switch-outline` | Empty (full tap area) | Toggle on/off |
| **climate** | `mdi:thermostat` | Temperature display + up/down buttons | Toggle on/off |
| **cover** | `mdi:window-shutter` | Up / Stop / Down buttons | Toggle open/close |
| **fan** | `mdi:fan` | Speed slider or level buttons | Toggle on/off |
| **media_player** | `mdi:cast` | Prev / Play-Pause / Next buttons | Toggle play/pause |
| **scene** | `mdi:palette` | Last triggered time | Activate scene |
| **script** | `mdi:script-text` | Last triggered time | Run script |
| **lock** | `mdi:lock` | Lock / Unlock buttons | Toggle lock |
| **vacuum** | `mdi:robot-vacuum` | Start / Pause / Return buttons | Toggle start/pause |
| **sensor** | `mdi:eye` | Empty (display only) | Open more-info |
| **binary_sensor** | `mdi:checkbox-marked-circle` | Empty (display only) | Open more-info |
| **button** | `mdi:gesture-tap-button` | Empty (full tap area) | Press button |
| **humidifier** | `mdi:air-humidifier` | Humidity slider | Toggle on/off |
| **automation** | `mdi:robot` | Last triggered time | Toggle on/off |

### 3.3 Color System

#### Domain Default Colors (when ON)
```javascript
const DOMAIN_COLORS = {
  light: "#FFB300",        // Amber
  switch: "#FFB300",       // Amber
  input_boolean: "#FFB300", // Amber
  fan: "#009688",          // Teal
  climate: "#FF9800",      // Orange (heating)
  climate_cool: "#2196F3", // Blue (cooling)
  cover: "#9C27B0",        // Purple
  lock: "#4CAF50",         // Green (locked)
  lock_unlocked: "#F44336", // Red (unlocked)
  vacuum: "#009688",       // Teal
  media_player: "#673AB7", // Deep Purple
  humidifier: "#00BCD4",   // Cyan
  automation: "#2196F3",   // Blue
  script: "#2196F3",       // Blue
  scene: "#E91E63",        // Pink
  sensor: "#607D8B",       // Blue Grey
  binary_sensor: "#607D8B", // Blue Grey
  button: "#FF9800",       // Orange
};
```

#### Color Logic
1. **RGB Light entities**: Use actual RGB color from entity attributes
2. **Other domains (ON state)**: Use domain default color
3. **OFF state**: Grey (`#45474B`)
4. **Unavailable state**: Dark grey (`#2C2C2C`) with reduced opacity

---

## 4. Responsive Layout

### 4.1 Grid Breakpoints

```css
/* Mobile: 2 columns */
@media (max-width: 599px) {
  .tiles-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Tablet: 3 columns */
@media (min-width: 600px) and (max-width: 1023px) {
  .tiles-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* Desktop: 4 columns */
@media (min-width: 1024px) {
  .tiles-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
```

### 4.2 Card Dimensions
- **Gap**: 8px between cards
- **Padding**: 12px inside cards
- **Border radius**: 12px
- **Min height**: 120px (to accommodate 2-row design)

---

## 5. Interactions

### 5.1 Tap/Click Actions

| Target | Action | Result |
|--------|--------|--------|
| Card icon area | Tap | Toggle entity state |
| Brightness slider | Drag | Adjust brightness in real-time |
| Temperature +/- | Tap | Increment/decrement target temp |
| Cover buttons | Tap | Execute cover action |
| Media buttons | Tap | Execute media action |
| Scene card | Tap | Activate scene |
| Domain summary tile | Tap | Navigate to domain filter view |
| Area card | Tap | Navigate to area detail view |

### 5.2 Long Press
- **Any entity card**: Open native HA `more-info` dialog
- Implementation: `hass.callService('browser_mod', 'more_info', { entity_id })`

### 5.3 Animations
- **State change**: Smooth color transition (200ms ease)
- **Slider drag**: Immediate visual feedback
- **Card hover**: Subtle elevation increase (box-shadow)
- **Section expand/collapse**: Smooth height transition (300ms)

---

## 6. Domain Summary Section

### 6.1 Display Logic
- Show tile for each domain that has at least 1 entity across all permitted areas
- Display count of entities in "ON" state
- Format: "{count} {domain_name} 開啟" (e.g., "3 盞燈開啟")

### 6.2 Summary Tile Design
```
┌─────────────────┐
│  [icon]         │
│  燈光           │
│  3 開啟         │
└─────────────────┘
```

### 6.3 Supported Summary Domains
- Lights (light)
- Climate (climate)
- Covers (cover)
- Fans (fan)
- Media Players (media_player)
- Locks (lock)
- Vacuums (vacuum)
- Switches (switch)

---

## 7. Technical Implementation

### 7.1 Technology Stack
- **Framework**: LitElement (using HA's bundled version)
- **Styling**: CSS-in-JS with LitElement's `css` template literal
- **State Management**: HA WebSocket API subscriptions
- **Icons**: Material Design Icons (mdi)

### 7.2 WebSocket API Calls
```javascript
// Get permitted areas
hass.callWS({ type: "area_control/get_permitted_areas" })

// Get area entities
hass.callWS({ type: "area_control/get_area_entities", area_id: "xxx" })

// Subscribe to state changes
hass.connection.subscribeEvents(callback, "state_changed")
```

### 7.3 File Structure
```
ha_area_control/
└── frontend/
    └── ha-area-control-panel.js  (single file, all components)
```

### 7.4 Component Hierarchy
```
HaAreaControlPanel (main)
├── AreaControlHomeView
│   ├── DomainSummarySection
│   │   └── DomainSummaryTile (per domain)
│   └── AreasGrid
│       └── AreaCard (per area)
├── AreaControlDetailView
│   └── DomainSection (per domain)
│       └── EntityTile (per entity)
└── DomainFilterView
    └── EntityTile (per entity)
```

---

## 8. Entity Tile Components

### 8.1 Base Tile Structure
All tiles share common structure, with domain-specific control slots:

```javascript
class EntityTile extends LitElement {
  // Common properties
  hass;           // HA instance
  entity;         // Entity state object

  // Computed
  get isOn() { }
  get stateDisplay() { }
  get iconColor() { }

  // Methods
  toggle() { }
  openMoreInfo() { }

  // Render
  render() {
    return html`
      <div class="tile" style="--tile-color: ${this.iconColor}">
        <div class="tile-header" @click=${this.toggle}>
          <ha-icon icon=${this.icon}></ha-icon>
          <div class="tile-info">
            <span class="name">${this.entity.attributes.friendly_name}</span>
            <span class="state">${this.stateDisplay}</span>
          </div>
        </div>
        <div class="tile-controls">
          ${this.renderControls()}
        </div>
      </div>
    `;
  }

  // Override in subclasses
  renderControls() { return html``; }
}
```

### 8.2 Domain-Specific Tiles
- `LightTile` - brightness slider, RGB color support
- `ClimateTile` - temperature display, +/- buttons
- `CoverTile` - up/stop/down buttons
- `FanTile` - speed slider
- `MediaPlayerTile` - playback controls
- `SceneTile` - last triggered display
- `LockTile` - lock/unlock buttons
- `VacuumTile` - start/pause/return buttons
- `SwitchTile` - simple toggle
- `SensorTile` - display only

---

## 9. Acceptance Criteria

### 9.1 Home View
- [ ] Shows domain summary tiles with active entity counts
- [ ] Shows areas grid with area cards
- [ ] Clicking domain summary navigates to filtered view
- [ ] Clicking area card navigates to area detail

### 9.2 Area Detail View
- [ ] Shows back button and area name in header
- [ ] Groups entities by domain in collapsible sections
- [ ] Each domain section shows entity count
- [ ] All entity tiles render with correct controls

### 9.3 Entity Tiles
- [ ] All 14 domain types render correctly
- [ ] Tap toggles entity state
- [ ] Long press opens more-info dialog
- [ ] Sliders adjust values in real-time
- [ ] Colors reflect entity state (ON/OFF/RGB)
- [ ] Unavailable entities show grey state

### 9.4 Responsive Design
- [ ] 2 columns on mobile (<600px)
- [ ] 3 columns on tablet (600-1024px)
- [ ] 4 columns on desktop (>1024px)

### 9.5 Performance
- [ ] Initial load under 2 seconds
- [ ] State updates reflect within 100ms
- [ ] Smooth animations at 60fps

---

## 10. Out of Scope (v1)

- Custom entity ordering/sorting
- Drag-and-drop tile arrangement
- Custom icons per entity
- Themes/dark mode toggle (uses HA theme)
- Area climate/sensor chips in header
- Entity history graphs in tiles

---

## Appendix: Visual Reference

### Home View Mockup
```
┌──────────────────────────────────────────────┐
│  Area Control                            ≡   │
├──────────────────────────────────────────────┤
│                                              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐        │
│  │ 💡      │ │ 🌡️      │ │ 🪟      │        │  ← Domain Summary
│  │ 燈光    │ │ 溫控    │ │ 窗簾    │        │
│  │ 5 開啟  │ │ 2 開啟  │ │ 1 開啟  │        │
│  └─────────┘ └─────────┘ └─────────┘        │
│                                              │
│  分區                                        │
│  ┌─────────────┐ ┌─────────────┐            │
│  │ 🏠 客廳     │ │ 🛏️ 臥室     │            │  ← Areas Grid
│  │ 15 entities │ │ 8 entities  │            │
│  └─────────────┘ └─────────────┘            │
│  ┌─────────────┐ ┌─────────────┐            │
│  │ 🍳 廚房     │ │ 🚿 浴室     │            │
│  │ 6 entities  │ │ 4 entities  │            │
│  └─────────────┘ └─────────────┘            │
└──────────────────────────────────────────────┘
```

### Area Detail View Mockup
```
┌──────────────────────────────────────────────┐
│  ← 客廳                                  ⋮   │
├──────────────────────────────────────────────┤
│                                              │
│  💡 燈光                              8  >   │
│  ┌──────────────────┐ ┌──────────────────┐  │
│  │ 💡 客廳主燈      │ │ 💡 客廳彩燈      │  │
│  │    80%           │ │    關閉          │  │
│  │ ████████████░░░░ │ │ ░░░░░░░░░░░░░░░░ │  │
│  └──────────────────┘ └──────────────────┘  │
│  ┌──────────────────┐ ┌──────────────────┐  │
│  │ 💡 電視燈        │ │ 💡 Hue Go        │  │
│  │    關閉          │ │    關閉          │  │
│  │ ░░░░░░░░░░░░░░░░ │ │ ░░░░░░░░░░░░░░░░ │  │
│  └──────────────────┘ └──────────────────┘  │
│                                              │
│  🌡️ 溫控                              1  >   │
│  ┌──────────────────┐                        │
│  │ 🌡️ 客廳空調      │                        │
│  │    22°C          │                        │
│  │   [−]  24°C  [+] │                        │
│  └──────────────────┘                        │
│                                              │
│  🎭 場景                              5  >   │
│  ┌──────────────────┐ ┌──────────────────┐  │
│  │ 🎭 閱讀模式      │ │ 🎭 電影模式      │  │
│  │    10分鐘前      │ │    2小時前       │  │
│  └──────────────────┘ └──────────────────┘  │
└──────────────────────────────────────────────┘
```

---

**End of PRD**
