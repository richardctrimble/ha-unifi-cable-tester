"""DataUpdateCoordinator for UniFi Cable Tester."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, TEST_RUN_COMPLETED, TEST_RUN_FAILED, TEST_RUN_IDLE, TEST_RUN_RUNNING
from .ssh_client import (
    CableTestResult,
    PortStatus,
    SwitchInfo,
    UniFiAuthError,
    UniFiCommandError,
    UniFiConnectionError,
    UniFiSSHClient,
)

_LOGGER = logging.getLogger(__name__)


class UniFiCableTesterCoordinator(DataUpdateCoordinator[dict[int, CableTestResult]]):
    """Coordinator for UniFi cable test data.

    This coordinator does NOT poll automatically. Data is only updated
    when a cable test is explicitly triggered via button press.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: UniFiSSHClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            # No update_interval — on-demand only
        )
        self.config_entry = entry
        self.client = client
        self.port_count: int = 0
        self.switch_info: SwitchInfo = SwitchInfo()
        self.port_statuses: dict[int, PortStatus] = {}
        self.test_failed_ports: set[int] = set()
        self._test_lock = asyncio.Lock()
        
        # Test run status tracking
        self.test_run_status: str = TEST_RUN_IDLE
        self.test_started: datetime | None = None
        self.test_completed: datetime | None = None
        self.test_ports_count: int = 0
        self.test_error_message: str | None = None

    async def async_setup(self, startup_lightweight_read: bool = False) -> None:
        """Connect to the switch and discover required startup data.

        Args:
            startup_lightweight_read: If True, also fetch switch info and port
                status details during startup.
        """
        try:
            await self.client.connect()
            if self.port_count <= 0:
                self.port_count = await self.client.get_port_count()
            else:
                _LOGGER.debug(
                    "Skipping startup port discovery, using known port count: %d",
                    self.port_count,
                )
            # Always fetch switch identity (fast, no side-effects)
            self.switch_info = await self.client.get_switch_info()
            # Optionally fetch per-port link details (slightly slower)
            if startup_lightweight_read:
                self.port_statuses = await self.client.get_port_statuses()
            _LOGGER.info(
                "Connected to %s (%s) with %d ports",
                self.switch_info.hostname,
                self.switch_info.model,
                self.port_count,
            )
        except UniFiAuthError as err:
            raise ConfigEntryNotReady(
                f"Authentication failed: {err}"
            ) from err
        except UniFiConnectionError as err:
            raise ConfigEntryNotReady(
                f"Cannot connect to switch: {err}"
            ) from err

        # Initialize with empty data (no tests run yet)
        self.async_set_updated_data({})

    async def async_shutdown(self) -> None:
        """Disconnect from the switch."""
        await self.client.disconnect()

    async def _async_update_data(self) -> dict[int, CableTestResult]:
        """Return current data. Not used for polling."""
        return self.data or {}

    async def async_refresh_switch_status(self) -> None:
        """Refresh switch identity and port link details on demand.

        This is a lightweight refresh and does not run cable tests.
        """
        try:
            self.switch_info = await self.client.get_switch_info()
            self.port_statuses = await self.client.get_port_statuses()
            # Notify entities so attributes/device info refresh immediately.
            self.async_set_updated_data(dict(self.data or {}))
        except UniFiConnectionError as err:
            _LOGGER.error("Connection lost during status refresh: %s", err)
            raise UpdateFailed(f"Connection lost: {err}") from err
        except UniFiCommandError as err:
            _LOGGER.error("Status refresh command failed: %s", err)
            raise UpdateFailed(f"Status refresh failed: {err}") from err

    async def async_request_cable_test(self, port: int | None = None) -> None:
        """Run a cable test and update results.

        Args:
            port: Specific port to test, or None for all ports.
        """
        async with self._test_lock:
            # Update test run status to running
            self.test_run_status = TEST_RUN_RUNNING
            self.test_started = datetime.now(timezone.utc)
            self.test_completed = None
            self.test_error_message = None
            self.test_ports_count = 1 if port is not None else self.port_count
            self.async_set_updated_data(dict(self.data or {}))
            
            try:
                # Run the cable test (CLI mode runs and returns results in one call)
                results = await self.client.run_cable_test(
                    port=port,
                    port_count=self.port_count,
                )

                # Refresh link/speed/type details
                self.port_statuses = await self.client.get_port_statuses()

                # Merge with existing data (in case we only tested one port)
                merged = dict(self.data or {})
                merged.update(results)

                # Clear any previous failures for tested ports
                tested_ports = (
                    {port} if port is not None
                    else set(range(1, self.port_count + 1))
                )
                self.test_failed_ports -= tested_ports

                # If we got no results at all, treat as a failure
                if not results:
                    _LOGGER.warning(
                        "Cable test returned no results for %s",
                        f"port {port}" if port else "all ports",
                    )
                    self.test_failed_ports |= tested_ports
                    self.async_set_updated_data(dict(self.data or {}))
                    raise UpdateFailed("Cable test returned no results")

                # Update test run status to completed
                self.test_run_status = TEST_RUN_COMPLETED
                self.test_completed = datetime.now(timezone.utc)
                self.test_ports_count = len(results)
                
                # Push updated data to all entities (including test run status)
                self.async_set_updated_data(merged)
                
                _LOGGER.debug(
                    "Cable test complete for %s, %d port results",
                    f"port {port}" if port else "all ports",
                    len(results),
                )

            except UpdateFailed:
                self.test_run_status = TEST_RUN_FAILED
                self.test_completed = datetime.now(timezone.utc)
                self.test_error_message = "No results returned"
                self.async_set_updated_data(dict(self.data or {}))
                raise
            except (UniFiConnectionError, UniFiCommandError, Exception) as err:
                # Mark the tested port(s) as failed and notify entities
                failed_ports = (
                    {port} if port is not None
                    else set(range(1, self.port_count + 1))
                )
                self.test_failed_ports |= failed_ports
                
                # Update test run status to failed
                self.test_run_status = TEST_RUN_FAILED
                self.test_completed = datetime.now(timezone.utc)
                self.test_error_message = str(err)
                
                self.async_set_updated_data(dict(self.data or {}))
                _LOGGER.error("Cable test failed: %s", err)
                raise UpdateFailed(f"Cable test failed: {err}") from err
