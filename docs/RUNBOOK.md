# Runbook — Consorcio Canalero 10 de Mayo

> Operations playbook for the Hetzner deploy. Read this before paging
> anyone at 3 AM. Update it after every incident — the next outage
> probably has the same root cause as the last one.

## TL;DR — common commands

```bash
# SSH to the server
ssh -i ~/.ssh/hetzner_ghagga -p 2222 javier@157.180.29.238

# Where the stack lives
cd /home/javier/stacks/consorcio

# Current service health
docker compose ps
curl -sf https://cc10demayo-api.javierzader.com/live    # 200 ⇒ process alive
curl -sf https://cc10demayo-api.javierzader.com/ready   # 200 ⇒ ready for traffic
curl -sf https://cc10demayo-api.javierzader.com/health  # legacy combined (always 200)

# Tail logs
docker compose logs -f backend
docker compose logs --tail 200 backend | jq -c 'select(.level=="error")'

# Restart a service safely
docker compose restart backend

# Full redeploy from main (build local)
git pull origin main && docker compose up -d --build backend worker geo-worker
```

---

## 1. First-time setup of the optional integrations

The repo wires Sentry, BetterStack and UptimeRobot opt-in. Default
configuration disables all three. To turn them on:

### 1.1 Sentry (error tracking)

1. Signup at <https://sentry.io>. Free tier: 5 000 errors/month.
2. Create **two projects** in the same organisation:
   - Platform: **FastAPI** → name it `consorcio-backend`.
   - Platform: **React** → name it `consorcio-frontend`.
3. In each project go to *Settings → Client Keys (DSN)* and copy the DSN.
4. **Backend**: edit `/home/javier/stacks/consorcio/.env` and set:
   ```env
   SENTRY_DSN=https://<key>@<org>.ingest.us.sentry.io/<project_id>
   SENTRY_TRACES_SAMPLE_RATE=0.0   # bump to 0.1 if you want perf traces
   ```
   Then `docker compose up -d backend worker celery-worker`.
5. **Frontend**: Cloudflare Pages → project → *Settings → Environment
   variables*. Add:
   ```
   VITE_SENTRY_DSN=https://<key>@<org>.ingest.us.sentry.io/<project_id>
   VITE_SENTRY_TRACES_SAMPLE_RATE=0
   VITE_SENTRY_ENVIRONMENT=production
   ```
   Trigger a new deploy (e.g. retry the latest one).
6. Smoke-test: in `gee-backend/app` add `raise RuntimeError("sentry test")`
   to a temporary endpoint, hit it, confirm the issue appears in Sentry,
   roll back. On the frontend: `throw new Error("sentry test")` from the
   browser console under a Sentry-wrapped route.

### 1.2 BetterStack / Logtail (centralised logs)

1. Signup at <https://betterstack.com> → *Telemetry → Logs* (`logs.betterstack.com`).
   Free tier: 1 GB/month.
2. Create **two sources** under *Sources*:
   - Platform: **FastAPI** → name `consorcio-backend`.
   - Platform: **JavaScript / Browser** → name `consorcio-frontend`.
3. From each source page copy the **Source token**.
4. **Backend** `.env`:
   ```env
   BETTERSTACK_TOKEN=<token from FastAPI source>
   # BETTERSTACK_HOST=https://eu1.logs.betterstack.com   # only if EU region
   ```
   `docker compose up -d backend worker celery-worker`.
5. **Frontend** Cloudflare Pages env vars:
   ```
   VITE_LOGTAIL_TOKEN=<token from JS/Browser source>
   # VITE_LOGTAIL_ENDPOINT=https://eu1.logs.betterstack.com   # only if EU
   ```
6. Smoke-test backend: tail `docker compose logs backend` and confirm
   the same line shows up in BetterStack's "Live tail" within ~5 s.

### 1.3 UptimeRobot (HTTP uptime monitor + alert)

1. Signup at <https://uptimerobot.com>. Free tier: 50 monitors / 5-min check.
2. *Add new monitor*:
   - Type: **HTTP(s)**
   - Friendly name: `Consorcio API health`
   - URL: `https://cc10demayo-api.javierzader.com/live`
   - Monitoring interval: 5 min (free-tier minimum)
