"""Button platform for UniFi Cable Tester."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UniFiCableTesterCoordinator

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


class UniFiCableTestButton(
    CoordinatorEntity[UniFiCableTesterCoordinator], ButtonEntity
):
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

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this entity to the switch device."""
        identifiers = {(DOMAIN, self.coordinator.config_entry.entry_id)}
        connections: set[tuple[str, str]] = set()

        if self.coordinator.switch_info.mac:
            mac = self.coordinator.switch_info.mac.lower()
            identifiers.add((DOMAIN, mac))
            connections.add((dr.CONNECTION_NETWORK_MAC, mac))

        return DeviceInfo(
            identifiers=identifiers,
            connections=connections,
            name=self.coordinator.switch_info.hostname,
            manufacturer="Ubiquiti",
            model=self.coordinator.switch_info.model,
            sw_version=self.coordinator.switch_info.version,
        )

    async def async_press(self) -> None:
        """Handle button press — trigger cable test on all ports."""
        try:
            await self.coordinator.async_request_cable_test(port=None)
        except Exception as err:
            _LOGGER.error("Cable test failed for all ports: %s", err)
            raise HomeAssistantError(f"Cable test failed: {err}") from err


class UniFiRefreshSwitchStatusButton(
    CoordinatorEntity[UniFiCableTesterCoordinator], ButtonEntity
):
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

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this entity to the switch device."""
        identifiers = {(DOMAIN, self.coordinator.config_entry.entry_id)}
        connections: set[tuple[str, str]] = set()

        if self.coordinator.switch_info.mac:
            mac = self.coordinator.switch_info.mac.lower()
            identifiers.add((DOMAIN, mac))
            connections.add((dr.CONNECTION_NETWORK_MAC, mac))

        return DeviceInfo(
            identifiers=identifiers,
            connections=connections,
            name=self.coordinator.switch_info.hostname,
            manufacturer="Ubiquiti",
            model=self.coordinator.switch_info.model,
            sw_version=self.coordinator.switch_info.version,
        )

    async def async_press(self) -> None:
        """Handle button press — trigger a safe, lightweight refresh."""
        try:
            await self.coordinator.async_refresh_switch_status()
        except Exception as err:
            _LOGGER.error("Switch status refresh failed: %s", err)
            raise HomeAssistantError(
                f"Switch status refresh failed: {err}"
            ) from err
