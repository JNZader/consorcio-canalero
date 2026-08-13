# Weekly geo ETL refresh (systemd timer)

The geo ETLs used to be run by hand, and the canal data on the box drifted 2.5
months out of date without anyone noticing. This directory turns that into a
system timer: **Sundays 03:00, with catch-up**.

| File | What it is |
|------|------------|
| `etl-refresh.sh` | The refresh itself. Runs on the HOST, drives `docker compose exec -T geo-worker python -m …` |
| `etl-refresh.service` | `Type=oneshot` unit that runs the script as `javier` |
| `etl-refresh.timer` | `OnCalendar=Sun *-*-* 03:00:00`, `Persistent=true` |

## What it runs (order is load-bearing)

1. `app.domains.geo.etl.load_canales_consorcio` — curated canal registry.
2. `app.domains.geo.etl.generate_canal_catchments` — upstream basin per canal.
   **After canales**: it iterates `canal_consorcio` and FKs onto it.
3. `app.domains.geo.etl.load_suelos_catastro` — soils + `mv_suelos_por_zona` refresh.

Not in the refresh, on purpose:

- `scripts/etl_canales`, `scripts/etl_pilar_verde`, `scripts/etl_escuelas` — offline
  KMZ → static GeoJSON converters. The KMZ inputs live on the operator's machine
  and the outputs are committed assets under `consorcio-web/public/`. Neither side
  exists on the box.
- `generate_chirps_normals` — static reference data (1991-2020 normals). Its own
  docstring: *"There is no scheduled job and none is wanted."* Regenerate by hand
  only when the normals period changes, the consorcio extent changes, or **the
  pipeline itself is fixed** — see the pending run below.

### PENDING one-off: regenerate the CHIRPS normals

The 13 rasters on the production volume were baked by the pre-fix pipeline, which
clipped each normal to the zona outline. Earth Engine serialises a masked pixel as
`0.0` with no nodata tag and the warp lacked `src_nodata`, so those zeros survived
as measurements: zones on the eastern edge of the extent averaged real millimetres
together with them (LT B read 0.0 mm every month, LT16 697.5 against 930, GRUPO35
611.2 against 916.8). The export and the warp are fixed in code; **the bytes on
disk only change on a re-run.**

Requires Earth Engine credentials, so it runs on the prod box:

```
docker compose exec backend python -m app.domains.geo.etl.generate_chirps_normals
```

