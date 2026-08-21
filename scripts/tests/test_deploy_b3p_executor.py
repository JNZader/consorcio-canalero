from __future__ import annotations
import io, json, shlex, subprocess
from urllib.error import HTTPError
import pytest
from scripts import deploy_b3p as base
from scripts import deploy_b3p_executor as module
from scripts.deploy_b3p_executor import Executor, Failure, Outcome, Refusal
TARGET_SHA = "a" * 40
CONFIG = base.Config(target_sha=TARGET_SHA)
MOUNTS=[{"Type":"volume","Name":"consorcio-backend-cache","Destination":"/app/.cache","RW":True},{"Type":"volume","Name":"consorcio-geo-data","Destination":"/data/geo","RW":True},{"Type":"volume","Name":"consorcio-denuncia-uploads","Destination":"/app/uploads","RW":True},{"Type":"bind","Source":"/home/javier/stacks/consorcio/gee-backend/data/waterways","Destination":"/app/data/waterways","RW":True}]
class Fake:
    def __init__(self, fail="", post_fail=False, live="sha256:old", lock_owner=None): self.calls=[]; self.fail=fail; self.post_fail=post_fail; self.live=live; self.ready=0; self.timed=False; self.public_calls=[]; self.compose_tag="old"; self.lock_owner=lock_owner; self.lock_events=[]
    def run(self, argv):
        cmd=shlex.split(argv[-1])[-1] if argv[0]=="ssh" else " ".join(argv); self.calls.append(cmd)
        if "mkdir /tmp/consorcio-b3p-deploy.lock" in cmd:
            if self.lock_owner: return 1,"","locked"
            self.lock_owner=cmd.split("printf %s ",1)[1].split(" >",1)[0]; self.lock_events.append("acquire"); return 0,"",""
        if "rmdir -- /tmp/consorcio-b3p-deploy.lock" in cmd:
            token=cmd.split(" = ",1)[1].split(" &&",1)[0]
            if token!=self.lock_owner: return 1,"","owner mismatch"
            self.lock_owner=None; self.lock_events.append("release"); return 0,"",""
        if self.fail=="build-timeout" and "build backend" in cmd: raise subprocess.TimeoutExpired(cmd, 600)
        if self.fail=="cutover-interrupt" and not self.timed and " up -d" in cmd: self.timed=True; raise KeyboardInterrupt()
        if self.fail=="timeout" and not self.timed and " up -d" in cmd: self.timed=True; raise subprocess.TimeoutExpired(cmd, 30)
        if self.fail=="rollback-timeout" and "--force-recreate" in cmd: self.live="sha256:old"; raise subprocess.TimeoutExpired(cmd, 30)
        if self.fail=="launch-timeout" and "run -d --no-deps" in cmd: raise subprocess.TimeoutExpired(cmd, 30)
        if self.fail and self.fail in cmd: return 1,"password=no","failed"
        if "up -d --no-deps --no-build backend" in cmd: self.live="sha256:raced" if self.fail=="live-race" else "sha256:new"
        if "--force-recreate backend" in cmd: self.live="sha256:old"
        if "mktemp /tmp" in cmd: return 0,"/tmp/b3p-compose",""
        if "build backend" in cmd: self.compose_tag="new"
        if "docker image tag sha256:old consorcio-backend" in cmd and "rollback-" not in cmd: self.compose_tag="old"
        if "Mounts" in cmd: return 0,json.dumps(MOUNTS),""
        if "docker image inspect consorcio-backend" in cmd: return 0,f"sha256:{self.compose_tag}",""
        if "docker inspect consorcio-backend --format '{{.Image}}'" in cmd: return 0,self.live,""
        if "docker inspect consorcio-backend" in cmd: return 0,"sha256:old|consorcio-backend",""
        if "b3p-canary" in cmd and "inspect" in cmd: return 0,"sha256:new",""
        if "biogas" in cmd: return 0,"biogas=same",""
        return 0,"ok",""
    def http(self, method,path,headers,body):
        if path=="/ready":
            self.ready+=1
            return (503 if self.post_fail and self.ready>3 and (self.post_fail!="once" or self.ready==4) else (200 if self.ready>1 else 503)),"ready"
        if path=="/api/v1/auth/login": return 200,'{"access_token":"token"}'
        if path.endswith("catastro-membership"): return (200 if headers else 401),"membership"
        return 200,"ok"
    def public(self, method,path,headers,body):
        self.public_calls.append((method,path)); return self.http(method,path,headers,body)
def subject(fake, fresh=None):
    seen=[]
    def gate(sha, runner): seen.append(sha)
    return Executor(CONFIG,fake.run,fake.http,fresh or gate,lambda argv: fake.calls.append("TUNNEL "+" ".join(argv)) or object(),lambda _:None,lambda _:None,fake.public,current=lambda *_: None),seen
