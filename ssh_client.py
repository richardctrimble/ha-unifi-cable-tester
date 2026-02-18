"""SSH client for communicating with UniFi switches."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import asyncssh

from .const import (
    CMD_CABLE_TEST_RUN,
    CMD_CABLE_TEST_RUN_PORT,
    CMD_CABLE_TEST_SHOW,
    CMD_PORT_SHOW,
    CMD_SYSTEM_INFO,
    STATUS_NOT_TESTED,
    STATUS_OK,
    STATUS_OPEN,
    STATUS_SHORT,
    STATUS_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class CableTestResult:
    """Cable test result for a single port."""

    port: int
    pair_1_status: str = STATUS_NOT_TESTED
    pair_1_length: float | None = None
    pair_2_status: str = STATUS_NOT_TESTED
    pair_2_length: float | None = None
    pair_3_status: str = STATUS_NOT_TESTED
    pair_3_length: float | None = None
    pair_4_status: str = STATUS_NOT_TESTED
    pair_4_length: float | None = None
    last_tested: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SwitchInfo:
    """Information about the UniFi switch."""

    hostname: str = "UniFi Switch"
    model: str = "USW"
    version: str | None = None
    mac: str | None = None


class UniFiSSHError(Exception):
    """Base exception for UniFi SSH errors."""


class UniFiConnectionError(UniFiSSHError):
    """Raised when unable to connect to the switch."""


class UniFiAuthError(UniFiSSHError):
    """Raised when authentication fails."""


class UniFiCommandError(UniFiSSHError):
    """Raised when a command fails to execute."""


class UniFiSSHClient:
    """Async SSH client for UniFi switches."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "admin",
        password: str | None = None,
        ssh_key_path: str | None = None,
        ssh_key_passphrase: str | None = None,
    ) -> None:
        """Initialize the SSH client."""
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._ssh_key_path = ssh_key_path
        self._ssh_key_passphrase = ssh_key_passphrase
        self._conn: asyncssh.SSHClientConnection | None = None

    @property
    def host(self) -> str:
        """Return the host."""
        return self._host

    async def connect(self) -> None:
        """Establish SSH connection to the switch."""
        try:
            kwargs: dict = {
                "host": self._host,
                "port": self._port,
                "username": self._username,
                "known_hosts": None,  # Accept any host key
            }

            if self._ssh_key_path:
                client_keys = asyncssh.read_private_key(
                    self._ssh_key_path,
                    passphrase=self._ssh_key_passphrase or None,
                )
                kwargs["client_keys"] = [client_keys]
            elif self._password:
                kwargs["password"] = self._password

            self._conn = await asyncio.wait_for(
                asyncssh.connect(**kwargs),
                timeout=10,
            )
            _LOGGER.debug("Connected to %s:%s", self._host, self._port)

        except asyncssh.PermissionDenied as err:
            raise UniFiAuthError(
                f"Authentication failed for {self._username}@{self._host}"
            ) from err
        except asyncssh.KeyImportError as err:
            raise UniFiAuthError(
                f"Invalid SSH key: {err}"
            ) from err
        except (OSError, asyncssh.Error) as err:
            raise UniFiConnectionError(
                f"Cannot connect to {self._host}:{self._port}: {err}"
            ) from err
        except asyncio.TimeoutError as err:
            raise UniFiConnectionError(
                f"Connection to {self._host}:{self._port} timed out"
            ) from err

    async def disconnect(self) -> None:
        """Close the SSH connection."""
        if self._conn:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None
            _LOGGER.debug("Disconnected from %s", self._host)

    async def _ensure_connected(self) -> None:
        """Ensure we have an active SSH connection, reconnect if needed."""
        if self._conn is None or self._conn.is_closed():
            _LOGGER.debug("Reconnecting to %s", self._host)
            await self.connect()

    async def run_command(self, command: str, timeout: int = 30) -> str:
        """Execute a command on the switch and return stdout."""
        await self._ensure_connected()
        assert self._conn is not None

        try:
            result = await asyncio.wait_for(
                self._conn.run(command, check=False),
                timeout=timeout,
            )
            output = result.stdout or ""
            if result.stderr:
                _LOGGER.debug("stderr from '%s': %s", command, result.stderr)
            return output

        except asyncio.TimeoutError as err:
            raise UniFiCommandError(
                f"Command '{command}' timed out after {timeout}s"
            ) from err
        except (asyncssh.Error, OSError) as err:
            # Connection may be broken, clear it so next call reconnects
            self._conn = None
            raise UniFiCommandError(
                f"Command '{command}' failed: {err}"
            ) from err

    async def get_port_count(self) -> int:
        """Discover the number of ports on the switch."""
        output = await self.run_command(CMD_PORT_SHOW)
        return self._parse_port_count(output)

    async def get_switch_info(self) -> SwitchInfo:
        """Get switch model and hostname information."""
        info = SwitchInfo()

        try:
            output = await self.run_command(CMD_SYSTEM_INFO)
            info = self._parse_switch_info(output)
        except UniFiCommandError:
            _LOGGER.debug("Could not get system info, using defaults")

        return info

    async def run_cable_test(self, port: int | None = None) -> None:
        """Run cable test on a specific port or all ports."""
        if port is not None:
            cmd = CMD_CABLE_TEST_RUN_PORT.format(port=port)
        else:
            cmd = CMD_CABLE_TEST_RUN

        _LOGGER.debug("Running cable test: %s", cmd)
        await self.run_command(cmd)

    async def get_cable_test_results(self) -> dict[int, CableTestResult]:
        """Fetch and parse cable test results."""
        output = await self.run_command(CMD_CABLE_TEST_SHOW)
        return self._parse_cable_test_output(output)

    @staticmethod
    def _parse_port_count(output: str) -> int:
        """Parse swctrl port show output to find number of ports."""
        max_port = 0
        for line in output.strip().splitlines():
            line = line.strip()
            # Look for lines starting with a port number
            match = re.match(r"^(\d+)\s+", line)
            if match:
                port_num = int(match.group(1))
                max_port = max(max_port, port_num)

        if max_port == 0:
            _LOGGER.warning("Could not determine port count from output: %s", output)
        return max_port

    @staticmethod
    def _parse_switch_info(output: str) -> SwitchInfo:
        """Parse info command output for switch details."""
        info = SwitchInfo()
        for line in output.strip().splitlines():
            line = line.strip()
            lower = line.lower()
            if "hostname" in lower:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    info.hostname = parts[1].strip()
            elif "model" in lower:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    info.model = parts[1].strip()
            elif "version" in lower or "firmware" in lower:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    info.version = parts[1].strip()
            elif "mac" in lower:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    # Rejoin after first colon since MAC addresses contain colons
                    info.mac = parts[1].strip()
        return info

    @staticmethod
    def _parse_cable_test_output(output: str) -> dict[int, CableTestResult]:
        """Parse swctrl cable-test show output into structured results.

        The output format varies by firmware but generally looks like:

        Port   Pair(A) Status   Length   Pair(B) Status   Length   ...
        ----   --------------   ------   --------------   ------   ...
        1      OK               45m      OK               45m      ...
        2      Open             15m      Open             15m      ...

        This parser tries multiple strategies to handle format variations.
        """
        results: dict[int, CableTestResult] = {}
        lines = output.strip().splitlines()
        now = datetime.now(timezone.utc)

        if not lines:
            return results

        # Strategy: find data lines that start with a port number
        # and extract status/length pairs
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip header and separator lines
            if line.startswith(("-", "=", "Port")) or "Status" in line or "Length" in line:
                continue

            # Try to parse a data row starting with port number
            match = re.match(r"^(\d+)\s+(.*)", line)
            if not match:
                continue

            port_num = int(match.group(1))
            rest = match.group(2)

            # Extract all status/length pairs from the rest of the line
            # Look for patterns like: OK 45m, Open 15m, Short 3m, N/A N/A
            pair_data = _extract_pairs(rest)

            result = CableTestResult(port=port_num, last_tested=now)

            if len(pair_data) >= 1:
                result.pair_1_status = pair_data[0][0]
                result.pair_1_length = pair_data[0][1]
            if len(pair_data) >= 2:
                result.pair_2_status = pair_data[1][0]
                result.pair_2_length = pair_data[1][1]
            if len(pair_data) >= 3:
                result.pair_3_status = pair_data[2][0]
                result.pair_3_length = pair_data[2][1]
            if len(pair_data) >= 4:
                result.pair_4_status = pair_data[3][0]
                result.pair_4_length = pair_data[3][1]

            results[port_num] = result

        if not results:
            _LOGGER.warning("Could not parse any cable test results from: %s", output)

        return results


