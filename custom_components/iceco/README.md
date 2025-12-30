# Iceco Refrigerator Integration for Home Assistant

Custom integration for controlling and monitoring Iceco dual-zone refrigerators via Bluetooth Low Energy (BLE).

## Features

- **Dual Climate Controls**: Independent temperature control for left and right zones
- **Real-time Monitoring**: Battery voltage, power state, and temperature readings
- **Smart Alarms**:
  - Power loss detection (configurable timeout)
  - Temperature deviation alarms (configurable threshold and duration)
- **Full Control**: Power, ECO mode, and control panel lock switches
- **Hybrid Connection**: BLE notifications for real-time updates + periodic health checks
- **Multi-Adapter Support**: Works with built-in Bluetooth, USB adapters, and ESP32 Bluetooth proxies

## Requirements

- Home Assistant 2024.1 or newer
- Bluetooth adapter (built-in, USB dongle, or ESP32 proxy)
- Iceco dual-zone refrigerator

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right
4. Select "Custom repositories"
5. Add this repository URL
6. Search for "Iceco Refrigerator"
7. Click "Download"
8. Restart Home Assistant

### Manual

1. Copy the `custom_components/iceco` directory to your `config/custom_components/` directory
2. Restart Home Assistant

## Setup

### Auto-Discovery

If your refrigerator is powered on and within Bluetooth range, Home Assistant will automatically discover it:

1. Go to **Settings** → **Devices & Services**
2. Look for the discovered "Iceco Refrigerator"
3. Click **Configure**
4. Confirm the device (temps will be shown to help identify)
5. Click **Submit**

### Manual Setup

If auto-discovery doesn't work:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Iceco Refrigerator"
4. Follow the prompts to select or enter device address

## Entities

Once configured, the following entities will be created:

### Climate Entities
- `climate.iceco_left_zone` - Left zone temperature control
- `climate.iceco_right_zone` - Right zone temperature control

### Sensors
- `sensor.iceco_battery_voltage` - Battery voltage (V) with protection level attribute

### Binary Sensors (Alarms)
- `binary_sensor.iceco_power_loss_alarm` - Triggers when device offline too long
- `binary_sensor.iceco_left_zone_temperature_alarm` - Left zone temp deviation
- `binary_sensor.iceco_right_zone_temperature_alarm` - Right zone temp deviation

### Switches
- `switch.iceco_power` - Main power control
- `switch.iceco_eco_mode` - ECO/MAX mode toggle
- `switch.iceco_control_panel_lock` - Lock physical controls

## Configuration

### Options

Configure alarm and monitoring settings:

1. Go to **Settings** → **Devices & Services**
2. Find "Iceco Refrigerator"
3. Click **Configure**

**Available Options:**

- **Poll Interval** (30-300 seconds, default: 60)
  - How often to check connection health
  - Does NOT affect real-time updates (those use BLE notifications)

- **Power Loss Timeout** (10-120 minutes, default: 30)
  - Time without any status update before triggering power loss alarm
  - Useful for detecting when refrigerator loses power or goes out of range

- **Temperature Deviation Threshold** (1-10°C, default: 5)
  - How far actual temperature can deviate from setpoint before alarming
  - Higher values reduce false alarms but increase risk

- **Temperature Deviation Duration** (5-60 minutes, default: 15)
  - How long temperature must stay deviated before triggering alarm
  - Prevents false alarms during normal temperature ramping

## Usage Examples

### Automation: Alert on Power Loss

```yaml
automation:
  - alias: "Iceco Power Loss Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.iceco_power_loss_alarm
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Refrigerator has lost power or connection!"
          title: "Iceco Alert"
```

### Automation: Alert on Temperature Problem

```yaml
automation:
  - alias: "Iceco Temperature Alert"
    trigger:
      - platform: state
        entity_id:
          - binary_sensor.iceco_left_zone_temperature_alarm
          - binary_sensor.iceco_right_zone_temperature_alarm
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Refrigerator temperature is deviating from setpoint!"
          title: "Iceco Temperature Alert"
```

### Automation: Auto ECO Mode at Night

```yaml
automation:
  - alias: "Iceco ECO Mode Schedule"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: switch.turn_on
        entity_id: switch.iceco_eco_mode

  - alias: "Iceco MAX Mode Morning"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      - service: switch.turn_off
        entity_id: switch.iceco_eco_mode
```

## Troubleshooting

### Integration won't discover device

- Ensure refrigerator is powered on
- Check that Bluetooth is enabled in Home Assistant
- Try moving closer to the device
- Disconnect from the mobile app (BLE connection is exclusive)

### Frequent disconnections

- Check Bluetooth adapter signal strength
- Consider adding an ESP32 Bluetooth proxy closer to refrigerator
- Increase poll interval to reduce connection attempts

### Temperature setpoints not matching

- Integration stores setpoints locally since protocol doesn't report them
- If temperature is changed via physical buttons or mobile app, HA won't know
- Set temperature via Home Assistant for accurate tracking

### ECO/Lock switch state incorrect

- Protocol doesn't report ECO mode or lock status
- Switches use optimistic state tracking
- If changed via physical buttons, toggle twice in HA to resync

## Technical Details

- **Protocol**: Iceco BLE protocol (service UUID: FFF0)
- **Connection**: Uses Home Assistant's Bluetooth integration with bleak-retry-connector
- **Updates**: Hybrid approach (real-time BLE notifications + periodic health checks)
- **Supported Adapters**: Any Bluetooth adapter supported by Home Assistant, including ESP32 proxies

## Known Limitations

1. **Exclusive Connection**: Only one BLE client can connect at a time (either HA or mobile app)
2. **Setpoint Tracking**: Temperature setpoints are stored locally; changes via app/buttons won't be reflected
3. **ECO/Lock State**: These states are tracked optimistically as protocol doesn't report them

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

## License

This integration is provided as-is with no warranty.
