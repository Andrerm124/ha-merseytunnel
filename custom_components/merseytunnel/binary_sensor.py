"""Low balance binary sensor for the Mersey Tunnels integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MerseyTunnelsConfigEntry
from .entity import MerseyTunnelsEntity

LOW_BALANCE = BinarySensorEntityDescription(
    key="low_balance",
    translation_key="low_balance",
    device_class=BinarySensorDeviceClass.PROBLEM,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MerseyTunnelsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the low balance sensor."""
    async_add_entities([MerseyTunnelsLowBalanceSensor(entry.runtime_data)])


class MerseyTunnelsLowBalanceSensor(MerseyTunnelsEntity, BinarySensorEntity):
    """Whether the balance has reached the account's own low-fund threshold.

    The threshold comes from the portal rather than this integration, so the
    trigger point matches the site's own warning.
    """

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, LOW_BALANCE)

    @property
    def is_on(self) -> bool | None:
        return self.account.is_low

    @property
    def available(self) -> bool:
        """Unavailable when the dashboard gave us no threshold to compare against."""
        return super().available and self.account.is_low is not None