def go(executor): return executor.execute(TARGET_SHA,"DEPLOY-B3P",{"CONSORCIO_B3P_DEPLOY_ALLOW_EXECUTE":"1","E2E_ADMIN_EMAIL":"a@b","E2E_ADMIN_PASSWORD":"secret"},"real-basin")
def test_admission_is_zero_action_and_post_ff_gate_failure_blocks_runtime_mutation():
    fake=Fake(); executor,seen=subject(fake)
    with pytest.raises(base.Refusal): executor.execute(None,None,{},None)
    with pytest.raises(Refusal): executor.execute(TARGET_SHA,base.CONFIRMATION,{"CONSORCIO_B3P_DEPLOY_ALLOW_EXECUTE":"1"},"real-basin")
    assert fake.calls==[] and seen==[]
    executor,_=subject(fake,lambda *_: (_ for _ in ()).throw(Failure("post-ff gate"))); report=go(executor)
    assert report.outcome is Outcome.FAILED and fake.lock_events==["acquire","release"]
    assert not any(any(command in call for command in ("docker image tag", "compose build", "run -d", " up -d", "mktemp", "cp -p")) for call in fake.calls)
def test_compose_image_canary_and_public_phase_contract():
    fake=Fake(); executor,seen=subject(fake); report=go(executor)
    assert report.outcome is Outcome.SUCCESS and seen==[TARGET_SHA]
    assert report.phases==["admission","lock","preflight","baseline","backup","old","build","canary","smoke","cleanup","cutover","post","lock"]
    assert any("docker image inspect consorcio-backend" in c for c in fake.calls)
    canary=next(c for c in fake.calls if "run -d --no-deps" in c)
    assert "--no-deps --no-build --name consorcio-b3p-canary --publish 127.0.0.1:18080:8000 backend python -m app.server" in canary
    tunnel=next(c for c in fake.calls if c.startswith("TUNNEL")); assert tunnel.index("-L")<tunnel.index(f"{base.DEFAULTS.user}@{base.DEFAULTS.host}")
    assert ("GET","/health") in fake.public_calls and all("secret" not in x for x in fake.calls+report.evidence)
    assert all("biogas" not in c or "docker ps" in c for c in fake.calls)
    assert all(not any(word in c for word in ("worker","geo-worker","migrate","prune"," down")) for c in fake.calls)
@pytest.mark.parametrize("failure,outcome",[("run -d --no-deps",Outcome.FAILED),("--force-recreate",Outcome.FAILED_ROLLBACK)])
def test_failure_boundaries_and_exact_rollback(failure,outcome):
    fake=Fake(failure,post_fail=failure=="--force-recreate"); executor,_=subject(fake); report=go(executor)
    assert report.outcome is outcome
    if outcome is Outcome.FAILED: assert not any("--no-build backend" in c for c in fake.calls)
    else: assert any("sha256:old" in c and "--force-recreate backend" in c for c in fake.calls)
def test_expected_401_is_not_transport_failure_and_route_is_v2(monkeypatch): error=HTTPError("x",401,"",None,io.BytesIO(b"unauthorized")); monkeypatch.setattr(module,"urlopen",lambda *_,**__: (_ for _ in ()).throw(error)); assert Executor._http("GET","/api/v2/geo/basins/x/catastro-membership",{},"")[0]==401
def test_cli_prints_sanitized_report_and_distinct_exit(monkeypatch,capsys): monkeypatch.setattr(module.Executor,"execute",lambda *_: module.Report(Outcome.FAILED_ROLLBACK,evidence=["password=***"])); assert module.main(["--target-sha",TARGET_SHA,"--confirm",base.CONFIRMATION,"--basin","x"])==4 and '"outcome": "failed_rollback"' in capsys.readouterr().out
def test_readiness_retries_only_transport_failure_with_bounded_sleep():
    waits=[]; attempts=iter((Failure("connection refused"),(200,"ready"))); executor,_=subject(Fake()); executor.sleeper=lambda seconds: waits.append(seconds)
    def ready(*_):
        item=next(attempts)
        if isinstance(item, Failure): raise item
        return item
    executor._wait(ready)
    assert waits==[1]
def test_canary_launch_timeout_owns_and_removes_exact_name(): fake=Fake("launch-timeout"); executor,_=subject(fake); assert go(executor).outcome is Outcome.FAILED and any("docker rm -f consorcio-b3p-canary" in call for call in fake.calls)
@pytest.mark.parametrize("failure",["run -d --no-deps","build-timeout"])
def test_rejected_pre_cutover_work_restores_and_asserts_mutable_compose_tag(failure):
    fake=Fake(failure); report=go(subject(fake)[0]); assert report.outcome is Outcome.FAILED
    tags=[call for call in fake.calls if call.endswith("docker image tag sha256:old consorcio-backend")]
    restore=max(index for index,call in enumerate(fake.calls) if "docker image inspect consorcio-backend --format '{{.Id}}'" in call)
    failed=next(index for index,call in enumerate(fake.calls) if failure.replace("build-timeout","build backend") in call)
    assert len(tags)==2 and failed<restore and not any("up -d --no-deps --no-build backend" in call for call in fake.calls)
