# UniFi Cable Tester

A Home Assistant integration that tests Ethernet cables on UniFi switches via SSH and displays port-by-port diagnostics.

## Installation

### HACS (Recommended)
1. Add this repository to HACS as a custom repository
2. Install "UniFi Cable Tester"
3. Restart Home Assistant

### Manual
Copy the contents to `custom_components/unifi_cable_tester/`

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "UniFi Cable Tester"
3. Enter your switch IP, username, and password (or SSH key)

## Dashboard Card

### Add the Resource
1. Go to **Settings → Dashboards**
2. Click **⋮** (three dots) → **Resources**
3. Click **Add Resource**
4. Enter:
   - **URL:** `/unifi_cable_tester/unifi-cable-tester-card.js`
   - **Type:** JavaScript Module
5. Click **Create**

### Add the Card
1. Edit your dashboard
2. Click **Add Card**
3. Search for **"UniFi Cable Tester"**
4. Configure:
   - **Switch Name:** Part of your switch's entity name (e.g., `192_168_2_9`)
   - **Columns:** Number of ports per row (default: 12)

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

## Card Features

- Visual port grid with color-coded status
- Click a port to see pair details (length, status)
- Test All Cables button
- Test single port button
- Real-time test progress indicator

## Status Colors

| Color | Status |
|-------|--------|
| 🟢 Green | OK |
| 🔴 Red | Open |
| 🟠 Orange | Short / Impedance |
| 🔵 Blue | Fiber |
| ⚫ Gray | Not Tested |
