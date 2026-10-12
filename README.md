# PAL ES Gates for Home Assistant (unofficial)

Open your PAL gates, barriers and garage doors from Home Assistant and see their state
(reed switch / input). Works with accounts on [portal.pal-es.com](https://portal.pal-es.com).

- Choose **which** devices appear in Home Assistant (changeable later in the integration options).
- Devices with **one or two relays/inputs** are supported (the portal field `outputs` says how
  many). Entity names are taken from the portal fields `name1` / `name2` only, without the
  device name, e.g. `button.szlaban`.
- An **Open button** per relay. It always works, whatever the input says. Its icon follows the
  gate state, and the attribute `gate_state` (`open` / `closed` / `unknown`) is available for cards.
- An **input state** binary sensor (door) per input, plus a diagnostic **Connected** sensor.
- Per relay you can choose the **icon type** (swing gate, up-and-over garage door, barrier) and
  the **input polarity** (normally-open or normally-closed sensor).
- An optional **gate (cover)** entity, disabled by default (for voice assistants / HomeKit).
- The portal token is renewed automatically (it lives about 24 h).

> Unofficial integration, not affiliated with PAL. Provided "as is".

## Install via HACS (custom repository)

1. HACS → ⋮ (top right) → **Custom repositories**.
2. Repository: `https://github.com/DiXmon/ha-pal-es`, type: **Integration** → Add.
3. Find **PAL ES Gates (unofficial)** in HACS → Download.
4. Restart Home Assistant.
5. Settings → Devices & services → **Add integration** → *PAL ES Gates*.
6. Enter your portal login/password, then tick the devices you want.

Manual install: copy `custom_components/pal_es` into your HA `config/custom_components/` and restart.
Requires Home Assistant 2025.1.0 or newer.

## Options

Settings → Devices & services → PAL ES Gates → **Configure**:

| Option | Meaning |
| --- | --- |
| Devices | Which devices are exposed. Un-ticked devices are removed from HA. |
| Polling interval | 3–300 s, default 10 s. Used only while MQTT push is not connected; otherwise the safety poll runs every 5 minutes. |
| Icon (per relay) | Swing gate, up-and-over garage door or barrier. Open and closed icons differ. |
| Input is inverted (per relay) | Off: input `active` = closed, `idle` = open. On: the opposite. |

The options are a two-step dialog: step 1 (devices, polling) ends with **Next**; the following
screens (one per relay) set the icon and the input polarity. The last one ends with **Submit**.

The raw value is always available in the sensor attribute `raw_status`.

### Home Assistant's default "Overview" dashboard

If you use the automatic *Przegląd / Overview* dashboard, open its edit dialog (pencil → *Personalize*).
Entities shown under **Favorites** are either the ones you pinned (*Add favorite*) or, when
**Suggested entities** is on, ones Home Assistant adds because you use them often. Turn
*Suggested entities* off if you want only the entities you pinned yourself.

## How the state is determined

The device reports its input to the PAL cloud. The portal also publishes an MQTT event
(`org/<orgId>/evt/device/<deviceId>/...`) whenever a device reports something. The integration
listens to it (WebSocket, `wss://portal.pal-es.com/mqtt`, port 443, your own organisation's topics only);
on an event it reads the input status of that one device immediately (and once more after 3 s if nothing changed yet). So a change shows up
within a couple of seconds and nothing is polled in between.

As a safety net the status is still read every 5 minutes while MQTT is connected, and every
*polling interval* (default 10 s) while it is not (portal unreachable, reconnecting). After you
press *Open* the status is read again after 3 s and 8 s. The portal's device list (names,
connected flag) is refreshed every 5 minutes.

## Dashboard examples

Use the Open **button** entity (its id is `button.<device>_<name>`; check it on the device page).

Button card with state:

```yaml
type: button
entity: button.ewatrade_szlaban
name: Szlaban
tap_action:
  action: perform-action
  perform_action: button.press
  target:
    entity_id: button.ewatrade_szlaban
```

Tile showing the gate state text:

```yaml
type: tile
entity: button.ewatrade_szlaban
name: Szlaban
state_content: gate_state
tap_action:
  action: perform-action
  perform_action: button.press
  target:
    entity_id: button.ewatrade_szlaban
```

Open button on a camera picture (picture-elements card):

```yaml
type: picture-elements
camera_image: camera.gate_camera
elements:
  - type: state-icon
    entity: button.ewatrade_szlaban
    style:
      top: 90%
      left: 90%
    tap_action:
      action: perform-action
      perform_action: button.press
      target:
        entity_id: button.ewatrade_szlaban
  - type: state-badge
    entity: binary_sensor.ewatrade_szlaban_state
    style:
      top: 90%
      left: 10%
```

Add a `confirmation:` block under `tap_action` (e.g. `text: Open the gate?`) to avoid accidental taps.

## Reporting problems

Open an issue and attach **Diagnostics** (device page → ⋮ → Download diagnostics). Credentials,
tokens, IMEI, phone numbers and addresses are redacted.

## Development

```
pip install aiohttp pytest
pytest
```

Tests run the API client against a fake PAL portal; no network and no Home Assistant needed.

## License

MIT