def test_canary_cleanup_accepts_not_found(): executor,_=subject(Fake()); executor.canary=True; executor.runner=lambda _: (1,"","No such container: consorcio-b3p-canary"); executor._cleanup()
def test_smoke_transport_failure_is_not_retried(): executor,_=subject(Fake()); waits=[]; executor.sleeper=lambda _: waits.append(1); pytest.raises(Failure,executor._smoke,"basin",{"E2E_ADMIN_EMAIL":"a","E2E_ADMIN_PASSWORD":"b"},lambda *_: (_ for _ in ()).throw(Failure("transport"))); assert waits==[]
def test_timeout_fences_reconcile_before_rollback_and_rollback_timeout_proves_old():
    fake=Fake("timeout"); report=go(subject(fake)[0])
    assert report.outcome is Outcome.FAILED and not any("--force-recreate" in call for call in fake.calls)
    fake=Fake("rollback-timeout",post_fail=True); assert go(subject(fake)[0]).outcome is Outcome.FAILED_ROLLBACK
    fake=Fake("rollback-timeout",post_fail="once"); assert go(subject(fake)[0]).outcome is Outcome.ROLLED_BACK; rollback=next(call for call in fake.calls if "--force-recreate" in call)
    reconcile=max(index for index,call in enumerate(fake.calls) if "docker inspect consorcio-backend --format '{{.Image}}'" in call)
    assert "timeout --signal=TERM --kill-after=15s" in rollback and module.FENCES["rollback"] < module.TIMEOUTS["rollback"] and fake.calls.index(rollback) < reconcile
def test_phase_timeouts_are_short_for_preflight_and_long_for_mutation(monkeypatch):
    seen=[]
    class Process: returncode=0; stdout="ok"; stderr=""
    monkeypatch.setattr(base.subprocess,"run",lambda *args,**kwargs: seen.append(kwargs["timeout"]) or Process()); executor=Executor()
    for phase in ("preflight","build","cutover","rollback"): executor._call(phase,"true")
    assert seen[0] < seen[1] and seen[0] < seen[2] <= seen[3]
def test_interrupt_rolls_back_after_cutover_and_canary_logs_are_targeted():
    fake=Fake(); executor,_=subject(fake); interrupted=[]
    def once(*args):
        if not interrupted: interrupted.append(True); raise KeyboardInterrupt()
        return fake.public(*args)
    executor.public=once; report=go(executor)
    assert report.outcome is Outcome.ROLLED_BACK and any("--force-recreate" in call for call in fake.calls)
    assert any("docker logs --tail 100 consorcio-b3p-canary" in call for call in fake.calls)
    assert any("docker logs --tail 100 consorcio-backend" in call for call in fake.calls)
def test_interrupt_during_cutover_waits_for_remote_fence_and_stable_polls_before_rollback():
    fake=Fake("cutover-interrupt",live="sha256:new"); executor,_=subject(fake); waits=[]; events=[]; runner=fake.run
    def guarded_runner(argv):
        command=shlex.split(argv[-1])[-1] if argv[0]=="ssh" else " ".join(argv)
        if "docker inspect consorcio-backend --format '{{.Image}}'" in command: assert "fence" in events; events.append("poll")
        if "--force-recreate backend" in command: assert events.count("poll")>=3; events.append("rollback")
        return runner(argv)
    def sleeper(seconds):
        waits.append(seconds)
        if seconds==module.FENCES["cutover"]+15: events.append("fence")
    executor.runner=guarded_runner; executor.sleeper=sleeper; report=go(executor)
    assert report.outcome is Outcome.ROLLED_BACK and module.FENCES["cutover"]+15 in waits
    assert events.index("fence")<events.index("poll")<events.index("rollback")
def test_report_reasons_and_cli_are_sanitized(monkeypatch,capsys):
    report=go(subject(Fake("run -d --no-deps"))[0])
    assert report.reasons and all("password=no" not in reason for reason in report.reasons)
    monkeypatch.setattr(module.Executor,"execute",lambda *_: module.Report(Outcome.FAILED,reasons=["primary:password=***"]))
    assert module.main(["--target-sha",TARGET_SHA,"--confirm",base.CONFIRMATION,"--basin","x"])==2
    assert '"reasons": ["primary:password=***"]' in capsys.readouterr().out
