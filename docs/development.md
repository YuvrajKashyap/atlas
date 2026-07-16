# Development

Start the local infrastructure from the repository root:

```powershell
docker compose up -d postgres redis opensearch
```

Atlas maps PostgreSQL to host port `5433` by default to avoid colliding with an existing
local PostgreSQL installation. Containers still reach it on the standard internal port `5432`.

## Backend on the host

```powershell
Set-Location backend
uv sync
uv run alembic upgrade head
uv run uvicorn atlas.api.app:create_app --factory --reload
```

In separate terminals:

```powershell
Set-Location backend
uv run python -m atlas.scheduler
```

```powershell
Set-Location backend
uv run python -m atlas.worker
```

## Frontend on the host

```powershell
Set-Location web
pnpm install
pnpm dev
```

## Checks

```powershell
Set-Location backend
uv run ruff check .
uv run pyright
uv run pytest

Set-Location ../web
pnpm lint
pnpm build
```
