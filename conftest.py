"""Root pytest configuration.

``pytest_plugins`` has to live in the top-level conftest, so the Home Assistant
test harness is enabled here and the shared fixtures stay in ``tests/conftest.py``.
"""

pytest_plugins = ["pytest_homeassistant_custom_component"]
