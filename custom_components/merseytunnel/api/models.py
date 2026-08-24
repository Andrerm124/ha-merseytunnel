"""Data returned by the Mersey Tunnels client."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Account:
    """A snapshot of the account as shown on the dashboard.

    Monetary values are Decimal so that repeated arithmetic on pence-precision
    balances does not drift the way floats do.
    """

    balance: Decimal
    account_number: str
    account_name: str | None = None
    account_type: str | None = None
    low_fund_threshold: Decimal | None = None
    email_statements: bool | None = None

    @property
    def is_low(self) -> bool | None:
        """Whether the balance has dropped to the account's own low-fund threshold.

        None when the site did not give us a threshold to compare against.
        """
        if self.low_fund_threshold is None:
            return None
        return self.balance <= self.low_fund_threshold
