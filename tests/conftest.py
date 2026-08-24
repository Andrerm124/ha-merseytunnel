"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/merseytunnel in every test."""
    yield


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture(name="dashboard_html")
def dashboard_html_fixture() -> str:
    return fixture("dashboard.html")


@pytest.fixture(name="landing_html")
def landing_html_fixture() -> str:
    return fixture("landing.html")


@pytest.fixture(name="login_error_html")
def login_error_html_fixture() -> str:
    return fixture("landing_login_error.html")


# --- Home Assistant side helpers -------------------------------------------

from decimal import Decimal  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from custom_components.merseytunnel.api import Account  # noqa: E402

ACCOUNT_NUMBER = "000000"
PASSWORD = "hunter2"

CONFIG_DATA = {"username": ACCOUNT_NUMBER, "password": PASSWORD}


def make_account(
    balance="8.90", threshold="10.00", *, name="A Test Account", number=ACCOUNT_NUMBER
) -> Account:
    """Build an Account the way the parser would."""
    return Account(
        balance=Decimal(balance),
        account_number=number,
        account_name=name,
        account_type="Personal",
        low_fund_threshold=Decimal(threshold) if threshold is not None else None,
        email_statements=False,
    )


@pytest.fixture(name="account")
def account_fixture() -> Account:
    return make_account()


class FakeClient:
    """Async-context-manager stand-in for MerseyTunnelsClient."""

    def __init__(self, result):
        self._result = result
        self.async_validate_credentials = AsyncMock(side_effect=self._resolve)
        self.async_get_account = AsyncMock(side_effect=self._resolve)
        self.async_close = AsyncMock()

    async def _resolve(self):
        if isinstance(self._result, list):
            outcome = self._result.pop(0) if len(self._result) > 1 else self._result[0]
        else:
            outcome = self._result
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


def patch_client(result, target="config_flow"):
    """Patch MerseyTunnelsClient in the config flow or the coordinator."""
    client = FakeClient(result)
    return patch(
        f"custom_components.merseytunnel.{target}.MerseyTunnelsClient",
        return_value=client,
    )
