#!/usr/bin/env python3
"""Receptor del webhook de deploy (INF-09).

Acepta solo el JSON que publica ``.github/workflows/deploy.yml``:

    {"revision": "<sha40>", "backend_image": "ghcr.io/.../backend@sha256:...",
     "geo_worker_image": "ghcr.io/.../geo-worker@sha256:..."}

Autenticación con comparación de tiempo constante, allowlist de los dos
repositorios GHCR en forma inmutable, y anti-replay por ``revision`` (una
revisión aceptada no se vuelve a aplicar). No interpola las imágenes en un
shell: escribe los digests en un env file y ejecuta ``docker compose`` con
argumentos en lista.

Escucha en 127.0.0.1. Caddy es quien lo publica. Ver
``docs/runbooks/infra-cicd-v6.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_IMAGE_RE = re.compile(
    r"^ghcr\.io/jnzader/consorcio-canalero/backend@(?P<digest>sha256:[0-9a-f]{64})$"
)
GEO_IMAGE_RE = re.compile(
    r"^ghcr\.io/jnzader/consorcio-canalero/geo-worker@(?P<digest>sha256:[0-9a-f]{64})$"
)
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_BODY_BYTES = 8192
WEBHOOK_PATH = "/hooks/deploy"


class WebhookError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def token_matches(presented: str, expected: str) -> bool:
    """Comparación de tiempo constante, también si las longitudes difieren."""
    presented_hash = hashlib.sha256(presented.encode("utf-8")).digest()
    expected_hash = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(presented_hash, expected_hash)


def bearer_token(header: str | None) -> str:
    if not header:
        return ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value or " " in value:
        return ""
    return value


def parse_payload(raw: bytes) -> tuple[str, str, str]:
    if len(raw) > MAX_BODY_BYTES:
        raise WebhookError(413, "body_too_large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebhookError(400, "invalid_json") from exc
    if not isinstance(data, dict):
        raise WebhookError(400, "invalid_json")
    revision = data.get("revision")
    backend_image = data.get("backend_image")
    geo_image = data.get("geo_worker_image")
    if not isinstance(revision, str) or REVISION_RE.fullmatch(revision) is None:
        raise WebhookError(400, "invalid_revision")
    if not isinstance(backend_image, str) or not isinstance(geo_image, str):
        raise WebhookError(400, "invalid_image")
    backend = BACKEND_IMAGE_RE.fullmatch(backend_image)
    geo = GEO_IMAGE_RE.fullmatch(geo_image)
    if backend is None or geo is None:
        raise WebhookError(400, "image_not_allowlisted")
    return revision, backend.group("digest"), geo.group("digest")


def _read_revisions(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def remember_revision(path: Path, revision: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_revisions(path)
    if revision in existing:
        raise WebhookError(409, "replay")
    # El caller graba la revisión solo después de un compose exitoso.
    with path.open("a", encoding="utf-8") as handle:
        handle.write(revision + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def assert_new_revision(path: Path, revision: str) -> None:
    if revision in _read_revisions(path):
        raise WebhookError(409, "replay")


def write_digest_env(path: Path, revision: str, backend_digest: str, geo_digest: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"DEPLOY_REVISION={revision}\n"
        f"BACKEND_DIGEST={backend_digest}\n"
        f"GEO_WORKER_DIGEST={geo_digest}\n"
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body, encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def log_event(event: str, **fields: object) -> None:
    payload = {"event": event, **fields}
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    sys.stdout.flush()


ApplyFn = Callable[[str, str, str], None]


def default_apply(stack_dir: Path, digest_env: Path, revision: str, backend: str, geo: str) -> None:
    import subprocess

    write_digest_env(digest_env, revision, backend, geo)
    stack_env = stack_dir / ".env"
    command = [
        "docker",
        "compose",
        "--env-file",
        str(stack_env),
        "--env-file",
        str(digest_env),
        "up",
        "-d",
        "--pull",
        "always",
        "--remove-orphans",
    ]
    completed = subprocess.run(
        command,
        cwd=stack_dir,
        check=False,
        timeout=int(os.environ.get("DEPLOY_COMPOSE_TIMEOUT_S", "900")),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        # No se reenvía stderr: compose puede imprimir DATABASE_URL.
        log_event("compose_failed", revision=revision, returncode=completed.returncode)
        raise WebhookError(500, "compose_failed")


def handle_deploy(
    *,
    authorization: str | None,
    body: bytes,
    expected_token: str,
    state_path: Path,
    apply: ApplyFn,
) -> dict[str, str]:
    if not expected_token:
        raise WebhookError(500, "server_misconfigured")
    if not token_matches(bearer_token(authorization), expected_token):
        raise WebhookError(401, "unauthorized")
    revision, backend_digest, geo_digest = parse_payload(body)
    assert_new_revision(state_path, revision)
    apply(revision, backend_digest, geo_digest)
    remember_revision(state_path, revision)
    log_event(
        "deploy_accepted",
        revision=revision,
        backend_digest=backend_digest,
        geo_worker_digest=geo_digest,
    )
    return {"status": "accepted", "revision": revision}


class _Handler(BaseHTTPRequestHandler):
    server: DeployWebhookServer

    def log_message(self, fmt: str, *args: object) -> None:
        log_event("http", peer=self.address_string(), message=fmt % args)

    def _send(self, status: int, payload: dict[str, str]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path != WEBHOOK_PATH:
            self._send(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self._send(400, {"error": "invalid_json"})
            return
        if length < 0 or length > MAX_BODY_BYTES:
            self._send(413, {"error": "body_too_large"})
            return
        body = self.rfile.read(length)
        try:
            with self.server.lock:
                result = handle_deploy(
                    authorization=self.headers.get("Authorization"),
                    body=body,
                    expected_token=self.server.expected_token,
                    state_path=self.server.state_path,
                    apply=self.server.apply,
                )
        except WebhookError as exc:
            log_event("deploy_rejected", code=exc.code, status=exc.status)
            self._send(exc.status, {"error": exc.code})
            return
        self._send(200, result)

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/health":
            self._send(200, {"status": "ok"})
            return
        self._send(404, {"error": "not_found"})


class DeployWebhookServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        expected_token: str,
        state_path: Path,
        apply: ApplyFn,
    ) -> None:
        self.expected_token = expected_token
        self.state_path = state_path
        self.apply = apply
        self.lock = threading.Lock()
        super().__init__(address, _Handler)


def build_apply(stack_dir: Path, digest_env: Path) -> ApplyFn:
    def apply(revision: str, backend_digest: str, geo_digest: str) -> None:
        default_apply(stack_dir, digest_env, revision, backend_digest, geo_digest)

    return apply


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Receptor local del webhook de deploy")
    parser.add_argument("--bind", default=os.environ.get("DEPLOY_WEBHOOK_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DEPLOY_WEBHOOK_PORT", "8090")))
    parser.add_argument(
        "--state",
        type=Path,
        default=Path(os.environ.get("DEPLOY_WEBHOOK_STATE", "/var/lib/consorcio-deploy/revisions")),
    )
    parser.add_argument(
        "--stack-dir",
        type=Path,
        default=Path(os.environ.get("STACK_DIR", "/home/javier/stacks/consorcio")),
    )
    parser.add_argument(
        "--digest-env",
        type=Path,
        default=Path(
            os.environ.get(
                "DEPLOY_DIGEST_ENV",
                "/home/javier/stacks/consorcio/deploy-digests.env",
            )
        ),
    )
    args = parser.parse_args(argv)
    if args.bind not in {"127.0.0.1", "::1"}:
        print("refusing to bind a non-loopback address", file=sys.stderr)
        return 2
    token = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
    if len(token) < 32:
        print("DEPLOY_WEBHOOK_SECRET must be at least 32 characters", file=sys.stderr)
        return 2
    server = DeployWebhookServer(
        (args.bind, args.port),
        token,
        args.state,
        build_apply(args.stack_dir, args.digest_env),
    )
    log_event("listen", bind=args.bind, port=args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
