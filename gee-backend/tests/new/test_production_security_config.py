"""Regression tests for production security and authorization configuration."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_repo_file(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_database_urls_are_derived_for_the_correct_sqlalchemy_driver() -> None:
    from app.config import database_async_url, database_sync_url

    canonical = "postgresql://app:secret@postgres:5432/consorcio"
    async_input = "postgresql+asyncpg://app:secret@postgres:5432/consorcio"

    assert database_sync_url(canonical) == canonical
    assert database_sync_url(async_input) == canonical
    assert database_async_url(canonical) == async_input
    assert database_async_url(async_input) == async_input


def test_production_example_uses_canonical_sync_database_url() -> None:
    env_example = _read_repo_file(".env.prod.example")
    database_line = next(
        line for line in env_example.splitlines() if line.startswith("DATABASE_URL=")
    )

    assert database_line.startswith("DATABASE_URL=postgresql://")
    assert "+asyncpg" not in database_line


@pytest.mark.parametrize("config_path", ["martin/config.yaml", "martin/config.prod.yaml"])
def test_martin_only_publishes_explicit_sanitized_views(config_path: str) -> None:
    config = _read_repo_file(config_path)
    configured_sources = set(
        re.findall(r"^    (vt_[a-z0-9_]+):\n      schema:", config, re.MULTILINE)
    )

    assert "auto_publish: false" in config
    assert configured_sources == {
        "vt_canal_network",
        "vt_denuncias",
        "vt_puntos_conflicto",
        "vt_zonas_operativas",
    }
    assert not re.search(
        r"^    (denuncias|geo_jobs|geo_layers|geo_analisis_gee):", config, re.MULTILINE
    )


def test_martin_production_example_uses_a_dedicated_reader_identity() -> None:
    env_example = _read_repo_file(".env.prod.example")
    app_url = next(line for line in env_example.splitlines() if line.startswith("DATABASE_URL="))
    martin_url = next(
        line for line in env_example.splitlines() if line.startswith("MARTIN_DB_URL=")
    )

    assert "postgresql://consorcio:" in app_url
    assert "postgresql://consorcio_martin:" in martin_url
    assert "CAMBIAR_PASSWORD_MARTIN" in martin_url


def _route_has_operator_guard(route: APIRoute) -> bool:
    from app.auth.dependencies import require_operator

    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        if dependency.call is require_operator:
            return True
        pending.extend(dependency.dependencies)
    return False


def test_global_geo_and_gee_routes_use_operator_guard() -> None:
    from app.domains.geo.router import router

    guarded_paths = {
        "/jobs",
        "/jobs/{job_id}",
        "/layers",
        "/layers/{layer_id}",
        "/layers/{layer_id}/file",
        "/gee/analysis",
        "/gee/analysis/{analisis_id}",
    }
    routes = {route.path: route for route in router.routes if isinstance(route, APIRoute)}

    assert guarded_paths <= routes.keys()
    assert all(_route_has_operator_guard(routes[path]) for path in guarded_paths)
    assert not _route_has_operator_guard(routes["/layers/public"])


def test_every_dynamically_registered_gee_route_uses_operator_guard() -> None:
    from app.domains.geo.router import router

    gee_routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path.startswith("/gee/")
    ]

    assert gee_routes
    assert all(_route_has_operator_guard(route) for route in gee_routes)


def test_operator_guard_denies_citizen_and_allows_operator() -> None:
    from app.auth.dependencies import require_operator
    from app.auth.models import UserRole

    citizen = SimpleNamespace(role=UserRole.CIUDADANO)
    operator = SimpleNamespace(role=UserRole.OPERADOR)

    with pytest.raises(HTTPException) as exc_info:
        require_operator(citizen)
    assert exc_info.value.status_code == 403
    assert require_operator(operator) is operator


def test_one_time_email_codes_are_the_default_and_production_example() -> None:
    from app.config import Settings

    assert Settings.model_fields["use_one_time_codes"].default is True
    assert "USE_ONE_TIME_CODES=true" in _read_repo_file(".env.prod.example")
    assert "USE_ONE_TIME_CODES=true" in _read_repo_file("gee-backend/.env.example")


def test_production_proxy_and_healthcheck_are_narrow_and_runnable() -> None:
    dockerfile = _read_repo_file("gee-backend/Dockerfile")
    compose = _read_repo_file("docker-compose.prod.yml")
    backend_block = compose.split("\n  celery-worker:", 1)[0].split("\n  backend:", 1)[1]

    assert "172.16.0.0/12" not in dockerfile
    assert "FORWARDED_ALLOW_IPS=127.0.0.1" in dockerfile
    assert 'CMD ["python", "-m", "app.server"]' in dockerfile
    assert "FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:-127.0.0.1,caddy}" in backend_block
    assert "FORWARDED_ALLOW_IPS=127.0.0.1,caddy" in _read_repo_file(".env.prod.example")
    assert "curl --fail --silent --show-error" in backend_block
    assert "wget " not in backend_block


def test_production_image_prepares_upload_directory_before_switching_user() -> None:
    dockerfile = _read_repo_file("gee-backend/Dockerfile")
    mkdir_position = dockerfile.index("mkdir -p credentials uploads")
    user_position = dockerfile.index("USER app")

    assert mkdir_position < user_position
    assert "chown -R app:app /app" in dockerfile[mkdir_position:user_position]


def test_one_time_email_links_match_spa_routes_and_exchange_flows() -> None:
    from urllib.parse import parse_qs, urlparse

    from app.shared.email import build_reset_email, build_verification_email

    frontend_url = "https://consorcio.example"
    verify_link = re.search(
        r"https://[^\s]+\?code=[A-Z0-9]+",
        build_verification_email("VERIFY42", frontend_url, query_parameter="code")["body_text"],
    )
    reset_link = re.search(
        r"https://[^\s]+\?code=[A-Z0-9]+",
        build_reset_email("RESET42", frontend_url, query_parameter="code")["body_text"],
    )

    assert verify_link is not None
    assert reset_link is not None
    verify_url = urlparse(verify_link.group(0))
    reset_url = urlparse(reset_link.group(0))
    assert (verify_url.path, parse_qs(verify_url.query)) == (
        "/verify-email",
        {"code": ["VERIFY42"]},
    )
    assert (reset_url.path, parse_qs(reset_url.query)) == (
        "/reset-password",
        {"code": ["RESET42"]},
    )

    route_tree = _read_repo_file("consorcio-web/src/routeTree.gen.tsx")
    verify_page = _read_repo_file("consorcio-web/src/components/auth/VerifyEmailPage.tsx")
    reset_page = _read_repo_file("consorcio-web/src/components/auth/ResetPasswordForm.tsx")

    assert "path: '/verify-email'" in route_tree
    assert "path: '/reset-password'" in route_tree
    assert "exchangeCodeForToken(code, 'verify')" in verify_page
    assert "verifyEmailWithToken(resolvedToken)" in verify_page
    assert "exchangeCodeForToken(code, 'reset')" in reset_page
    assert "resetPasswordWithToken(effectiveToken" in reset_page


def test_production_upload_volume_init_repairs_existing_volume_and_gates_backend() -> None:
    compose = _read_repo_file("docker-compose.prod.yml")
    dockerfile = _read_repo_file("gee-backend/Dockerfile")
    init_block = compose.split("\n  uploads-init:", 1)[1].split("\n  backend:", 1)[0]
    backend_block = compose.split("\n  backend:", 1)[1].split("\n  celery-worker:", 1)[0]

    assert 'user: "0:0"' in init_block
    assert "network_mode: none" in init_block
    assert "read_only: true" in init_block
    assert "- denuncia-uploads:/app/uploads" in init_block
    assert "chown -R app:app /app/uploads" in init_block
    assert "chmod 0750 /app/uploads" in init_block
    assert "uploads-init:" in backend_block
    assert "condition: service_completed_successfully" in backend_block.split("uploads-init:", 1)[1]
    assert "USER app" in dockerfile
