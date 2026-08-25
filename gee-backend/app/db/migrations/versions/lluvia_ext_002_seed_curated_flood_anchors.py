"""lluvia_ext_002: the three curated flood anchors, verbatim

Seeds `mar_2015`, `feb_2017` and `sep_2025` — until now a module-level literal
in `router_gee_support.py` — as `provenance = 'curated'` rows of the catalog
`lluvia_ext_001` created (design.md D8).

**Verbatim, including the ids.** The slugs are addressed by name in five
existing dispatcher tests, they are what an operator wrote down, and they are
the ids in the roadmap; renaming them would buy nothing and cost all of that.
Their human fields go into `curated_payload` rather than into columns because
they are exactly the fields a DETECTED row does not have: names and
descriptions for detected events are synthesized at read time, so a shared
column would be NULL on every detected row and mean two different things.

**Why `days_buffer: 30` is carried EXPLICITLY for `mar_2015`.** Today that 30
coincides with the epoch default the router applies to any pre-2020 event, and
an existing dispatcher test asserts it. An anchor that inherited the number
instead of carrying it would make that assertion accidental — and would
silently become 15 the day the epoch rule moved. The other two anchors store no
buffer at all, because they genuinely do rely on the default and pinning a
value on them would be inventing one.

**Every statistic stays NULL.** These events were never ranked, and
`ck_curated_unranked` refuses a curated row wearing statistics. That refusal is
the point: it makes fabricating a percentile for a curated anchor impossible
rather than merely discouraged.

Revision ID: lluvia_ext_002
Revises: lluvia_ext_001
"""

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "lluvia_ext_002"
down_revision: Union[str, None] = "lluvia_ext_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rainfall_extreme_event"

#: The catalog scope: the same provider-asset key the persisted baseline uses,
#: spelled out here rather than imported. A migration that read today's config
#: would seed different rows on a box whose asset version had moved.
SOURCE_ID = "chirps-v3-final"
SCOPE_KIND = "provider_asset"
SCOPE_ID = "zona_cc_ampliada"
SCOPE_VERSION = "v1"

#: `(event_key, date, curated_payload)` — copied field for field from the
#: literal this seed replaces.
ANCHORS: tuple[tuple[str, str, dict], ...] = (
    (
        "mar_2015",
        "2015-03-15",
        {
            "name": "Inundacion Marzo 2015",
            "description": "Evento historico para revisar con Landsat 8/Landsat 7 y Sentinel-1",
            "severity": "alta",
            "sensor": "landsat8",
            "max_cloud": 80,
            "days_buffer": 30,
        },
    ),
    (
        "feb_2017",
        "2017-02-20",
        {
            "name": "Inundacion Febrero 2017",
            "description": "Gran inundacion que afecto Bell Ville y zona rural",
            "severity": "alta",
            "sensor": "sentinel2",
        },
    ),
    (
        "sep_2025",
        "2025-09-05",
        {
            "name": "Inundacion Septiembre 2025",
            "description": "Evento de anegamiento por lluvias intensas",
            "severity": "media",
        },
    ),
)

_INSERT = sa.text(
    "INSERT INTO rainfall_extreme_event "
    "(id, source_id, scope_kind, scope_id, scope_version, detector_revision, "
    " provenance, event_key, start_date, end_date, curated_payload) "
    "VALUES (:id, :source_id, :scope_kind, :scope_id, :scope_version, 'curated', "
    " 'curated', :event_key, CAST(:day AS date), CAST(:day AS date), "
    " CAST(:payload AS json))"
)


def upgrade() -> None:
    connection = op.get_bind()
    for event_key, day, payload in ANCHORS:
        connection.execute(
            _INSERT,
            {
                "id": uuid.uuid4(),
                "source_id": SOURCE_ID,
                "scope_kind": SCOPE_KIND,
                "scope_id": SCOPE_ID,
                "scope_version": SCOPE_VERSION,
                "event_key": event_key,
                # A curated anchor is a single day: `end_date = start_date`.
                "day": day,
                "payload": json.dumps(payload),
            },
        )


def downgrade() -> None:
    # Scoped to the three seeded keys, never a bare `DELETE FROM`: by the time
    # anyone downgrades this revision the table may also hold detected rows,
    # and a catalog row is permanent evidence, not scratch data.
    op.get_bind().execute(
        sa.text(
            "DELETE FROM rainfall_extreme_event WHERE provenance = 'curated' AND event_key IN :keys"
        ).bindparams(sa.bindparam("keys", expanding=True)),
        {"keys": [event_key for event_key, _day, _payload in ANCHORS]},
    )
