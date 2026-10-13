"""Public canal length must fall back to geometry when longitud_m is null."""

from pathlib import Path

SERVICE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "domains"
    / "geo"
    / "canales_publicacion"
    / "service.py"
)
FALLBACK = "COALESCE(c.longitud_m, ST_Length(c.geom::geography))"


def test_public_and_list_sql_use_st_length_fallback() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    assert source.count(FALLBACK) >= 3
