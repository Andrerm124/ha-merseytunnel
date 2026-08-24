"""Standalone client for the Mersey Tunnels Fast Tag portal.

Imports nothing from Home Assistant so it can be exercised on its own.
"""

from .client import BASE_URL, MerseyTunnelsClient
from .exceptions import (
    CannotConnect,
    InvalidAuth,
    LoginThrottled,
    MerseyTunnelsError,
    ParseError,
    SessionExpired,
)
from .models import Account

__all__ = [
    "BASE_URL",
    "Account",
    "CannotConnect",
    "InvalidAuth",
    "LoginThrottled",
    "MerseyTunnelsClient",
    "MerseyTunnelsError",
    "ParseError",
    "SessionExpired",
]
