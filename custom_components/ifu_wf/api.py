"""Local IFU-WF HTML/XML protocol, independent of Home Assistant."""

import asyncio
import math
import re
from dataclasses import dataclass
from html import unescape
from ipaddress import ip_address
from xml.etree import ElementTree

from aiohttp import ClientError, ClientSession, ClientTimeout, encode_basic_auth
from yarl import URL

PAGE = "/login/ifuwf.htm"
STATUS = "/login/stamon.xml"
MODES = {"HEAT": "1", "DRY": "2", "COOL": "3", "FAN": "7", "AUTO": "8"}
VANES = {
    "AUTO": "0",
    "P1": "1",
    "P2": "2",
    "P3": "3",
    "P4": "4",
    "P5": "5",
    "Swing": "7",
}
FANS = {"AUTO": "0", "LOW": "2", "MID1": "3", "MID2": "5", "MID": "5", "HI": "6"}


class IfuWfError(Exception):
    """A connection, protocol, or command failure."""


class IfuWfAuthError(IfuWfError):
    """Device credentials are missing, invalid, or rejected."""


def normalize_host(value: str) -> str:
    """Accept only a hostname or IP address."""
    host = value.strip().lower().rstrip(".")
    try:
        return str(ip_address(host))
    except ValueError:
        pass
    if (
        not host
        or len(host) > 253
        or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        )
    ):
        raise ValueError("Enter a hostname or IP address, not a URL")
    return host


@dataclass(frozen=True)
class Capabilities:
    """Capabilities advertised by the device's active script flags."""

    modes: tuple[str, ...]
    fans: tuple[str, ...]
    vanes: tuple[str, ...]
    temperatures: tuple[float, ...]


@dataclass(frozen=True)
class DeviceState:
    """Confirmed device state, never an optimistic command result."""

    device_id: str
    current_temperature: float
    target_temperature: float
    power: bool
    mode: str
    fan: str
    vane: str
    capabilities: Capabilities


def parse_state(page: str, status: str) -> DeviceState:
    """Parse the observed IFU-WF firmware format; reject unknown layouts."""
    try:
        identity = re.search(r"\bIFU-WF[0-9A-Fa-f]{8}\b", page)
        if identity is None:
            raise ValueError("Missing IFU-WF module identity")
        flags = {}
        for name in ("Getvane", "Getfspeed", "Gettemp", "Getmode"):
            match = re.search(rf"\b{name}\(\s*([01](?:\s*,\s*[01])?)\s*\)\s*;", page)
            if match is None:
                raise ValueError(f"Missing capability flag {name}")
            flags[name] = tuple(int(value) for value in match[1].split(","))
        auto, heat = flags["Getmode"]
        capabilities = Capabilities(
            modes=tuple(
                mode
                for mode in MODES
                if (mode != "HEAT" or heat) and (mode != "AUTO" or auto)
            ),
            fans=("AUTO", "LOW", "MID1", "MID2", "HI")
            if flags["Getfspeed"] == (1,)
            else ("AUTO", "LOW", "MID", "HI"),
            vanes=tuple(VANES) if flags["Getvane"] == (1,) else (),
            temperatures=tuple(
                value / 10
                for value in range(
                    160,
                    316 if flags["Gettemp"] == (1,) else 311,
                    5 if flags["Gettemp"] == (1,) else 10,
                )
            ),
        )
        # Room temperature is server-rendered, not present in stamon.xml.
        visible = re.sub(r"<script\b.*?</script>", "", page, flags=re.S | re.I)
        visible = unescape(re.sub(r"<[^>]+>", " ", visible))
        room = re.search(r"TempRoom\[°C\]\s+(-?\d+(?:\.\d+)?)", visible)
        if room is None:
            raise ValueError("Missing room temperature")
        if "<!" in status:
            raise ValueError("XML declarations/entities are not supported")
        root = ElementTree.fromstring(status)
        if root.tag != "response":
            raise ValueError("Unexpected XML root")
        values = [(root.findtext(f"m{i}") or "").strip() for i in range(5)]
        power, vane, fan, temperature, mode = values
        target = float(temperature)
        if (
            power not in ("ON", "OFF")
            or mode not in capabilities.modes
            or fan not in capabilities.fans
            or (capabilities.vanes and vane not in capabilities.vanes)
            or target not in capabilities.temperatures
        ):
            raise ValueError("Unsupported state value")
        # Firmware sometimes returns an empty LED indicator with valid readings.
        # Empty means unknown; preserve explicit faults and reject missing tags.
        indicator = root.findtext("am3")
        if indicator is None or indicator.strip() not in ("", "1"):
            raise ValueError("CN105 connection is unavailable")
        return DeviceState(
            identity[0].upper(),
            float(room[1]),
            target,
            power == "ON",
            mode,
            fan,
            vane,
            capabilities,
        )
    except (ValueError, ElementTree.ParseError) as err:
        raise IfuWfError(f"Invalid IFU-WF response: {err}") from err


