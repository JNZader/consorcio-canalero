import hashlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).parents[2]
SCRIPT = ROOT / "scripts/relocate_backup_local.sh"


class RelocatorFixture(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp())
        self.source = self.temp / "checkout" / "backup.sh"
        self.dest = self.temp / "safe" / "backup.sh"
        self.cron = self.temp / "cron"
        self.expected_git = self.temp / "git.receipt"
        self.expected_containers = self.temp / "containers.receipt"
        self.bin = self.temp / "bin"
        self.source.parent.mkdir(parents=True)
        self.dest.parent.mkdir()
        self.bin.mkdir()
        self.source.write_text("#!/bin/sh\necho safe\n")
        self.source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.old = f"0 2 * * * {self.source}"
        self.new = f"0 2 * * * {self.dest}"
        self.cron.write_text(self.old + "\n")
        self.expected_git.write_bytes(b" M scripts/backup_local.sh\0")
        self.expected_containers.write_text("a|img|now|0|/api\n")
        self._fake("git", "#!/bin/sh\ndd if=\"$FAKE_GIT_FILE\" bs=4096 2>/dev/null\n")
        self._fake("docker", "#!/bin/sh\ncase \"$1\" in ps) printf '%s' \"$FAKE_DOCKER_IDS\" ;; inspect) printf '%s' \"$FAKE_DOCKER\" ;; esac\n")

    def tearDown(self):
        shutil.rmtree(self.temp)

    def _fake(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def invoke(self, mode=None, **extra):
        env = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "RELOCATE_SOURCE": str(self.source), "RELOCATE_DEST": str(self.dest),
            "RELOCATE_CRON_FILE": str(self.cron), "RELOCATE_CRON_OLD": self.old,
            "RELOCATE_CRON_NEW": self.new, "RELOCATE_GIT_RECEIPT": str(self.expected_git),
            "RELOCATE_CONTAINER_RECEIPT": str(self.expected_containers),
            "RELOCATE_SHA256": self.source_hash,
            "RELOCATE_TEST_HOOKS": "1",
            "FAKE_GIT_FILE": str(self.expected_git),
            "FAKE_DOCKER_IDS": "cid\n",
            "FAKE_DOCKER": "a|img|now|0|api\n",
        } | extra
        args = ["/bin/sh", str(SCRIPT)] + ([] if mode is None else [mode])
        return subprocess.run(args, env=env, text=True, capture_output=True, check=False)

    def test_default_mode_fails_closed(self):
        self.assertNotEqual(self.invoke().returncode, 0)

    def test_red_contract_requires_artifact(self):
        result = self.invoke("admit")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_prerequisite_fails_closed(self):
        self._fake("sha256sum", "#!/bin/sh\nexit 127\n")
        result = self.invoke("admit", PATH=str(self.bin))
        self.assertNotEqual(result.returncode, 0)

    def test_raw_git_receipt_requires_nul_and_never_decompresses(self):
        self.expected_git.write_bytes(b" M x.z")
        result = self.invoke("admit")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("zstd", result.stderr + result.stdout)

    def test_container_receipt_is_canonical_and_exact(self):
        result = self.invoke("admit", FAKE_DOCKER="b|z|later|1|worker\na|img|now|0|/api\n")
        self.assertNotEqual(result.returncode, 0)
        self.expected_containers.write_text("a|img|now|0|/api\nb|z|later|1|/worker\n")
        result = self.invoke("admit", FAKE_DOCKER="b|z|later|1|worker\na|img|now|0|/api\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failure_and_signal_roll_back(self):
        for step in ("dest", "cron", "signal", "postrm"):
            with self.subTest(step=step):
                self.tearDown()
                self.setUp()
                self.cron.chmod(0o600)
                result = self.invoke("execute", RELOCATE_FAIL_STEP=step)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(self.source.exists())
                self.assertFalse(self.dest.exists())
                self.assertEqual(self.cron.read_text(), self.old + "\n")
                self.assertEqual(self.cron.stat().st_mode & 0o777, 0o600)
                self.assertFalse(list(self.dest.parent.glob(".backup-relocator.*")))

    def test_partial_state_is_rejected(self):
        shutil.copy2(self.source, self.dest)
        result = self.invoke("execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("divergent", result.stderr.lower())

    def test_execute_is_idempotent_only_after_exact_completion(self):
        result = self.invoke("execute")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.source.exists())
        self.assertTrue(self.dest.exists())
        self.assertEqual(self.cron.read_text(), self.new + "\n")
        result = self.invoke("execute")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.cron.write_text(self.old + "\n")
        result = self.invoke("execute")
        self.assertNotEqual(result.returncode, 0)

    def test_cron_file_mode_and_inode_survive_replacement(self):
        self.cron.chmod(0o600)
        before = self.cron.stat()
        result = self.invoke("execute")
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.cron.stat()
        self.assertEqual(after.st_mode, before.st_mode)
        self.assertEqual(after.st_ino, before.st_ino)
        self.assertEqual(self.cron.read_text(), self.new + "\n")

    def test_fail_hooks_are_inert_without_test_hook_gate(self):
        result = self.invoke("execute", RELOCATE_FAIL_STEP="dest", RELOCATE_TEST_HOOKS="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.dest.exists())
        self.assertFalse(self.source.exists())

    def test_stale_lock_with_dead_owner_is_reclaimed(self):
        lock = self.dest.parent / ".backup-relocator.lock"
        lock.mkdir()
        dead = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
        dead.wait()
        (lock / "owner").write_text(f"{dead.pid}\n")
        result = self.invoke("execute")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(lock.exists())
        self.assertTrue(self.dest.exists())

    def test_lock_with_live_owner_fails_closed(self):
        lock = self.dest.parent / ".backup-relocator.lock"
        lock.mkdir()
        (lock / "owner").write_text(f"{os.getpid()}\n")
        result = self.invoke("execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(lock.exists())
        self.assertTrue(self.source.exists())
        self.assertFalse(self.dest.exists())

    def test_lock_without_provable_owner_fails_closed(self):
        lock = self.dest.parent / ".backup-relocator.lock"
        lock.mkdir()
        result = self.invoke("execute")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(lock.exists())
        self.assertTrue(self.source.exists())

    def test_source_prohibits_deploy_lifecycle_and_backup_execution(self):
        text = SCRIPT.read_text()
        for forbidden in ("deploy_b3p", "docker start", "docker stop", "docker restart",
                          "docker compose", "docker run", "backup_local.sh"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
