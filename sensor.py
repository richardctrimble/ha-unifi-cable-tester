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
    ATTR_ERROR_MESSAGE,
    ATTR_LAST_TESTED,
    ATTR_PORT_CONNECTED,
    ATTR_PORT_SPEED,
    ATTR_PORT_SPEED_MBPS,
    ATTR_PORT_TYPE,
    ATTR_PORTS_FAILED,
    ATTR_PORTS_TESTED,
    ATTR_PAIR_1_LENGTH,
    ATTR_PAIR_1_STATUS,
    ATTR_PAIR_2_LENGTH,
    ATTR_PAIR_2_STATUS,
    ATTR_PAIR_3_LENGTH,
    ATTR_PAIR_3_STATUS,
    ATTR_PAIR_4_LENGTH,
    ATTR_PAIR_4_STATUS,
    ATTR_TEST_COMPLETED,
    ATTR_TEST_DURATION,
    ATTR_TEST_STARTED,
    DOMAIN,
    STATUS_FIBER,
    STATUS_NOT_TESTED,
    STATUS_OK,
    STATUS_OPEN,
    STATUS_SHORT,
    STATUS_TEST_FAILED,
    STATUS_UNKNOWN,
    TEST_RUN_IDLE,
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

    entities: list[SensorEntity] = [
        # Test run status sensor
        UniFiTestRunStatusSensor(coordinator),
    ]
    
    # Per-port cable status sensors
    entities.extend(
        UniFiCableTestSensor(coordinator, port)
        for port in range(1, coordinator.port_count + 1)
    )

    async_add_entities(entities)


class UniFiTestRunStatusSensor(
    CoordinatorEntity[UniFiCableTesterCoordinator], SensorEntity
):
    """Sensor showing the status of the current/last cable test run."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:test-tube"

    def __init__(self, coordinator: UniFiCableTesterCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_test_run_status"
        )
        self._attr_name = "Test Run Status"

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
        """Return the current test run status."""
        return self.coordinator.test_run_status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return test run details as attributes."""
        attrs: dict[str, Any] = {}

        if self.coordinator.test_started:
            attrs[ATTR_TEST_STARTED] = self.coordinator.test_started.isoformat()

        if self.coordinator.test_completed:
            attrs[ATTR_TEST_COMPLETED] = self.coordinator.test_completed.isoformat()
            
            # Calculate duration if both timestamps exist
            if self.coordinator.test_started:
                duration = (
                    self.coordinator.test_completed - self.coordinator.test_started
                ).total_seconds()
                attrs[ATTR_TEST_DURATION] = round(duration, 1)

        attrs[ATTR_PORTS_TESTED] = self.coordinator.test_ports_count
        attrs[ATTR_PORTS_FAILED] = len(self.coordinator.test_failed_ports)

        if self.coordinator.test_error_message:
            attrs[ATTR_ERROR_MESSAGE] = self.coordinator.test_error_message

        return attrs


class UniFiCableTestSensor(
    CoordinatorEntity[UniFiCableTesterCoordinator], SensorEntity
):
    """Sensor showing cable test status for a switch port."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
    def icon(self) -> str:
        """Return icon based on port type."""
        # Check if this port returned Fiber in cable test
        if self.coordinator.data and self._port in self.coordinator.data:
            result = self.coordinator.data[self._port]
            if result.pair_1_status == STATUS_FIBER:
                return "mdi:fiber-manual-record"  # Fiber optic icon
        return "mdi:ethernet-cable"

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

        # Fiber ports return Fiber status for all pairs
        if all(s == STATUS_FIBER for s in statuses):
            return STATUS_FIBER
        
        # Check for problems first (Short/Open are always bad)
        if STATUS_SHORT in statuses:
            return STATUS_SHORT
        if STATUS_OPEN in statuses:
            return STATUS_OPEN
        
        # Filter out "Not Tested" pairs (100Mbps only uses pairs A/B)
        tested_statuses = [s for s in statuses if s != STATUS_NOT_TESTED]
        
        # If we have tested pairs and all are OK, the cable is good
        if tested_statuses and all(s == STATUS_OK for s in tested_statuses):
            return STATUS_OK
        
        # No pairs tested yet
        if not tested_statuses:
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

        # Set port type from port status if available
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
