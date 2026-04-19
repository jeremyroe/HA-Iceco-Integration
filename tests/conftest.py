# Shared fixtures for the Iceco integration test suite.

from unittest.mock import patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integration loading for all tests in this suite."""


@pytest.fixture(autouse=True)
def patch_bluetooth_expire():
    """Prevent BT scanner from scheduling the device expiry timer during tests."""
    with patch(
        "homeassistant.components.bluetooth.base_scanner.BaseHaScanner._async_expire_devices_schedule_next",
    ):
        yield


@pytest.fixture(autouse=True)
def patch_bluetooth_history():
    """Patch bluetooth history loading which relies on D-Bus (Linux only).

    async_load_history_from_system is called during bluetooth component setup.
    On macOS the dbus code path crashes because BlueZ isn't available,
    even when mock_bluetooth_adapters is active. Returning empty dicts is
    correct for a test environment with no real adapters.
    """
    with patch(
        "homeassistant.components.bluetooth.manager.async_load_history_from_system",
        return_value=({}, {}),
    ):
        yield