3. *Alert contacts*: add the email(s) that should receive an "is down" notice.
4. Repeat with URL `https://consorcio-canalero.pages.dev/` for the frontend.
5. (Optional) Add `https://cc10demayo-api.javierzader.com/ready` as a
   third monitor — it returns 503 when DB / Redis are down even if the
   process is alive, so you'll notice dependency outages even before
   the process dies.

> **Why `/live` and not `/health`?**  The legacy `/health` endpoint
> always returns HTTP 200, with degradation only in the JSON body.
> UptimeRobot would never alert on it. `/live` is the new liveness
> probe (200 = process responsive); `/ready` is true readiness (503
> when DB or Redis are down).

### 1.4 Offsite backups (Phase 2 / F2-A + F2-B)

Two scripts in `scripts/` plus two compose services run the daily
encrypted backups. **Pick one storage backend** (Backblaze B2 *or*
Hetzner Storage Box) — the same `.env` drives both backup runners.

#### 1.4.a Option A — Backblaze B2 (recommended for offsite separation)

1. Signup at <https://www.backblaze.com/sign-up/cloud-storage>. Free
   tier: 10 GB storage + 1 GB egress/day. Past that ~€5/TB/month.
2. *Create a Bucket* → name it `consorcio-backups`, **Files in Bucket
   are: Private**, **Default Lifecycle Settings**: "Keep prior versions
   for X days" → 30. Use the EU region if available.
3. *App Keys → Add a New Application Key* → name "consorcio-backup",
   bucket = your bucket, capabilities = `listBuckets`, `listFiles`,
   `readFiles`, `writeFiles`, `deleteFiles`. Copy the **keyID** and
   the **applicationKey** (the long one) — Backblaze shows the secret
   exactly once.
4. Edit `/home/javier/stacks/consorcio/.env`:
   ```env
   # pg_dump backup (F2-A)
   BACKUP_BACKEND=b2
   B2_BUCKET=consorcio-backups
   B2_KEY_ID=<keyID from step 3>
   B2_APPLICATION_KEY=<applicationKey from step 3>
   BACKUP_ENCRYPTION_PASSPHRASE=<openssl rand -base64 48>
   BACKUP_RETENTION_DAYS=30

   # restic volume backup (F2-B)
   RESTIC_REPOSITORY=b2:consorcio-backups:/restic/consorcio
   RESTIC_PASSWORD=<openssl rand -base64 48>
   B2_ACCOUNT_ID=<same keyID as B2_KEY_ID>
   B2_ACCOUNT_KEY=<same as B2_APPLICATION_KEY>
   ```
5. **Store both passphrases off-server** (password manager). Lose them
   and the backups are unrecoverable.

#### 1.4.b Option B — Hetzner Storage Box (cheapest if VPS is Hetzner)

1. Hetzner Cloud Console → *Storage Boxes* → add a 100 GB box (~€3.20
   /month, same datacenter as the VPS for fastest writes).
2. *Settings* of the new box → **enable SSH support** + create a
   sub-account dedicated to the consorcio (`u123456-sub1`) with its
   own password.
3. (Recommended) Generate an SSH key on the server (`ssh-keygen -t
   ed25519 -f ~/.ssh/hetzner_sb`), then add the public key in the
   Storage Box UI.
4. Edit `.env`:
   ```env
   # pg_dump backup
   BACKUP_BACKEND=hetzner-sb
   HETZNER_SB_HOST=u123456.your-storagebox.de
   HETZNER_SB_USER=u123456-sub1
   HETZNER_SB_SSH_KEY=/home/javier/.ssh/hetzner_sb   # or HETZNER_SB_PASS=...
   BACKUP_ENCRYPTION_PASSPHRASE=<openssl rand -base64 48>
   BACKUP_RETENTION_DAYS=30

   # restic volume backup
   RESTIC_REPOSITORY=sftp:u123456-sub1@u123456.your-storagebox.de:/restic/consorcio
   RESTIC_PASSWORD=<openssl rand -base64 48>
   ```
