"""PAL ES gates: open buttons and input status for selected devices."""
from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PalApi
from .const import DOMAIN
from .coordinator import PalConfigEntry, PalCoordinator
from .mqtt import PalMqtt

PLATFORMS = [Platform.COVER, Platform.BUTTON, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: PalConfigEntry) -> bool:
    api = PalApi(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = PalCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _remove_deselected_devices(hass, entry, coordinator)

    # Push channel: events from the portal trigger an immediate status read.
    mqtt = PalMqtt(
        async_get_clientsession(hass),
        api,
        coordinator.handle_device_event,
        coordinator.set_mqtt_connected,
    )
    entry.async_create_background_task(hass, mqtt.async_run(), "pal_es_mqtt")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


def _remove_deselected_devices(
    hass: HomeAssistant, entry: PalConfigEntry, coordinator: PalCoordinator
) -> None:
    """Drop registry devices (and their entities) the user un-ticked in options."""
    keep = set(coordinator.selected_ids)
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        ids = {i for domain, i in device.identifiers if domain == DOMAIN}
        if ids and not ids & keep:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def _async_reload(hass: HomeAssistant, entry: PalConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PalConfigEntry) -> bool:
    entry.runtime_data.cancel_pending()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
