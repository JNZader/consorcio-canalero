"""V0 exposes no retrieval surface at all (task 3.9, design.md D8).

This test has no GREEN counterpart because there is nothing to implement: it
asserts an ABSENCE. `conocimiento` follows the house domain pattern minus
`router.py` — not an empty router, not an unmounted one, none at all. An
unmounted router is dead code a future contributor wires up by accident, and the
thing it would expose is a legal-retrieval endpoint with no auth story, no rate
limit and no answer contract. V1 adds it when there is a contract to test.

The test is written to fail on the two ways the absence could quietly end: the
file appearing, and something reaching the retrieval service through HTTP.
"""

from __future__ import annotations

from pathlib import Path

DOMAIN_DIR = Path(__file__).resolve().parents[3] / "app" / "domains" / "conocimiento"
API_V2_DIR = Path(__file__).resolve().parents[3] / "app" / "api" / "v2"


def test_no_conocimiento_router_mounted():
    """No `router.py` in the domain, and nothing under `app/api/v2/` names it."""
    assert DOMAIN_DIR.is_dir(), "the conocimiento domain must exist"
    assert not (DOMAIN_DIR / "router.py").exists(), (
        "conocimiento must not have a router.py. V0 ships no HTTP surface: an "
        "unmounted router is dead code a future contributor wires up by accident "
        "(design.md D8)."
    )

    culpables = [
        path.name
        for path in sorted(API_V2_DIR.rglob("*.py"))
        if "conocimiento" in path.read_text(encoding="utf-8")
    ]
    assert culpables == [], f"{culpables} reference the conocimiento domain from the API layer"


def test_no_mounted_route_reaches_the_retrieval_service():
    """The stronger form: inspect the ASSEMBLED app, not just the source tree.

    A grep can be defeated by an import alias; the mounted route table cannot.
    """
    from app.main import app

    rutas = [getattr(route, "path", "") for route in app.routes]
    assert not any("conocimiento" in ruta or "/rag" in ruta for ruta in rutas)


def test_the_domain_still_follows_the_rest_of_the_house_pattern():
    """Absence of `router.py` is a decision, not an unfinished domain."""
    for nombre in ("models.py", "schemas.py", "repository.py", "service.py"):
        assert (DOMAIN_DIR / nombre).is_file(), f"conocimiento/{nombre} is missing"
