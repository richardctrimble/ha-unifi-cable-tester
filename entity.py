"""Base entity for UniFi Cable Tester."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UniFiCableTesterCoordinator


class UniFiCableTesterEntity(CoordinatorEntity[UniFiCableTesterCoordinator]):
    """Base entity for UniFi Cable Tester integration."""

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
