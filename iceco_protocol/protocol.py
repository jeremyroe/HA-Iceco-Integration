"""
Iceco Refrigerator BLE Protocol Implementation

This module implements the command construction and notification parsing
for the Iceco refrigerator BLE protocol.

Protocol details:
- Service UUID: FFF0
- Commands: ASCII strings sent to characteristic FFF1
- Notifications: ASCII strings received from characteristic FFF4
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class IcecoStatus:
    """Represents the current status of the Iceco refrigerator."""

    # Current temperatures (Celsius)
    left_temp: int
    right_temp: int

    # Battery information
    battery_protection_level: int  # 1, 2, or 3
    battery_voltage: float  # Volts (e.g., 12.6)

    # Power state
    power_on: bool  # True if on, False if off

    # Set temperatures (from secondary status, if available)
    left_set_temp: Optional[int] = None
    right_set_temp: Optional[int] = None


class IcecoProtocol:
    """
    Handles command construction and notification parsing for Iceco protocol.

    Command format: /S<ID>/1/<Value>\n
    - S03: Left zone temperature
    - S05: Right zone temperature
    - S00: Power state toggle
    - S01: ECO/MAX mode toggle
    - S06: Lock/unlock toggle

    Notification format (primary): ,<L_Temp>,<R_Temp>,<BattProtect>,<Voltage>,<PowerStatus>\n
    Notification format (secondary): /S00/U/2,1,2,<L_SetTemp>,<R_SetTemp>\n
    """

    # BLE characteristics
    SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"  # Main service
    WRITE_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"    # Send commands
    NOTIFY_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"   # Receive status

    # Command IDs
    CMD_LEFT_TEMP = "03"
    CMD_RIGHT_TEMP = "05"
    CMD_POWER = "00"
    CMD_ECO_MODE = "01"
    CMD_LOCK = "06"

    @staticmethod
    def build_command(command_id: str, value: str) -> bytes:
        """
        Build a command string for the refrigerator.

        Args:
            command_id: Command ID (e.g., "S03", "S05")
            value: Value to set (e.g., "-18", "004", "-01")

        Returns:
            ASCII-encoded bytes ready to send to characteristic FFF1
        """
        # Format: /S<ID>/1/<Value>\n
        command = f"/S{command_id}/1/{value}\n"
        return command.encode('ascii')

    @staticmethod
    def set_left_temperature(temp: int) -> bytes:
        """
        Build command to set left zone temperature.

        Args:
            temp: Temperature in Celsius (negative for freezing, positive for refrigeration)

        Returns:
            Command bytes
        """
        # Format temperature with sign and zero-padding
        if temp < 0:
            value = f"-{abs(temp):02d}"
        else:
            value = f"{temp:03d}"
        return IcecoProtocol.build_command(IcecoProtocol.CMD_LEFT_TEMP, value)

    @staticmethod
    def set_right_temperature(temp: int) -> bytes:
        """
        Build command to set right zone temperature.

        Args:
            temp: Temperature in Celsius (negative for freezing, positive for refrigeration)

        Returns:
            Command bytes
        """
        # Format temperature with sign and zero-padding
        if temp < 0:
            value = f"-{abs(temp):02d}"
        else:
            value = f"{temp:03d}"
        return IcecoProtocol.build_command(IcecoProtocol.CMD_RIGHT_TEMP, value)

    @staticmethod
    def toggle_power() -> bytes:
        """
        Build command to toggle power state.

        Note: Same command is used for both on and off.

        Returns:
            Command bytes
        """
        return IcecoProtocol.build_command(IcecoProtocol.CMD_POWER, "-01")

    @staticmethod
    def toggle_eco_mode() -> bytes:
        """
        Build command to toggle ECO/MAX mode.

        Returns:
            Command bytes
        """
        return IcecoProtocol.build_command(IcecoProtocol.CMD_ECO_MODE, "001")

    @staticmethod
    def toggle_lock() -> bytes:
        """
        Build command to toggle control panel lock.

        Returns:
            Command bytes
        """
        # Note: Protocol shows both "001" and "002" for lock toggle
        # Using "001" as default based on observations
        return IcecoProtocol.build_command(IcecoProtocol.CMD_LOCK, "001")

    @staticmethod
    def parse_notification(data: bytes) -> Optional[IcecoStatus]:
        """
        Parse a notification from the refrigerator.

        Args:
            data: Raw bytes from characteristic FFF4

        Returns:
            IcecoStatus object if parsing succeeds, None otherwise
        """
        try:
            # Decode ASCII data
            message = data.decode('ascii').strip()

            # Check if this is a primary status notification
            # Format: ,<L_Temp>,<R_Temp>,<BattProtect>,<Voltage>,<PowerStatus>
            if message.startswith(','):
                parts = message[1:].split(',')
                if len(parts) == 5:
                    left_temp = int(parts[0])
                    right_temp = int(parts[1])
                    batt_protect = int(parts[2])
                    # Voltage is sent as integer (e.g., 126 = 12.6V)
                    voltage = int(parts[3]) / 10.0
                    power_status = int(parts[4])

                    return IcecoStatus(
                        left_temp=left_temp,
                        right_temp=right_temp,
                        battery_protection_level=batt_protect,
                        battery_voltage=voltage,
                        power_on=(power_status == 1)
                    )

            # Check if this is a secondary status notification
            # Format: /S00/U/2,1,2,<L_SetTemp>,<R_SetTemp>
            # This appears to be redundant and possibly in Fahrenheit
            # We'll parse it but it's not required for the integration
            elif message.startswith('/S00/U/'):
                # Extract the part after /S00/U/
                parts = message.split('/')
                if len(parts) >= 3:
                    data_parts = parts[2].split(',')
                    if len(data_parts) >= 5:
                        # The last two values appear to be set temperatures
                        # This is informational only and not used by the integration
                        pass

            # Unknown notification format
            return None

        except (ValueError, UnicodeDecodeError, IndexError):
            # Parsing failed
            return None
