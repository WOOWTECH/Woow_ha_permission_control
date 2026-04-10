# Home Assistant Area Control

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/WOOWTECH/ha_area_control)](https://github.com/WOOWTECH/ha_area_control/releases)
[![License](https://img.shields.io/github/license/WOOWTECH/ha_area_control)](LICENSE)

English | [简体中文](README_CN.md)

A Home Assistant custom component that provides a sidebar panel for controlling entities organized by areas. Works with the [Permission Manager](https://github.com/WOOWTECH/ha_permission_manager) integration to show only the areas each user has permission to access.

**Current Version: 1.0.2**

## Features

- **Area-based Entity Control**: View and control entities grouped by their assigned areas
- **Permission-aware**: Integrates with Permission Manager to show only permitted areas for each user
- **Multi-language Support**: English, Traditional Chinese (zh-Hant), and Simplified Chinese (zh-Hans)
- **Native HA Style UI**: Clean, responsive interface matching Home Assistant's modern design
- **Domain Summary Dashboard**: 3x3 grid showing 9 domain categories (Lights, Climate, Covers, Fans, Media, Locks, Vacuums, Switches, Input Boolean)
- **Domain Detail View**: Click domain summary cards to see all entities of that domain across all areas
- **Area Detail View**: Click area cards to see all entities in that area, organized by domain
- **Compact Domain Tabs**: Horizontal scrollable tabs showing domain icons and entity counts
- **Search Functionality**: Real-time filtering of entities by name or entity ID
- **Interactive Entity Tiles**:
  - Brightness sliders for lights
  - Temperature +/- controls for climate
  - Up/Stop/Down buttons for covers
  - Speed sliders for fans
  - Play/Pause/Next controls for media players
  - Lock/Unlock buttons for locks
  - Start/Pause/Return buttons for vacuums
- **Real-time Updates**: Entity states update in real-time
- **Optimized Performance**: Parallel data loading for fast initial render

## Screenshots

The panel features three views:

1. **Home View**: Summary section with 9 domain category cards + Area cards grid
2. **Domain View**: Click a domain summary card to see all entities of that domain across all areas
3. **Area View**: Click an area card to see all entities in that area, organized by domain

## Requirements

- Home Assistant 2024.1.0 or newer
- [Permission Manager](https://github.com/WOOWTECH/ha_permission_manager) integration (dependency)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/WOOWTECH/ha_area_control`
5. Select "Integration" as the category
6. Click "Add"
7. Search for "Area Control" and install it
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/WOOWTECH/ha_area_control/releases)
2. Extract the `ha_area_control` folder to your `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Area Control"
4. Click to add it

After installation, a new "Area Control" (分區控制) panel will appear in your sidebar.

## How It Works

### For Admin Users
Admin users see all areas defined in Home Assistant with full access.

### For Non-Admin Users
Non-admin users see only the areas they have been granted access to via the Permission Manager integration. The permission levels are:

- **Closed (0)**: No access
- **View (1)**: Can see the area and its entities
- **Limited (2)**: Can view and limited control
- **Edit (3)**: Full control

## Supported Domains

The panel provides specialized tile controls for these domains:

| Domain | Features |
|--------|----------|
| `light` | Toggle, brightness slider, RGB color support |
| `climate` | Toggle, temperature +/- buttons, current temp display |
| `cover` | Open/Stop/Close buttons, position display |
| `fan` | Toggle, speed slider |
| `media_player` | Previous/Play-Pause/Next buttons |
| `lock` | Lock/Unlock buttons |
| `vacuum` | Start/Pause/Return buttons |
| `switch` | Toggle |
| `input_boolean` | Toggle |
| `scene` | Activate, last triggered time |
| `script` | Activate, last triggered time |
| `automation` | Toggle enable/disable |
| `sensor` | Display value with unit, 24h history sparkline chart |
| `binary_sensor` | Display state |
| `button` | Press action |
| `humidifier` | Toggle, humidity slider |

## File Structure

```
custom_components/ha_area_control/
├── __init__.py           # Main integration setup
├── manifest.json         # Component manifest
├── config_flow.py        # Configuration flow
├── const.py              # Constants
├── panel.py              # WebSocket API handlers
├── strings.json          # Default strings
├── frontend/
│   └── ha-area-control-panel.js  # Frontend panel
└── translations/
    ├── en.json           # English translations
    ├── zh-Hant.json      # Traditional Chinese
    └── zh-Hans.json      # Simplified Chinese
```

## WebSocket API

The integration exposes two WebSocket commands:

### `area_control/get_permitted_areas`
Returns a list of areas the current user has permission to access.

### `area_control/get_area_entities`
Returns entities grouped by domain for a specific area.

## Changelog

### v1.0.2
- Added compact horizontal domain tabs replacing collapsible sections
- Added search bar for filtering entities by name or ID
- Added 24h history sparkline charts on sensor tiles
- Fixed card width consistency with uniform sizing

### v1.0.1
- Performance optimization: parallel loading for area entities
- Reduced UI jitter on initial load

### v1.0.0
- Native HA style UI redesign
- Domain summary dashboard with 3x3 grid
- Domain detail view
- Interactive entity tiles with embedded controls

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

If you encounter any issues or have feature requests, please [open an issue](https://github.com/WOOWTECH/ha_area_control/issues).

## Credits

Developed by [WOOWTECH](https://github.com/WOOWTECH)
