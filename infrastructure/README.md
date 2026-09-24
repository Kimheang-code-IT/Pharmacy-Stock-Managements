# Infrastructure — Stock & POS

Everything needed to run Stock & POS in Docker lives in **this folder**:
the Compose files, the `.env` templates, the Windows launchers, and the helper
scripts. The application code stays in `../backend` and `../frontend`; the
Compose files build from those folders.

- `docker-compose.yml` — the **single** stack (PostgreSQL, Redis, API, frontend, Telegram bot).
- `.env.local.example` — template for the local-only run (recommended).
- `Start Stock POS.bat` / `Stop Stock POS.bat` — one-click daily use.
- `First Time Setup.bat` — first run (creates `.env`, builds, starts).
- `scripts/` — PowerShell helpers (see the bottom of this file).
- `nginx/stock-pos.conf` — optional HTTPS host reverse-proxy example (TLS termination).

## 1. Local-only deployment in one minute (Windows PC)

Requirements: **Docker Desktop** installed and running. Git is optional (only
needed for the clone/upgrade step).

1. Get the code (pick one):
   - `git clone https://github.com/Kimheang-code-IT/stock_pos.git`
   - or download the ZIP and unzip it.
2. Open this `infrastructure` folder.
3. Double-click **`First Time Setup.bat`** and wait. It:
   - generates `infrastructure\.env` with strong random secrets,
   - builds the API + frontend images from source (no GHCR account needed),
   - starts PostgreSQL, Redis, API and frontend,
   - prints the administrator email and password — **save them**.
