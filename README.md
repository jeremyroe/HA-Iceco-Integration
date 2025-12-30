# Iceco Refrigerator Home Assistant Integration

Home Assistant integration for Iceco dual-zone Bluetooth refrigerators.

## Project Structure

- `iceco_protocol/` - Standalone Python library for Iceco BLE protocol
- `custom_components/iceco/` - Home Assistant integration (Phase 2)

## Development Status

**Current Phase:** Phase 1 - Protocol Library Development

### Phase 1: Standalone Python Protocol Library
Creating a BLE protocol library using `bleak` that handles all communication with the Iceco refrigerator.

### Phase 2: Home Assistant Integration
Integration with Home Assistant using the protocol library.

### Phase 3: Documentation & Deployment
User documentation and packaging.

## Requirements

- Python 3.10+
- bleak (BLE library)

## Installation

```bash
pip install -r requirements.txt
```

## Hardware Support

- Iceco APL35 dual-zone refrigerator
- Other Iceco models may be compatible (untested)
