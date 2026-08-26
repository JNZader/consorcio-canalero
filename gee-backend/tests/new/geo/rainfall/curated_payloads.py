"""The floor EVERY curated payload carries, in one place.

`catalog_view._curated_record` is LOUD about a curated payload missing `name`
or `description`: the frontend's `isHistoricFlood` drops a nameless record
silently, so a broken payload has to raise rather than vanish a card with a
200. Every seeded anchor (`lluvia_ext_002`) carries both fields, which makes
any fixture that omits them a fixture describing a row the seed cannot
produce.

Three test files plant curated anchors, and each had patched that floor its own
way -- one defaulting the whole payload, one merging a description, one
building it in a local `_payload`. Three patches for one rule is how a fourth
file arrives without it and fails as a 60-second hang (the catch-all handler
hands the SQLAlchemy row to `rich`, which pretty-prints it out of every
frame's locals). The floor lives here now; the local seeding functions stay
local, because what they persist legitimately differs.
"""

from __future__ import annotations

from typing import Any

#: The `mar_2015` anchor's name, the default because it is the anchor most of
#: these fixtures address.
DEFAULT_NAME = "Inundacion Marzo 2015"


def curated_payload(**overrides: Any) -> dict[str, Any]:
    """A curated payload with the floor the seed always provides.

    `severity` rides along because the served record takes it verbatim (D8) and
    a payload without one serves `severity: None` into a picker that styles by
    it. Any field an anchor actually needs -- `sensor`, `max_cloud`,
    `days_buffer` -- is passed as an override, so no fixture inherits a field
    its assertions never asked for.
    """
    name = overrides.get("name", DEFAULT_NAME)
    return {
        "name": name,
        "description": f"{name} -- descripcion curada",
        "severity": "alta",
    } | overrides
