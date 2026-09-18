<div align="center">

<h1>
  <img src="client/src/assets/snowball-icon-readme.png" alt="" width="36" height="42" align="absmiddle"> Telegram Snowball
</h1>

**A telegram scraper and media analysis workbench.**<br>
Crawl  -  Collect  -  Process  -  Analyse

<p>
  <a href="#quick-start"><img src="https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-green" alt="Apache License 2.0"></a>
</p>

</div>

## What it is

- A **local web app** in Docker (nginx + FastAPI + one worker)
- **One worker**, **one Telegram session**, **one job at a time**
- Postgres (pgvector) for messages, peers, jobs, and graph edges
- Media, models, and the session secret on a `./data` volume
- Forward snowball with live progress; catalogs and graphs coming next

It is not a hosted SaaS, not a harvester fleet, and not a scrape of chats you cannot already see. **No NVIDIA/GPU is required to boot.**

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Compose v2 (macOS, Linux, or Windows)
- A Telegram account and a [Telegram API app](https://my.telegram.org)

Host Python and Node are **not** required.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Open http://127.0.0.1:8080. The first-run wizard walks through creating a Telegram API app, then signing in (phone → code → 2FA). After login you land on Home; dialogues (peer full + profile photos only) start loading in the background.

Compose services:

| Service | Role |
|---|---|
| `postgres` | Postgres 16 + pgvector (internal only) |
| `api` | FastAPI on the compose network |
| `worker` | One process; claims at most one job; one Telethon session |
| `client` | Static UI on loopback `:8080`, proxies `/api` (including WebSocket login) |

Data that survives restart:

- Docker volume `snowball_pg` — database
- `./data` — media, embedding markers, `secret.key`

Stop with Ctrl+C, or `docker compose down`. Add `-v` only if you want to wipe the database volume.

## Snowball embedding gate

Forward snowball jobs default to **embed images** and **embed text** both on. If a toggle is on, that model must be healthy or the job is rejected. Turn a toggle off to scrape without that embedder. Hashing always runs on downloaded media. Dialogue import is not gated on embeddings.

v1 does not download GPU models at boot. Until real weights are wired, you can mark a model ready on the data volume:

```bash
mkdir -p data/models/siglip2-base-patch16-256 data/models/bge-m3
touch data/models/siglip2-base-patch16-256/READY data/models/bge-m3/READY
```

## Contributor install (optional)

`docker compose up` uses Vite HMR for the UI (`docker-compose.override.yml` bind-mounts `client/src`). Saving a client file should refresh in the browser.

API and worker still need an image rebuild after Python changes, or the host path below.

To serve the static nginx client instead:

```bash
COMPOSE_FILE=docker-compose.yml docker compose up --build
```

Use a host venv only if you are changing the Python or Vite code without Docker:

```bash
docker compose up -d postgres
cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
uvicorn telegram_snowball.api.main:app --reload --host 127.0.0.1 --port 8000
python -m telegram_snowball.worker
cd ../client && npm install && npm run dev
```

Investigators can keep using `docker compose up`.

## Status

Early scaffolding. Collection, catalogs, graphs, and local embedding models are being built in phases.
