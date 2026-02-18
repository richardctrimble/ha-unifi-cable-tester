"""Sensor platform for UniFi Cable Tester."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_LAST_TESTED,
    ATTR_PORT_CONNECTED,
    ATTR_PORT_SPEED,
    ATTR_PORT_SPEED_MBPS,
    ATTR_PORT_TYPE,
    ATTR_PAIR_1_LENGTH,
    ATTR_PAIR_1_STATUS,
    ATTR_PAIR_2_LENGTH,
    ATTR_PAIR_2_STATUS,
    ATTR_PAIR_3_LENGTH,
    ATTR_PAIR_3_STATUS,
    ATTR_PAIR_4_LENGTH,
    ATTR_PAIR_4_STATUS,
    DOMAIN,
    STATUS_NOT_TESTED,
    STATUS_OK,
    STATUS_OPEN,
    STATUS_SHORT,
    STATUS_TEST_FAILED,
    STATUS_UNKNOWN,
)
from .coordinator import UniFiCableTesterCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UniFi cable test sensors."""
    coordinator: UniFiCableTesterCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        UniFiCableTestSensor(coordinator, port)
        for port in range(1, coordinator.port_count + 1)
    ]

    async_add_entities(entities)


class UniFiCableTestSensor(
    CoordinatorEntity[UniFiCableTesterCoordinator], SensorEntity
):
    """Sensor showing cable test status for a switch port."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:ethernet-cable"

    def __init__(
        self,
        coordinator: UniFiCableTesterCoordinator,
        port: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._port = port
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_port_{port}_cable_status"
        )
        self._attr_name = f"Port {port} Cable Status"

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

    @property
    def native_value(self) -> str:
        """Return the overall cable status for this port."""
        if self._port in self.coordinator.test_failed_ports:
            return STATUS_TEST_FAILED
        if not self.coordinator.data or self._port not in self.coordinator.data:
            return STATUS_NOT_TESTED

        result = self.coordinator.data[self._port]
        statuses = [
            result.pair_1_status,
            result.pair_2_status,
            result.pair_3_status,
            result.pair_4_status,
        ]

        if STATUS_SHORT in statuses:
            return STATUS_SHORT
        if STATUS_OPEN in statuses:
            return STATUS_OPEN
        if all(s == STATUS_OK for s in statuses):
            return STATUS_OK
        if all(s == STATUS_NOT_TESTED for s in statuses):
            return STATUS_NOT_TESTED
        return STATUS_UNKNOWN

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return per-pair cable test details as attributes."""
        attrs: dict[str, Any] = {}

        port_status = self.coordinator.port_statuses.get(self._port)
        # Always include port status keys so they're visible in the attribute panel
        # even before a "Refresh Switch Status" has been triggered.
        attrs[ATTR_PORT_CONNECTED] = port_status.connected if port_status else None
        attrs[ATTR_PORT_SPEED] = port_status.speed_display if port_status else None
        attrs[ATTR_PORT_SPEED_MBPS] = port_status.speed_mbps if port_status else None
        attrs[ATTR_PORT_TYPE] = port_status.port_type if port_status else None

        if not self.coordinator.data or self._port not in self.coordinator.data:
            return attrs

        result = self.coordinator.data[self._port]
        attrs.update(
            {
            ATTR_PAIR_1_STATUS: result.pair_1_status,
            ATTR_PAIR_1_LENGTH: result.pair_1_length,
            ATTR_PAIR_2_STATUS: result.pair_2_status,
            ATTR_PAIR_2_LENGTH: result.pair_2_length,
            ATTR_PAIR_3_STATUS: result.pair_3_status,
            ATTR_PAIR_3_LENGTH: result.pair_3_length,
            ATTR_PAIR_4_STATUS: result.pair_4_status,
            ATTR_PAIR_4_LENGTH: result.pair_4_length,
            ATTR_LAST_TESTED: result.last_tested.isoformat(),
            }
        )
        return attrs
