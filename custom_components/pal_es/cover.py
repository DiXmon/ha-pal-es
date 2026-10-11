"""Optional gate (cover) entity: open/closed state plus an "open" command.

Disabled by default for new installs. Home Assistant greys out the "open"
control of a cover that is already open, so for one-tap opening use the button
entity; enable this one for voice assistants / HomeKit or the state tile.
"""
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
    """PAL can only trigger the relay, so the only command is "open"."""

    _attr_supported_features = CoverEntityFeature.OPEN
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: PalCoordinator, device_id: str, output: int) -> None:
        super().__init__(coordinator, device_id)
        self._output = output
        self._attr_unique_id = f"{device_id}_gate_{output}"

    @property
    def name(self) -> str:
        return self.output_name(self._output)

    @property
    def device_class(self) -> CoverDeviceClass:
        if self.output_icon_type(self._output) == "garage_door":
            return CoverDeviceClass.GARAGE
        return CoverDeviceClass.GATE

    @property
    def icon(self) -> str:
        return self.output_icon(self._output)

    @property
    def is_closed(self) -> bool | None:
        state = self.output_state(self._output)
        if state == "unknown":
            return None
        return state == "closed"

    async def async_open_cover(self, **kwargs) -> None:
        try:
            await self.coordinator.api.async_open_gate(self._device_id, self._output)
        except PalApiError as err:
            raise HomeAssistantError(
                f"Cannot open {self.output_name(self._output)}: {err}"
            ) from err
        self.coordinator.schedule_refreshes_after_open()
