# PAL ES Gates for Home Assistant (unofficial)

Open your PAL gates/barriers from Home Assistant and see the gate input (reed switch) state.
Works with accounts on [portal.pal-es.com](https://portal.pal-es.com).

- Choose **which** devices appear in Home Assistant (you can change it later in the integration options).
- A **gate** (`cover`) per output showing *open/closed* from the reed input, with an **Open** command.
  Use this one on your dashboard (tile card).
- A plain **Open** button per output, e.g. `button.ewatrade_open_szlaban`.
- **Input state** binary sensor (door) per input, plus a diagnostic **Connected** sensor.
- The portal token is renewed automatically (it lives about 24 h).
- Cloud polling (default 10 s, configurable).

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
| Polling interval | 3–300 s. Each poll = 1 list request + 1 request per selected device. |
| Invert input | By default input `active` = closed, `idle` = open. Tick this if your wiring is the opposite. |

The raw value is always available in the sensor attribute `raw_status`.

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
