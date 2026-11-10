"""Sensors (input registers) for the LuxPower LXP 3600 ACS."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATUS_CODES
from .coordinator import LuxConfigEntry, LuxCoordinator
from .entity import LuxEntity

Value = Callable[[LuxCoordinator], float | int | str | None]


@dataclass(frozen=True, kw_only=True)
class LuxSensorDescription(SensorEntityDescription):
    value_fn: Value


def u16(reg: int, scale: float = 1) -> Value:
    def fn(c: LuxCoordinator) -> float | None:
        v = c.input(reg)
        return None if v is None else round(v / scale, 3)

    return fn


def s16(reg: int, scale: float = 1) -> Value:
    def fn(c: LuxCoordinator) -> float | None:
        v = c.input(reg)
        if v is None:
            return None
        if v & 0x8000:
            v -= 0x10000
        return round(v / scale, 3)

    return fn


def u32(reg: int, scale: float = 1) -> Value:
    def fn(c: LuxCoordinator) -> float | None:
        lo, hi = c.input(reg), c.input(reg + 1)
        if lo is None or hi is None:
            return None
        return round(((hi << 16) | lo) / scale, 3)

    return fn


def _status(c: LuxCoordinator) -> str | None:
    v = c.input(0)
    return None if v is None else STATUS_CODES.get(v, f"Unknown (0x{v:02X})")


def _soc(c: LuxCoordinator) -> int | None:
    v = c.input(5)
    return None if v is None else v & 0xFF


def _soh(c: LuxCoordinator) -> int | None:
    v = c.input(5)
    return None if v is None else v >> 8


def _battery_power(c: LuxCoordinator) -> int | None:
    chg, dis = c.input(10), c.input(11)
    return None if chg is None or dis is None else chg - dis


def power(key: str, name: str, fn: Value, **kw) -> LuxSensorDescription:
    return LuxSensorDescription(
        key=key,
        name=name,
        value_fn=fn,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        **kw,
    )


def voltage(key: str, name: str, fn: Value, **kw) -> LuxSensorDescription:
    return LuxSensorDescription(
        key=key,
        name=name,
        value_fn=fn,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        **kw,
    )


def frequency(key: str, name: str, fn: Value) -> LuxSensorDescription:
    return LuxSensorDescription(
        key=key,
        name=name,
        value_fn=fn,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    )


def energy(key: str, name: str, fn: Value) -> LuxSensorDescription:
    return LuxSensorDescription(
        key=key,
        name=name,
        value_fn=fn,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    )


def temperature(key: str, name: str, fn: Value, **kw) -> LuxSensorDescription:
    return LuxSensorDescription(
        key=key,
        name=name,
        value_fn=fn,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        **kw,
    )


DIAG = {"entity_category": EntityCategory.DIAGNOSTIC}

# (key, name, today register, lifetime register)
ENERGY_COUNTERS = (
    ("inverter", "Inverter output", 31, 46),
    ("rectifier", "AC charge input", 32, 48),
    ("charge", "Battery charge", 33, 50),
    ("discharge", "Battery discharge", 34, 52),
    ("eps", "EPS output", 35, 54),
    ("export", "Grid export", 36, 56),
    ("import", "Grid import", 37, 58),
)

SENSORS: tuple[LuxSensorDescription, ...] = (
    LuxSensorDescription(key="status", name="Status", value_fn=_status),
    LuxSensorDescription(
        key="soc",
        name="Battery SOC",
        value_fn=_soc,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    LuxSensorDescription(
        key="soh",
        name="Battery SOH",
        value_fn=_soh,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        **DIAG,
    ),
    voltage("battery_voltage", "Battery voltage", u16(4, 10)),
    power("charge_power", "Battery charge power", u16(10)),
    power("discharge_power", "Battery discharge power", u16(11)),
    power("battery_power", "Battery power", _battery_power),
    voltage("grid_voltage", "Grid voltage", u16(12, 10)),
    frequency("grid_frequency", "Grid frequency", u16(15, 100)),
    power("inverter_power", "Inverter output power", u16(16)),
    power("rectifier_power", "AC charge power", u16(17)),
    voltage("eps_voltage", "EPS voltage", u16(20, 10)),
    frequency("eps_frequency", "EPS frequency", u16(23, 100)),
    power("eps_power", "EPS power", u16(24)),
    power("export_power", "Grid export power", u16(26)),
    power("import_power", "Grid import power", u16(27)),
    *(energy(f"{k}_today", f"{n} today", u16(today, 10)) for k, n, today, _ in ENERGY_COUNTERS),
    *(energy(f"{k}_total", f"{n} total", u32(total, 10)) for k, n, _, total in ENERGY_COUNTERS),
    voltage("bus_voltage_1", "Bus voltage 1", u16(38, 10), **DIAG),
    voltage("bus_voltage_2", "Bus voltage 2", u16(39, 10), **DIAG),
    LuxSensorDescription(key="fault_code", name="Fault code", value_fn=u32(60), **DIAG),
    LuxSensorDescription(key="warning_code", name="Warning code", value_fn=u32(62), **DIAG),
    temperature("internal_temperature", "Internal temperature", s16(64)),
    temperature("radiator_temperature_1", "Radiator temperature 1", s16(65), **DIAG),
    temperature("radiator_temperature_2", "Radiator temperature 2", s16(66), **DIAG),
    temperature("battery_temperature", "Battery temperature", s16(67)),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LuxSensor(coordinator, d) for d in SENSORS)


class LuxSensor(LuxEntity, SensorEntity):
    entity_description: LuxSensorDescription

    @property
    def native_value(self) -> float | int | str | None:
        return self.entity_description.value_fn(self.coordinator)
