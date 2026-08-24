"""Shared entity base for the Mersey Tunnels integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Account
from .api.client import BASE_URL, DASHBOARD_PATH
from .const import DOMAIN
from .coordinator import MerseyTunnelsCoordinator


class MerseyTunnelsEntity(CoordinatorEntity[MerseyTunnelsCoordinator]):
    """Base entity tied to one Fast Tag account."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MerseyTunnelsCoordinator, description: EntityDescription
    ) -> None:
        """Attach the entity to the account's device."""
        super().__init__(coordinator)
        self.entity_description = description

        account = coordinator.data
        self._attr_unique_id = f"{account.account_number}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account.account_number)},
            name=account.account_name or f"Account {account.account_number}",
            manufacturer="Merseytravel",
            model=f"{account.account_type} Fast Tag account"
            if account.account_type
            else "Fast Tag account",
            configuration_url=f"{BASE_URL}{DASHBOARD_PATH}",
        )

    @property
    def account(self) -> Account:
        """The most recent dashboard reading."""
        return self.coordinator.data
