"""End-to-end checks against the real Mersey Tunnels website.

Excluded from the default test run. To include them:

    pytest -m live

Needs MERSEYTUNNELS_USERNAME and MERSEYTUNNELS_PASSWORD in the environment or in
a .env file at the repo root.
"""

from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.merseytunnel.api import MerseyTunnelsClient
from custom_components.merseytunnel.const import DOMAIN

pytestmark = pytest.mark.live


def _credentials() -> dict[str, str]:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

    username = os.environ.get("MERSEYTUNNELS_USERNAME")
    password = os.environ.get("MERSEYTUNNELS_PASSWORD")
    if not username or not password:
        pytest.skip("No Mersey Tunnels credentials available")
    return {CONF_USERNAME: username, CONF_PASSWORD: password}


@pytest.fixture(name="credentials")
def credentials_fixture() -> dict[str, str]:
    return _credentials()


async def test_client_reads_a_balance(credentials) -> None:
    """The client layer, straight against the site."""
    async with MerseyTunnelsClient(
        credentials[CONF_USERNAME], credentials[CONF_PASSWORD]
    ) as client:
        account = await client.async_get_account()

    assert isinstance(account.balance, Decimal)
    assert account.account_number == credentials[CONF_USERNAME]
    print(f"\n  live balance: £{account.balance}")


async def test_the_integration_sets_up_and_reports_a_balance(
    hass: HomeAssistant, credentials
) -> None:
    """The whole integration, with no mocking anywhere."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=credentials[CONF_USERNAME], data=credentials
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    balance = next(
        s
        for s in hass.states.async_all("sensor")
        if s.entity_id.endswith("_balance")
    )
    assert Decimal(balance.state) == entry.runtime_data.data.balance
    assert balance.attributes["unit_of_measurement"] == "GBP"

    low = next(iter(hass.states.async_all("binary_sensor")))
    print(f"\n  {balance.entity_id} = {balance.state} GBP")
    print(f"  {low.entity_id} = {low.state}")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_the_integration_recovers_from_a_logout(
    hass: HomeAssistant, credentials
) -> None:
    """A real server-side logout mid-session must not break the next poll."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=credentials[CONF_USERNAME], data=credentials
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    coordinator = entry.runtime_data
    first = coordinator.data.balance

    # Log out on the server, exactly as clicking Logout would.
    await coordinator.client._session.get(
        "https://www.merseytunnels.co.uk/logout", allow_redirects=False, timeout=30
    )

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success
    assert coordinator.data.balance == first
    print(f"\n  recovered after logout, balance still £{coordinator.data.balance}")
