"""Tests for the balance sensors."""

from __future__ import annotations

from decimal import Decimal

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.merseytunnel.api import CannotConnect
from custom_components.merseytunnel.const import DOMAIN

from .conftest import ACCOUNT_NUMBER, CONFIG_DATA, make_account, patch_client

BALANCE = "sensor.a_test_account_balance"
THRESHOLD = "sensor.a_test_account_low_fund_threshold"


async def setup_entry(hass: HomeAssistant, result) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT_NUMBER, data=CONFIG_DATA)
    entry.add_to_hass(hass)
    with patch_client(result, "coordinator"):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_balance_state_and_attributes(hass: HomeAssistant, account) -> None:
    await setup_entry(hass, account)
    state = hass.states.get(BALANCE)

    assert state.state == "8.90"
    assert state.attributes["device_class"] == "monetary"
    assert state.attributes["state_class"] == "total"
    assert state.attributes["unit_of_measurement"] == "GBP"
    assert state.attributes["account_number"] == ACCOUNT_NUMBER
    assert state.attributes["account_name"] == "A Test Account"
    assert state.attributes["account_type"] == "Personal"
    assert state.attributes["email_statements"] is False


async def test_a_zero_balance_is_reported_not_dropped(hass: HomeAssistant) -> None:
    """A £0.00 balance is meaningful and must not read as unknown."""
    await setup_entry(hass, make_account(balance="0.00"))
    assert hass.states.get(BALANCE).state == "0.00"


async def test_a_negative_balance_is_reported(hass: HomeAssistant) -> None:
    await setup_entry(hass, make_account(balance="-1.60"))
    assert hass.states.get(BALANCE).state == "-1.60"


async def test_unique_ids_are_scoped_to_the_account(
    hass: HomeAssistant, account
) -> None:
    await setup_entry(hass, account)
    registry = er.async_get(hass)

    assert registry.async_get(BALANCE).unique_id == f"{ACCOUNT_NUMBER}_balance"


async def test_the_threshold_sensor_is_off_by_default(
    hass: HomeAssistant, account
) -> None:
    """It is a setting rather than a reading, so it ships disabled."""
    await setup_entry(hass, account)
    registry = er.async_get(hass)

    entry = registry.async_get(THRESHOLD)
    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(THRESHOLD) is None


async def test_entities_share_one_device(hass: HomeAssistant, account) -> None:
    config_entry = await setup_entry(hass, account)
    devices = dr.async_get(hass)

    device = devices.async_get_device(identifiers={(DOMAIN, ACCOUNT_NUMBER)})
    assert device is not None
    assert device.name == "A Test Account"
    assert device.manufacturer == "Merseytravel"
    assert device.model == "Personal Fast Tag account"
    assert device.config_entries == {config_entry.entry_id}


async def test_the_balance_goes_unavailable_when_a_poll_fails(
    hass: HomeAssistant, account
) -> None:
    entry = await setup_entry(hass, account)
    assert hass.states.get(BALANCE).state == "8.90"

    entry.runtime_data.client.async_get_account.side_effect = CannotConnect("offline")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(BALANCE).state == STATE_UNAVAILABLE


async def test_a_new_reading_updates_the_state(hass: HomeAssistant, account) -> None:
    entry = await setup_entry(hass, account)

    entry.runtime_data.client.async_get_account.side_effect = None
    entry.runtime_data.client.async_get_account.return_value = make_account(
        balance="25.40"
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(BALANCE).state == "25.40"
    assert entry.runtime_data.data.balance == Decimal("25.40")
