# IFU-WF protocol

Sanitized firmware responses are in `tests/fixtures/`.

- `GET /login/ifuwf.htm`: module identity, room temperature and capability flags.
- `GET /login/stamon.xml`: XML status rooted at `response`.
- `POST /login/ifuwf.htm`: URL-encoded control form.
- Optional HTTP Basic authentication; HTTP 401/403 triggers reauthentication.

| Status element | Meaning |
| --- | --- |
| `m0` | Power: ON/OFF |
| `m1` | Vane position |
| `m2` | Fan speed |
| `m3` | Target temperature in °C |
| `m4` | Operating mode |
| `am3` | CN105 indicator: `1` or empty accepted; other values rejected |

| Form field | Encoding |
| --- | --- |
| `ifu1` | Power: OFF=0, ON=1 |
| `ifu2` | Vane: AUTO=0, P1–P5=1–5, Swing=7 |
| `ifu3` | Fan: AUTO=0, LOW=2, MID1=3, MID2/MID=5, HI=6 |
| `ifu4` | Temperature × 10 |
| `ifu5` | Mode: HEAT=1, DRY=2, COOL=3, FAN=7, AUTO=8 |

Active `Getvane`, `Getfspeed`, `Gettemp` and `Getmode` flags determine supported
settings. Each command reads current state, preserves unchanged fields, posts
the complete form, then reads state back. Reads and commands are serialized.
Requests time out after ten seconds; redirects and automatic write retries are
disabled. Polling runs every 30 seconds.

The module name (`IFU-WF` plus eight hex digits) is used as device identity;
its stability across factory resets or hostname changes is unverified.
