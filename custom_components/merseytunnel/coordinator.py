"""Polling coordinator for the Mersey Tunnels account."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Account, InvalidAuth, MerseyTunnelsClient, MerseyTunnelsError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type MerseyTunnelsConfigEntry = ConfigEntry[MerseyTunnelsCoordinator]


class MerseyTunnelsCoordinator(DataUpdateCoordinator[Account]):
    """Keeps one account's dashboard reading up to date."""

    config_entry: MerseyTunnelsConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: MerseyTunnelsConfigEntry
    ) -> None:
        """Set up the coordinator and the portal client it polls through."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = MerseyTunnelsClient(
            config_entry.data[CONF_USERNAME],
            config_entry.data[CONF_PASSWORD],
        )

    async def _async_update_data(self) -> Account:
        """Read the dashboard, letting the client re-authenticate as needed."""
        try:
            return await self.client.async_get_account()
        except InvalidAuth as err:
            # Surfaces a "reconfigure" prompt rather than retrying a password the
            # site has already rejected.
            raise ConfigEntryAuthFailed(str(err)) from err
        except MerseyTunnelsError as err:
            raise UpdateFailed(str(err)) from err

    async def async_shutdown(self) -> None:
        """Close the portal session along with the coordinator."""
        await super().async_shutdown()
        await self.client.async_close()
