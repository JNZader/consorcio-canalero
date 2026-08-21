from __future__ import annotations

import io
import os

import pytest

from scripts import deploy_b3p as deploy


class Runner:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def __call__(self, argv):
        self.calls.append(argv)
        return self.results.pop(0) if self.results else (0, "ok", "")


def test_plan_is_default_and_never_runs_a_subprocess():
    runner = Runner()
    output = io.StringIO()
    assert deploy.main([], runner=runner, stdout=output) == 0
    assert runner.calls == []
    assert "plan" in output.getvalue()
    assert "\"argv\"" in output.getvalue()
    assert deploy.DEFAULTS.target_sha in output.getvalue()


def test_execute_refuses_in_gate_order_before_ssh(monkeypatch):
    runner = Runner()
    verified = []
    monkeypatch.setattr(deploy, "verify_github_commit", lambda *args: verified.append(args))
    for argv, message in [
        (["execute"], "target"),
        (["execute", "--target-sha", "bad"], "target"),
        (["execute", "--target-sha", deploy.DEFAULTS.target_sha], "confirmation"),
        (["execute", "--target-sha", deploy.DEFAULTS.target_sha, "--confirm", "DEPLOY-B3P"], "opt-in"),
    ]:
        with pytest.raises(deploy.Refusal, match=message):
            deploy.main(argv, runner=runner, environ={})
    assert runner.calls == []
    assert verified == []


def test_execute_requires_github_verification_before_unimplemented_mutation(monkeypatch):
    runner = Runner()
    monkeypatch.setattr(deploy, "verify_github_commit", lambda *args: None)
    with pytest.raises(deploy.Refusal, match="not implemented"):
        deploy.main(
            ["execute", "--target-sha", deploy.DEFAULTS.target_sha, "--confirm", "DEPLOY-B3P"],
            runner=runner,
            environ={"CONSORCIO_B3P_DEPLOY_ALLOW_EXECUTE": "1"},
        )
    assert runner.calls == []


def test_preflight_uses_one_read_only_ssh_argv_per_gate_and_stops_on_failure():
    runner = Runner([(0, "main", ""), (9, "secret=password=bad", "failure")])
    with pytest.raises(deploy.Refusal, match="compose"):
        deploy.preflight(deploy.DEFAULTS, runner)
    assert len(runner.calls) == 2
    assert all(call[0] == "ssh" and "&&" not in call[-1] and "\n" not in call[-1] for call in runner.calls)
    assert "password=***" in deploy.redact("password=bad")


def test_preflight_fails_closed_when_a_read_only_output_disagrees_with_its_gate():
    with pytest.raises(deploy.Refusal, match="branch"):
        deploy.preflight(deploy.DEFAULTS, Runner([(0, "feature/unsafe", "")]))


def test_mount_normalization_requires_exact_named_volume_contract():
    mounts = [
        {"Type": "volume", "Name": "consorcio-backend-cache", "Destination": "/app/.cache", "RW": True},
        {"Type": "volume", "Name": "consorcio-geo-data", "Destination": "/data/geo", "RW": True},
        {"Type": "volume", "Name": "consorcio-denuncia-uploads", "Destination": "/app/uploads", "RW": True},
    ]
    assert deploy.normalize_mounts(mounts) == {
        ("volume", "backend-cache", "/app/.cache", "rw"),
        ("volume", "geo-data", "/data/geo", "rw"),
        ("volume", "denuncia-uploads", "/app/uploads", "rw"),
    }
    with pytest.raises(deploy.Refusal, match="mount"):
        deploy.normalize_mounts(mounts + [{"Type": "bind", "Source": "/", "Destination": "/app", "RW": True}])


def test_services_and_volumes_are_backend_only_and_biogas_is_observational():
    assert deploy.TARGET_SERVICE == "backend"
    assert all("biogas" not in gate.command.lower() for gate in deploy.GATES)
    assert deploy.LOGICAL_VOLUMES == {"consorcio-backend-cache", "consorcio-geo-data", "consorcio-denuncia-uploads"}


def test_smoke_command_keeps_credentials_out_of_argv_and_redacts_errors():
    args, env = deploy.smoke_tunnel_command({"E2E_ADMIN_EMAIL": "a@b", "E2E_ADMIN_PASSWORD": "shh"})
    assert "a@b" not in " ".join(args) and "shh" not in " ".join(args)
    assert env["E2E_ADMIN_PASSWORD"] == "shh"
    assert args[-1] == f"{deploy.DEFAULTS.user}@{deploy.DEFAULTS.host}"
    assert args.index("-N") < len(args) - 1
    assert "shh" not in deploy.redact("token=shh password=shh")


def test_rollback_uses_immutable_old_image_id_and_never_touches_biogas():
    plan = deploy.rollback_plan("sha256:old-image")
    assert "sha256:old-image" in " ".join(plan)
    assert "biogas" not in " ".join(plan).lower()
    assert "docker compose down" not in " ".join(plan)


def test_github_verification_fails_closed_for_invalid_or_malformed_payload():
    class Response:
        def __init__(self, payload): self.payload = payload
        def read(self): return self.payload
        def __enter__(self): return self
        def __exit__(self, *args): pass
    for payload in [b"not json", b'{"sha":"wrong"}', b'{"sha":"' + deploy.DEFAULTS.target_sha.encode() + b'","commit":{"verification":{"verified":true,"reason":"unsigned"}}}']:
        with pytest.raises(deploy.Refusal):
            deploy.verify_github_commit(deploy.DEFAULTS, deploy.DEFAULTS.target_sha, opener=lambda request, timeout: Response(payload))


def test_reviewed_remote_plan_and_free_port_contract():
    import shlex
    command = "git -C /home/javier/stacks/consorcio status --porcelain"
    argv = deploy.ssh_argv(deploy.DEFAULTS, command)
    assert argv[-1] == "sh -lc " + shlex.quote(command)
    assert argv[-2] == f"{deploy.DEFAULTS.user}@{deploy.DEFAULTS.host}"
    assert shlex.split(argv[-1]) == ["sh", "-lc", command]
    plan = deploy.deployment_plan(deploy.DEFAULTS)
    assert all(step["argv"][0] == "ssh" and deploy.DEFAULTS.stack in shlex.split(step["argv"][-1])[-1] for step in plan)
    with pytest.raises(deploy.Refusal, match="compose image"):
        deploy._validate_gate(deploy.Gate("live-image", ""), "sha256:old-image|unproven")
    deploy._validate_gate(deploy.Gate("live-image", ""), "sha256:old-image|consorcio-backend")
    with pytest.raises(TypeError):
        deploy.rollback_plan("sha256:old-image", deploy.DEFAULTS, "unproven")
    text = shlex.split(deploy.rollback_plan("sha256:old-image")[-1])[-1]
    assert "rollback-old-image" in text and "docker image tag sha256:old-image consorcio-backend" in text
    assert "--no-build --force-recreate backend" in text and "docker inspect" in text
    loopback = next(gate for gate in deploy.GATES if gate.name == "loopback-port")
    assert loopback.command == "ss -H -ltn sport = :18080"
    deploy._validate_gate(loopback, "")
    with pytest.raises(deploy.Refusal, match="occupied"):
        deploy._validate_gate(loopback, "LISTEN 0 4096 127.0.0.1:18080 0.0.0.0:*")
