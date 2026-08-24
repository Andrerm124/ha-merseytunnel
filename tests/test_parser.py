"""Tests for the dashboard scraping helpers."""

from __future__ import annotations

from decimal import Decimal

import pytest

from custom_components.merseytunnel.api.exceptions import ParseError
from custom_components.merseytunnel.api.parser import (
    extract_csrf_token,
    extract_login_error,
    is_logged_in,
    parse_account,
    parse_money,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("£8.90", Decimal("8.90")),
        ("Account Balance: £8.90", Decimal("8.90")),
        ("£1,234.50", Decimal("1234.50")),
        ("£0.00", Decimal("0")),
        ("-£1.60", Decimal("-1.60")),
        ("(£1.60)", Decimal("-1.60")),
        ("£10", Decimal("10")),
        ("", None),
        (None, None),
        ("no digits here", None),
    ],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


def test_extract_csrf_token(landing_html):
    assert (
        extract_csrf_token(landing_html) == "tcFvNhxnZrkuTMIMU8GMvx8GBl9yYBQEIdmuiJ9X"
    )


def test_extract_csrf_token_missing(dashboard_html):
    with pytest.raises(ParseError):
        extract_csrf_token(dashboard_html)


def test_is_logged_in(dashboard_html, landing_html):
    assert is_logged_in(dashboard_html) is True
    assert is_logged_in(landing_html) is False


def test_extract_login_error_prefers_the_specific_reason(login_error_html):
    assert extract_login_error(login_error_html) == (
        "These credentials do not match our records."
    )


def test_extract_login_error_absent(landing_html):
    assert extract_login_error(landing_html) is None


def test_parse_account(dashboard_html):
    account = parse_account(dashboard_html)
    assert account.balance == Decimal("8.90")
    assert account.account_number == "000000"
    assert account.account_name == "A Test Account"
    assert account.account_type == "Personal"
    assert account.low_fund_threshold == Decimal("10.00")
    assert account.email_statements is False
    assert account.is_low is True


def test_parse_account_falls_back_to_the_header_widget():
    html = """
    <div class="user-panel logged-in">
      <div class="user-balance"><a><span>&pound;42.10</span></a></div>
    </div>
    <ul><li>Account Number: <b>000000</b></li></ul>
    """
    account = parse_account(html)
    assert account.balance == Decimal("42.10")
    assert account.account_number == "000000"
    assert account.low_fund_threshold is None
    assert account.is_low is None


def test_parse_account_without_a_balance_raises():
    with pytest.raises(ParseError):
        parse_account("<html><body><p>nothing useful</p></body></html>")


def test_account_not_low_when_above_threshold():
    html = """
    <ul>
      <li>Account Balance: <b>&pound;25.00</b></li>
      <li>Account Number: <b>000000</b></li>
      <li>Low Fund Threshold: <b>&pound;10.00</b></li>
    </ul>
    """
    assert parse_account(html).is_low is False
