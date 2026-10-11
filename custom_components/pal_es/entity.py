"""Base entity."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ICON_TYPE, CONF_OUTPUT_INVERT, DOMAIN
from .coordinator import PalCoordinator
from .logic import GateState, gate_icon, gate_state, output_settings


class PalEntity(CoordinatorEntity[PalCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PalCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        info = coordinator.data[device_id]["info"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=info.get("name") or device_id,
            manufacturer="PAL",
            model=info.get("model"),
            sw_version=str(info.get("version")) if info.get("version") else None,
            serial_number=device_id,
        )

    @property
    def _info(self) -> dict[str, Any]:
        return (self.coordinator.data.get(self._device_id) or {}).get("info", {})

    @property
    def _inputs(self) -> dict[int, str | None]:
        return (self.coordinator.data.get(self._device_id) or {}).get("inputs", {})

    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data

    def output_name(self, n: int) -> str:
        """Name of relay n: the portal's name1 / name2 field."""
        return self._info.get(f"name{n}") or f"Output {n}"

    def output_state(self, n: int) -> GateState:
        settings = output_settings(
            self.coordinator.config_entry.options, self._device_id, n
        )
        return gate_state(self._inputs.get(n), settings[CONF_OUTPUT_INVERT])

    def output_icon(self, n: int) -> str:
        settings = output_settings(
            self.coordinator.config_entry.options, self._device_id, n
        )
        return gate_icon(settings[CONF_ICON_TYPE], self.output_state(n))

    def output_icon_type(self, n: int) -> str:
        return output_settings(
            self.coordinator.config_entry.options, self._device_id, n
        )[CONF_ICON_TYPE]
