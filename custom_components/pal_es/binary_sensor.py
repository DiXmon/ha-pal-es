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

from .coordinator import PalConfigEntry, PalCoordinator
from .entity import PalEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PalConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for dev_id, item in coordinator.data.items():
        # "outputs" is the number of relays and of inputs of the device.
        for n in range(1, int(item["info"].get("outputs") or 1) + 1):
            entities.append(PalInputSensor(coordinator, dev_id, n))
        entities.append(PalConnectedSensor(coordinator, dev_id))
    async_add_entities(entities)


class PalInputSensor(PalEntity, BinarySensorEntity):
    """Gate position from input N. "on" = open.

    Whether "active" means open or closed is set per output in the options
    (normally-open vs normally-closed sensors).
    """

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: PalCoordinator, device_id: str, n: int) -> None:
        super().__init__(coordinator, device_id)
        self._n = n
        self._attr_unique_id = f"{device_id}_in{n}"

    @property
    def name(self) -> str:
        return f"{self.output_name(self._n)} state"

    @property
    def is_on(self) -> bool | None:
        state = self.output_state(self._n)
        if state == "unknown":
            return None
        return state == "open"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"raw_status": self._inputs.get(self._n)}


class PalConnectedSensor(PalEntity, BinarySensorEntity):
    """Connection flag from the device list (refreshed every few minutes)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PalCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_connected"

    @property
    def name(self) -> str:
        return f"{self._info.get('name') or self._device_id} connected"

    @property
    def is_on(self) -> bool | None:
        value = self._info.get("connected")
        return None if value is None else bool(value)
