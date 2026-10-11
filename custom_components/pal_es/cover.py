"""Gate entity: shows open/closed from the reed input and opens via the portal."""
from __future__ import annotations

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PalApiError
from .const import CONF_INVERT
from .coordinator import PalConfigEntry, PalCoordinator
from .entity import PalEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PalConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[PalGate] = []
    for dev_id, item in coordinator.data.items():
        outputs = int(item["info"].get("outputs") or 1)
        for n in range(1, outputs + 1):
            entities.append(PalGate(coordinator, dev_id, n))
    async_add_entities(entities)


class PalGate(PalEntity, CoverEntity):
    """PAL can only trigger the output, so the only command is "open".

    State comes from input N (reed switch). Default mapping: input "active" =
    closed, anything else = open; the "invert" option flips it. Without a
    readable input the state is unknown, opening still works.
    """

    _attr_device_class = CoverDeviceClass.GATE
    _attr_supported_features = CoverEntityFeature.OPEN

    def __init__(self, coordinator: PalCoordinator, device_id: str, output: int) -> None:
        super().__init__(coordinator, device_id)
        self._output = output
        self._attr_unique_id = f"{device_id}_gate_{output}"

    @property
    def name(self) -> str:
        return self.output_name(self._output)

    @property
    def is_closed(self) -> bool | None:
        raw = self._inputs.get(self._output)
        if raw is None:
            return None
        closed = raw == "active"
        if self.coordinator.config_entry.options.get(CONF_INVERT, False):
            closed = not closed
        return closed

    async def async_open_cover(self, **kwargs) -> None:
        try:
            await self.coordinator.api.async_open_gate(self._device_id, self._output)
        except PalApiError as err:
            raise HomeAssistantError(
                f"Cannot open {self.output_name(self._output)}: {err}"
            ) from err
        self.coordinator.schedule_refreshes_after_open()
