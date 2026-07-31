"""Operator-run ETL entry points for the geo domain.

These modules live under ``app/`` on purpose: ``gee-backend/Dockerfile`` copies
only ``app/`` and ``alembic.ini`` into the runtime image, so anything under
``gee-backend/scripts/`` or the repo-root ``scripts/`` does not exist inside the
backend container. Everything here is therefore invoked as a module::

    docker compose exec backend python -m app.domains.geo.etl.<module>

The repo-root ``scripts/`` tree (``etl_pilar_verde.py``) is a different, host-run
execution model and is left alone.
"""
