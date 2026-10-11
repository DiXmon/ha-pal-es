"""Input status (reed switch) and connectivity sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_INVERT
from .coordinator import PalConfigEntry, PalCoordinator
from .entity import PalEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PalConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    invert = bool(entry.options.get(CONF_INVERT, False))
    entities: list[BinarySensorEntity] = []
    for dev_id, item in coordinator.data.items():
        for n in item["inputs"]:
            entities.append(PalInputSensor(coordinator, dev_id, n, invert))
        entities.append(PalConnectedSensor(coordinator, dev_id))
    async_add_entities(entities)


class PalInputSensor(PalEntity, BinarySensorEntity):
    """Gate position from the reed input.

    Observed values: "active" / "idle". Default mapping: active = closed,
    idle = open ("on" = open). Flip with the "invert" option.
    """

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(
        self, coordinator: PalCoordinator, device_id: str, n: int, invert: bool
    ) -> None:
        super().__init__(coordinator, device_id)
        self._n = n
        self._invert = invert
        self._attr_unique_id = f"{device_id}_in{n}"

    @property
    def name(self) -> str:
        return f"{self.output_name(self._n)} state"

    @property
    def is_on(self) -> bool | None:
        raw = self._inputs.get(self._n)
        if raw is None:
            return None
        opened = raw != "active"
        return not opened if self._invert else opened

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"raw_status": self._inputs.get(self._n)}


class PalConnectedSensor(PalEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Connected"

    def __init__(self, coordinator: PalCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_connected"

    @property
    def is_on(self) -> bool | None:
        value = self._info.get("connected")
        return None if value is None else bool(value)