5. Storage Box doesn't have lifecycle rules; rotate manually or rely
   on `restic forget --prune` (already in the script).

#### 1.4.c Trigger a one-off backup (verifies the credentials are right)

```bash
ssh -i ~/.ssh/hetzner_ghagga -p 2222 javier@157.180.29.238
cd /home/javier/stacks/consorcio
docker compose --profile backup run --rm backup-postgres
docker compose --profile backup run --rm backup-volumes
```

The two services live behind the `backup` compose profile so they
don't auto-start with `docker compose up`. First run will build the
image (~1 min); subsequent runs are seconds.

#### 1.4.d Schedule the daily backup via host crontab

```cron
# m h dom mon dow  command
15 03 * * *  cd /home/javier/stacks/consorcio && /usr/bin/docker compose --profile backup run --rm backup-postgres >>/var/log/consorcio-backup-postgres.log 2>&1
45 03 * * *  cd /home/javier/stacks/consorcio && /usr/bin/docker compose --profile backup run --rm backup-volumes  >>/var/log/consorcio-backup-volumes.log  2>&1
```

The 30-min gap keeps the two jobs from saturating the upload bandwidth
at the same time. Both logs rotate via logrotate in
`/etc/logrotate.d/consorcio` (template in `docs/templates/`).

### 1.5 Email / SMTP (Phase 2 / F2-J)

Currently the password-reset and the (incoming) email verification
flow write the token to the structured logger. Wire any SMTP provider
to send actual mails. Brevo (300/day free, no card) is the easiest
LATAM choice; Resend (100/day) is fine if your domain is set up with
SPF/DKIM/DMARC.

1. Provider signup (Brevo example):
   - <https://www.brevo.com/free-shop-account/> → free plan.
   - *SMTP & API* → enable the SMTP relay → copy the **SMTP key**.
2. Edit `.env`:
   ```env
   SMTP_HOST=smtp-relay.brevo.com
   SMTP_PORT=587
   SMTP_USERNAME=<your brevo login email>
   SMTP_PASSWORD=<SMTP key from step 1>
   SMTP_FROM=no-reply@<your domain>
   SMTP_FROM_NAME=Consorcio Canalero 10 de Mayo
   ```
3. `docker compose up -d backend worker`. The backend reads these vars
   on boot; password reset + email verification flows start delivering.

---

## 2. Daily ops

### 2.1 Deploy from `main`

The Hetzner stack currently builds locally on `git pull` (no image
pull). The simpler flow:

```bash
ssh -i ~/.ssh/hetzner_ghagga -p 2222 javier@157.180.29.238
cd /home/javier/stacks/consorcio
git pull origin main
docker compose up -d --build backend worker geo-worker
```

This rebuilds the affected containers in place and rolling-restarts
them; healthchecks gate the rollover.

#### Optional path: pull pre-built images from GHCR

The GitHub Actions workflow `.github/workflows/deploy.yml` publishes
images to `ghcr.io/jnzader/consorcio-canalero/{backend,geo-worker}`
on every push to `main` with two tags: the short SHA and `:latest`.
The summary on every workflow run prints the SHA + the `.env` line
to paste. To migrate the server to this mode:

1. Replace `/home/javier/stacks/consorcio/docker-compose.yml` with a
   copy of `docker-compose.prod.yml` from the repo.
2. In `.env`, set `BACKEND_IMAGE` and `GEO_WORKER_IMAGE` to the SHA-pinned
   refs (see `.env.prod.example` for the format).
3. To deploy a new build: edit those two lines, then
   `docker compose pull backend geo-worker && docker compose up -d backend geo-worker worker`.
4. To roll back: same flow, just point at the previous SHA from
   <https://github.com/JNZader/consorcio-canalero/pkgs/container/consorcio-canalero%2Fbackend>.

### 2.2 Rotate JWT secret

Every user logged in right now has a session signed with the current
`JWT_SECRET`. Rotating invalidates all sessions — schedule outside
peak hours.

