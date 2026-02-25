"""The UniFi Cable Tester integration."""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)

from .const import (
    ATTR_PORT,
    CONF_AUTH_METHOD,
    CONF_SSH_KEY_PASSPHRASE,
    CONF_SSH_KEY_PATH,
    CONF_STARTUP_LIGHTWEIGHT_READ,
    AUTH_METHOD_KEY,
    DOMAIN,
    PLATFORMS,
    SERVICE_RUN_CABLE_TEST,
)
from .coordinator import UniFiCableTesterCoordinator
from .ssh_client import UniFiSSHClient

_LOGGER = logging.getLogger(__name__)

# Frontend card path
CARD_NAME = "unifi-cable-tester-card.js"
CARD_URL_PATH = f"/{DOMAIN}/{CARD_NAME}"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the UniFi Cable Tester integration."""
    hass.data.setdefault(DOMAIN, {})

    # Register the static path for our custom card
    card_path = Path(__file__).parent / "www" / CARD_NAME

    if card_path.exists():
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_URL_PATH, str(card_path), cache_headers=False)]
            )
            _LOGGER.info(
                "UniFi Cable Tester card registered. Add to Lovelace resources: %s",
                CARD_URL_PATH,
            )
        except Exception as err:
            _LOGGER.warning("Failed to register frontend card: %s", err)
    else:
        _LOGGER.debug("Frontend card not found at %s", card_path)

    return True


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

    # Reuse known port count from existing entities if available.
    registry = er.async_get(hass)
    known_ports: set[int] = set()
    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if not entity_entry.unique_id:
            continue
        match = re.search(r"_port_(\d+)_", entity_entry.unique_id)
        if match:
            known_ports.add(int(match.group(1)))
    if known_ports:
        coordinator.port_count = max(known_ports)

    startup_lightweight_read = bool(
        entry.options.get(
            CONF_STARTUP_LIGHTWEIGHT_READ,
            entry.data.get(CONF_STARTUP_LIGHTWEIGHT_READ, False),
        )
    )

    # Connect and discover ports
    await coordinator.async_setup(
        startup_lightweight_read=startup_lightweight_read
    )

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once for the domain)
    _async_register_services(hass)

    return True


SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=52)
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services."""
    if hass.services.has_service(DOMAIN, SERVICE_RUN_CABLE_TEST):
        return

    async def async_handle_cable_test(call: ServiceCall) -> None:
        """Handle run_cable_test service call."""
        port: int | None = call.data.get(ATTR_PORT)
        device_ids: set[str] = set()

        # Collect target device IDs from service data
        raw_ids = call.data.get("device_id")
        if raw_ids:
            device_ids.update(
                raw_ids if isinstance(raw_ids, list) else [raw_ids]
            )

        if not device_ids:
            # No specific device targeted — run on all configured switches
            for coordinator in hass.data.get(DOMAIN, {}).values():
                if isinstance(coordinator, UniFiCableTesterCoordinator):
                    await coordinator.async_request_cable_test(port)
            return

        # Map device IDs back to coordinators
        device_reg = dr.async_get(hass)
        for device_id in device_ids:
            device_entry = device_reg.async_get(device_id)
            if device_entry is None:
                continue
            for entry_id in device_entry.config_entries:
                coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
                if isinstance(coordinator, UniFiCableTesterCoordinator):
                    await coordinator.async_request_cable_test(port)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_CABLE_TEST,
        async_handle_cable_test,
        schema=SERVICE_SCHEMA,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: UniFiCableTesterCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
