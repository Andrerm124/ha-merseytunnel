"""Tests for the authentication and session-recovery logic."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from custom_components.merseytunnel.api.client import BASE_URL, MerseyTunnelsClient
from custom_components.merseytunnel.api.exceptions import (
    CannotConnect,
    InvalidAuth,
    LoginThrottled,
)


class FakeResponse:
    """Stands in for a curl_cffi Response."""

    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


class FakeSession:
    """Replays scripted responses and records what was asked for."""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[tuple[str, str, dict]] = []
        self.closed = False

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self._handler(method, url, kwargs, len(self.calls) - 1)

    async def close(self):
        self.closed = True

    def paths(self, method=None):
        return [
            url.replace(BASE_URL, "") or "/"
            for m, url, _ in self.calls
            if method is None or m == method
        ]

    @property
    def login_count(self):
        return self.paths("POST").count("/login")


def make_client(handler, **kwargs):
    session = FakeSession(handler)
    client = MerseyTunnelsClient("000000", "pw", session=session, **kwargs)
    return client, session


def ok_login_then(*dashboard_responses, landing_html, dashboard_html):
    """Handler where every login succeeds and dashboards come from a queue."""
    queue = list(dashboard_responses)

    def handler(method, url, kwargs, index):
        path = url.replace(BASE_URL, "") or "/"
        if path == "/login" and method == "POST":
            return FakeResponse(302, headers={"Location": f"{BASE_URL}/dashboard"})
        if path == "/dashboard":
            return queue.pop(0) if queue else FakeResponse(200, dashboard_html)
        return FakeResponse(200, landing_html)

    return handler


@pytest.mark.asyncio
async def test_login_then_read_balance(landing_html, dashboard_html):
    client, session = make_client(
        ok_login_then(landing_html=landing_html, dashboard_html=dashboard_html)
    )
    account = await client.async_get_account()

    assert account.balance == Decimal("8.90")
    assert client.is_authenticated
    assert session.paths() == ["/", "/login", "/dashboard"]


@pytest.mark.asyncio
async def test_login_posts_the_form_token_and_credentials(landing_html, dashboard_html):
    client, session = make_client(
        ok_login_then(landing_html=landing_html, dashboard_html=dashboard_html)
    )
    await client.async_login()

    _, _, kwargs = next(c for c in session.calls if c[0] == "POST")
    assert kwargs["data"] == {
        "_token": "tcFvNhxnZrkuTMIMU8GMvx8GBl9yYBQEIdmuiJ9X",
        "username": "000000",
        "password": "pw",
    }
    assert kwargs["headers"]["Referer"] == f"{BASE_URL}/"


@pytest.mark.asyncio
async def test_second_poll_reuses_the_session(landing_html, dashboard_html):
    client, session = make_client(
        ok_login_then(landing_html=landing_html, dashboard_html=dashboard_html)
    )
    await client.async_get_account()
    await client.async_get_account()

    assert session.login_count == 1
    assert session.paths().count("/dashboard") == 2


@pytest.mark.asyncio
async def test_redirect_off_the_dashboard_triggers_a_fresh_login(
    landing_html, dashboard_html
):
    client, session = make_client(
        ok_login_then(
            FakeResponse(200, dashboard_html),
            FakeResponse(302, headers={"Location": BASE_URL}),
            landing_html=landing_html,
            dashboard_html=dashboard_html,
        )
    )
    await client.async_get_account()

    account = await client.async_get_account()

    assert account.balance == Decimal("8.90")
    assert session.login_count == 2
    assert client.is_authenticated


@pytest.mark.asyncio
async def test_signed_out_dashboard_triggers_a_fresh_login(
    landing_html, dashboard_html
):
    """A 200 that renders as an anonymous visitor also counts as logged out."""
    client, session = make_client(
        ok_login_then(
            FakeResponse(200, landing_html),
            landing_html=landing_html,
            dashboard_html=dashboard_html,
        )
    )
    account = await client.async_get_account()

    assert account.balance == Decimal("8.90")
    assert session.login_count == 2


@pytest.mark.asyncio
async def test_bad_credentials_raise_invalid_auth(login_error_html):
    def handler(method, url, kwargs, index):
        path = url.replace(BASE_URL, "") or "/"
        if path == "/login":
            return FakeResponse(302, headers={"Location": f"{BASE_URL}/"})
        return FakeResponse(200, login_error_html)

    client, session = make_client(handler)
    with pytest.raises(InvalidAuth, match="do not match our records"):
        await client.async_get_account()

    assert not client.is_authenticated
    assert session.login_count == 1


@pytest.mark.asyncio
async def test_login_rate_limit_is_surfaced(landing_html):
    def handler(method, url, kwargs, index):
        path = url.replace(BASE_URL, "") or "/"
        if path == "/login":
            return FakeResponse(429, headers={"Retry-After": "45"})
        return FakeResponse(200, landing_html)

    client, _ = make_client(handler)
    with pytest.raises(LoginThrottled) as err:
        await client.async_login()

    assert err.value.retry_after == 45


@pytest.mark.asyncio
async def test_successful_logins_are_never_held_back(landing_html):
    """Re-authenticating after a lapse is the normal path, not something to throttle."""

    def handler(method, url, kwargs, index):
        path = url.replace(BASE_URL, "") or "/"
        if path == "/login":
            return FakeResponse(302, headers={"Location": f"{BASE_URL}/dashboard"})
        return FakeResponse(200, landing_html)

    client, session = make_client(handler)
    await client.async_login()
    await client.async_login()

    assert session.login_count == 2


@pytest.mark.asyncio
async def test_a_rejected_login_puts_further_attempts_on_hold(login_error_html):
    """Guards against re-trying a wrong password on every polling cycle."""

    def handler(method, url, kwargs, index):
        path = url.replace(BASE_URL, "") or "/"
        if path == "/login":
            return FakeResponse(302, headers={"Location": f"{BASE_URL}/"})
        return FakeResponse(200, login_error_html)

    client, session = make_client(handler)
    with pytest.raises(InvalidAuth):
        await client.async_login()

    with pytest.raises(LoginThrottled) as err:
        await client.async_login()

    assert err.value.retry_after is not None
    assert session.login_count == 1


@pytest.mark.asyncio
async def test_a_throttled_login_honours_the_sites_retry_after(landing_html):
    def handler(method, url, kwargs, index):
        path = url.replace(BASE_URL, "") or "/"
        if path == "/login":
            return FakeResponse(429, headers={"Retry-After": "45"})
        return FakeResponse(200, landing_html)

    client, session = make_client(handler)
    with pytest.raises(LoginThrottled):
        await client.async_login()

    with pytest.raises(LoginThrottled) as err:
        await client.async_login()

    assert 40 <= err.value.retry_after <= 46
    assert session.login_count == 1


@pytest.mark.asyncio
async def test_cloudflare_challenge_reads_as_a_connection_problem():
    def handler(method, url, kwargs, index):
        return FakeResponse(403, "Just a moment...", {"cf-mitigated": "challenge"})

    client, _ = make_client(handler)
    with pytest.raises(CannotConnect, match="Cloudflare"):
        await client.async_login()


@pytest.mark.asyncio
async def test_server_error_reads_as_a_connection_problem():
    def handler(method, url, kwargs, index):
        return FakeResponse(503, "")

    client, _ = make_client(handler)
    with pytest.raises(CannotConnect):
        await client.async_login()


@pytest.mark.asyncio
async def test_concurrent_polls_only_log_in_once(landing_html, dashboard_html):
    client, session = make_client(
        ok_login_then(landing_html=landing_html, dashboard_html=dashboard_html)
    )
    results = await asyncio.gather(*(client.async_get_account() for _ in range(4)))

    assert {r.balance for r in results} == {Decimal("8.90")}
    assert session.login_count == 1


@pytest.mark.asyncio
async def test_injected_sessions_are_left_open(landing_html, dashboard_html):
    client, session = make_client(
        ok_login_then(landing_html=landing_html, dashboard_html=dashboard_html)
    )
    async with client:
        await client.async_get_account()

    assert session.closed is False
