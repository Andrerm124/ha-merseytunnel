"""Async client for the Mersey Tunnels Fast Tag account portal.

The portal is a Laravel app with no public API and no OAuth, so there are no
refresh tokens to manage. Authentication is a plain session cookie
(``mersey_tunnels_session``) obtained by posting the sign-in form, and it lapses
after roughly two hours of inactivity. The client therefore treats a redirect
away from a protected page as "session gone", signs in again, and retries once.

The site also sits behind Cloudflare bot management, which rejects clients whose
TLS handshake does not look like a browser's. ``curl_cffi`` is used instead of
aiohttp because it reproduces a real Chrome fingerprint; a stock HTTP client gets
a 403 challenge page on every request.
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import TracebackType
from typing import Any, Final, Self
from urllib.parse import urlsplit

from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession, Response

from .exceptions import (
    CannotConnect,
    InvalidAuth,
    LoginThrottled,
    MerseyTunnelsError,
    ParseError,
    SessionExpired,
)
from .models import Account
from .parser import extract_csrf_token, extract_login_error, is_logged_in, parse_account

_LOGGER = logging.getLogger(__name__)

BASE_URL: Final = "https://www.merseytunnels.co.uk"
LOGIN_PATH: Final = "/login"
DASHBOARD_PATH: Final = "/dashboard"

BROWSER_IMPERSONATE: Final = "chrome"
REQUEST_TIMEOUT: Final = 30
REDIRECT_CODES: Final = frozenset({301, 302, 303, 307, 308})

# Laravel throttles sign-ins, and a wrong password is not going to start working
# on its own, so a rejected or throttled attempt puts sign-in on hold for a
# while. Successful sign-ins are never held back: re-authenticating after the
# session lapses is the normal path and must not be blocked.
LOGIN_FAILURE_BACKOFF: Final = 300.0
DEFAULT_THROTTLE_BACKOFF: Final = 60


class MerseyTunnelsClient:
    """Signs in to the tunnels portal and reads the account balance."""

    def __init__(
        self,
        username: str,
        password: str,
        *,
        session: AsyncSession | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        """Store credentials. Pass ``session`` to reuse an existing one."""
        self._username = username
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._owns_session = session is None
        self._lock = asyncio.Lock()
        self._login_blocked_until = 0.0
        self._authenticated = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.async_close()

    @property
    def is_authenticated(self) -> bool:
        """Whether we believe we currently hold a usable session."""
        return self._authenticated

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _ensure_session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(impersonate=BROWSER_IMPERSONATE)
            self._owns_session = True
        return self._session

    async def async_close(self) -> None:
        """Release the HTTP session if this client created it."""
        if self._session is not None and self._owns_session:
            await self._session.close()
        self._session = None
        self._authenticated = False

    async def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        """Issue a request, translating transport failures into CannotConnect."""
        session = self._ensure_session()
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        kwargs.setdefault("allow_redirects", False)
        try:
            return await session.request(method, self._url(path), **kwargs)
        except CurlError as err:
            raise CannotConnect(
                f"Could not reach {self._base_url}{path}: {err}"
            ) from err

    @staticmethod
    def _redirect_path(response: Response) -> str | None:
        """The path a redirect points at, or None if this is not a redirect."""
        if response.status_code not in REDIRECT_CODES:
            return None
        location = response.headers.get("location")
        if not location:
            return ""
        return urlsplit(location).path or "/"

    async def async_login(self) -> None:
        """Sign in and hold the resulting session cookie.

        Raises InvalidAuth on rejected credentials, LoginThrottled when the site
        rate-limits us, and CannotConnect on transport or Cloudflare failures.
        """
        async with self._lock:
            await self._login_locked()

    async def _login_locked(self) -> None:
        held_for = self._login_blocked_until - time.monotonic()
        if held_for > 0:
            raise LoginThrottled(
                "Sign-in is on hold after an earlier attempt was rejected",
                retry_after=int(held_for) + 1,
            )
        self._authenticated = False

        try:
            await self._perform_login()
        except (InvalidAuth, LoginThrottled) as err:
            self._login_blocked_until = time.monotonic() + (
                err.retry_after
                if isinstance(err, LoginThrottled) and err.retry_after
                else LOGIN_FAILURE_BACKOFF
            )
            raise

        self._login_blocked_until = 0.0
        self._authenticated = True
        _LOGGER.debug("Signed in to Mersey Tunnels as %s", self._username)

    async def _perform_login(self) -> None:
        """Post the sign-in form. Raises unless the session cookie is now valid."""
        landing = await self._request("GET", "/", allow_redirects=True)
        self._raise_for_challenge(landing)
        token = extract_csrf_token(landing.text)

        response = await self._request(
            "POST",
            LOGIN_PATH,
            data={
                "_token": token,
                "username": self._username,
                "password": self._password,
            },
            headers={
                "Referer": f"{self._base_url}/",
                "Origin": self._base_url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        if response.status_code == 429:
            raise LoginThrottled(
                "The site is rate-limiting sign-in attempts",
                retry_after=self._retry_after(response),
            )

        target = self._redirect_path(response)
        if target == DASHBOARD_PATH:
            return

        # A rejected login bounces back to the landing page with the error in the
        # session flash bag, so the reason is only visible if we follow it.
        if target is not None:
            raise InvalidAuth(await self._describe_login_failure())

        self._raise_for_challenge(response)
        raise CannotConnect(
            f"Unexpected response {response.status_code} from the sign-in form"
        )

    async def _describe_login_failure(self) -> str:
        """Fetch the landing page and quote the site's own error message."""
        try:
            landing = await self._request("GET", "/", allow_redirects=True)
        except MerseyTunnelsError:
            return "Sign-in was rejected"
        return extract_login_error(landing.text) or "Sign-in was rejected"

    @staticmethod
    def _retry_after(response: Response) -> int:
        raw = response.headers.get("retry-after")
        try:
            return int(raw) if raw else DEFAULT_THROTTLE_BACKOFF
        except ValueError:
            return DEFAULT_THROTTLE_BACKOFF

    @staticmethod
    def _raise_for_challenge(response: Response) -> None:
        """Turn a Cloudflare interstitial into a clear connection error."""
        if response.status_code in (403, 503) and response.headers.get("cf-mitigated"):
            raise CannotConnect(
                "Cloudflare served a bot challenge instead of the page; "
                "the browser impersonation profile may need updating"
            )
        if response.status_code >= 500:
            raise CannotConnect(f"The site returned {response.status_code}")

    async def _fetch_dashboard(self) -> str:
        """Load the dashboard, raising SessionExpired if we are signed out."""
        response = await self._request("GET", DASHBOARD_PATH, allow_redirects=False)
        self._raise_for_challenge(response)

        if self._redirect_path(response) is not None:
            self._authenticated = False
            raise SessionExpired(
                "The dashboard redirected away; the session has lapsed"
            )

        if response.status_code != 200:
            raise CannotConnect(f"Dashboard returned {response.status_code}")

        if not is_logged_in(response.text):
            self._authenticated = False
            raise SessionExpired("The dashboard rendered as a signed-out visitor")

        self._authenticated = True
        return response.text

    async def async_get_account(self) -> Account:
        """Return the current account snapshot, signing in again if needed.

        Handles the two ways the portal can log us out: an outright redirect, and
        a page that renders as an anonymous visitor.
        """
        async with self._lock:
            if not self._authenticated:
                await self._login_locked()

            try:
                html = await self._fetch_dashboard()
            except SessionExpired:
                _LOGGER.debug("Session lapsed, signing in again")
                await self._login_locked()
                html = await self._fetch_dashboard()

            return parse_account(html)

    async def async_validate_credentials(self) -> Account:
        """Prove the credentials work and return what we can read.

        Used by the config flow so setup fails fast on a bad account number
        rather than at the first poll.
        """
        await self.async_login()
        async with self._lock:
            return parse_account(await self._fetch_dashboard())


__all__ = [
    "BASE_URL",
    "Account",
    "CannotConnect",
    "InvalidAuth",
    "LoginThrottled",
    "MerseyTunnelsClient",
    "MerseyTunnelsError",
    "ParseError",
    "SessionExpired",
]
