# Mersey Tunnels for Home Assistant

Reads your Fast Tag account balance from the Mersey Tunnels customer portal and
exposes it as a Home Assistant sensor.

The portal has no public API, so this signs in and scrapes the dashboard at
`https://www.merseytunnels.co.uk/dashboard`.

## Entities

Everything sits under one device per account.

| Entity | Type | Notes |
| --- | --- | --- |
| Balance | `sensor` | Monetary, GBP. Carries the account number, name, type, and email-statement setting as attributes |
| Low balance | `binary_sensor` | `problem` class. On when the balance reaches the threshold set on the portal |
| Low fund threshold | `sensor` | Disabled by default; it is a setting rather than a reading |

The low balance sensor uses the portal's own threshold rather than a number
invented here, so it turns on at the same point the website starts warning you.
It reports unavailable if the dashboard stops giving a threshold.

## Installing

### HACS

Add this repository as a custom repository of type Integration, install it, then
restart Home Assistant.

### Manually

Copy `custom_components/merseytunnel` into your `config/custom_components/`
directory and restart.

Then go to Settings, Devices and services, Add integration, and search for Mersey
Tunnels. Sign in with the account number and password you use on the website.

Needs Home Assistant 2025.2 or later. Developed and tested against 2026.2.

### Dependencies in Docker

Nothing to do by hand. Home Assistant installs an integration's requirements
itself the first time the integration is set up, and both of these resolve to
prebuilt wheels on the architectures the official image is published for:

- The container is Alpine based, so it needs musl wheels. `curl_cffi` publishes
  `cp310-abi3` musllinux wheels for x86_64 and aarch64, which are the only
  architectures `homeassistant/home-assistant` is published for. Resolving with
  `uv --no-build` succeeds on both, so nothing is compiled and no Alpine packages
  are needed. The wheel bundles its own native library.
- `beautifulsoup4` already ships with Home Assistant, and Home Assistant skips
  requirements that are already satisfied, so this one installs nothing.

Two things follow from how the container works. The install needs outbound HTTPS
to PyPI at the moment you add the integration, so allowlist `pypi.org` and
`files.pythonhosted.org` if the container's egress is restricted. And because
Home Assistant installs into the container's own site-packages rather than into
`/config/deps` when it detects Docker, the package goes away when the container is
recreated on an image update and is reinstalled automatically on the next start.

To confirm it landed:

```bash
docker exec homeassistant python -c "import curl_cffi; print(curl_cffi.__version__)"
```

## How authentication works

The portal is a Laravel app. There is no OAuth and no refresh token, so there is
nothing to refresh. Signing in means posting the homepage login form:

| Step | Request | Result |
| --- | --- | --- |
| 1 | `GET /` | Returns the login form carrying a CSRF `_token` |
| 2 | `POST /login` with `_token`, `username`, `password` | `302` to `/dashboard` on success, `302` to `/` on failure |
| 3 | `GET /dashboard` | The balance, as long as `mersey_tunnels_session` is valid |

The session cookie lapses after about two hours of inactivity. The client spots
that and signs in again on its own, so the coordinator only ever sees a balance or
an error. Two things count as logged out:

- the dashboard redirects away, which is what the server does after a logout
- the dashboard returns `200` but renders as an anonymous visitor

A rejected password or a `429` from the site's rate limiter puts sign-in on hold
for five minutes, so a wrong password cannot hammer the login endpoint on every
polling cycle. Successful sign-ins are never held back, since re-authenticating
after a lapse is the normal path.

Polling runs every 30 minutes. The balance only moves when a journey is billed or
the account is topped up, so there is nothing to gain from asking more often. Call
`homeassistant.update_entity` if you want a reading immediately.

### Why curl_cffi instead of aiohttp

Every path on the site sits behind a Cloudflare managed challenge that inspects
the TLS handshake. Plain `curl`, `requests`, and `aiohttp` all get a `403` with
`cf-mitigated: challenge` on the homepage. `curl_cffi` presents a real Chrome
fingerprint and is served the page normally, with no JavaScript challenge to
solve. This is why the integration cannot use Home Assistant's shared aiohttp
session. If Cloudflare tightens this later, the client raises `CannotConnect` with
a message pointing at the impersonation profile rather than failing obscurely.

## Layout

```
custom_components/merseytunnel/
  api/               Portal client, imports nothing from Home Assistant
    client.py          Sign-in, session recovery, dashboard fetch
    parser.py          Dashboard scraping
    models.py          The Account dataclass
    exceptions.py      Error types the integration maps onto HA behaviour
  coordinator.py     Polling, and the mapping from client errors to HA behaviour
  config_flow.py     Setup and reauthentication
  entity.py          Shared device and naming
  sensor.py          Balance and threshold
  binary_sensor.py   Low balance
tests/               Offline tests against saved HTML fixtures, plus opt-in live tests
validate.py          Manual check of the client against the live site
```

Keeping `api/` free of Home Assistant imports means the scraping can be exercised
on its own, which is how the fixtures and the client tests work.

## Errors and what Home Assistant does about them

| Client exception | Meaning | Behaviour |
| --- | --- | --- |
| `InvalidAuth` | Credentials rejected | Raises `ConfigEntryAuthFailed`, so Home Assistant prompts you to sign in again |
| `LoginThrottled` | Sign-in on hold | `UpdateFailed`; entities keep the last value until the next poll |
| `CannotConnect` | Network failure, `5xx`, or a Cloudflare challenge | `UpdateFailed` |
| `ParseError` | Page loaded but the balance was missing | `UpdateFailed`, and the markup needs a look |
| `SessionExpired` | Handled inside the client, retried once | Never reaches the coordinator |

A missing balance is treated as a site change rather than a credentials problem,
so it retries instead of wrongly asking you for a new password.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest              # 65 offline tests, no network
.venv/bin/python -m ruff check .
```

The live tests are excluded by default because they hit the real website and need
credentials:

```bash
.venv/bin/python -m pytest -m live -s   # signs in for real
.venv/bin/python validate.py            # client only, prints what it reads
```

Both read `MERSEYTUNNELS_USERNAME` and `MERSEYTUNNELS_PASSWORD` from the
environment or from a `.env` file in the repo root. `.env` is gitignored. Keep
real credentials out of committed files and out of the test fixtures, which use a
placeholder account number.

## Known limits

This is a scraper, so changes to the site's markup will break it. `ParseError`
fires loudly rather than reporting a stale balance, and the parser falls back to
the header balance widget if the dashboard card moves.

The dashboard also shows tags, vehicles, and recent transactions. None of those
are parsed. They would be separate entities rather than part of a balance sensor.
