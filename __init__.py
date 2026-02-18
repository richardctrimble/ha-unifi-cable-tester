"""The UniFi Cable Tester integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AUTH_METHOD,
    CONF_SSH_KEY_PASSPHRASE,
    CONF_SSH_KEY_PATH,
    AUTH_METHOD_KEY,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import UniFiCableTesterCoordinator
from .ssh_client import UniFiSSHClient

_LOGGER = logging.getLogger(__name__)


def _create_client(data: dict) -> UniFiSSHClient:
    """Create an SSH client from config entry data."""
    kwargs: dict = {
        "host": data[CONF_HOST],
        "port": data.get(CONF_PORT, 22),
        "username": data.get(CONF_USERNAME, "admin"),
    }

    if data.get(CONF_AUTH_METHOD) == AUTH_METHOD_KEY:
        kwargs["ssh_key_path"] = data[CONF_SSH_KEY_PATH]
        kwargs["ssh_key_passphrase"] = data.get(CONF_SSH_KEY_PASSPHRASE)
    else:
        kwargs["password"] = data.get(CONF_PASSWORD)

    return UniFiSSHClient(**kwargs)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Cable Tester from a config entry."""
    client = _create_client(entry.data)
    coordinator = UniFiCableTesterCoordinator(hass, entry, client)

    # Connect and discover ports
    await coordinator.async_setup()

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: UniFiCableTesterCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
