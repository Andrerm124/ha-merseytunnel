"""Constants for the Mersey Tunnels integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "merseytunnel"

CONF_ACCOUNT_NUMBER: Final = "account_number"

# The balance only moves when a journey is billed or the account is topped up,
# and every poll costs a scrape of a rate-limited site, so this is deliberately
# slow. Users who want a reading sooner can call homeassistant.update_entity.
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=30)

ATTR_ACCOUNT_NAME: Final = "account_name"
ATTR_ACCOUNT_NUMBER: Final = "account_number"
ATTR_ACCOUNT_TYPE: Final = "account_type"
ATTR_EMAIL_STATEMENTS: Final = "email_statements"