```bash
NEW=$(openssl rand -hex 32)
ssh -i ~/.ssh/hetzner_ghagga -p 2222 javier@157.180.29.238 \
  "cd /home/javier/stacks/consorcio && \
   cp .env .env.bak-\$(date +%Y%m%d-%H%M%S) && \
   sed -i 's|^JWT_SECRET=.*|JWT_SECRET=${NEW}|' .env && \
   docker compose up -d backend worker celery-worker"
```

### 2.3 Apply a new Alembic migration

The compose files now include a `migrate` service that runs
`alembic upgrade head` before `backend` / `celery-worker` start. After
a `git pull` that includes a new revision, the normal
`docker compose up -d --build` flow runs it automatically.

If you need to run it manually (e.g. baseline an existing DB):

```bash
docker compose run --rm migrate
```

### 2.4 Inspect denuncia uploads

Photos live in the `consorcio-denuncia-uploads` named volume. To list:

```bash
docker run --rm -v consorcio-denuncia-uploads:/data alpine ls -lh /data
```

To back up:

```bash
docker run --rm -v consorcio-denuncia-uploads:/data -v "$PWD:/out" \
  alpine tar czf /out/denuncia-uploads-$(date +%Y%m%d).tgz -C /data .
```

---

## 3. Incident playbooks

Each section: **detection → triage → mitigation → root cause**.

### 3.1 Backend container OOM

**Detection**
- UptimeRobot reports `/live` 5xx or timeouts.
- `docker compose ps` shows `backend` `unhealthy` or restarting.
- `docker compose events --since 10m` shows `oom-kill` events.

**Triage**
```bash
docker stats --no-stream consorcio-backend
# Memory column at 100 % of the 512M limit ⇒ OOM
docker compose logs --tail 200 backend | grep -i -E 'killed|memory|oom'
```

**Mitigation**
- Short-term: `docker compose restart backend` to clear any leak.
- If it OOMs immediately again, raise `mem_limit` in
  `docker-compose.yml` (currently 512M) and `up -d backend`.

**Root cause hunting**
- Inspect any new endpoints introduced in the last deploy that load
  large GeoJSON / raster into memory.
- Check rate-limit middleware isn't disabled (`RATE_LIMIT_DISABLED`
  must be false in prod — the boot-time check enforces this).
- If sustained, enable `py-spy` profiling: temporarily add
  `command: ["py-spy", "top", "--pid", "1"]` in a sidecar container.

### 3.2 Database down / unreachable

**Detection**
- `/ready` returns 503 (`database.status != healthy`).
- `docker compose logs backend | grep -i 'connection\|psycopg\|asyncpg'`.
- Sentry: spike of `OperationalError: could not connect to server`.

**Triage**
```bash
docker compose ps postgres
docker compose logs --tail 100 postgres | tail -50
```

**Mitigation**
- If postgres exited: `docker compose up -d postgres` and watch logs.
- If healthy but backend can't reach it: check `DATABASE_URL` host;
  in the multi-stack shared-postgres setup the host is `shared-postgres`
  (Docker network alias).
- If the volume is corrupt: `docker compose down postgres`, restore
  from the last `pg_dump` (see 4.1), `docker compose up -d postgres`.

**Root cause**
- Disk full? `df -h` on the host.
- Connection-limit exhaustion? `SELECT count(*) FROM pg_stat_activity;`
  in `psql`. Default `max_connections=100`; raise temporarily and
  schedule PgBouncer (roadmap F4).

### 3.3 GEE rate limit / auth failure

