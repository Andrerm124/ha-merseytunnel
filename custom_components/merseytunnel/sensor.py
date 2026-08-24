"""Balance sensor for the Mersey Tunnels integration."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_ACCOUNT_NAME,
    ATTR_ACCOUNT_NUMBER,
    ATTR_ACCOUNT_TYPE,
    ATTR_EMAIL_STATEMENTS,
)
from .coordinator import MerseyTunnelsConfigEntry
from .entity import MerseyTunnelsEntity

BALANCE = SensorEntityDescription(
    key="balance",
    translation_key="balance",
    device_class=SensorDeviceClass.MONETARY,
    state_class=SensorStateClass.TOTAL,
    native_unit_of_measurement="GBP",
)

LOW_FUND_THRESHOLD = SensorEntityDescription(
    key="low_fund_threshold",
    translation_key="low_fund_threshold",
    device_class=SensorDeviceClass.MONETARY,
    native_unit_of_measurement="GBP",
    entity_registry_enabled_default=False,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MerseyTunnelsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the account sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            MerseyTunnelsBalanceSensor(coordinator),
            MerseyTunnelsThresholdSensor(coordinator),
        ]
    )


class MerseyTunnelsBalanceSensor(MerseyTunnelsEntity, SensorEntity):
    """The current Fast Tag account balance."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, BALANCE)

    @property
    def native_value(self) -> Decimal:
        """The balance as shown on the dashboard."""
        return self.account.balance

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Account details from the same dashboard card."""
        return {
            ATTR_ACCOUNT_NUMBER: self.account.account_number,
            ATTR_ACCOUNT_NAME: self.account.account_name,
            ATTR_ACCOUNT_TYPE: self.account.account_type,
            ATTR_EMAIL_STATEMENTS: self.account.email_statements,
        }


class MerseyTunnelsThresholdSensor(MerseyTunnelsEntity, SensorEntity):
    """The account's own low-fund threshold.

    Disabled by default: it is a setting rather than a reading, and it only
    changes when the account holder edits it on the portal.
    """

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, LOW_FUND_THRESHOLD)

    @property
    def native_value(self) -> Decimal | None:
        return self.account.low_fund_threshold

    @property
    def available(self) -> bool:
        return super().available and self.account.low_fund_threshold is not None