def _normalize_status(status: str) -> str:
    """Normalize a cable status string."""
    status = status.strip().lower()
    if status in ("ok", "normal", "good"):
        return STATUS_OK
    if status in ("open", "disconnect"):
        return STATUS_OPEN
    if status in ("short",):
        return STATUS_SHORT
    if status in ("n/a", "na", "-", ""):
        return STATUS_NOT_TESTED
    return STATUS_UNKNOWN


def _parse_length(length_str: str) -> float | None:
    """Parse a length value like '45m' or '45' into meters."""
    length_str = length_str.strip().lower()
    if length_str in ("n/a", "na", "-", ""):
        return None
    # Remove unit suffix
    match = re.match(r"^([\d.]+)\s*m?$", length_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _extract_pairs(text: str) -> list[tuple[str, float | None]]:
    """Extract status/length pairs from a cable test result line.

    Handles various formats:
    - "OK 45m OK 45m OK 45m OK 45m"
    - "OK  45  OK  45  OK  45  OK  45"
    - "Open 15m Short 3m N/A N/A N/A N/A"
    """
    pairs: list[tuple[str, float | None]] = []

    # Split into tokens
    tokens = text.split()
    if not tokens:
        return pairs

    i = 0
    while i < len(tokens) and len(pairs) < 4:
        token = tokens[i]

        # Check if this token looks like a status
        normalized = _normalize_status(token)
        if normalized != STATUS_UNKNOWN or token.lower() in ("n/a", "na", "-"):
            status = normalized if normalized != STATUS_UNKNOWN else STATUS_NOT_TESTED

            # Next token might be a length
            length: float | None = None
            if i + 1 < len(tokens):
                candidate = tokens[i + 1]
                # Check if it's a length value (not another status)
                if _normalize_status(candidate) == STATUS_UNKNOWN and candidate.lower() not in ("n/a", "na", "-"):
                    length = _parse_length(candidate)
                    if length is not None:
                        i += 1  # consume the length token
                elif candidate.lower() in ("n/a", "na", "-"):
                    i += 1  # consume the N/A length

            pairs.append((status, length))
        i += 1

    return pairs
