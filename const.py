"""Constants for the UniFi Cable Tester integration."""

DOMAIN = "unifi_cable_tester"

# Config keys
CONF_AUTH_METHOD = "auth_method"
CONF_SSH_KEY_PATH = "ssh_key_path"
CONF_SSH_KEY_PASSPHRASE = "ssh_key_passphrase"

AUTH_METHOD_PASSWORD = "password"
AUTH_METHOD_KEY = "key"

# Defaults
DEFAULT_SSH_PORT = 22
DEFAULT_USERNAME = "admin"

# SSH commands
CMD_PORT_SHOW = "swctrl port show"
CMD_CABLE_TEST_RUN = "swctrl cable-test run"
CMD_CABLE_TEST_RUN_PORT = "swctrl cable-test run port {port}"
CMD_CABLE_TEST_SHOW = "swctrl cable-test show"
CMD_SYSTEM_INFO = "info"

# Cable test wait time (seconds) for results to be ready
CABLE_TEST_WAIT = 8

# Sensor attribute keys
ATTR_PAIR_1_STATUS = "pair_1_status"
ATTR_PAIR_1_LENGTH = "pair_1_length"
ATTR_PAIR_2_STATUS = "pair_2_status"
ATTR_PAIR_2_LENGTH = "pair_2_length"
ATTR_PAIR_3_STATUS = "pair_3_status"
ATTR_PAIR_3_LENGTH = "pair_3_length"
ATTR_PAIR_4_STATUS = "pair_4_status"
ATTR_PAIR_4_LENGTH = "pair_4_length"
ATTR_LAST_TESTED = "last_tested"

# Cable statuses
STATUS_OK = "OK"
STATUS_OPEN = "Open"
STATUS_SHORT = "Short"
STATUS_NOT_TESTED = "Not Tested"
STATUS_UNKNOWN = "Unknown"

# Platforms
PLATFORMS = ["sensor", "button"]
