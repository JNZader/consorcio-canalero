# Derivative Postgres image for dev-only pgvector support
# (openspec/changes/archive/2026-08-11-consorcio-rag/design.md D7).
#
# PINNING CONTRACT (INF-2): the FROM below must be the EXACT image string
# `docker-compose.yml` pins for the `postgres` service — repository, tag AND
# digest, verbatim. This overlay swaps the server binaries over the SAME
# `consorcio-postgres-data` volume the default compose image initialized, so
# any drift between the two strings is an unsupported PostGIS/PostgreSQL
# minor upgrade or downgrade over live data. Bumping one string requires
# bumping the other IN THE SAME PR. Enforced mechanically by
# gee-backend/tests/test_infra_v6_contracts.py
#   ::test_pgvector_overlay_base_matches_compose_postgres_image.
#
# Base facts (read from the pinned image's config): Debian 11 bullseye,
# PostgreSQL 16.9, PostGIS 3.5.2, pgRouting 3.8.0, with PGDG apt scoped to
# `bullseye-pgdg main 16` in /etc/apt/sources.list.d/pgdg.list.
#
# Debian 11 left LTS on 2026-08-31 and PGDG dropped `bullseye-pgdg` from
# apt.postgresql.org — the base's stock PGDG source 404s, so a plain
# `apt-get update` fails before this overlay can install anything. PGDG
# freezes dropped suites on apt-archive.postgresql.org, which still serves
# the exact package pinned below (signed with the same key already in the
# base's keyring). The RUN below rewrites only the hostname; the suite stays
# `bullseye-pgdg`. The build-time asserts are the test of every assumption
# above: if the source rewrite no-ops, the archive goes away, or the package
# or its extension control file is missing, this build FAILS LOUDLY instead
# of shipping a container that silently lacks `CREATE EXTENSION vector`
# (design.md D7's silent-skip trap).
#
# Tagged `consorcio-postgres:16-vector`. Used ONLY via
# `docker-compose.pgvector.yml` (`-f`, opt-in) or `make rag-db` — never the
# default `docker-compose.yml`, which keeps pulling this same pinned image
# without building. Prod is unreachable by this file by construction.
FROM pgrouting/pgrouting:16-3.5-3.8@sha256:4c480c7f9e25a3490573cd6ef86b286fd21162e288cc355e8da2b52518ef6ab8

RUN sed -i 's#apt\.postgresql\.org#apt-archive.postgresql.org#' /etc/apt/sources.list.d/pgdg.list \
    && grep -q 'apt-archive.postgresql.org/pub/repos/apt/ bullseye-pgdg main' /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector=0.8.6-1.pgdg11+1 \
    && rm -rf /var/lib/apt/lists/* \
    && test -f /usr/share/postgresql/16/extension/vector.control
