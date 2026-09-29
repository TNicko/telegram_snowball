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

## What it does

- ❄️ **Forward snowball:** Start from a channel, scrape its messages, then walk Telegram forwards outward — one live job, with progress you can watch and stop.
- 🎯 **Seed search:** Type `@username` or a peer id, pick the hit, and set depth, media, and whether to embed while scraping.
- 🔭 **Scope:** Drop example images (or a caption, with a multimodal vision model). Rescore the catalog so the next snowball prefers channels that look like those examples.
- 📚 **Catalogs:** Browse peers, messages, images, videos, and files. Filter, search, open a peer, export a slice.
- 🧠 **Meaning search:** Once vectors exist, search messages and images by meaning — not just keywords.
- 🕸️ **Graphs:** Who forwards from whom. Switch to each forwarded message, or to **shared images** — the same photo in two chats even when it was never forwarded.
- 🖼️ **pHash:** Fingerprint photos so reused media clusters together, alongside vision embeddings.
- 🧩 **Local models:** Download a vision model (SigLIP / CLIP / MobileNet) and a text model (E5 / BGE) onto disk. Turn embedding off to scrape without them.
- 💬 **Your session:** Sign in once. Dialogues and profile photos load in the background. Media, models, and the session stay on this machine.

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
| `api` | FastAPI on the compose network (no torch) |
| `worker` | Scrape process; claims `fetch_dialogues` / `forward_snowball`; one Telethon session |
| `embed` | Torch sidecar; claims `download_model` / `embed`; HTTP encode for search and snowball |
| `client` | Static UI on loopback `:8080`, proxies `/api` (including WebSocket login) |

Data that survives restart:

- Docker volume `snowball_pg` — database
- `./data` — media, embedding markers, `secret.key`

Stop with Ctrl+C, or `docker compose down`. Add `-v` only if you want to wipe the database volume.

## Snowball embedding

Forward snowball jobs default to **embed images** and **embed text** both on. If a toggle is on, that model must be downloaded (READY + weight files under `data/models/<id>/`) or the job is rejected. Turn a toggle off to scrape without embedding.

After scrape, the embed sidecar encodes:

- **Message text** with the selected text model (E5 / BGE) into a message-to-message space
- **Images on disk** (persisted or still in the image cache) with the selected vision model

CLIP and SigLIP also encode **text queries in the vision space** (text-to-image). MobileNet is image-only. **Do not mix E5 vectors with SigLIP vectors** — they are different spaces.

Catalog → Messages / Images has a **Meaning** search once the matching model is ready and vectors exist. Per-peer **Embed remainder** in the peer coverage modal backfills rows that were scraped before models were ready. Image embedding needs the pixels: hash-only images with no file on disk are skipped.

The Home **Models** cards open a picker. Defaults are **SigLIP2 Base** (vision) and **E5 Small multilingual** (message text).

Downloads go to `data/models/<id>/` via an **embed-sidecar** job. A download can run while a scrape job is in progress; it does not take the Telegram session. Switching the selected text or vision model clears stored vectors for that slot so they are not compared across models.

## Contributor install (optional)

`docker compose up` uses Vite HMR for the UI (`docker-compose.override.yml` bind-mounts `client/src`). Saving a client file should refresh in the browser.

API, scrape worker, and embed sidecar still need an image rebuild after Python changes, or the host path below.

To serve the static nginx client instead:

```bash
COMPOSE_FILE=docker-compose.yml docker compose up --build
```

Use a host venv only if you are changing the Python or Vite code without Docker:

```bash
docker compose up -d postgres
cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
pytest
uvicorn telegram_snowball.api.main:app --reload --host 127.0.0.1 --port 8000
python -m telegram_snowball.worker
python -m telegram_snowball.embed
cd ../client && npm install && npm run dev
```

Embedding inference lives in the **embed** Compose image (CPU PyTorch). A host venv needs `pip install -e ".[embed]"` plus a CPU/GPU torch wheel if you run the sidecar outside Docker. Point `SNOWBALL_EMBED_URL` at that process (default `http://127.0.0.1:8001`).

Investigators can keep using `docker compose up`.

## Status

Local collector and analysis workbench: scrape, catalogs, forward/shared-image graphs, pHash, and on-device text/image embeddings.
