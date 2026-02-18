"""Config flow for UniFi Cable Tester."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

from .const import (
    AUTH_METHOD_KEY,
    AUTH_METHOD_PASSWORD,
    CONF_AUTH_METHOD,
    CONF_SSH_KEY_PASSPHRASE,
    CONF_SSH_KEY_PATH,
    CONF_STARTUP_LIGHTWEIGHT_READ,
    DEFAULT_SSH_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
)
from .ssh_client import (
    UniFiAuthError,
    UniFiConnectionError,
    UniFiSSHClient,
)

_LOGGER = logging.getLogger(__name__)


class UniFiCableTesterConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for UniFi Cable Tester."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return options flow for this config entry."""
        return UniFiCableTesterOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial connection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Store connection data and move to auth step
            self._data.update(user_input)

            # Check for duplicate
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            if user_input[CONF_AUTH_METHOD] == AUTH_METHOD_KEY:
                return await self.async_step_auth_key()
            return await self.async_step_auth_password()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_SSH_PORT): int,
                vol.Required(CONF_AUTH_METHOD, default=AUTH_METHOD_PASSWORD): vol.In(
                    {
                        AUTH_METHOD_PASSWORD: "Password",
                        AUTH_METHOD_KEY: "SSH Key",
                    }
                ),
                vol.Optional(CONF_STARTUP_LIGHTWEIGHT_READ, default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_auth_password(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle password authentication step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)

            # Validate the connection
            error = await self._validate_connection(self._data)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"UniFi Switch ({self._data[CONF_HOST]})",
                    data=self._data,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="auth_password",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_auth_key(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle SSH key authentication step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)

            # Validate the connection
            error = await self._validate_connection(self._data)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"UniFi Switch ({self._data[CONF_HOST]})",
                    data=self._data,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Required(CONF_SSH_KEY_PATH): str,
                vol.Optional(CONF_SSH_KEY_PASSPHRASE, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="auth_key",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle reconfiguration — change connection or credentials."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        existing = dict(entry.data)

        if user_input is not None:
            self._data = {**existing, **user_input}

            # Route to the appropriate auth step based on selected method
            if user_input[CONF_AUTH_METHOD] == AUTH_METHOD_KEY:
                return await self.async_step_reconfigure_auth_key()
            return await self.async_step_reconfigure_auth_password()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=existing.get(CONF_HOST, "")): str,
                vol.Required(
                    CONF_PORT, default=existing.get(CONF_PORT, DEFAULT_SSH_PORT)
                ): int,
                vol.Required(
                    CONF_AUTH_METHOD,
                    default=existing.get(CONF_AUTH_METHOD, AUTH_METHOD_PASSWORD),
                ): vol.In(
                    {
                        AUTH_METHOD_PASSWORD: "Password",
                        AUTH_METHOD_KEY: "SSH Key",
                    }
                ),
                vol.Optional(
                    CONF_STARTUP_LIGHTWEIGHT_READ,
                    default=existing.get(CONF_STARTUP_LIGHTWEIGHT_READ, False),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure_auth_password(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle password auth during reconfiguration."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        existing = dict(entry.data)

        if user_input is not None:
            self._data.update(user_input)

            error = await self._validate_connection(self._data)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data=self._data,
                    title=f"UniFi Switch ({self._data[CONF_HOST]})",
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=existing.get(CONF_USERNAME, DEFAULT_USERNAME),
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure_auth_password",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure_auth_key(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle SSH key auth during reconfiguration."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        existing = dict(entry.data)

        if user_input is not None:
            self._data.update(user_input)

            error = await self._validate_connection(self._data)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data=self._data,
                    title=f"UniFi Switch ({self._data[CONF_HOST]})",
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=existing.get(CONF_USERNAME, DEFAULT_USERNAME),
                ): str,
                vol.Required(
                    CONF_SSH_KEY_PATH,
                    default=existing.get(CONF_SSH_KEY_PATH, ""),
                ): str,
                vol.Optional(
                    CONF_SSH_KEY_PASSPHRASE,
                    default=existing.get(CONF_SSH_KEY_PASSPHRASE, ""),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure_auth_key",
            data_schema=schema,
            errors=errors,
        )

    async def _validate_connection(self, data: dict[str, Any]) -> str | None:
        """Validate SSH connection to the switch.

        Returns an error key string on failure, or None on success.
        """
        kwargs: dict = {
            "host": data[CONF_HOST],
            "port": data.get(CONF_PORT, DEFAULT_SSH_PORT),
            "username": data.get(CONF_USERNAME, DEFAULT_USERNAME),
        }

        if data.get(CONF_AUTH_METHOD) == AUTH_METHOD_KEY:
            kwargs["ssh_key_path"] = data.get(CONF_SSH_KEY_PATH)
            kwargs["ssh_key_passphrase"] = data.get(CONF_SSH_KEY_PASSPHRASE) or None
        else:
            kwargs["password"] = data.get(CONF_PASSWORD)

        client = UniFiSSHClient(**kwargs)

        try:
            await client.connect()

            # Verify it's a UniFi switch by running swctrl
            output = await client.run_command("swctrl port show")
            if "command not found" in output.lower():
                return "not_unifi_switch"

            # Try to get port count to fully validate
            port_count = client._parse_port_count(output)
            if port_count == 0:
                _LOGGER.warning(
                    "Connected but could not determine port count for %s",
                    data[CONF_HOST],
                )

            return None

        except UniFiAuthError:
            return "invalid_auth"
        except UniFiConnectionError:
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error during validation")
            return "unknown"
        finally:
            await client.disconnect()


class UniFiCableTesterOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for UniFi Cable Tester."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        default_value = self.config_entry.options.get(
            CONF_STARTUP_LIGHTWEIGHT_READ,
            self.config_entry.data.get(CONF_STARTUP_LIGHTWEIGHT_READ, False),
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_STARTUP_LIGHTWEIGHT_READ,
                    default=default_value,
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
