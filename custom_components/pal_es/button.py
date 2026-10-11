"""Open buttons - one per relay of every selected device.

The button always works, whatever the input says. Its icon follows the gate
state and the attribute `gate_state` (open / closed / unknown) can be shown on
cards, e.g. a camera picture.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PalApiError
from .coordinator import PalConfigEntry, PalCoordinator
from .entity import PalEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PalConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[PalOpenButton] = []
    for dev_id, item in coordinator.data.items():
        outputs = int(item["info"].get("outputs") or 1)
        for n in range(1, outputs + 1):
            entities.append(PalOpenButton(coordinator, dev_id, n))
    async_add_entities(entities)


class PalOpenButton(PalEntity, ButtonEntity):
    def __init__(self, coordinator: PalCoordinator, device_id: str, output: int) -> None:
        super().__init__(coordinator, device_id)
        self._output = output
        self._attr_unique_id = f"{device_id}_open_{output}"

    @property
    def name(self) -> str:
        return self.output_name(self._output)

    @property
    def icon(self) -> str:
        return self.output_icon(self._output)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "gate_state": self.output_state(self._output),
            "input_status": self._inputs.get(self._output),
            "output": self._output,
        }

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.async_open_gate(self._device_id, self._output)
        except PalApiError as err:
            raise HomeAssistantError(
                f"Cannot open {self.output_name(self._output)}: {err}"
            ) from err
        self.coordinator.schedule_refreshes_after_open()
