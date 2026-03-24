# Iceco Refrigerator — Home Assistant Integration

Home Assistant integration for Iceco dual-zone Bluetooth refrigerators. Control temperatures, monitor battery, and get alarms for power loss or temperature deviation — all from HA.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jeremyroe&repository=HA-Iceco-Integration&category=integration)

---

## Features

- **Dual-zone temperature control** with independent setpoints
- **Real-time temperature monitoring** (current vs. target per zone)
- **ECO / MAX mode** control
- **Control panel lock/unlock**
- **Power on/off**
- **Battery voltage sensor** with protection level
- **Power loss alarm** — triggers after configurable timeout with no BLE updates
- **Temperature deviation alarms** — triggers when a zone drifts too far from setpoint for too long
- **Auto-discovery** — finds the fridge automatically via Bluetooth service UUID
- **Unit preference** — displays in °F or °C based on your HA settings
- **Multi-adapter support** — works with built-in Bluetooth, USB dongles, and ESP32 proxies

---

## Compatibility

Tested on:
- Iceco APL35 dual-zone refrigerator

Other Iceco dual-zone models using the FFF0 BLE service are likely compatible.

---

## Installation

### HACS (Recommended)

1. Click the button above, or in HACS go to **Integrations → Custom repositories** and add `https://github.com/jeremyroe/HA-Iceco-Integration` as an **Integration**.
2. Search for **Iceco Refrigerator** in HACS and install.
3. Restart Home Assistant.

### Manual

1. Copy the `custom_components/iceco` folder into your HA `config/custom_components/` directory.
2. Restart Home Assistant.

---

## Setup

1. Make sure your Iceco refrigerator is powered on and Bluetooth is enabled on your HA host.
2. Go to **Settings → Devices & Services → Add Integration** and search for **Iceco Refrigerator**.
3. HA will auto-discover the fridge. Select it and confirm.

If auto-discovery doesn't find it, enter the Bluetooth address manually.

---

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| Left Zone | Climate | Current and target temperature, preset selection |
| Right Zone | Climate | Current and target temperature, preset selection |
| Battery Voltage | Sensor | Battery voltage in volts |
| Power | Switch | Turn fridge on/off |
| ECO Mode | Switch | Toggle ECO / MAX compressor mode |
| Control Panel Lock | Switch | Lock/unlock the physical control panel |
| BLE Connection | Switch | Manually disconnect to allow mobile app access |
| Power Loss Alarm | Binary Sensor | Triggers when no BLE updates received for configured timeout |
| Left Zone Alarm | Binary Sensor | Triggers when left zone deviates from setpoint |
| Right Zone Alarm | Binary Sensor | Triggers when right zone deviates from setpoint |

### Temperature Presets

The climate entities include two quick-set presets:
- **Refrigeration** — sets zone to 4°C / 39°F
- **Freezing** — sets zone to -18°C / 0°F

---

## Alarm Configuration

Go to the integration's **Configure** (three-dot menu → Configure) to adjust:

| Setting | Default | Description |
|---------|---------|-------------|
| Poll Interval | 60s | How often to check connection health |
| Power Loss Timeout | 15 min | No-update time before power loss alarm fires |
| Temp Deviation Threshold | 5°C | How far from setpoint before alarm starts |
| Temp Deviation Duration | 5 min | How long deviation must persist before alarm fires |

### Example Automation — Push Notification on Power Loss

```yaml
alias: Iceco Power Loss Alert
trigger:
  - platform: state
    entity_id: binary_sensor.iceco_refrigerator_power_loss_alarm
    to: "on"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Fridge Alert"
      message: "Iceco refrigerator has lost power or BLE connection!"
```

### Example Automation — Alert on Temperature Deviation

```yaml
alias: Iceco Temperature Alarm
trigger:
  - platform: state
    entity_id:
      - binary_sensor.iceco_refrigerator_left_zone_alarm
      - binary_sensor.iceco_refrigerator_right_zone_alarm
    to: "on"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Fridge Alert"
      message: "{{ trigger.to_state.name }} is outside target temperature range!"
```

---

## Mobile App Access

The Iceco mobile app requires an exclusive BLE connection. If HA is connected, the app can't connect. Use the **BLE Connection** switch to temporarily disconnect HA and free up the connection for the app. HA will reconnect automatically when you turn the switch back on.

---

## Notes

- Commands are always sent in °C (protocol requirement). HA handles display unit conversion.
- The fridge does not report setpoints in real time — they are read from BLE notifications immediately after a command is accepted.
- ECO mode state is read from the fridge directly; no optimistic tracking.
- Lock state is encoded in the power status field of the primary notification.
