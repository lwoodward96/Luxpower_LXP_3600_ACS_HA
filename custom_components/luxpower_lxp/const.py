"""Constants and register map for the LuxPower LXP 3600 ACS."""

from __future__ import annotations

DOMAIN = "luxpower_lxp"

CONF_DONGLE_SERIAL = "dongle_serial"
CONF_INVERTER_SERIAL = "inverter_serial"

DEFAULT_PORT = 8000
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10

# Blocks polled every update: (start register, count)
INPUT_BLOCKS = ((0, 40), (40, 40))
HOLD_BLOCKS = ((0, 40), (40, 40), (80, 40), (120, 40))

# ---- Holding registers -------------------------------------------------------
REG_TIME = 12  # 12..14: year|month, day|hour, minute|second
REG_FUNCTION = 21  # bit field, see BIT_*

BIT_EPS = 0
BIT_AC_CHARGE = 7
BIT_POWER_ON = 9  # 1 = normal operation, 0 = standby
BIT_FORCED_DISCHARGE = 10
BIT_CHARGE_PRIORITY = 11
BIT_FEED_IN_GRID = 15

REG_CHARGE_RATE = 64
REG_DISCHARGE_RATE = 65
REG_AC_CHARGE_RATE = 66
REG_AC_CHARGE_SOC_LIMIT = 67
REG_AC_CHARGE_TIMES = 68  # 68..73, three start/end pairs
REG_CHARGE_PRIORITY_RATE = 74
REG_CHARGE_PRIORITY_SOC_LIMIT = 75
REG_CHARGE_PRIORITY_TIMES = 76  # 76..81
REG_FORCED_DISCHARGE_RATE = 82
REG_FORCED_DISCHARGE_SOC_LIMIT = 83
REG_FORCED_DISCHARGE_TIMES = 84  # 84..89
REG_FEED_IN_GRID_RATE = 103
REG_DISCHARGE_CUTOFF_SOC = 105
REG_EPS_DISCHARGE_CUTOFF_SOC = 125

# ---- Input register 0: operating state ----------------------------------------
STATUS_CODES: dict[int, str] = {
    0x00: "Standby",
    0x01: "Fault",
    0x02: "Programming",
    0x04: "PV on-grid",
    0x08: "PV charge",
    0x0C: "PV charge on-grid",
    0x10: "Battery on-grid",
    0x11: "Bypass",
    0x14: "PV & battery on-grid",
    0x19: "PV charge + battery on-grid",
    0x20: "AC charge",
    0x28: "PV & AC charge",
    0x40: "Battery off-grid",
    0x60: "Off-grid + battery charge",
    0x80: "PV off-grid",
    0x88: "PV charge off-grid",
    0xC0: "PV & battery off-grid",
}
