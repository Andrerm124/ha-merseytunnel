"""Exceptions raised by the Mersey Tunnels API client."""


class MerseyTunnelsError(Exception):
    """Base class for all errors raised by this client."""


class CannotConnect(MerseyTunnelsError):
    """The site could not be reached, or returned an unusable response."""


class InvalidAuth(MerseyTunnelsError):
    """The account number or password was rejected.

    This is terminal: retrying with the same credentials will not help.
    """


class LoginThrottled(MerseyTunnelsError):
    """Laravel's login rate limiter rejected the attempt.

    Carries the number of seconds to wait before trying again, when the site
    tells us.
    """

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class SessionExpired(MerseyTunnelsError):
    """The session cookie is no longer valid and a fresh login is needed."""


class ParseError(MerseyTunnelsError):
    """The dashboard loaded but did not contain the fields we expect.

    Usually means the site markup changed.
    """