Exit 0 = 13 rasters written and registered under a fresh `version` (the previous
rows stay, the ficha's month-scoped lookup takes the newest). Exit 1 = credentials
/ extent resolution failed and NOTHING was written. Exit 3 = the batch rolled back.

After a successful run, verify one edge parcel in the ficha (LT B should report
real millimetres, not `sin_cobertura`).

**DONE 2026-08-12.** The 13 rasters were regenerated and verified in production
(LT B went `0.0` → 926.26 mm), and the stop-gap in
`ficha_service._perfil_precip` — the `treat_zero_as_nodata=True` call — was
retired together with the `treat_zero_as_nodata` parameter of
`composites.extract_zonal_profile`. Absence is now read from the nodata value
alone; a `0.0` pixel counts as a real measurement. Re-running this job on rasters
baked by the pre-fix pipeline is therefore no longer survivable — if the extent
or the normals period ever changes, run it with the CURRENT pipeline only.

## Why no `--force`

`generate_canal_catchments` resumes by `version` = the id of the `flow_dir` layer
pointer. With an unchanged pointer every stored catchment is skipped, so the weekly
run only pays for canals that are new or previously failed — which is exactly what
a periodic refresh should do.

`--force` exists for a different reason, and it is the thing that bites: **the
read-path caps (`ficha_max_*`) AND the simplify tolerance
(`CATCHMENT_SIMPLIFY_TOLERANCE_M`) both live OUTSIDE the version key.** Change
either one, deploy it, and the weekly run skips all 60 rows and keeps the OLD
geometries and the OLD `oversized` verdicts. The new value is **inert** until the
rows are recomputed — the code ships, the map does not change, and nothing warns
you. See the one-time step below.

## Install (on the box)

Same source as the rest of the stack files in `DEPLOY.md` § 3.2 — the repo checkout
on the server. Copy-paste the whole block, it is self-contained:

```
REPO=/home/javier/programacion/consorcio-canalero && \
sudo install -m 0755 "$REPO/deploy/etl-refresh.sh" /usr/local/bin/etl-refresh.sh && \
sudo cp "$REPO/deploy/etl-refresh.service" "$REPO/deploy/etl-refresh.timer" /etc/systemd/system/ && \
sudo systemctl daemon-reload && \
sudo systemctl enable --now etl-refresh.timer
```

Re-run the same block after pulling a change to any of those three files.

Check it is armed:

```
systemctl list-timers etl-refresh.timer
```

### ONE-TIME after a caps or tolerance change (do not skip)

Whenever a deploy changed `ficha_max_*` or `CATCHMENT_SIMPLIFY_TOLERANCE_M`, run
this ONCE by hand right after installing/updating. The weekly cron will never do it
for you — it deliberately runs without `--force`, and without this the change stays
inert (see above):

```
cd ~/stacks/consorcio && docker compose exec -T geo-worker python -m app.domains.geo.etl.generate_canal_catchments --force
```

It re-delineates and re-gates all 60 canals, so it is slow — expect the long pole of
a full run. Grep the output for `canal_catchment.oversized` to see the new
per-motivo verdict, which is how you find out how many catchments the change
actually rescued.

**Applies right now**: batch 4d moved the tolerance from 8 m to 20 m. Until this
command runs against prod, every stored catchment still carries its 8 m geometry.

## Logs

Two places, on purpose. The journal has the per-step summary; the log file has the
full ETL stdout/stderr.

```
journalctl -u etl-refresh.service -n 200          # last run, per-step exit codes
journalctl -u etl-refresh.service --since '7 days ago'
ls -lt ~/stacks/consorcio/logs/etl/                # one file per run, UTC-stamped
```

Each run logs `START` / `READY` (the stack is up) / one `STEP` + `DONE module=…
exit=N` pair per ETL / `END result=OK|FAILED`. A non-zero exit on any step makes the
unit fail, so `systemctl status etl-refresh.service` is enough to know the week went
wrong.

Run logs older than `ETL_LOG_RETENTION_DAYS` (default 90) are purged at the start of
each run; a `PURGE removed=N` line says how many went. Set it to `0` to keep
everything.

## Known gaps

Two, both real, both documented instead of papered over.

**1. A failed run notifies nobody.** It is visible — `systemctl status`, the journal,
the run log — but only if somebody looks. There is no `OnFailure=` hook and no
heartbeat. The plan, for when the owner turns on the uptime monitoring that already
exists on this box: have the script emit a heartbeat on success (touch a file the
proxy serves, or curl a push-monitor URL) and point Uptime Kuma at it, so a run that
never happens is as loud as one that failed. Not implemented on purpose — a
half-wired alerting path is worse than a documented gap.

**2. A hung step is only killed on the host side.** Each step runs under `timeout`
(`ETL_STEP_TIMEOUT_S`, default 2100 s), which is well under the unit's
`TimeoutStartSec=2h`, so the script itself reports which module hung instead of
systemd killing the run anonymously. But `docker compose exec` does **not** forward
the signal into the container: verified empirically — after `timeout` returns 124,
the process is still listed by `docker compose top`. So a timed-out ETL may still be
running inside `geo-worker`, holding DB locks and still writing. There is no clean
fix without redesigning the invocation. The log says so explicitly on the TIMEOUT
line; when you see one, check and clean up by hand:

```
cd ~/stacks/consorcio && docker compose top geo-worker
```

## Run it by hand

```
sudo systemctl start etl-refresh.service   # same path as the timer, logs to the journal
```

or directly, to watch it:

```
/usr/local/bin/etl-refresh.sh
```

Environment overrides:

| Variable | Default | What it does |
|----------|---------|--------------|
| `STACK_DIR` | `~/stacks/consorcio` | compose project directory |
| `ETL_SERVICE` | `geo-worker` | container to exec into |
| `ETL_LOG_DIR` | `$STACK_DIR/logs/etl` | where run logs go |
| `ETL_LOG_RETENTION_DAYS` | `90` | purge older run logs (`0` = keep all) |
| `ETL_STACK_WAIT_S` | `300` | how long to wait for the stack to come up |
| `ETL_STACK_POLL_S` | `10` | seconds between stack polls |
| `ETL_STEP_TIMEOUT_S` | `2100` | per-step wall-clock ceiling |

## Why it waits for the stack

The unit orders itself after `docker.service` — the **daemon**, which is ready long
before the containers are. `geo-worker` waits on postgres being healthy and on the
migrate job completing: tens of seconds to minutes after a boot.

That matters specifically because of `Persistent=true`. If the box was off on
Sunday, systemd fires the unit at the next boot — and without a wait, that catch-up
run would land while the stack is still starting, fail all three steps, and (with
`Restart=no`) burn the catch-up entirely, leaving the data stale for another week.
That is the exact failure the timer exists to prevent, so the script polls
`docker compose ps --status running` for up to `ETL_STACK_WAIT_S` before step 1,
logging each attempt, and fails with a specific `FATAL … the stack never came up`
if it never arrives.

## Why `geo-worker` and not `backend`

The ETL module docstrings say `docker compose exec backend …`. The timer uses
`geo-worker` instead because `generate_canal_catchments` needs the WhiteboxTools
binary and the GDAL stack, and only the geo image (`Dockerfile.geo`) pre-downloads
WBT at build time — in the backend image the first call would try to fetch it at
runtime. The two loaders are container-agnostic (same `app/` code, same
`DATABASE_URL`), so running all three in one container keeps the refresh on a
single dependency.
