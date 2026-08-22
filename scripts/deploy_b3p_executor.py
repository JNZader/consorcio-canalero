"""B3-P backend-only executor; only invoke in an approved production window."""
from __future__ import annotations
import argparse, json, os, shlex, signal, subprocess, time, uuid
from dataclasses import dataclass, field
from enum import Enum
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from scripts import deploy_b3p as base
class Refusal(RuntimeError): pass
class Failure(RuntimeError): pass
class Interrupted(RuntimeError): pass
class Outcome(Enum): SUCCESS="success"; FAILED="failed"; ROLLED_BACK="rolled_back"; FAILED_ROLLBACK="failed_rollback"; FAILED_RESTORE="failed_restore"; FAILED_LOCK="failed_lock"
@dataclass
class Report:
    outcome: Outcome; phases: list[str] = field(default_factory=list); evidence: list[str] = field(default_factory=list); reasons: list[str] = field(default_factory=list)
TIMEOUTS={"preflight":15,"build":600,"cutover":300,"rollback":600}; FENCES={"cutover":240,"rollback":540}; LOCK="/tmp/consorcio-b3p-deploy.lock"
class Executor:
    def __init__(self, config=base.DEFAULTS, runner=base._run, http=None, fresh=None, tunnel=None, close_tunnel=None, sleeper=time.sleep, public=None, current=None):
        self.config,self.runner,self.http,self.sleeper,self.public=config,runner,http or self._http,sleeper,public or self._public
        self.current,self.fresh,self.tunnel,self.close_tunnel=current or base.current_checkout_preflight,fresh or self._fresh,tunnel or self._tunnel,close_tunnel or self._close
        self.report=Report(Outcome.FAILED); self.canary=False; self.tunnel_process=None; self.cutover=False; self.cutover_inflight=False; self.cutover_timeout=False; self.compose_tag_owned=False; self.lock_token=None; self.lock_release_attempted=False
    def _invoke(self,argv,timeout):
        if self.runner is base._run:
            process=subprocess.run(argv,capture_output=True,text=True,timeout=timeout,check=False); return process.returncode,process.stdout,process.stderr
        return self.runner(argv)
    def _acquire_lock(self):
        self.lock_token=uuid.uuid4().hex
        try: self._call("lock",f"umask 077; mkdir {LOCK} && printf %s {self.lock_token} > {LOCK}/owner")
        except Exception as exc:
            self._reason("lock-acquire",exc)
            if not self._release_lock(): raise Failure("unsafe lock acquisition") from exc
            raise Refusal("deployment lock unavailable") from exc
    def _release_lock(self):
        if not self.lock_token: return True
        if self.lock_release_attempted: return False
        self.lock_release_attempted=True
        try: self._call("lock",f'test "$(cat {LOCK}/owner)" = {self.lock_token} && rm -- {LOCK}/owner && rmdir -- {LOCK}')
        except Exception as exc: self._reason("lock-release",exc); return False
        self.lock_token=None; return True
    def _fresh(self, sha, runner):
        code,_,_=self._invoke(base.remote_argv(self.config,f"git -C {self.config.stack} fetch origin main"),TIMEOUTS["preflight"])
        if code: raise Failure("remote fetch preflight failed")
        if self._invoke(base.remote_argv(self.config,"timeout --version"),TIMEOUTS["preflight"])[0]: raise Failure("remote timeout preflight failed")
        base.verify_github_commit(self.config,sha)
        base.target_git_preflight(self.config,lambda argv:self._invoke(argv,TIMEOUTS["preflight"]))
        code,_,_=self._invoke(base.remote_argv(self.config,f"git -C {self.config.stack} merge --ff-only {sha}"),TIMEOUTS["preflight"])
        if code: raise Failure("ff-only target update failed")
        base.full_target_contract_preflight(self.config,lambda argv:self._invoke(argv,TIMEOUTS["preflight"]))
    @staticmethod
    def _request(url,method,path,headers,body):
        request=Request(url+path,data=body.encode() if body else None,headers=headers,method=method)
        try:
            with urlopen(request,timeout=10) as response: return response.status,response.read().decode()
        except HTTPError as response: return response.code,response.read().decode()
        except OSError as exc: raise Failure("HTTP transport failed") from exc
    @staticmethod
    def _http(method,path,headers,body): return Executor._request("http://127.0.0.1:18080",method,path,headers,body)
    @staticmethod
    def _public(method,path,headers,body): return Executor._request("https://cc10demayo-api.javierzader.com",method,path,headers,body)
    @staticmethod
    def _tunnel(argv): return subprocess.Popen(argv,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    @staticmethod
    def _close(process): process and (process.terminate(),process.wait(timeout=5))
    def _phase(self,name): self.report.phases.append(name) if not self.report.phases or self.report.phases[-1]!=name else None
    def _call(self,phase,command):
        self._phase(phase); code,out,err=self._invoke(base.remote_argv(self.config,command),TIMEOUTS.get(phase,60)); text=base.redact((out or err)[:400])
        self.report.evidence.append(f"{phase}:{text}")
        if code: raise Failure(f"{phase} failed")
        return out.strip()
    def _image(self,value):
        parts=value.split("|")
        if len(parts)!=2 or not parts[0].startswith("sha256:") or parts[1]!=base.COMPOSE_IMAGE: raise Failure("unvalidated runtime image")
        return parts[0]
    def _tunnel_argv(self): c=self.config; return ["ssh","-o","BatchMode=yes","-o","IdentitiesOnly=yes","-i",str(c.key.expanduser()),"-p",str(c.port),"-N","-L","127.0.0.1:18080:127.0.0.1:18080",f"{c.user}@{c.host}"]
    def _wait(self,client):
        reason="not ready"
        for attempt in range(60):
            try:
                status,_=client("GET","/ready",{},"")
                if status==200: return
                reason=f"ready status {status}"
            except Failure as exc: reason=base.redact(str(exc))
            if attempt<59: self.sleeper(1)
        raise Failure(f"bounded readiness timeout: {reason}")
    def _semantic(self,client):
        for path in ("/live","/ready","/health"):
            status,body=client("GET",path,{},"")
            if status!=200 or not body: raise Failure("health semantics failed")
    def _smoke(self,basin,environ,client):
        self._semantic(client); email,password=environ.get("E2E_ADMIN_EMAIL",""),environ.get("E2E_ADMIN_PASSWORD","")
        if not email or not password: raise Refusal("local E2E credentials required")
        status,body=client("POST","/api/v1/auth/login",{"Content-Type":"application/json"},json.dumps({"email":email,"password":password}))
        try: token=json.loads(body)["access_token"]
        except (KeyError,json.JSONDecodeError): raise Failure("credentialed login failed")
        path=f"/api/v2/geo/basins/{basin}/catastro-membership"
        if status!=200 or client("GET",path,{},"")[0]!=401 or client("GET",path,{"Authorization":"Bearer "+token},"")[0]!=200: raise Failure("membership smoke failed")
    def _observe(self,phase,target):
        if self._call(phase,f"docker logs --tail 100 {shlex.quote(target)}").lower().count("error")>5: raise Failure("bounded error counter failed")
    def _cleanup(self):
        errors=[]
        if self.canary:
            try:
                self._phase("cleanup"); code,out,err=self.runner(base.remote_argv(self.config,"docker rm -f consorcio-b3p-canary"))
                self.report.evidence.append(f"cleanup:{base.redact((out or err)[:400])}")
                if code and "no such container" not in (out+err).lower(): errors.append(Failure("canary removal failed"))
            except Exception as exc: errors.append(exc)
            self.canary=False
        try: self.close_tunnel(self.tunnel_process)
        except Exception as exc: errors.append(exc)
        self.tunnel_process=None
        if errors: raise Failure("canary/tunnel cleanup failed")
    def _rollback_admission(self,basin,environ,baseline):
        self._wait(self.public); self._smoke(basin,environ,self.public); self._observe("rollback","consorcio-backend")
        if self._call("rollback","docker ps --filter name=biogas --format '{{.ID}}|{{.Image}}|{{.Status}}'")!=baseline: raise Failure("Biogas rollback baseline changed")
    def _rollback(self,old,basin,environ,baseline):
        command=" && ".join((f"docker image tag {old} consorcio-backend:rollback-{old.removeprefix('sha256:')}",f"docker image tag {old} {base.COMPOSE_IMAGE}",base.compose_command("up", "-d", "--no-deps", "--no-build", "--force-recreate", "backend"),f"test \"$(docker inspect --format '{{{{.Image}}}}' consorcio-backend)\" = {old}"))
        self._fenced("rollback",command); self._rollback_admission(basin,environ,baseline)
    def _reason(self,label,exc): self.report.reasons.append(f"{label}:{base.redact(str(exc))[:400]}")
    def _fenced(self,phase,command): return self._call(phase,f"timeout --signal=TERM --kill-after=15s {FENCES[phase]}s sh -lc {shlex.quote(command)}")
    def _live(self): return self._call("reconcile","docker inspect consorcio-backend --format '{{.Image}}'")
    def _stable(self):
        states=[self._live()]
        for _ in range(2): self.sleeper(1); states.append(self._live())
        return states[0] if len(set(states))==1 else ""
    def _recover(self,old,basin,environ,baseline):
        try: self._rollback(old,basin,environ,baseline); return Outcome.ROLLED_BACK
        except subprocess.TimeoutExpired as exc:
            self._reason("rollback",exc)
            try:
                if self._stable()!=old: return Outcome.FAILED_ROLLBACK
                self._rollback_admission(basin,environ,baseline); return Outcome.ROLLED_BACK
            except Exception as recovery: self._reason("recovery",recovery)
        except Exception as exc: self._reason("rollback",exc)
        return Outcome.FAILED_ROLLBACK
    def _restore_compose_tag(self,old):
        if not self.compose_tag_owned or not old: return True
        try:
            self._call("restore",f"docker image tag {old} {base.COMPOSE_IMAGE}"); restored=self._call("restore",f"docker image inspect {base.COMPOSE_IMAGE} --format '{{{{.Id}}}}'")
            if restored!=old: raise Failure("compose tag restore mismatch")
        except Exception as exc: self._reason("restore",exc); return False
        self.compose_tag_owned=False; return True
    def _failed_with_restored_tag(self,old):
        if self._restore_compose_tag(old): self.report.outcome=Outcome.FAILED; return
        self._reason("unsafe",Failure("compose tag restore failed")); self.report.outcome=Outcome.FAILED_RESTORE
    def _defer_interrupts(self):
        for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,lambda *_: self.report.evidence.append("reconcile:deferred additional interruption"))
    def _await_cutover_fence(self): self._phase("reconcile"); self.report.evidence.append(f"reconcile:waiting {FENCES['cutover']+15}s for remote cutover fence"); self.sleeper(FENCES["cutover"]+15)
    def _finish(self,label,exc,old,new,basin,environ,baseline):
        self._reason(label,exc)
        if label=="interrupted" and self.cutover_inflight:
            self._defer_interrupts(); self._await_cutover_fence()
            try: live=self._stable()
            except Exception as reconcile: self._reason("reconcile",reconcile); self.report.outcome=Outcome.FAILED_ROLLBACK; return
            if live==old: self._failed_with_restored_tag(old); return
            if live!=new: self.report.outcome=Outcome.FAILED_ROLLBACK; return
            self.report.outcome=self._recover(old,basin,environ,baseline); return
        try: self._cleanup()
        except Exception as cleanup: self._reason("cleanup",cleanup)
        if not self.cutover:
            self._failed_with_restored_tag(old)
            return
        self._defer_interrupts()
        if self.cutover_timeout:
            try: live=self._stable()
            except Exception as reconcile: self._reason("reconcile",reconcile); self.report.outcome=Outcome.FAILED_ROLLBACK; return
            if live==old: self._failed_with_restored_tag(old); return
            if live!=new: self.report.outcome=Outcome.FAILED_ROLLBACK; return
        self.report.outcome=self._recover(old,basin,environ,baseline)
    def execute(self,sha,confirmation,environ,basin):
        if base.require_target_sha(sha) != self.config.target_sha or confirmation!=base.CONFIRMATION or environ.get("CONSORCIO_B3P_DEPLOY_ALLOW_EXECUTE")!="1": raise Refusal("exact configured target, confirmation, and execute opt-in required")
        if not basin or not environ.get("E2E_ADMIN_EMAIL") or not environ.get("E2E_ADMIN_PASSWORD"): raise Refusal("real basin is required" if not basin else "local E2E credentials required")
        old=baseline=new=""; handlers={}
        def interrupt(*_): raise Interrupted("interrupted")
        for sig in (signal.SIGINT,signal.SIGTERM): handlers[sig]=signal.signal(sig,interrupt)
        try:
            self._phase("admission"); self.current(self.config,self.runner)
            self._acquire_lock(); self._phase("preflight"); self.fresh(sha,self.runner)
            baseline=self._call("baseline","docker ps --filter name=biogas --format '{{.ID}}|{{.Image}}|{{.Status}}'")
            backup=self._call("backup","umask 077; mktemp /tmp/consorcio-b3p-compose.XXXXXX")
            if not backup.startswith("/tmp/"): raise Failure("unsafe compose backup")
            self._call("backup",f"cp -p docker-compose.yml {shlex.quote(backup)}")
            old=self._image(self._call("old","docker inspect consorcio-backend --format '{{.Image}}|{{.Config.Image}}'"))
            self.compose_tag_owned=True; self._call("old",f"docker image tag {old} {base.COMPOSE_IMAGE}")
            self._call("old",f"docker image tag {old} consorcio-backend:rollback-{old.removeprefix('sha256:')}")
            self._call("build",base.compose_command("build", "backend"))
            new=self._call("build","docker image inspect consorcio-backend --format '{{.Id}}'")
            if not new.startswith("sha256:") or new==old: raise Failure("new compose image invalid")
            self.canary=True
            self._call("canary",base.compose_command("run", "-d", "--no-deps", "--no-build", "--name", "consorcio-b3p-canary", "--publish", "127.0.0.1:18080:8000", "backend", "python", "-m", "app.server"))
            if self._call("canary","docker inspect consorcio-b3p-canary --format '{{.Image}}'")!=new: raise Failure("canary image mismatch")
            self.tunnel_process=self.tunnel(self._tunnel_argv()); self._wait(self.http); self._phase("smoke"); self._smoke(basin,environ,self.http); self._observe("smoke","consorcio-b3p-canary")
            self._cleanup(); self.cutover=True; self.cutover_inflight=True
            try: self._fenced("cutover",base.compose_command("up", "-d", "--no-deps", "--no-build", "backend"))
            except subprocess.TimeoutExpired: self.cutover_timeout=True; self.cutover_inflight=False; raise
            self.cutover_inflight=False
            if self._call("post","docker inspect consorcio-backend --format '{{.Image}}'")!=new: raise Failure("post-cutover image mismatch")
            self._phase("post"); self._smoke(basin,environ,self.public); self._observe("post","consorcio-backend")
            if self._call("post","docker ps --filter name=biogas --format '{{.ID}}|{{.Image}}|{{.Status}}'")!=baseline: raise Failure("Biogas baseline changed")
            if self._call("post","docker inspect consorcio-backend --format '{{.Image}}'")!=new: raise Failure("final backend image mismatch")
            self.report.outcome=Outcome.SUCCESS
        except Refusal: raise
        except (KeyboardInterrupt,Interrupted) as exc: self._finish("interrupted",exc,old,new,basin,environ,baseline)
        except Exception as exc: self._finish("primary",exc,old,new,basin,environ,baseline)
        finally:
            if not self._release_lock(): self._reason("unsafe-lock",Failure("lock release unproven")); self.report.outcome=Outcome.FAILED_LOCK
            for sig,handler in handlers.items(): signal.signal(sig,handler)
        return self.report
def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--target-sha"); parser.add_argument("--confirm"); parser.add_argument("--basin")
    args=parser.parse_args(argv); config=base.Config(target_sha=args.target_sha); report=Executor(config).execute(args.target_sha,args.confirm,os.environ,args.basin)
    print(json.dumps({"outcome":report.outcome.value,"phases":report.phases,"evidence":[base.redact(item) for item in report.evidence],"reasons":[base.redact(item) for item in report.reasons]}))
    return {Outcome.SUCCESS:0,Outcome.FAILED:2,Outcome.ROLLED_BACK:3,Outcome.FAILED_ROLLBACK:4,Outcome.FAILED_RESTORE:5,Outcome.FAILED_LOCK:6}[report.outcome]
if __name__=="__main__": raise SystemExit(main())
