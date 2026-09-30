# Security

Telegram Snowball is a **local-first** workbench. It is not a hardened production service. The UI is published on loopback (`127.0.0.1:8080`). The Telegram session, API credentials, media, and database stay on the machine that runs Compose.

Fixes land on the default branch. There are no separate supported-release lines.

## Reporting a vulnerability

Do **not** open a public issue for anything exploitable.

Use [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) (Security → Report a vulnerability), or contact the maintainer from the GitHub profile.

Include impact and enough detail to reproduce. We will acknowledge the report and credit you on a fix if you want that.

## What to protect

Anyone who can reach the UI or the data directory can use the signed-in Telegram account and read scraped content.

- Keep Compose published on loopback. Do not publish `:8080` (or the API) to a LAN or the internet unless you understand that this shares the session.
- `.env` is gitignored. Never commit `TELEGRAM_API_HASH`, session material, or `SNOWBALL_SECRET_KEY`.
- `./data` holds `secret.key` and media. The Postgres volume holds the encrypted session. Treat both like credentials.
- Optional `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_PHONE` only prefill local setup. They are not a substitute for keeping the running stack private.

Telegram's terms and API limits still apply. This project is for accounts and data you are allowed to access.
