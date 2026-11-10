# LuxPower LXP 3600 ACS – local Home Assistant integration

A lightweight custom integration that monitors **and controls** a LuxPower
LXP 3600 ACS (AC-coupled battery inverter) over your local network. It talks
directly to the LuxPower WiFi dongle on TCP port 8000. There are no cloud calls
and no extra Python dependencies.

## Requirements

* The WiFi dongle is on your LAN with a fixed IP address (use a DHCP reservation).
* Port 8000 on the dongle is reachable. This is the default "TCP server" mode of
  the dongle. The LuxPower cloud keeps working at the same time.
* You know the **dongle serial** (on the dongle sticker, e.g. `BA12345678`)
  and the **inverter serial** (on the inverter label). Both are 10 characters.
* Home Assistant 2025.6 or newer.

## Installation

**HACS:** add this repository as a custom repository (category *Integration*),
install **LuxPower LXP 3600 ACS (local)**, then restart Home Assistant.

**Manual:** copy `custom_components/luxpower_lxp` into your
`<config>/custom_components/` folder, then restart Home Assistant.

Then go to *Settings → Devices & services → Add integration → LuxPower LXP 3600 ACS*
and enter the dongle IP, port (8000) and both serial numbers. The polling interval
(default 30 s) can be changed later under *Configure*.

## Entities

### Sensors (read-only)
| Entity | Register |
|---|---|
| Status (Standby, AC charge, Battery on-grid, Battery off-grid, Fault …) | input 0 |
| Battery SOC / SOH, battery voltage | input 5, 4 |
| Battery charge / discharge power and signed *Battery power* (+ = charging) | input 10, 11 |
| Grid voltage / frequency | input 12, 15 |
| Inverter output power, AC charge (rectifier) power | input 16, 17 |
| EPS voltage / frequency / power | input 20, 23, 24 |
| Grid export / import power | input 26, 27 |
| Energy today and lifetime for: inverter output, AC charge input, battery charge, battery discharge, EPS, grid export, grid import | input 31–37, 46–59 |
| Internal, radiator and battery temperatures | input 64–67 |
| Bus voltages, fault code, warning code (diagnostic) | input 38–39, 60–63 |

The energy sensors use `total_increasing` and can be used directly in the
Energy dashboard: battery charge/discharge for the battery, and grid
import/export if the inverter's CT measures your grid connection.

### Controls
| Entity | Type | Register |
|---|---|---|
| AC charge | switch | hold 21 bit 7 |
| Forced discharge | switch | hold 21 bit 10 |
| Charge priority | switch | hold 21 bit 11 |
| Feed-in to grid | switch | hold 21 bit 15 |
| EPS (backup) output | switch | hold 21 bit 0 |
| Inverter on (off = standby) | switch | hold 21 bit 9 |
| System charge / discharge rate (%) | number | hold 64 / 65 |
| AC charge rate / SOC limit (%) | number | hold 66 / 67 |
| Charge priority rate / SOC limit (%) | number | hold 74 / 75 |
| Forced discharge rate / SOC limit (%) | number | hold 82 / 83 |
| Feed-in grid power limit (%) | number | hold 103 |
| Discharge cut-off SOC on-grid / EPS (%) | number | hold 105 / 125 |
| AC charge, charge priority and forced discharge start/end times, 3 slots each | time | hold 68–73, 76–81, 84–89 |
| Sync inverter clock | button | hold 12–14 |

Time slots 2 and 3 are disabled by default. Enable them in the entity settings if
you need them.

Switches use read-modify-write on register 21, so changing one flag never
changes the others.

### Service: `luxpower_lxp.write_holding_register`
Writes a raw value to any holding register, for settings this integration has no
entity for. **Use it with care.** Writing the wrong register can change grid
protection settings.

```yaml
action: luxpower_lxp.write_holding_register
data:
  register: 66
  value: 50
```

## Blueprint: Octopus cheap-rate charging (Intelligent Octopus Go)

[`blueprints/automation/luxpower_lxp/octopus_cheap_rate_battery.yaml`](blueprints/automation/luxpower_lxp/octopus_cheap_rate_battery.yaml)

* **Cheap rate on:** the battery charges from the grid and does not discharge.
* **Cheap rate off:** grid charging stops and the battery discharges to power
  your home.
* **Power cap:** charging and discharging are capped at a percentage of rated
  power (default **50%**, which is 1.8 kW).
* **Export (optional, off by default):** force-discharge to the grid at peak,
  down to a minimum SOC.

**Import:** *Settings → Automations & scenes → Blueprints → Import blueprint*, and
paste:

```
https://github.com/lwoodward96/Luxpower_LXP_3600_ACS_HA/blob/claude/brave-dijkstra-9t6oir/blueprints/automation/luxpower_lxp/octopus_cheap_rate_battery.yaml
```

Then create an automation from it. For the cheap-rate sensor, choose
`binary_sensor.octopus_energy_<account>_intelligent_dispatching` from the
[Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy).
That sensor is on during the off-peak window and during smart-charge dispatches.

The blueprint sets AC charge slot 1 (and forced discharge slot 1, when export is
enabled) to 00:00–23:59, and turns charging on and off itself. It overwrites any
schedule set in those slots in the LuxPower app. It re-applies its settings every
15 minutes, but values that haven't changed are not rewritten to the inverter.

## Example automation: charge from the grid overnight

```yaml
automation:
  - alias: Cheap rate battery charge
    triggers:
      - trigger: time
        at: "00:25"
    actions:
      - action: time.set_value
        target: { entity_id: time.luxpower_lxp_3600_acs_ac_charge_start_1 }
        data: { time: "00:30:00" }
      - action: time.set_value
        target: { entity_id: time.luxpower_lxp_3600_acs_ac_charge_end_1 }
        data: { time: "04:30:00" }
      - action: number.set_value
        target: { entity_id: number.luxpower_lxp_3600_acs_ac_charge_soc_limit }
        data: { value: 100 }
      - action: switch.turn_on
        target: { entity_id: switch.luxpower_lxp_3600_acs_ac_charge }
```

## Troubleshooting

* **"Could not open a TCP connection"**: the IP or port is wrong, or the dongle is
  unreachable. Test it with `nc -vz <ip> 8000`.
* **"The dongle reports different serials"**: copy the serials shown in the
  message into the form.
* **"Connected … but the inverter did not reply"**: enable debug logging (below),
  try again, and look for `TX`/`RX` lines in the log.
* Enable debug logs to see traffic:
  ```yaml
  logger:
    logs:
      custom_components.luxpower_lxp: debug
  ```

## Development

The protocol and client code does not depend on Home Assistant and has its own
tests:

```bash
pip install pytest pytest-asyncio
pytest
```

## Disclaimer

This is an unofficial integration. You use it at your own risk. Changing inverter
settings can affect your battery and your grid connection.
