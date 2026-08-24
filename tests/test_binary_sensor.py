"""Tests for the low balance sensor."""

from __future__ import annotations

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.merseytunnel.const import DOMAIN

from .conftest import ACCOUNT_NUMBER, CONFIG_DATA, make_account, patch_client

LOW_BALANCE = "binary_sensor.a_test_account_low_balance"


async def setup_entry(hass: HomeAssistant, result) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT_NUMBER, data=CONFIG_DATA)
    entry.add_to_hass(hass)
    with patch_client(result, "coordinator"):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_on_when_the_balance_is_below_the_threshold(hass: HomeAssistant) -> None:
    await setup_entry(hass, make_account(balance="8.90", threshold="10.00"))
    state = hass.states.get(LOW_BALANCE)

    assert state.state == STATE_ON
    assert state.attributes["device_class"] == "problem"


async def test_on_when_the_balance_exactly_meets_the_threshold(
    hass: HomeAssistant,
) -> None:
    """The portal warns at the threshold, so this integration matches it."""
    await setup_entry(hass, make_account(balance="10.00", threshold="10.00"))
    assert hass.states.get(LOW_BALANCE).state == STATE_ON


async def test_off_when_the_balance_is_above_the_threshold(hass: HomeAssistant) -> None:
    await setup_entry(hass, make_account(balance="25.00", threshold="10.00"))
    assert hass.states.get(LOW_BALANCE).state == STATE_OFF


async def test_unavailable_without_a_threshold_to_compare_against(
    hass: HomeAssistant,
) -> None:
    await setup_entry(hass, make_account(balance="8.90", threshold=None))
    assert hass.states.get(LOW_BALANCE).state == STATE_UNAVAILABLE
