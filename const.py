"""Constants for the UniFi Cable Tester integration."""

DOMAIN = "unifi_cable_tester"

# Config keys
CONF_AUTH_METHOD = "auth_method"
CONF_SSH_KEY_PATH = "ssh_key_path"
CONF_SSH_KEY_PASSPHRASE = "ssh_key_passphrase"
CONF_STARTUP_LIGHTWEIGHT_READ = "startup_lightweight_read"

AUTH_METHOD_PASSWORD = "password"
AUTH_METHOD_KEY = "key"

# Defaults
DEFAULT_SSH_PORT = 22
DEFAULT_USERNAME = "admin"

# SSH commands (shell mode)
CMD_PORT_SHOW = "swctrl port show"
CMD_SYSTEM_INFO = "info"

# CLI mode commands for cable testing
# Enter CLI mode with "cli", then run cable diag, then "exit" twice
CMD_CLI_ENTER = "cli"
CMD_CLI_EXIT = "exit"
CMD_CABLE_DIAG = "sh cable-diag int gi{port}"

# Cable test wait time (seconds) - reduced since CLI command is synchronous
CABLE_TEST_WAIT = 2

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
ATTR_PORT_CONNECTED = "port_connected"
ATTR_PORT_SPEED = "port_speed"
ATTR_PORT_SPEED_MBPS = "port_speed_mbps"
ATTR_PORT_TYPE = "port_type"

# Cable statuses
STATUS_OK = "OK"
STATUS_OPEN = "Open"
STATUS_SHORT = "Short"
STATUS_NOT_TESTED = "Not Tested"
STATUS_TEST_FAILED = "Test Failed"
STATUS_FIBER = "Fiber"
STATUS_UNKNOWN = "Unknown"

# Test run status values
TEST_RUN_IDLE = "Idle"
TEST_RUN_RUNNING = "Running"
TEST_RUN_COMPLETED = "Completed"
TEST_RUN_FAILED = "Failed"

# Test run status attributes
ATTR_TEST_STARTED = "test_started"
ATTR_TEST_COMPLETED = "test_completed"
ATTR_PORTS_TESTED = "ports_tested"
ATTR_PORTS_FAILED = "ports_failed"
ATTR_ERROR_MESSAGE = "error_message"
ATTR_TEST_DURATION = "test_duration_seconds"

# Platforms
PLATFORMS = ["sensor", "button"]