def test_sigterm_is_caught_and_handlers_are_restored(monkeypatch):
    seen=[]; monkeypatch.setattr(module.signal,"signal",lambda sig,handler: seen.append((sig,handler)) or module.signal.SIG_DFL); executor,_=subject(Fake(),lambda *_: seen[1][1](module.signal.SIGTERM,None))
    assert go(executor).outcome is Outcome.FAILED and [handler for _,handler in seen[-2:]]==[module.signal.SIG_DFL]*2
def test_timeout_fence_is_remote_and_requires_stable_post_fence_state():
    fake=Fake("timeout"); report=go(subject(fake)[0]); cutover=next(call for call in fake.calls if "up -d --no-deps --no-build backend" in call)
    polls=[call for call in fake.calls if "docker inspect consorcio-backend --format '{{.Image}}'" in call]
    assert "timeout --signal=TERM --kill-after=15s" in cutover and module.FENCES["cutover"] < module.TIMEOUTS["cutover"] and len(polls)==3 and report.outcome is Outcome.FAILED
@pytest.mark.parametrize("failure",["timeout","cutover-interrupt"])
def test_stable_old_cutover_reconciliation_restores_mutable_compose_tag(failure):
    fake=Fake(failure,live="sha256:old"); report=go(subject(fake)[0]); tags=[call for call in fake.calls if call.endswith("docker image tag sha256:old consorcio-backend")]
    assert report.outcome is Outcome.FAILED and len(tags)==2
    if failure=="timeout": assert fake.calls.index(tags[-1])<max(index for index,call in enumerate(fake.calls) if "docker image inspect consorcio-backend --format '{{.Id}}'" in call)
def test_restore_failure_is_reported_as_unsafe_failed_restore():
    fake=Fake("run -d --no-deps"); executor,_=subject(fake); runner=fake.run; tags=[]
    def fail_restore(argv):
        command=shlex.split(argv[-1])[-1] if argv[0]=="ssh" else " ".join(argv)
        if command.endswith("docker image tag sha256:old consorcio-backend"):
            tags.append(command)
            if len(tags)==2: return 1,"","restore failed"
        return runner(argv)
    executor.runner=fail_restore; report=go(executor); assert report.outcome is Outcome.FAILED_RESTORE and any(reason.startswith("unsafe:") for reason in report.reasons)
def test_second_signal_during_inflight_recovery_is_deferred_until_handlers_are_restored(monkeypatch):
    fake=Fake("cutover-interrupt",live="sha256:new"); executor,_=subject(fake); installed={}
    def install(sig,handler): previous=installed.get(sig,module.signal.SIG_DFL); installed[sig]=handler; return previous
    monkeypatch.setattr(module.signal,"signal",install); executor.sleeper=lambda seconds: installed[module.signal.SIGTERM](module.signal.SIGTERM,None) if seconds==module.FENCES["cutover"]+15 else None; report=go(executor)
    assert report.outcome is Outcome.ROLLED_BACK and any("deferred additional interruption" in item for item in report.evidence) and installed=={module.signal.SIGINT:module.signal.SIG_DFL,module.signal.SIGTERM:module.signal.SIG_DFL}
@pytest.mark.parametrize("owner",["stale","foreign"])
def test_existing_lock_refuses_before_fetch_or_mutation(owner):
    fake=Fake(lock_owner=owner); assert go(subject(fake)[0]).outcome is Outcome.FAILED_LOCK and fake.lock_owner==owner and not any(any(word in call for word in ("fetch origin","compose build"," up -d")) for call in fake.calls)
@pytest.mark.parametrize("failure,outcome",[("",Outcome.SUCCESS),("run -d --no-deps",Outcome.FAILED),("live-race",Outcome.ROLLED_BACK)])
def test_lock_spans_final_validation_and_releases_on_all_outcomes(failure,outcome):
    fake=Fake(failure); report=go(subject(fake)[0]); release=next(index for index,call in enumerate(fake.calls) if "rmdir -- /tmp/consorcio-b3p-deploy.lock" in call)
    assert report.outcome is outcome and fake.lock_owner is None and fake.lock_events==["acquire","release"] and (failure!="live-race" or any("--force-recreate backend" in call for call in fake.calls))
    if outcome is Outcome.SUCCESS: checks=[index for index,call in enumerate(fake.calls) if "docker inspect consorcio-backend --format '{{.Image}}'" in call]; assert len(checks)>=2 and max(checks)<release


def test_every_executor_compose_command_uses_the_shared_production_local_selector():
    fake=Fake(); report=go(subject(fake)[0])
    assert report.outcome is Outcome.SUCCESS
    compose_calls=[call for call in fake.calls if "docker compose" in call]
    selector=base.compose_command().strip()
    assert compose_calls and all(selector in call for call in compose_calls)
