"""Scraping helpers for the Mersey Tunnels dashboard.

The dashboard is server-rendered Laravel Blade output. Account fields appear as
``<li>Label: <b>value</b></li>`` inside cards, which is what most of this module
keys off.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

from bs4 import BeautifulSoup

from .exceptions import ParseError
from .models import Account

_CSRF_INPUT = {"name": "_token"}
_MONEY = re.compile(r"-?[\d,]+(?:\.\d+)?")


def parse_html(html: str) -> BeautifulSoup:
    """Parse a page with the stdlib HTML parser so we need no lxml build."""
    return BeautifulSoup(html, "html.parser")


def extract_csrf_token(html: str) -> str:
    """Pull the ``_token`` value out of any form on the page."""
    field = parse_html(html).find("input", attrs=_CSRF_INPUT)
    if field is None or not field.get("value"):
        raise ParseError("No CSRF token found on the page")
    return str(field["value"])


def is_logged_in(html: str) -> bool:
    """Whether the page was rendered for a signed-in visitor.

    The site marks the header panel ``logged-in`` only once a session exists.
    """
    panel = parse_html(html).select_one(".user-panel")
    return panel is not None and "logged-in" in panel.get("class", [])


def extract_login_error(html: str) -> str | None:
    """Return the validation message shown after a rejected login, if any.

    Laravel renders a generic heading above a list holding the actual reason, so
    the list items are preferred and the heading is only a fallback.
    """
    soup = parse_html(html)

    reasons = [
        text
        for node in soup.select(
            "li[aria-live=assertive], ul.text-red-600 li,"
            " .invalid-feedback, [role=alert]"
        )
        if (text := " ".join(node.get_text(" ", strip=True).split()))
    ]
    if reasons:
        return "; ".join(dict.fromkeys(reasons))

    for node in soup.select(".text-red-600"):
        if text := " ".join(node.get_text(" ", strip=True).split()):
            return text
    return None


def parse_money(raw: str | None) -> Decimal | None:
    """Turn ``£8.90`` or ``-£1,234.50`` into a Decimal.

    Returns None when there is no number to read, so callers can tell "field
    absent" apart from "field is zero".
    """
    if not raw:
        return None
    negative = "-" in raw or ("(" in raw and ")" in raw)
    # The site uses an ASCII hyphen, but normalise the Unicode minus sign too so a
    # markup change does not silently flip a negative balance positive.
    match = _MONEY.search(raw.replace("−", "-"))  # noqa: RUF001
    if match is None:
        return None
    try:
        value = Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None
    return -value if negative and value > 0 else value


def _labelled_values(soup: BeautifulSoup) -> dict[str, str]:
    """Collect every ``Label: value`` pair from the dashboard's card lists.

    Later cards repeat some labels with the same values, so first write wins and
    duplicates are ignored.
    """
    values: dict[str, str] = {}
    for item in soup.select("li"):
        strong = item.find(["b", "strong"])
        if strong is None:
            continue
        label = item.get_text(" ", strip=True)
        value = strong.get_text(" ", strip=True)
        label = label[: len(label) - len(value)].rstrip().rstrip(":").strip().lower()
        if label and label not in values:
            values[label] = value
    return values


def _nav_balance(soup: BeautifulSoup) -> Decimal | None:
    """Read the balance from the header widget, used as a fallback."""
    widget = soup.select_one(".user-balance")
    return parse_money(widget.get_text(" ", strip=True)) if widget else None


def _as_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    lookup = {"yes": True, "true": True, "no": False, "false": False}
    return lookup.get(raw.strip().lower())


def parse_account(html: str) -> Account:
    """Build an :class:`Account` from the dashboard HTML.

    Raises ParseError if no balance can be found, since that is the one field
    the integration cannot do without.
    """
    soup = parse_html(html)
    fields = _labelled_values(soup)

    balance = parse_money(fields.get("account balance"))
    if balance is None:
        balance = _nav_balance(soup)
    if balance is None:
        raise ParseError("Could not find an account balance on the dashboard")

    return Account(
        balance=balance,
        account_number=fields.get("account number", ""),
        account_name=fields.get("account name"),
        account_type=fields.get("account type"),
        low_fund_threshold=parse_money(fields.get("low fund threshold")),
        email_statements=_as_bool(fields.get("email statements")),
    )
