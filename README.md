# UniFi Cable Tester

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/richardctrimble/ha-unifi-cable-tester.svg)](https://github.com/richardctrimble/ha-unifi-cable-tester/releases/)

A Home Assistant custom integration that runs Ethernet cable diagnostics on UniFi switches via SSH, providing port-by-port cable status with a custom Lovelace card.

## Features

- SSH-based cable diagnostics on UniFi switches (CLI mode `sh cable-diag`)
- Per-port cable test sensors with pair-level status and length data
- Support for password and SSH key authentication
- Custom Lovelace card with interactive color-coded port grid
- Single port or all-port cable testing from the card UI
- Real-time test progress indicator with animation
- Switch device info display (model, hostname, MAC, firmware)
- Port link status and speed detection (`swctrl port show`)
- Fiber/SFP port detection
- Multi-switch support

## Requirements

- Home Assistant 2024.1.0 or newer
- A UniFi switch accessible via SSH
- SSH credentials (password or SSH key)
- [HACS](https://hacs.xyz/) (recommended for installation)

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Install "UniFi Cable Tester"
3. Restart Home Assistant

### Manual

Copy the contents of this repository to `custom_components/ha_unifi_cable_tester/` in your Home Assistant configuration directory.

## Configuration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **UniFi Cable Tester**
3. Enter your switch IP address, SSH port, and authentication method
4. Provide your credentials (password or SSH key path)
5. The integration will validate the connection and discover switch ports

## Dashboard Card

### Add the Resource

1. Go to **Settings > Dashboards**
2. Click the three-dot menu > **Resources**
3. Click **Add Resource**
4. Enter URL: `/ha_unifi_cable_tester/unifi-cable-tester-card.js`
5. Set type to **JavaScript Module**
6. Click **Create**

### Add the Card

1. Edit your dashboard
2. Click **Add Card**
3. Search for **UniFi Cable Tester**
4. Select your switch from the dropdown
5. Adjust columns to match your switch port layout

### Manual YAML

```yaml
type: custom:unifi-cable-tester-card
title: Switch Cable Status
switch_name: "192_168_2_9"
columns: 12
show_device_info: true
show_test_button: true
compact: false
```

### Status Colors

| Color  | Status       |
|--------|--------------|
| Green  | OK           |
| Red    | Open         |
| Orange | Short        |
| Blue   | Fiber        |
| Gray   | Not Tested   |
| Dark Red | Test Failed |

## Troubleshooting

**Debug logging:**

Add this to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.ha_unifi_cable_tester: debug
```

## Licence

This project is licensed under the MIT Licence. See the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not affiliated with or endorsed by Ubiquiti Inc. Use at your own risk. Cable diagnostics may briefly interrupt port connectivity during testing.
