"""Button platform for UniFi Cable Tester."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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

    entities: list[ButtonEntity] = []

    # Per-port test buttons
    for port in range(1, coordinator.port_count + 1):
        entities.append(UniFiCableTestButton(coordinator, port))

    # "Test All" button
    entities.append(UniFiCableTestButton(coordinator, port=None))

    async_add_entities(entities)


class UniFiCableTestButton(
    CoordinatorEntity[UniFiCableTesterCoordinator], ButtonEntity
):
    """Button to trigger a cable test on a switch port."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UniFiCableTesterCoordinator,
        port: int | None,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._port = port

        if port is None:
            self._attr_unique_id = (
                f"{coordinator.config_entry.entry_id}_test_all_cables"
            )
            self._attr_name = "Test All Cables"
            self._attr_icon = "mdi:ethernet-cable-off"
        else:
            self._attr_unique_id = (
                f"{coordinator.config_entry.entry_id}_port_{port}_test_cable"
            )
            self._attr_name = f"Port {port} Test Cable"
            self._attr_icon = "mdi:ethernet-cable"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this entity to the switch device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=self.coordinator.switch_info.hostname,
            manufacturer="Ubiquiti",
            model=self.coordinator.switch_info.model,
            sw_version=self.coordinator.switch_info.version,
        )

    async def async_press(self) -> None:
        """Handle button press — trigger cable test."""
        try:
            await self.coordinator.async_request_cable_test(self._port)
        except Exception as err:
            _LOGGER.error(
                "Cable test failed for %s: %s",
                f"port {self._port}" if self._port else "all ports",
                err,
            )
            raise HomeAssistantError(
                f"Cable test failed: {err}"
            ) from err
