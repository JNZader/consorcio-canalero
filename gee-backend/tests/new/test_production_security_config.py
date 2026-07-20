"""Regression tests for production security and authorization configuration."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute


REPO_ROOT = Path(__file__).resolve().parents[3]
MARTIN_VIEWS = {
    "vt_canal_network",
    "vt_denuncias",
    "vt_puntos_conflicto",
    "vt_zonas_operativas",
}


def _read_repo_file(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _read_env_example(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in _read_repo_file(path).splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _compose_service_block(path: str, service: str) -> str:
    compose = _read_repo_file(path)
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|^networks:\n)",
        compose,
    )
    assert match is not None
    return match.group("body")


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


@pytest.mark.parametrize(
    "config_path",
    ["martin/config.yaml", "martin/config.prod.yaml", "martin-config.deploy.yaml"],
)
def test_martin_only_publishes_explicit_sanitized_views(config_path: str) -> None:
    config = _read_repo_file(config_path)
    configured_sources = set(
        re.findall(r"^    (vt_[a-z0-9_]+):\n      schema:", config, re.MULTILINE)
    )

    assert "auto_publish: false" in config
    assert configured_sources == MARTIN_VIEWS
    assert not re.search(
        r"^    (denuncias|geo_jobs|geo_layers|geo_analisis_gee):", config, re.MULTILINE
    )


@pytest.mark.parametrize(
    ("env_path", "expected_host", "expected_database"),
    [
        (".env.prod.example", "shared-postgres", "consorcio_canalero"),
        (".env.deploy.example", "postgres", "consorcio"),
    ],
)
def test_martin_examples_use_a_dedicated_reader_identity(
    env_path: str, expected_host: str, expected_database: str
) -> None:
    env = _read_env_example(env_path)
    app_url = urlsplit(env["DATABASE_URL"])
    martin_url = urlsplit(env["MARTIN_DB_URL"])

    assert app_url.scheme == martin_url.scheme == "postgresql"
    assert app_url.username == "consorcio"
    assert martin_url.username == "consorcio_martin"
    assert martin_url.username != app_url.username
    assert martin_url.password != app_url.password
    assert app_url.hostname == martin_url.hostname == expected_host
    assert app_url.path == martin_url.path == f"/{expected_database}"


def test_primary_production_database_variables_match_the_canonical_url() -> None:
    env = _read_env_example(".env.prod.example")
    app_url = urlsplit(env["DATABASE_URL"])

    assert env["POSTGRES_HOST"] == app_url.hostname
    assert env["POSTGRES_USER"] == app_url.username
    assert env["POSTGRES_PASSWORD"] == app_url.password
    assert env["POSTGRES_DB"] == app_url.path.removeprefix("/")
    assert env["USE_PGBOUNCER"] == "false"


@pytest.mark.parametrize("compose_path", ["docker-compose.prod.yml", "docker-compose.deploy.yml"])
def test_martin_compose_injection_is_required_and_has_no_app_fallback(
    compose_path: str,
) -> None:
    martin_block = _compose_service_block(compose_path, "martin")

    assert (
        "DATABASE_URL: ${MARTIN_DB_URL:?MARTIN_DB_URL is required for the "
        "dedicated read-only Martin role}" in martin_block
    )
    assert "env_file:" not in martin_block
    assert "DATABASE_URL=${" not in martin_block
    assert ":-" not in martin_block


def test_legacy_martin_mounts_the_checked_in_hardened_config() -> None:
    martin_block = _compose_service_block("docker-compose.deploy.yml", "martin")
    mount = "./martin-config.deploy.yaml:/config/config.yaml:ro"

    assert f"- {mount}" in martin_block
    assert "./martin-config.yaml:/config/config.yaml:ro" not in martin_block
    assert (REPO_ROOT / mount.split(":", 1)[0]).is_file()
    assert "auto_publish: false" in _read_repo_file("martin-config.deploy.yaml")


def test_legacy_runbook_uses_the_container_bootstrap_admin() -> None:
    env = _read_env_example(".env.deploy.example")
    compose_postgres = _compose_service_block("docker-compose.deploy.yml", "postgres")
    legacy_runbook = (
        _read_repo_file("docs/MARTIN_DB_ROLE.md")
        .split("## Stack legado embebido", 1)[1]
        .split("## Verificación y reejecución", 1)[0]
    )
    database_name = urlsplit(env["DATABASE_URL"]).path.removeprefix("/")

    assert f"POSTGRES_USER: ${{DB_USER:-{env['DB_USER']}}}" in compose_postgres
    assert f"POSTGRES_DB: {database_name}" in compose_postgres
    assert legacy_runbook.count("docker compose --env-file .env -f docker-compose.deploy.yml") == 3
    assert legacy_runbook.count('--username "$POSTGRES_USER"') == 2
    assert legacy_runbook.count('--dbname "$POSTGRES_DB"') == 2
    assert '--set=database_name="$POSTGRES_DB"' in legacy_runbook
    assert '--set=app_role="$POSTGRES_USER"' in legacy_runbook
    assert "docker exec" not in legacy_runbook
    assert "-U postgres" not in legacy_runbook
    assert "--username postgres" not in legacy_runbook
    assert "DB_PASSWORD" not in legacy_runbook
    assert r"\password consorcio_martin" in legacy_runbook


@pytest.mark.parametrize("doc_path", ["DEPLOY.md", "docs/DEPLOY_GUIDE.md"])
def test_deploy_docs_use_the_least_privilege_martin_contract(doc_path: str) -> None:
    document = _read_repo_file(doc_path)

    assert "+asyncpg" not in document
    assert "MARTIN_DB_URL=postgresql://consorcio:" not in document
    assert "MARTIN_DB_URL=postgresql://consorcio_martin:" in document
    assert MARTIN_VIEWS <= set(re.findall(r"vt_[a-z0-9_]+", document))
    assert "MARTIN_DB_ROLE.md" in document
    assert "provision_martin_reader.sql" in document
    assert document.index("docker compose run --rm migrate") < document.index(
        "docker compose up -d"
    )


def test_martin_reader_sql_is_deny_by_default_and_credential_free() -> None:
    script = _read_repo_file("scripts/provision_martin_reader.sql")

    assert set(re.findall(r"vt_[a-z0-9_]+", script)) == MARTIN_VIEWS
    assert r"\set ON_ERROR_STOP on" in script
    assert "CREATE ROLE %I LOGIN" in script
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in script
    assert "NOREPLICATION NOBYPASSRLS" in script
    assert "default_transaction_read_only = on" in script
    assert "REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC" in script
    assert "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public" in script
    assert "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public" in script
    assert "REVOKE ALL PRIVILEGES ON ALL ROUTINES IN SCHEMA public" in script
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public" in script
    assert "GRANT SELECT ON TABLE" in script
    assert "unexpected_application_function_privileges" in script
    assert "Martin role % owns database objects" in script
    assert "WHERE parent.rolname = reader_name" in script
    assert "unexpected_role_memberships" in script
    assert "PASSWORD" not in script.upper()


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
    assert "exchangeEmailCode(code, 'verify')" in verify_page
    assert "verifyEmailWithToken(exchange.token)" in verify_page
    assert "exchangeEmailCode(code, 'reset')" in reset_page
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
