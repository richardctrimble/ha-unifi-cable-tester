"""SSH client for communicating with UniFi switches."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import asyncssh

from .const import (
    CMD_CABLE_DIAG,
    CMD_CLI_ENTER,
    CMD_CLI_EXIT,
    CMD_PORT_SHOW,
    CMD_SYSTEM_INFO,
    STATUS_FIBER,
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

    async def run_cli_commands(self, commands: list[str], timeout: int = 60) -> str:
        """Execute multiple commands in a single CLI session.

        SSH is already connected. This opens an interactive shell,
        runs 'cli' to enter CLI mode, executes commands, then exits.
        
        Sequence: 
        - cli (enter CLI mode)
        - commands
        - exit (leave first CLI layer)
        - exit (leave second CLI layer - shows "Terminated")
        - exit (close SSH shell)
        """
        await self._ensure_connected()
        assert self._conn is not None

        _LOGGER.debug("Running CLI commands: %s", commands)

        collected_output = ""
        
        try:
            async with self._conn.create_process(
                term_type="vt100",
                encoding="utf-8",
            ) as process:
                # Enter CLI mode
                process.stdin.write(f"{CMD_CLI_ENTER}\n")
                await asyncio.sleep(1.0)  # CLI takes a moment to start
                
                # Run all the cable test commands
                for cmd in commands:
                    process.stdin.write(f"{cmd}\n")
                    await asyncio.sleep(0.5)
                
                # Exit first CLI layer
                process.stdin.write(f"{CMD_CLI_EXIT}\n")
                await asyncio.sleep(0.3)
                
                # Exit second CLI layer (will print "Terminated")
                process.stdin.write(f"{CMD_CLI_EXIT}\n")
                await asyncio.sleep(0.3)
                
                # Exit SSH shell
                process.stdin.write(f"{CMD_CLI_EXIT}\n")
                await asyncio.sleep(0.3)

                # Now read output until process ends or timeout
                deadline = asyncio.get_event_loop().time() + timeout
                
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        chunk = await asyncio.wait_for(
                            process.stdout.read(4096),
                            timeout=3.0,
                        )
                        if not chunk:
                            # EOF - process ended (SSH shell closed)
                            _LOGGER.debug("EOF reached, shell closed")
                            break
                        collected_output += chunk
                        _LOGGER.debug("Read chunk: %d bytes", len(chunk))
                    except asyncio.TimeoutError:
                        # No data for 3 seconds - send extra exit to ensure we close
                        _LOGGER.debug("Read timeout, sending extra exit")
                        try:
                            process.stdin.write(f"{CMD_CLI_EXIT}\n")
                        except Exception:
                            pass
                        continue

                _LOGGER.debug("CLI output length: %d chars", len(collected_output))
                _LOGGER.debug("CLI output:\n%s", collected_output[:3000] if len(collected_output) > 3000 else collected_output)
                return collected_output

        except asyncio.TimeoutError as err:
            _LOGGER.debug("Final timeout, collected %d chars", len(collected_output))
            if collected_output:
                return collected_output
            raise UniFiCommandError(
                f"CLI commands timed out after {timeout}s"
            ) from err
        except (asyncssh.Error, OSError) as err:
            self._conn = None
            raise UniFiCommandError(
                f"CLI commands failed: {err}"
            ) from err

    async def run_cable_test(
        self,
        port: int | None = None,
        port_count: int = 24,
    ) -> dict[int, CableTestResult]:
        """Run cable test and return results.

        Uses CLI mode: cli -> sh cable-diag int gi{port} -> exit -> exit

        Args:
            port: Specific port to test, or None for all ports.
            port_count: Total number of ports (used when testing all).

        Returns:
            Dictionary mapping port numbers to CableTestResult objects.
        """
        if port is not None:
            # Single port test
            commands = [CMD_CABLE_DIAG.format(port=port)]
            timeout = 30
        else:
            # All ports - build list of commands
            commands = [CMD_CABLE_DIAG.format(port=p) for p in range(1, port_count + 1)]
            # Allow more time for all ports (1.5s per port + overhead)
            timeout = max(60, len(commands) * 2 + 10)

        _LOGGER.debug(
            "Running cable test in CLI mode: %d commands, timeout=%ds",
            len(commands),
            timeout,
        )
        output = await self.run_cli_commands(commands, timeout=timeout)
        _LOGGER.debug("Cable test raw output length: %d chars", len(output))
        return self._parse_cable_diag_output(output)

    async def get_cable_test_results(self) -> dict[int, CableTestResult]:
        """Fetch cable test results (alias for run_cable_test with no port).

        Note: On UniFi switches, the cable test runs when the command is issued,
        so this effectively runs a test on all ports.
        """
        return await self.run_cable_test(port=None)

    @staticmethod
    def _parse_port_count(output: str) -> int:
        """Parse swctrl port show output to find number of ports."""
        max_port = 0
        for line in output.strip().splitlines():
            line = line.strip()
            # Look for lines starting with a port number (with optional U prefix)
            # Examples: "1  U/U", "14  U/D", "U24  U/U"
            match = re.match(r"^U?(\d+)\s+", line)
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
        """Parse swctrl port show output into per-port status details.

        Example output format:
           1  U/U    100F  104575713   46802349 ...
          14  U/D      0H          0          0 ...
         U24  U/U   1000F  329265178  170170901 ...

        - Port: number with optional U prefix (U24 = uplink port 24)
        - Link: U/U = up/up (connected), U/D = up/down (disconnected)
        - Rate: 100F = 100Mbps Full, 1000F = 1Gbps Full, 0H = no link
        """
        statuses: dict[int, PortStatus] = {}

        for line in output.strip().splitlines():
            raw = line.strip()
            if not raw:
                continue

            # Match port number (with optional U prefix for uplink ports)
            # Examples: "1", "14", "U24"
            match = re.match(r"^U?(\d+)\s+(.*)", raw)
            if not match:
                continue

            port = int(match.group(1))
            rest = match.group(2)

            # Parse link status: U/U = connected, U/D = disconnected
            connected: bool | None = None
            link_match = re.search(r"\bU/([UD])\b", rest)
            if link_match:
                connected = link_match.group(1) == "U"
            elif "disabled" in rest.lower():
                connected = False

            # Parse rate: 100F, 1000F, 0H, etc.
            # The number is the speed in Mbps, letter is duplex (F=Full, H=Half)
            speed_mbps: int | None = None
            speed_display: str | None = None
            rate_match = re.search(r"\b(\d+)[FH]\b", rest)
            if rate_match:
                speed_mbps = int(rate_match.group(1))
                if speed_mbps == 0:
                    speed_mbps = None  # 0H means no link
                elif speed_mbps >= 1000 and speed_mbps % 1000 == 0:
                    speed_display = f"{speed_mbps // 1000} Gbps"
                else:
                    speed_display = f"{speed_mbps} Mbps"

            # Port type detection (SFP ports are typically 25/26 on USW-24-PoE)
            # For now we can't reliably detect this from the output
            port_type: str | None = None

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

    @staticmethod
    def _parse_cable_diag_output(output: str) -> dict[int, CableTestResult]:
        """Parse CLI 'sh cable-diag' output into structured results.

        Example output format:
        Port   |  Speed | Local pair | Pair length | Pair status
        --------+--------+------------+-------------+---------------
          gi1   |  auto  |    Pair A  |    24.00    | Normal
                              Pair B  |    24.00    | Normal
                              Pair C  |     N/A     | Not Supported
                              Pair D  |     N/A     | Not Supported

        Status values: Normal=OK, Open, Short, Not Supported=N/A
        """
        results: dict[int, CableTestResult] = {}
        lines = output.strip().splitlines()
        now = datetime.now(timezone.utc)

        _LOGGER.debug("Parsing cable diag output, %d lines", len(lines))

        if not lines:
            _LOGGER.warning("No lines to parse in cable diag output")
            return results

        current_port: int | None = None
        current_result: CableTestResult | None = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip header and separator lines
            if line.startswith(("-", "=", "Port")) or "--------" in line:
                continue

            # Check if this line starts with a port identifier (gi1, gi2, etc.)
            port_match = re.match(r"gi(\d+)\s*\|", line)
            if port_match:
                current_port = int(port_match.group(1))
                current_result = CableTestResult(port=current_port, last_tested=now)
                results[current_port] = current_result
                _LOGGER.debug("Found port %d in line: %s", current_port, line[:60])

                # Check if this is a fiber port (line contains "Fiber" after the port)
                if "fiber" in line.lower():
                    # Mark all pairs as Fiber - no cable test possible
                    current_result.pair_1_status = STATUS_FIBER
                    current_result.pair_2_status = STATUS_FIBER
                    current_result.pair_3_status = STATUS_FIBER
                    current_result.pair_4_status = STATUS_FIBER
                    _LOGGER.debug("Port %d is fiber", current_port)
                    continue

            if current_result is None:
                continue

            # Parse pair data from this line
            # Look for: Pair [A-D] | length | status
            pair_match = re.search(
                r"Pair\s+([A-D])\s*\|\s*([^\|]+)\s*\|\s*(.+)$",
                line,
                re.IGNORECASE,
            )
            if pair_match:
                pair_letter = pair_match.group(1).upper()
                length_str = pair_match.group(2).strip()
                status_str = pair_match.group(3).strip()

                _LOGGER.debug(
                    "Port %d Pair %s: length=%s status=%s",
                    current_result.port, pair_letter, length_str, status_str
                )

                # Map pair letter to index
                pair_index = {"A": 1, "B": 2, "C": 3, "D": 4}.get(pair_letter)
                if pair_index is None:
                    continue

                # Parse length
                length: float | None = None
                if length_str.lower() not in ("n/a", "na", "-", ""):
                    try:
                        length = float(length_str)
                    except ValueError:
                        pass

                # Normalize status
                status = _normalize_cable_status(status_str)

                # Set the pair result
                _set_pair_result(current_result, pair_index, status, length)

        _LOGGER.debug("Parsed %d port results", len(results))
        if not results:
            _LOGGER.warning("Could not parse CLI cable-diag output: %s", output)

        return results


def _normalize_cable_status(status: str) -> str:
    """Normalize a cable status string from CLI output."""
    status = status.strip().lower()
    if status in ("normal", "ok", "good"):
        return STATUS_OK
    if status in ("open", "disconnect", "disconnected"):
        return STATUS_OPEN
    if status in ("short",):
        return STATUS_SHORT
    if status in ("not supported", "n/a", "na", "-", ""):
        return STATUS_NOT_TESTED
    return STATUS_UNKNOWN


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
