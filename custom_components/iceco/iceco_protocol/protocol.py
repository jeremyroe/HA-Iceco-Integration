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
    """Represents the current status from PRIMARY notification.

    IMPORTANT: PRIMARY notification contains SETPOINTS, not current temps!
    Current temps come from SECONDARY notification.
    """

    # Temperature SETPOINTS (in Celsius, always)
    # These are what the fridge is trying to reach, not current temps
    left_temp: int  # Left zone setpoint in Celsius
    right_temp: int  # Right zone setpoint in Celsius

    # Battery information
    battery_protection_level: int  # 1, 2, or 3
    battery_voltage: float  # Volts (e.g., 12.6)

    # Power state
    power_on: bool  # True if on, False if off

    # Deprecated fields (kept for compatibility)
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

    PRIMARY notification: ,<L_Setpoint_C>,<R_Setpoint_C>,<BattProtect>,<Voltage>,<PowerStatus>\n
    - Contains SETPOINTS in Celsius (updates immediately when setpoint changed)

    SECONDARY notification: /S00/U/2,<power>,<unit_mode>,<L_Current>,<R_Current>\n
    - Contains CURRENT temperatures in user's chosen unit (C or F)
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
            temp: Temperature in fridge's configured unit (F or C)

        Returns:
            Command bytes
        """
        # Format temperature as 3 digits with leading zeros for positive, minus sign for negative
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
            temp: Temperature in fridge's configured unit (F or C)

        Returns:
            Command bytes
        """
        # Format temperature as 3 digits with leading zeros for positive, minus sign for negative
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
        Parse PRIMARY notification from the refrigerator.

        PRIMARY contains SETPOINTS (in Celsius), not current temps!

        Args:
            data: Raw bytes from characteristic FFF4

        Returns:
            IcecoStatus with setpoints if parsing succeeds, None otherwise
        """
        try:
            # Decode ASCII data
            message = data.decode('ascii').strip()

            # Check if this is a primary status notification
            # Format: ,<L_Setpoint_C>,<R_Setpoint_C>,<BattProtect>,<Voltage>,<PowerStatus>
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

            # Secondary status is parsed separately
            # Unknown notification format
            return None

        except (ValueError, UnicodeDecodeError, IndexError):
            # Parsing failed
            return None

    @staticmethod
    def parse_secondary_status(data: bytes) -> Optional[dict]:
        """
        Parse secondary status notification to extract current temps and unit mode.

        Args:
            data: Raw bytes from characteristic FFF4

        Returns:
            Dict with 'left_setpoint', 'right_setpoint', 'unit_mode', and 'zone_count' if parsing succeeds
            unit_mode: 1 = Celsius, 2 = Fahrenheit (temps are in this unit)
            zone_count: Number extracted from /S00/U/X (likely 1=single-zone, 2=dual-zone)
        """
        try:
            message = data.decode('ascii').strip()

            # Format: /S00/U/<zone_count>,<eco_max>,<unit_mode>,<L_Temp>,<R_Temp>
            if message.startswith('/S00/U/'):
                # Extract zone count from the header (e.g., /S00/U/2)
                header_end = message.index(',')
                header = message[:header_end]  # e.g., "/S00/U/2"
                zone_count = int(header.split('/')[-1])  # Extract the "2"

                parts = message.split(',')
                if len(parts) >= 5:
                    eco_max = int(parts[1])  # 0=ECO, 1=MAX
                    unit_mode = int(parts[2])  # 1=C, 2=F
                    left_setpoint = int(parts[3])
                    right_setpoint = int(parts[4])
                    return {
                        'left_setpoint': left_setpoint,
                        'right_setpoint': right_setpoint,
                        'unit_mode': unit_mode,
                        'zone_count': zone_count,
                        'eco_max': eco_max,
                    }

            return None

        except (ValueError, UnicodeDecodeError, IndexError):
            return None
