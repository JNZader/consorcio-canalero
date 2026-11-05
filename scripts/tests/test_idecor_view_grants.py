"""INF-2: IDECOR views are not granted to PUBLIC.

Martin's reader role receives SELECT from scripts/provision_martin_reader.sql.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HYDRO = (ROOT / "scripts" / "sql" / "idecor_hidrografia.sql").read_text(encoding="utf-8")
MARTIN = (ROOT / "scripts" / "provision_martin_reader.sql").read_text(encoding="utf-8")

VIEWS = (
    "vt_idecor_consorcios",
    "vt_idecor_cursos",
    "vt_idecor_cuencas",
    "vt_idecor_canales_riego",
)


def test_hidrografia_revokes_public_instead_of_granting_it() -> None:
    assert "TO PUBLIC" not in HYDRO
    assert "FROM PUBLIC" in HYDRO
    for view in VIEWS:
        assert view in HYDRO.split("FROM PUBLIC", 1)[0].split("REVOKE ALL ON", 1)[1]


def test_martin_reader_still_receives_select_on_the_views() -> None:
    grant = MARTIN.lower()
    assert "grant select on table" in grant
    for view in VIEWS:
        assert view in grant
