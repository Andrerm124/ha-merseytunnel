"""The Mersey Tunnels integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import MerseyTunnelsConfigEntry, MerseyTunnelsCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: MerseyTunnelsConfigEntry
) -> bool:
    """Set up Mersey Tunnels from a config entry."""
    coordinator = MerseyTunnelsCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MerseyTunnelsConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
