# Derivative Postgres image for dev-only pgvector support (design.md D7).
#
# Base: pgrouting/pgrouting:16-3.4-3.6.1 — the SAME image docker-compose.yml
# uses for the `postgres` service (PostGIS + pgRouting, Debian bullseye,
# PostgreSQL 16.2). This adds ONLY `postgresql-16-pgvector` from PGDG's
# apt repo, which the base image already configures scoped to
# `bullseye-pgdg main 16` (`/etc/apt/sources.list.d/pgdg.list`) — no extra
# repo/keyring setup needed.
#
# The build-time assert below IS the test of that PGDG-availability
# assumption (proposal.md: "Empirically confirmed absent from the pinned
# image ... PG 16.2 Debian pgdg"): if the package, or its extension
# control file, ever go missing from the PGDG repo for this Debian/PG
# combination, this build fails loudly at build time instead of shipping
# a container that silently lacks `CREATE EXTENSION vector`.
#
# Tagged `consorcio-postgres:16-vector`. Used ONLY via
# `docker-compose.pgvector.yml` (`-f`, opt-in) — never the default
# `docker-compose.yml`, which keeps `image: pgrouting/pgrouting:...`
# untouched (design.md D7 "prod untouched"; consorcio's prod box runs a
# compose file outside this repository entirely, so this image is
# unreachable by construction from production).
FROM pgrouting/pgrouting:16-3.4-3.6.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector=0.8.6-1.pgdg11+1 \
    && rm -rf /var/lib/apt/lists/* \
    && test -f /usr/share/postgresql/16/extension/vector.control
