"""Button platform for UniFi Cable Tester."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import UniFiCableTesterCoordinator
from .entity import UniFiCableTesterEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi cable test buttons."""
    coordinator: UniFiCableTesterCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ButtonEntity] = [
        # "Test All Cables" button
        UniFiCableTestButton(coordinator),
        # Manual switch status refresh button (no cable test)
        UniFiRefreshSwitchStatusButton(coordinator),
    ]

    async_add_entities(entities)


class UniFiCableTestButton(UniFiCableTesterEntity, ButtonEntity):
    """Button to trigger a cable test on all ports."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:ethernet-cable-off"

    def __init__(self, coordinator: UniFiCableTesterCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_test_all_cables"
        )
        self._attr_name = "Test All Cables"

    async def async_press(self) -> None:
        """Handle button press — trigger cable test on all ports."""
        try:
            await self.coordinator.async_request_cable_test(port=None)
        except Exception as err:
            _LOGGER.error("Cable test failed for all ports: %s", err)
            raise HomeAssistantError(f"Cable test failed: {err}") from err


class UniFiRefreshSwitchStatusButton(UniFiCableTesterEntity, ButtonEntity):
    """Button to manually refresh switch status/details."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: UniFiCableTesterCoordinator) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_refresh_switch_status"
        )
        self._attr_name = "Refresh Switch Status"

    async def async_press(self) -> None:
        """Handle button press — trigger a safe, lightweight refresh."""
        try:
            await self.coordinator.async_refresh_switch_status()
        except Exception as err:
            _LOGGER.error("Switch status refresh failed: %s", err)
            raise HomeAssistantError(
                f"Switch status refresh failed: {err}"
            ) from err
