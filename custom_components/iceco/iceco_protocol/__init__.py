"""
Iceco Refrigerator Bluetooth Protocol Library

This library provides a Python interface for controlling Iceco dual-zone
Bluetooth refrigerators via BLE using the reverse-engineered protocol.
"""

from .client import IcecoClient
from .protocol import IcecoProtocol, IcecoStatus

__all__ = ["IcecoClient", "IcecoProtocol", "IcecoStatus"]
__version__ = "0.1.0"