**Detection**
- `/ready` shows `gee.status = degraded` (non-critical, won't 503).
- Sentry: `EEException: rate limit` or `Permission denied`.

**Triage**
- Visit <https://console.cloud.google.com/iam-admin/quotas?project=cc10demayo>
  and check the daily compute quota.
- Confirm the service-account JSON in `GEE_SERVICE_ACCOUNT_KEY` is
  current (rotate annually in GCP IAM).

**Mitigation**
- Rate limit: throttle the cron / Celery beat tasks that hit GEE.
- Auth: regenerate the service account key in GCP, update the env
  var, `docker compose up -d backend geo-worker`.

### 3.4 Deploy broken — fail-fast rejected the boot

The `_enforce_production_secrets()` check refuses to start when
production config is unsafe. See `gee-backend/app/config.py:_enforce_production_secrets`.

**Detection**
- `docker compose ps backend` shows `Exited (1)`.
- `docker compose logs --tail 30 backend` ends with:
  ```
  RuntimeError: Refusing to start with insecure configuration:
    - JWT_SECRET is too short (X bytes); must be at least 64 bytes...
    - CORS_ORIGINS contains a localhost/dev origin in production...
    - REDIS_PASSWORD is set to the placeholder 'changeme'...
  ```

**Mitigation** — fix the env var(s) listed:
- `JWT_SECRET`: `openssl rand -hex 32` ⇒ 64-char value.
- `CORS_ORIGINS`: explicit comma-separated list of `https://…`
  origins; no `*`, no localhost.
- `REDIS_PASSWORD`: anything that isn't `changeme` or empty.
- `RATE_LIMIT_DISABLED`: must not be truthy in prod.

Then `docker compose up -d backend`.

### 3.5 Deploy broken — Alembic migration failed

**Detection**
- `docker compose ps migrate` shows `Exited (1)`.
- `backend` never starts (depends_on the migrate completion).

**Triage**
```bash
docker compose logs migrate | tail -50
```

Common causes:
- New revision references a column that doesn't exist on the prod DB
  → manual schema diverged from the model; reconcile by hand.
- Migration ran on a DB the auth user doesn't own → check `DATABASE_URL`
  user has `ALTER` privileges on the schema.

**Mitigation**
- Fix the revision (locally, push, redeploy).
- Roll back one revision: `docker compose run --rm migrate alembic downgrade -1`.

### 3.6 Restore from backup

> **Pre-req**: backups must already exist. Phase 1 doesn't wire
> Pre-req: section 1.4 (offsite backups) must be configured. The
> commands below assume Backblaze B2; for Hetzner SB just swap the
> download step.

**Postgres dump restore** (F2-A):

```bash
# 1. Download the most recent dump from B2 (or sftp from Storage Box)
docker compose --profile backup run --rm --entrypoint sh backup-postgres -c '
  B2_ACCOUNT_INFO=/tmp/.b2 b2 account authorize "$B2_KEY_ID" "$B2_APPLICATION_KEY" &&
  B2_ACCOUNT_INFO=/tmp/.b2 b2 ls "$B2_BUCKET" postgres/ | tail -1 |
  awk "{print \$NF}" |
  xargs -I {} B2_ACCOUNT_INFO=/tmp/.b2 b2 file download "$B2_BUCKET" {} /tmp/latest.sql.zst.enc &&
  cat /tmp/latest.sql.zst.enc
' > latest.sql.zst.enc

# 2. Decrypt + decompress
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass "env:BACKUP_ENCRYPTION_PASSPHRASE" \
  -in latest.sql.zst.enc | zstd -d -o latest.sql

# 3. Stop dependants so they don't write during restore
docker compose stop backend worker celery-worker

# 4. Wipe + restore (psql, since the dump uses CLEAN/IF-EXISTS)
docker compose exec -T postgres psql -U "$DB_USER" -d consorcio_canalero < latest.sql

# 5. Restart
docker compose up -d backend worker celery-worker
```

**File-backed volumes restore** (F2-B, restic):

```bash
# List snapshots
docker compose --profile backup run --rm --entrypoint restic backup-volumes snapshots

# Restore the most recent into a scratch path on the host
docker compose --profile backup run --rm \
  --entrypoint restic \
  -v "$PWD/restore:/restore" \
  backup-volumes \
  restore latest --target /restore

# Move into the live volumes (stops the consumers first)
docker compose stop backend geo-worker
docker run --rm -v consorcio-denuncia-uploads:/dest -v "$PWD/restore/app/uploads:/src:ro" \
  alpine sh -c 'cp -av /src/. /dest/'
docker run --rm -v consorcio-geo-data:/dest -v "$PWD/restore/data/geo:/src:ro" \
  alpine sh -c 'cp -av /src/. /dest/'
docker compose up -d backend geo-worker
```

---

## 4. Periodic drills

- **Daily (automated)**: section 1.4.d cron triggers
  `backup-postgres` at 03:15 UTC and `backup-volumes` at 03:45 UTC.
  Confirm both runs every Monday — check `/var/log/consorcio-backup-*.log`
  for "backup OK" within the past 24 h.
- **Monthly (manual drill)**: practice section 3.6 against a
  `consorcio_canalero_drill` database (not the live one!). Steps:
  1. `docker compose exec postgres psql -U $DB_USER -c "CREATE DATABASE consorcio_canalero_drill;"`
  2. Pull the latest dump from B2/SB into a scratch dir.
  3. Run the restore commands from section 3.6 against `_drill`.
  4. `\dt` to confirm tables, count a few rows (`SELECT COUNT(*) FROM denuncias;`).
  5. `DROP DATABASE consorcio_canalero_drill` when done.
  Time the end-to-end procedure; the target RTO is 4 h. Note the
  timing in this file under "Last drill" so you can spot regressions.
- **Quarterly**: rotate `JWT_SECRET`, `REDIS_PASSWORD`, GCP service
  account key, GHCR token, Cloudflare API token,
  `BACKUP_ENCRYPTION_PASSPHRASE`, and `RESTIC_PASSWORD`. When you
  rotate the restic password you MUST keep the old one accessible
  until every snapshot encrypted with it has aged out.
- **Annually**: rebuild the `Dockerfile.backup` image to pick up the
  latest base + ``b2``/``restic`` security patches:
  `docker compose --profile backup build --no-cache`.

**Last drill**: not yet executed. Update this line after the first
real run.

---

## 5. Where things live

| Component | Location |
|-----------|----------|
| Repo | <https://github.com/JNZader/consorcio-canalero> |
| Frontend | Cloudflare Pages — project `consorcio-canalero` |
| Backend, geo-worker, martin | Hetzner CX33 — `/home/javier/stacks/consorcio` |
| Postgres + Redis | Same VPS, shared across stacks |
| Container registry | `ghcr.io/jnzader/consorcio-canalero` |
| CI/CD | GitHub Actions — `.github/workflows/{frontend,backend,deploy,gh-pages}.yml` |
| Tile server | `https://cc10demayo-tiles.javierzader.com` (Martin) |
| API | `https://cc10demayo-api.javierzader.com` |
| Sentry | <https://sentry.io> (when configured) |
| BetterStack | <https://logs.betterstack.com> (when configured) |
| UptimeRobot | <https://uptimerobot.com> (when configured) |
| Backblaze B2 | <https://secure.backblaze.com> (when F2-A on B2) |
| Hetzner Storage Box | <https://console.hetzner.cloud/projects> (when F2-A on SB) |
| SMTP provider | Brevo / Resend / etc. (when F2-J configured) |

### 5.1 External accounts checklist

Tick each as you create the account and stash credentials in the
password manager. Empty rows = the integration is wireable but not
yet activated.

| Integration | Account created? | Where token / key lives | RUNBOOK section |
|-------------|------------------|--------------------------|-----------------|
| Sentry (errors) | ☐ | `.env` SENTRY_DSN + Cloudflare Pages VITE_SENTRY_DSN | 1.1 |
| BetterStack (logs) | ☐ | `.env` BETTERSTACK_TOKEN + Cloudflare Pages VITE_LOGTAIL_TOKEN | 1.2 |
| UptimeRobot (uptime) | ☐ | Monitor created in UptimeRobot UI (no app token) | 1.3 |
| Backblaze B2 (backups) | ☐ | `.env` B2_KEY_ID / B2_APPLICATION_KEY / B2_BUCKET | 1.4.a |
| Hetzner Storage Box (backups) | ☐ | `.env` HETZNER_SB_HOST / USER / SSH_KEY | 1.4.b |
| SMTP (email verify, reset) | ☐ | `.env` SMTP_HOST / USERNAME / PASSWORD | 1.5 |
| Backup encryption passphrase | ☐ | `.env` BACKUP_ENCRYPTION_PASSPHRASE (LOSE = backups unrecoverable) | 1.4 |
| Restic passphrase | ☐ | `.env` RESTIC_PASSWORD (LOSE = backups unrecoverable) | 1.4 |
