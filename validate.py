#!/usr/bin/env python3
"""Exercise the Mersey Tunnels client against the live site.

Reads MERSEYTUNNELS_USERNAME and MERSEYTUNNELS_PASSWORD from the environment or
from a .env file beside this script. Nothing here is imported by the Home
Assistant integration.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from custom_components.merseytunnel.api import (
    MerseyTunnelsClient,
    MerseyTunnelsError,
)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def show(account) -> None:
    print(f"  balance             {account.balance:>10}")
    print(f"  account number      {account.account_number:>10}")
    print(f"  account name        {account.account_name}")
    print(f"  account type        {account.account_type}")
    print(f"  low fund threshold  {account.low_fund_threshold}")
    print(f"  email statements    {account.email_statements}")
    print(f"  below threshold     {account.is_low}")


async def main() -> int:
    load_env(Path(__file__).parent / ".env")
    username = os.environ.get("MERSEYTUNNELS_USERNAME")
    password = os.environ.get("MERSEYTUNNELS_PASSWORD")
    if not username or not password:
        print("Set MERSEYTUNNELS_USERNAME and MERSEYTUNNELS_PASSWORD first.")
        return 2

    if "-v" in sys.argv:
        logging.basicConfig(level=logging.DEBUG)

    async with MerseyTunnelsClient(username, password) as client:
        try:
            print("1. validate credentials")
            show(await client.async_validate_credentials())

            print("\n2. second poll on the same session")
            show(await client.async_get_account())

            print("\n3. recover from a dropped session")
            client._session.cookies.clear()
            client._authenticated = False
            show(await client.async_get_account())
            print(f"\n   re-authenticated: {client.is_authenticated}")
        except MerseyTunnelsError as err:
            print(f"\nFAILED: {type(err).__name__}: {err}")
            return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
