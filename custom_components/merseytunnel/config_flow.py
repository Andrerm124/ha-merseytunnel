"""Config flow for the Mersey Tunnels integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .api import (
    Account,
    CannotConnect,
    InvalidAuth,
    LoginThrottled,
    MerseyTunnelsClient,
    ParseError,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): cv.string})


async def _async_validate(username: str, password: str) -> Account:
    """Sign in once to prove the credentials work.

    Raises the client's own exceptions, which the caller maps onto form errors.
    """
    async with MerseyTunnelsClient(username, password) as client:
        return await client.async_validate_credentials()


class MerseyTunnelsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup and reauthentication."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect an account number and password, then verify them."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            try:
                account = await _async_validate(username, user_input[CONF_PASSWORD])
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except LoginThrottled:
                errors["base"] = "throttled"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except ParseError:
                errors["base"] = "unexpected_page"
            except Exception:
                _LOGGER.exception("Unexpected error validating Mersey Tunnels login")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(account.account_number or username)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=account.account_name or f"Account {account.account_number}",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the site rejected the stored password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take a new password for the account already configured."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _async_validate(
                    entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except LoginThrottled:
                errors["base"] = "throttled"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except ParseError:
                errors["base"] = "unexpected_page"
            except Exception:
                _LOGGER.exception("Unexpected error reauthenticating Mersey Tunnels")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={CONF_USERNAME: entry.data[CONF_USERNAME]},
            errors=errors,
        )
