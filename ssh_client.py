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


@dataclass
class PortStatus:
    """Current link status details for a switch port."""

    port: int
    connected: bool | None = None
    speed_mbps: int | None = None
    speed_display: str | None = None
    port_type: str | None = None


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

    async def get_port_statuses(self) -> dict[int, PortStatus]:
        """Fetch and parse port link status details."""
        output = await self.run_command(CMD_PORT_SHOW)
        return self._parse_port_statuses(output)

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

        def _value_after_delim(text: str) -> str | None:
            for delim in (":", "="):
                if delim in text:
                    return text.split(delim, 1)[1].strip()
            return None

        for line in output.strip().splitlines():
            line = line.strip()
            if not line:
                continue

            lower = line.lower()
            value = _value_after_delim(line)

            if any(k in lower for k in ("hostname", "host name", "system name", "device name")):
                if value:
                    info.hostname = value
            elif any(k in lower for k in ("model", "board name", "product")):
                if value:
                    info.model = value
            elif "version" in lower or "firmware" in lower:
                if value:
                    info.version = value
            elif "mac" in lower:
                mac_match = re.search(
                    r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}",
                    line,
                )
                if mac_match:
                    info.mac = mac_match.group(0).replace("-", ":").lower()
                elif value:
                    # Rejoin after first delimiter for uncommon formats
                    normalized = re.search(
                        r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}",
                        value,
                    )
                    if normalized:
                        info.mac = normalized.group(0).replace("-", ":").lower()
                    else:
                        info.mac = value

        return info

    @staticmethod
    def _parse_port_statuses(output: str) -> dict[int, PortStatus]:
        """Parse swctrl port show output into per-port status details."""
        statuses: dict[int, PortStatus] = {}

        for line in output.strip().splitlines():
            raw = line.strip()
            if not raw:
                continue

            match = re.match(r"^(\d+)\s+(.*)", raw)
            if not match:
                continue

            port = int(match.group(1))
            details = match.group(2)
            lower = details.lower()

            connected: bool | None = None
            if any(
                marker in lower
                for marker in (
                    "notconnect",
                    "not connected",
                    "disconnected",
                    "link down",
                    " down",
                    "disabled",
                    "no-link",
                    "nolink",
                )
            ):
                connected = False
            elif any(
                marker in lower
                for marker in (
                    "connected",
                    "link up",
                    " up",
                    "active",
                )
            ):
                connected = True

            speed_mbps: int | None = None
            speed_display: str | None = None

            speed_with_unit = re.search(
                r"\b(\d+(?:\.\d+)?)\s*(g(?:bps)?|m(?:bps)?)\b",
                lower,
            )
            if speed_with_unit:
                value = float(speed_with_unit.group(1))
                unit = speed_with_unit.group(2)
                if unit.startswith("g"):
                    speed_mbps = int(value * 1000)
                else:
                    speed_mbps = int(value)
            else:
                speed_plain = re.search(
                    r"\b(10|100|1000|2500|5000|10000)\b",
                    lower,
                )
                if speed_plain:
                    speed_mbps = int(speed_plain.group(1))

            if speed_mbps is not None:
                if speed_mbps >= 1000 and speed_mbps % 1000 == 0:
                    speed_display = f"{speed_mbps // 1000} Gbps"
                else:
                    speed_display = f"{speed_mbps} Mbps"

            port_type: str | None = None
            if any(k in lower for k in ("sfp", "sfp+", "sfp28", "fiber", "fibre")):
                port_type = "fiber"
            elif any(k in lower for k in ("rj45", "base-t", "copper", "ethernet")):
                port_type = "copper"

            statuses[port] = PortStatus(
                port=port,
                connected=connected,
                speed_mbps=speed_mbps,
                speed_display=speed_display,
                port_type=port_type,
            )

        return statuses

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

        # Strategy 1: find single-line rows that start with a port number
        # and extract status/length pairs
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip header and separator lines
            lower = line.lower()
            if line.startswith(("-", "=")):
                continue
            if (
                lower.startswith("port")
                and "pair" in lower
                and "status" in lower
            ):
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

        # Strategy 2: multiline formats, e.g.:
        # Port 1
        # Pair A: OK 12m
        # Pair B: Open 4m
        if not results:
            current_port: int | None = None
            by_port: dict[int, CableTestResult] = {}

            for raw in lines:
                line = raw.strip()
                if not line:
                    continue

                lower = line.lower()

                port_header = re.search(r"\bport\s*(\d+)\b", lower)
                if port_header:
                    current_port = int(port_header.group(1))
                    by_port.setdefault(
                        current_port,
                        CableTestResult(port=current_port, last_tested=now),
                    )
                    continue

                bare_port = re.match(r"^(\d+)\s*$", lower)
                if bare_port:
                    current_port = int(bare_port.group(1))
                    by_port.setdefault(
                        current_port,
                        CableTestResult(port=current_port, last_tested=now),
                    )
                    continue

                if current_port is None:
                    continue

                pair_label_match = re.search(r"pair\s*([abcd1-4])", lower)
                pairs = _extract_pairs(line)
                if not pairs:
                    continue

                result = by_port[current_port]
                if pair_label_match:
                    pair_label = pair_label_match.group(1)
                    pair_index = {
                        "a": 1,
                        "b": 2,
                        "c": 3,
                        "d": 4,
                        "1": 1,
                        "2": 2,
                        "3": 3,
                        "4": 4,
                    }.get(pair_label)
                    if pair_index is not None:
                        _set_pair_result(result, pair_index, pairs[0][0], pairs[0][1])
                        continue

                # Fallback: append in first available slot when no explicit pair label
                for status, length in pairs:
                    if result.pair_1_status == STATUS_NOT_TESTED:
                        _set_pair_result(result, 1, status, length)
                    elif result.pair_2_status == STATUS_NOT_TESTED:
                        _set_pair_result(result, 2, status, length)
                    elif result.pair_3_status == STATUS_NOT_TESTED:
                        _set_pair_result(result, 3, status, length)
                    elif result.pair_4_status == STATUS_NOT_TESTED:
                        _set_pair_result(result, 4, status, length)

            results = by_port

        if not results:
            _LOGGER.warning("Could not parse any cable test results from: %s", output)

        return results


def _normalize_status(status: str) -> str:
    """Normalize a cable status string."""
    status = status.strip().lower()
    if status in ("ok", "normal", "good"):
        return STATUS_OK
    if status in ("open", "disconnect", "disconnected"):
        return STATUS_OPEN
    if status in ("short",):
        return STATUS_SHORT
    if status in ("n/a", "na", "-", ""):
        return STATUS_NOT_TESTED
    return STATUS_UNKNOWN


def _set_pair_result(
    result: CableTestResult,
    pair_index: int,
    status: str,
    length: float | None,
) -> None:
    """Set result values for a specific cable pair index."""
    if pair_index == 1:
        result.pair_1_status = status
        result.pair_1_length = length
    elif pair_index == 2:
        result.pair_2_status = status
        result.pair_2_length = length
    elif pair_index == 3:
        result.pair_3_status = status
        result.pair_3_length = length
    elif pair_index == 4:
        result.pair_4_status = status
        result.pair_4_length = length


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
