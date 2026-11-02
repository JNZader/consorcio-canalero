"""The WFS type names must be the ones GetCapabilities actually publishes."""

from pathlib import Path

from scripts.etl_idecor_capas.layers import IDECOR_LAYER_NAMES, IDECOR_PARCELAS_BV, public_feature

FIXTURE = Path(__file__).parent / "fixtures" / "idecor_capabilities_names.txt"


def test_requested_layers_are_in_the_capabilities_snapshot() -> None:
    published = {
        line.strip()
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    missing = [name for name in IDECOR_LAYER_NAMES.values() if name not in published]
    assert missing == []
    assert IDECOR_PARCELAS_BV in published


def test_public_feature_drops_anything_that_is_not_a_name() -> None:
    cleaned = public_feature(
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [1, 2]},
            "properties": {"nombre": "Canal Sur", "cuit": "20-1", "titular": "Ada"},
        }
    )
    assert cleaned["properties"] == {"nombre": "Canal Sur"}