4. Double-click **`Start Stock POS.bat`** (or open <http://localhost>).

In the local-only mode the app binds to **`127.0.0.1:80`**, so it is reachable
from this computer only. PostgreSQL, Redis and the API are **not** published to
the host at all — they stay on the internal Docker network.

## 2. Daily use

| Action | How |
|---|---|
| Start and open the app | double-click `Start Stock POS.bat` |
| Open anytime (keyboard) | press **Ctrl+Alt+S** |
| Open from shortcuts | Desktop / Start Menu → *Yoeun Sokhon Pharmacy* |
| Stop safely | double-click `Stop Stock POS.bat` |
| Restart | `scripts\stockpos\restart-system.bat` |
| Start automatically at sign-in | `scripts\stockpos\install-autostart.bat` |
| Desktop shortcut only | `scripts\stockpos\install-desktop-shortcut.bat` |
| Remove auto-start | `scripts\stockpos\remove-autostart.bat` |

`Start Stock POS.bat` waits for Docker Desktop and for `GET /health/ready`
(which checks PostgreSQL and Redis) before opening the browser, so it is safe
to double-click right after logging in.

### Open with a keyboard shortcut

`install-desktop-shortcut.bat` (also run by `install-autostart.bat`) creates the
*Yoeun Sokhon Pharmacy* Desktop + Start Menu shortcuts and assigns the global
hotkey **Ctrl+Alt+S** to the Desktop shortcut, so the app can be opened from
anywhere. Change it with e.g.:

```powershell
scripts\stockpos\install-desktop-shortcut.bat -Hotkey "CTRL+ALT+P"
```

### Start automatically when Windows signs in

`scripts\stockpos\install-autostart.bat` (current user, no admin) sets up the
whole unattended start:

- Docker Desktop is enabled to **start at sign-in** (an entry is added only when
  Docker's own *Start Docker Desktop when you sign in* toggle is off).
- A Startup shortcut runs `wait-and-open-system.bat`, which starts Docker
  Desktop if needed, brings the Compose stack up (`restart: unless-stopped`),
  waits for `GET /health/ready`, then opens the browser once.
- The Desktop/Start Menu shortcuts and the Ctrl+Alt+S hotkey are created too.

No admin rights are required. Undo with `scripts\stockpos\remove-autostart.bat`.


## 3. Configuration (`infrastructure\.env`)

`init-env.ps1` fills the secrets for you. The settings you may change:

| Key | Meaning |
|---|---|
| `FRONTEND_PORT` | host port for the app (default `80`). |
| `FRONTEND_BIND` | `127.0.0.1` = this PC only (default); set a LAN IP or `0.0.0.0` for LAN access. |
| `TELEGRAM_BOT_TOKEN` | optional; leave empty to disable Telegram. |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | unused at startup; kept only for an explicit `python -m app.seed` run. |
| `COMPOSE_PROJECT_NAME` | defaults to `stock_pos`; set to `stockmanagement` only to reuse very old volumes. |

> Never commit `.env` — it contains secrets. It is already git-ignored.

### LAN access (optional)
To open the app from another device (iPad, phone, laptop) on the same Wi-Fi:

1. Set `FRONTEND_BIND=0.0.0.0` (or the PC's LAN IP) in `.env`, then run
   `scripts\stockpos\restart-system.bat`.
2. Allow the port through Windows Firewall (one-time, asks for admin):
   `scripts\allow-lan-access.ps1` — it adds the inbound rule and prints the
   URLs to use, e.g. `http://192.168.1.50/`.
3. On the other device, connect to the **same Wi-Fi** and open that URL.

Add your frontend URL to `CORS_ORIGINS` if you keep `ENVIRONMENT=production`.
Set `FRONTEND_BASE_URL` to the LAN URL too if you use Telegram password resets
(deep links would otherwise point at `localhost`).

> Some Wi-Fi routers (guest networks, phone hotspots) use "AP/client
> isolation", which blocks device-to-device traffic regardless of the firewall.
> If a device still cannot connect, disable isolation or join the main network.
> DHCP can also change the PC's IP — set a static IP / DHCP reservation and
> update `CORS_ORIGINS` / `FRONTEND_BASE_URL` if the URL stops working.

## 4. Data, backups and reset

PostgreSQL data, Redis data and uploaded images live in Docker **named
volumes** (`stock-pgdata`, `stock-redisdata`, `stock-mediadata`) —
they survive `Stop Stock POS.bat` and image rebuilds.

### Automated, verified backups

`scripts\backup.ps1` (Windows) and `scripts\backup.sh` (Linux/CI) produce
**timestamped** artifacts in `infrastructure\backups` (git-ignored):

```powershell
.\scripts\backup.ps1                        # DB + media, 14-day retention
.\scripts\backup.ps1 -RetentionDays 30 -SkipMedia
```

Each run:
1. runs `pg_dump -Fc` (custom/`pg_restore` format) into
   `backups\stock_pos_<UTC-timestamp>.dump`;
2. tars the media volume into `backups\media_<UTC-timestamp>.tgz`;
3. **verifies integrity** with `pg_restore --list` (fails loudly on a corrupt
   archive);
4. prunes artifacts older than the retention window.

The `backup` / `media-backup` Compose services are one-shot helpers behind the
`tools` profile, so they never start with the stack:

```powershell
docker compose --profile tools run --rm backup
docker compose --profile tools run --rm media-backup
```

**Schedule it** with Windows Task Scheduler (run `backup.ps1` daily) or a host
cron job calling `backup.sh`.

### Restore

```powershell
# 1. Prove a backup is restorable into a throwaway DB (production untouched):
.\scripts\restore-test.ps1

# 2. Real restore (takes a safety backup, stops api/telegram, restores, restarts):
.\scripts\restore.ps1 -Dump .\backups\stock_pos_20260923T101500Z.dump `
                      -Media .\backups\media_20260923T101500Z.tgz `
                      -ConfirmPhrase "RESTORE DATABASE"
```

The API container runs `alembic upgrade head` on start, so the restored schema
is brought up to date automatically.

### Disk space and health

- Watch the host disk where Docker stores volumes; a full disk stops Postgres
  writes. Keep enough free space for at least two full backups.
- Deep health (Postgres + Redis): `GET /health/ready` on the API
  (<http://localhost:8100/health/ready>). Liveness: `/health/live`.
- Container health: `docker compose ps` shows `healthy` per service.

### Destructive reset

To erase everything and start over (irreversible):
```powershell
docker compose -f docker-compose.yml down -v
```
Inside the app, destructive reset/clear is guarded (password reauth + one-use
confirmation token + exact phrase + automatic pre-deletion backup) — see the
Settings page. Audit history and the protected system-event store survive.

## 5. Upgrade

```powershell
# Always back up first:
.\scripts\backup.ps1 -SkipMedia
git pull
.\scripts\install-client.ps1 -SkipGitPull   # rebuild images and restart
```
The API entrypoint runs `alembic upgrade head` on every start, so schema changes
apply automatically and existing data is preserved.

### Rollback

If an upgrade misbehaves, roll back in this order:
1. `docker compose stop api telegram-bot frontend`
2. `git checkout <previous-tag-or-commit>`
3. Restore the pre-upgrade backup with `scripts\restore.ps1` (above).
4. `.\scripts\install-client.ps1 -SkipGitPull` to rebuild the previous code and
   restart.

Never roll back only the database or only the code: keep schema and application
in step by restoring the backup taken before the upgrade.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| Browser shows a connection error | `Start Stock POS.bat`, wait ~1 minute, retry. |
| "Docker is not available yet" | Wait a minute, or run `scripts\stockpos\install-autostart.bat` to make Docker Desktop start at sign-in automatically. |
| Port 80 already in use | set `FRONTEND_PORT=8080` in `.env`, then restart. |
| Login fails after setup | the first administrator is created on the app's **Setup** page; no credentials are seeded. |
| Need logs | `docker compose logs -f frontend api` (run from this folder). |
| Wrong timezone/alerts | check `SCHEDULER_ENABLED` / `EXPIRY_ALERT_SCAN_HOUR` in the API settings. |

## 7. Scripts reference

| Script | Purpose |
|---|---|
| `scripts\backup.ps1` / `.sh` | Timestamped DB + media backup, verified, with retention. |
| `scripts\restore.ps1` | Guarded restore from a dump (safety backup + phrase). |
| `scripts\restore-test.ps1` | Restore the newest backup into a scratch DB. |
| `scripts\init-env.ps1` | Create `.env` with strong random secrets. |
| `scripts\install-client.ps1` / `.sh` | Clone + build + start from source. |
| `scripts\deploy-from-registry.ps1` / `.sh` | Pull prebuilt GHCR images and start (remote prod). |
| `scripts\start-docker.ps1` / `.sh` | Start the **development** stack (`docker compose up -d --build`). |
| `scripts\prepare-production.ps1` | First-time local prep (creates `.env`, cleans caches). |
| `scripts\stockpos\*` | Daily-use helpers behind the `.bat` files. |

Advanced Compose usage (run from this folder, where `.env` lives):
```powershell
docker compose up -d --build        # build images and start
docker compose up -d                # start (images already built)
docker compose down                 # stop (volumes preserved)
docker compose logs -f api frontend # follow logs
docker compose config --quiet       # validate config
```

There is one Compose file — `docker-compose.yml`. It runs only `db`, `redis`,
`api`, `frontend` and `telegram-bot` (no RabbitMQ, no Celery workers: scheduled
jobs run inside the API process). The `backup` / `media-backup` helpers live
behind the `tools` profile and only run when invoked explicitly. To use prebuilt
registry images instead of a local build, set `IMAGE_REGISTRY`, `IMAGE_TAG` and
`PULL_POLICY=always` in `.env`.

## 8. Continuous integration

`.github/workflows/ci.yml` runs on every push/PR:
- **backend** — `ruff check app`, a production-config safety assertion, and
  `python -m pytest tests -q` against Postgres + Redis service containers;
- **alembic** — `alembic upgrade head` from an empty database, asserts exactly
  one head, then `downgrade base` + `upgrade head` to prove reversibility;
- **frontend** — `pnpm install --frozen-lockfile`, `pnpm prepare:nuxt`,
  `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm build`.

Reproduce the backend jobs locally with the Docker DB/Redis from section 1 and
the commands in `AGENTS.md`.
