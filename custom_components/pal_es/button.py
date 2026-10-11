"""Open buttons - one per output of every selected device."""
from __future__ import annotations

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
    _attr_icon = "mdi:gate-open"

    def __init__(self, coordinator: PalCoordinator, device_id: str, output: int) -> None:
        super().__init__(coordinator, device_id)
        self._output = output
        self._attr_unique_id = f"{device_id}_open_{output}"

    @property
    def name(self) -> str:
        return f"Open {self.output_name(self._output)}"

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.async_open_gate(self._device_id, self._output)
        except PalApiError as err:
            raise HomeAssistantError(f"Cannot open {self.output_name(self._output)}: {err}") from err
        self.coordinator.schedule_refreshes_after_open()
