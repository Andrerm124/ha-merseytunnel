"""Tests for setting up and tearing down the config entry."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.merseytunnel.api import CannotConnect, InvalidAuth, ParseError
from custom_components.merseytunnel.const import DOMAIN

from .conftest import ACCOUNT_NUMBER, CONFIG_DATA, patch_client


def make_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT_NUMBER, data=CONFIG_DATA)
    entry.add_to_hass(hass)
    return entry


async def setup_entry(hass: HomeAssistant, result) -> MockConfigEntry:
    entry = make_entry(hass)
    with patch_client(result, "coordinator"):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_setup_and_unload(hass: HomeAssistant, account) -> None:
    entry = await setup_entry(hass, account)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.data == account

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_unload_closes_the_portal_session(hass: HomeAssistant, account) -> None:
    entry = await setup_entry(hass, account)
    client = entry.runtime_data.client

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    client.async_close.assert_awaited()


async def test_a_rejected_password_starts_a_reauth_flow(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, InvalidAuth("credentials do not match"))

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["step_id"] for f in flows] == ["reauth_confirm"]


async def test_a_connection_failure_retries_later(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, CannotConnect("Cloudflare challenge"))

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress()


async def test_a_changed_page_retries_rather_than_asking_for_a_password(
    hass: HomeAssistant,
) -> None:
    """A missing balance is a site change, not a credentials problem."""
    entry = await setup_entry(hass, ParseError("no balance on the dashboard"))

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress()


async def test_entities_are_created(hass: HomeAssistant, account) -> None:
    await setup_entry(hass, account)

    assert hass.states.get("sensor.a_test_account_balance") is not None
    assert hass.states.get("binary_sensor.a_test_account_low_balance") is not None
