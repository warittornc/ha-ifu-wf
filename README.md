# ha-ifu-wf

Home Assistant custom integration for local HTTP control of IFU-WF air
conditioner Wi-Fi modules. Provides a climate entity with power, target temperature, operating mode, fan
speed, and vane position. Room temperature is not reported.

**Status: implemented and tested locally; live reads and a container staging
instance verified. Live command coverage is still limited.**
The supported protocol is the firmware layout captured in `tests/fixtures/`.
HTTP Basic authentication is supported with optional device credentials.

## Install in Home Assistant

Target version: Home Assistant **2026.11.1**. Copy `custom_components/ifu_wf`
into your Home Assistant configuration directory under `custom_components/ifu_wf`
and restart Home Assistant. Open **Settings → Devices & services → Add
integration**, search for **IFU-WF**, and enter the module's hostname or IP
address, for example `192.168.1.60` (without `http://`).

For password-protected devices, enter the device username and password during setup.
For an existing entry, use its menu → **Reconfigure** to update credentials.
Re-enter the password when updating; leave both credential fields empty for
unprotected devices. Home Assistant stores credentials in its local config entry.
The device uses plain HTTP, so Basic authentication is not encrypted in transit.

Home Assistant must be able to reach the device on port 80. Supported modes,
fan speeds, temperature range and vane positions are detected from the device.
State is refreshed every 30 seconds from the small `stamon.xml` status file. See [protocol notes](docs/device-protocol.md).

## Development

Run a local Home Assistant instance with any Docker Compose runtime:

```sh
docker compose up -d --wait --wait-timeout 180
```

Open <http://127.0.0.1:8124>. For uv setup, tests, and local development, see [CONTRIBUTING.md](CONTRIBUTING.md).
