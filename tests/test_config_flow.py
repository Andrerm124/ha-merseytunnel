"""Tests for the Mersey Tunnels config flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.merseytunnel.api import (
    CannotConnect,
    InvalidAuth,
    LoginThrottled,
    ParseError,
)
from custom_components.merseytunnel.const import DOMAIN

from .conftest import ACCOUNT_NUMBER, CONFIG_DATA, PASSWORD, make_account, patch_client


async def start_flow(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def test_form_is_shown_first(hass: HomeAssistant) -> None:
    result = await start_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_successful_setup(hass: HomeAssistant, account) -> None:
    result = await start_flow(hass)

    with patch_client(account):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CONFIG_DATA
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "A Test Account"
    assert result["data"] == {
        CONF_USERNAME: ACCOUNT_NUMBER,
        CONF_PASSWORD: PASSWORD,
    }
    assert result["result"].unique_id == ACCOUNT_NUMBER


async def test_account_number_is_trimmed(hass: HomeAssistant, account) -> None:
    """Copy-pasting the number from the website tends to bring whitespace along."""
    result = await start_flow(hass)

    with patch_client(account) as mock:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**CONFIG_DATA, CONF_USERNAME: f"  {ACCOUNT_NUMBER} "}
        )
        await hass.async_block_till_done()

    assert result["data"][CONF_USERNAME] == ACCOUNT_NUMBER
    assert mock.call_args.args[0] == ACCOUNT_NUMBER


async def test_title_falls_back_to_the_account_number(hass: HomeAssistant) -> None:
    result = await start_flow(hass)

    with patch_client(make_account(name=None)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CONFIG_DATA
        )
        await hass.async_block_till_done()

    assert result["title"] == f"Account {ACCOUNT_NUMBER}"


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (InvalidAuth("nope"), "invalid_auth"),
        (LoginThrottled("hold on", retry_after=60), "throttled"),
        (CannotConnect("offline"), "cannot_connect"),
        (ParseError("no balance"), "unexpected_page"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_errors_are_surfaced_on_the_form(
    hass: HomeAssistant, raised, expected
) -> None:
    result = await start_flow(hass)

    with patch_client(raised):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CONFIG_DATA
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": expected}


async def test_the_form_can_be_corrected_and_resubmitted(
    hass: HomeAssistant, account
) -> None:
    result = await start_flow(hass)

    with patch_client(InvalidAuth("nope")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**CONFIG_DATA, CONF_PASSWORD: "wrong"}
        )
    assert result["errors"] == {"base": "invalid_auth"}

    with patch_client(account):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CONFIG_DATA
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_the_same_account_cannot_be_added_twice(
    hass: HomeAssistant, account
) -> None:
    MockConfigEntry(
        domain=DOMAIN, unique_id=ACCOUNT_NUMBER, data=CONFIG_DATA
    ).add_to_hass(hass)

    result = await start_flow(hass)
    with patch_client(account):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CONFIG_DATA
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_the_stored_password(hass: HomeAssistant, account) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT_NUMBER, data=CONFIG_DATA)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    # Home Assistant merges its own "name" placeholder in alongside ours.
    assert result["description_placeholders"][CONF_USERNAME] == ACCOUNT_NUMBER

    with patch_client(account), patch_client(account, "coordinator"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "a-new-password"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "a-new-password"
    assert entry.data[CONF_USERNAME] == ACCOUNT_NUMBER


async def test_reauth_reports_a_still_wrong_password(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT_NUMBER, data=CONFIG_DATA)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch_client(InvalidAuth("still wrong")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "also-wrong"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_PASSWORD] == PASSWORD


async def test_reauth_keeps_the_original_account_number(
    hass: HomeAssistant, account
) -> None:
    """Reauth only asks for a password, so the number must not be lost."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT_NUMBER, data=CONFIG_DATA)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch_client(account) as mock, patch_client(account, "coordinator"):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "fresh"}
        )
        await hass.async_block_till_done()

    assert mock.call_args.args == (ACCOUNT_NUMBER, "fresh")