class IfuWfClient:
    """Serialize reads and full-form writes using a caller-owned HTTP session."""

    def __init__(
        self, session: ClientSession, host: str, username: str = "", password: str = ""
    ) -> None:
        if (password and not username) or ":" in username:
            raise IfuWfAuthError("Invalid username")
        self._session = session
        self.host = normalize_host(host)
        self._base = URL.build(scheme="http", host=self.host)
        self._lock = asyncio.Lock()
        self._headers = (
            {"Authorization": encode_basic_auth(username, password)} if username else {}
        )

    async def _request(
        self, method: str, path: str, data: dict[str, str] | None = None
    ) -> str:
        try:
            async with self._session.request(
                method,
                self._base.with_path(path),
                data=data,
                timeout=ClientTimeout(total=10),
                allow_redirects=False,
                headers=self._headers,
            ) as response:
                if response.status in (401, 403):
                    raise IfuWfAuthError("The device requires authentication")
                # Never follow redirects carrying control data to another host.
                if not 200 <= response.status < 300:
                    raise IfuWfError(f"Device returned HTTP {response.status}")
                body = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    body.extend(chunk)
                    if len(body) > 131072:
                        raise IfuWfError("Device response exceeded 128 KiB")
                return body.decode("utf-8")
        except (ClientError, TimeoutError, UnicodeError) as err:
            raise IfuWfError(f"Device request failed: {err}") from err

    async def _read(self) -> DeviceState:
        page = await self._request("GET", PAGE)
        status = await self._request("GET", STATUS)
        return parse_state(page, status)

    async def async_get_state(self) -> DeviceState:
        async with self._lock:
            return await self._read()

    async def async_set(
        self,
        *,
        power: bool | None = None,
        mode: str | None = None,
        temperature: float | None = None,
        fan: str | None = None,
        vane: str | None = None,
    ) -> DeviceState:
        """Read/modify/write all five fields, then return freshly read state."""
        async with self._lock:
            state = await self._read()
            caps = state.capabilities
            mode = state.mode if mode is None else mode
            fan = state.fan if fan is None else fan
            vane = state.vane if vane is None else vane
            temperature = (
                state.target_temperature if temperature is None else temperature
            )
            if (
                mode not in caps.modes
                or fan not in caps.fans
                or (caps.vanes and vane not in caps.vanes)
                or not math.isfinite(temperature)
                or temperature not in caps.temperatures
            ):
                raise IfuWfError("Unsupported setting for this device")
            data = {
                "ifu1": "1" if (state.power if power is None else power) else "0",
                "ifu3": FANS[fan],
                "ifu4": str(round(temperature * 10)),
                "ifu5": MODES[mode],
            }
            if caps.vanes:
                data["ifu2"] = VANES[vane]
            await self._request("POST", PAGE, data)
            return await self._read()
