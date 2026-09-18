#!/usr/bin/env python3
"""Focused regression probes for pressure-aware watchdog and safe remediation."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
WATCHDOG = REPO / "scripts" / "hermes-watchdog.sh"
AUTO_REMEDIATE = REPO / "scripts" / "auto-remediate.sh"
HEARTBEAT = REPO / "scripts" / "heartbeat.sh"
DEPLOY = REPO / "deploy.sh"


class WatchdogSwapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="argus-watchdog-")
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.hermes = self.home / ".hermes"
        self.proc = self.root / "proc"
        self.bin = self.root / "bin"
        (self.hermes / "logs" / "auto-remediate-state").mkdir(parents=True)
        (self.home / "scripts").mkdir(parents=True)
        (self.proc / "pressure").mkdir(parents=True)
        self.bin.mkdir()
        (self.hermes / ".env").write_text("", encoding="utf-8")
        (self.home / "scripts" / "check-integrations.sh").write_text(
            "#!/bin/bash\nexit 0\n", encoding="utf-8"
        )
        (self.home / "scripts" / "check-integrations.sh").chmod(0o755)
        now = datetime.now(timezone.utc).isoformat()
        (self.hermes / "logs" / "health-state.json").write_text(
            '{"last_check": ' + repr(now).replace("'", '"') + '}\n',
            encoding="utf-8",
        )
        self._write_fake_commands()
        self.watchdog = self.root / "hermes-watchdog.sh"
        rendered = WATCHDOG.read_text(encoding="utf-8")
        rendered = rendered.replace("@HERMES_HOST@", "127.0.0.1")
        rendered = rendered.replace("@HERMES_PORT@", "9119")
        rendered = rendered.replace("@HERMES_DIR@", str(self.hermes))
        rendered = rendered.replace("@HOME_DIR@", str(self.home))
        self.watchdog.write_text(rendered, encoding="utf-8")
        self.watchdog.chmod(0o755)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_fake_commands(self) -> None:
        (self.bin / "curl").write_text(
            "#!/bin/bash\nprintf '200'\n", encoding="utf-8"
        )
        (self.bin / "pgrep").write_text(
            "#!/bin/bash\nprintf '1234\\n'\n", encoding="utf-8"
        )
        (self.bin / "df").write_text(
            "#!/bin/bash\n"
            "printf 'Filesystem 1K-blocks Used Available Use%% Mounted on\\n'\n"
            "printf '/dev/mock 1000000 200000 800000 20%% /\\n'\n",
            encoding="utf-8",
        )
        (self.bin / "free").write_text(
            "#!/bin/bash\n"
            "if [ \"${1:-}\" = \"-h\" ]; then\n"
            "  printf '              total used free shared buff/cache available\\n'\n"
            "  printf 'Mem: 3.7Gi 1.0Gi 1.0Gi 0B 1.7Gi 2.7Gi\\n'\n"
            "  printf 'Swap: 2.0Gi 1.2Gi 0B 0B\\n'\n"
            "else\n"
            "  printf '              total used free shared buff/cache available\\n'\n"
            "  printf 'Mem: 4000000 1000000 1000000 0 2000000 3000000\\n'\n"
            "  printf 'Swap: 2000000 1200000 800000 0 0 0\\n'\n"
            "fi\n",
            encoding="utf-8",
        )
        (self.bin / "crontab").write_text(
            "#!/bin/bash\n"
            "if [ \"${1:-}\" = \"-l\" ]; then\n"
            "  for i in $(seq 1 20); do printf '* * * * * true\\n'; done\n"
            "fi\n",
            encoding="utf-8",
        )
        (self.bin / "sudo").write_text(
            f"#!/bin/bash\nprintf 'sudo-called\\n' > '{self.root / 'sudo-called'}'\n",
            encoding="utf-8",
        )
        for path in self.bin.iterdir():
            path.chmod(0o755)
        self._set_metrics(70, 2_400_000, 0, 0, "0.00")

    def _set_metrics(
        self,
        swap_pct: int,
        mem_available_kb: int,
        pswpin: int,
        pswpout: int,
        psi_some_avg10: str,
    ) -> None:
        swap_total = 2_000_000
        swap_used = swap_total * swap_pct // 100
        (self.proc / "meminfo").write_text(
            "MemTotal:       4000000 kB\n"
            f"MemAvailable:   {mem_available_kb} kB\n"
            f"SwapTotal:      {swap_total} kB\n"
            f"SwapFree:       {swap_total - swap_used} kB\n",
            encoding="utf-8",
        )
        (self.proc / "vmstat").write_text(
            f"pswpin {pswpin}\npswpout {pswpout}\n", encoding="utf-8"
        )
        (self.proc / "pressure" / "memory").write_text(
            f"some avg10={psi_some_avg10} avg60=0.00 avg300=0.00 total=0\n"
            "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",
            encoding="utf-8",
        )

    def _run_watchdog(self) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            HOME=str(self.home),
            PROC_ROOT=str(self.proc),
            PATH=f"{self.bin}:{env['PATH']}",
        )
        for name in ("WATCHDOG_BOT_TOKEN", "WATCHDOG_CHAT_ID", "TELEGRAM_PROXY"):
            env.pop(name, None)
        return subprocess.run(
            ["bash", str(self.watchdog)],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def _run_auto_remediate(self) -> subprocess.CompletedProcess[str]:
        auto = self.root / "auto-remediate.sh"
        rendered = AUTO_REMEDIATE.read_text(encoding="utf-8")
        rendered = rendered.replace("@HERMES_DIR@", str(self.hermes))
        auto.write_text(rendered, encoding="utf-8")
        auto.chmod(0o755)
        env = os.environ.copy()
        env.update(HOME=str(self.home), PATH=f"{self.bin}:{env['PATH']}")
        for name in ("WATCHDOG_BOT_TOKEN", "WATCHDOG_CHAT_ID", "TELEGRAM_PROXY"):
            env.pop(name, None)
        return subprocess.run(
            ["bash", str(auto)],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_swap_occupancy_without_pressure_is_silent(self) -> None:
        self._set_metrics(70, 2_400_000, 100, 100, "0.00")
        result = self._run_watchdog()
        state = self.hermes / "logs" / "auto-remediate-state" / "watchdog-alerts.state"
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(
            state.exists() and "swap_high" in state.read_text(encoding="utf-8"),
            state.read_text(encoding="utf-8") if state.exists() else "",
        )
        log = (self.hermes / "logs" / "watchdog.log").read_text(encoding="utf-8")
        self.assertNotIn("WATCHDOG АЛЕРТ", log)

    def test_swap_alert_needs_two_bad_cycles(self) -> None:
        self._set_metrics(40, 500_000, 100, 100, "0.00")
        first = self._run_watchdog()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self._set_metrics(60, 400_000, 130, 130, "0.00")
        second = self._run_watchdog()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        log_path = self.hermes / "logs" / "watchdog.log"
        log = log_path.read_text(encoding="utf-8")
        self.assertNotIn("WATCHDOG АЛЕРТ", log)
        self._set_metrics(60, 400_000, 160, 160, "0.00")
        third = self._run_watchdog()
        self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("📤 Отправлен алерт"), 1, log)
        state = (
            self.hermes / "logs" / "auto-remediate-state" / "watchdog-alerts.state"
        ).read_text(encoding="utf-8")
        self.assertIn("swap_high\t1", state)

    def test_swap_recovery_needs_two_clean_cycles(self) -> None:
        self._set_metrics(40, 500_000, 100, 100, "0.00")
        self._run_watchdog()
        self._set_metrics(60, 400_000, 130, 130, "0.00")
        self._run_watchdog()
        self._set_metrics(60, 400_000, 160, 160, "0.00")
        self._run_watchdog()
        self._set_metrics(60, 2_400_000, 160, 160, "0.00")
        first_clean = self._run_watchdog()
        self.assertEqual(first_clean.returncode, 0, first_clean.stdout + first_clean.stderr)
        log_path = self.hermes / "logs" / "watchdog.log"
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("📤 Отправлено восстановление"), 0, log)
        second_clean = self._run_watchdog()
        self.assertEqual(second_clean.returncode, 0, second_clean.stdout + second_clean.stderr)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("📤 Отправлено восстановление"), 1, log)

    def test_auto_remediate_does_not_act_on_swap_occupancy(self) -> None:
        result = self._run_auto_remediate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "sudo-called").exists())
        log = (self.hermes / "logs" / "auto-remediate.log").read_text(encoding="utf-8")
        self.assertIn("occupancy only", log)


class RemediationAndContractTests(unittest.TestCase):
    def test_stateful_scripts_use_nonblocking_locks(self) -> None:
        for path in (WATCHDOG, AUTO_REMEDIATE, HEARTBEAT):
            with self.subTest(path=path.name):
                self.assertIn("flock -n", path.read_text(encoding="utf-8"))

    def test_swap_remediation_never_drops_page_cache(self) -> None:
        self.assertNotIn("drop_caches", AUTO_REMEDIATE.read_text(encoding="utf-8"))
        self.assertNotIn("sudo tee /proc/sys/vm", AUTO_REMEDIATE.read_text(encoding="utf-8"))

    def test_telegram_tokens_stay_out_of_curl_argv(self) -> None:
        for path in (WATCHDOG, AUTO_REMEDIATE):
            text = path.read_text(encoding="utf-8")
            self.assertIn("-K -", text, path.name)
            self.assertNotIn(
                'curl -sS -m 15 -x "${TELEGRAM_PROXY', text, path.name
            )

    def test_cron_merge_normalizes_home_paths(self) -> None:
        deploy = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("gsub(/~\\//", deploy)
        self.assertIn("if (!seen[line]++)", deploy)


if __name__ == "__main__":
    unittest.main(verbosity=2)
