# Development

Install [uv](https://docs.astral.sh/uv/) and run:

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
```

Tests run without hardware. Sanitize captures before adding them to `tests/fixtures/`.

## Local Home Assistant

With a Docker engine and Compose v2 available:

```sh
docker compose up -d --wait --wait-timeout 180
```

Open <http://127.0.0.1:8124>, complete onboarding, and add IFU-WF using your
device address and optional credentials. Controls operate the real AC.
Copy `.env.example` to `.env` to change the port or container timezone.

After editing integration code:

```sh
docker compose restart homeassistant
docker compose logs --tail=100 -f homeassistant
```

`docker compose down` stops the instance and keeps its data.
`docker compose down --volumes` also deletes its accounts, settings and history.
