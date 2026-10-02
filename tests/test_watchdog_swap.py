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
WATCHDOG_HEALTH = REPO / "scripts" / "watchdog-health.sh"
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
        self.integration_call_log = self.root / "integration-calls.log"
        self.git_call_log = self.root / "git-calls.log"
        integration_checker = self.hermes / "scripts" / "health-check-integrations.sh"
        integration_checker.parent.mkdir(parents=True)
        integration_checker.write_text(
            '#!/bin/bash\nprintf "%s\\n" "$*" >> "$INTEGRATION_CALL_LOG"\nexit 0\n',
            encoding="utf-8",
        )
        integration_checker.chmod(0o755)
        now = datetime.now(timezone.utc).isoformat()
        (self.hermes / "logs" / "health-state.json").write_text(
            '{"last_check": ' + repr(now).replace("'", '"') + '}\n',
            encoding="utf-8",
        )
        self._write_fake_commands()
        self.watchdog = self.root / "hermes-watchdog.sh"

        self._render_watchdog()

    def _render_watchdog(
        self, *, integrations: str = "ON", analyzer: str = "OFF"
    ) -> None:
        rendered = WATCHDOG.read_text(encoding="utf-8")
        rendered = rendered.replace("@HERMES_HOST@", "127.0.0.1")
        rendered = rendered.replace("@HERMES_PORT@", "9119")
        rendered = rendered.replace("@HERMES_DIR@", str(self.hermes))
        rendered = rendered.replace("@HOME_DIR@", str(self.home))
        rendered = rendered.replace("@MODULE_INTEGRATIONS@", integrations)
        rendered = rendered.replace("@MODULE_ANALYZER@", analyzer)
        self.watchdog.write_text(rendered, encoding="utf-8")
        self.watchdog.chmod(0o755)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_fake_commands(self) -> None:
        (self.bin / "curl").write_text(
            "#!/bin/bash\nprintf '200'\n", encoding="utf-8"
        )
        # 2026-10-02: watchdog определяет живость gateway каноническим матчером
        # $HOME_DIR/scripts/hermes-gateway-pids.py, а не pgrep по argv. Прежний
        # шим pgrep стал мёртвым кодом, и без живого helper блок уходил в ветку
        # «матчер недоступен» — цикл не засчитывался как плохой, и тест гистерезиса
        # вёл себя иначе, чем на боевом скрипте. Ставим helper в scripts/ рядом
        # с отрендеренным шаблоном: тот же путь, что и в проде.
        (self.bin / "pgrep").write_text(
            "#!/bin/bash\nprintf '1234\\n'\n", encoding="utf-8"
        )
        helper = self.home / "scripts" / "hermes-gateway-pids.py"
        helper.parent.mkdir(parents=True, exist_ok=True)
        # Вызов идёт как `python3 <helper>`: стаб обязан быть Python-сценарием,
        # иначе SyntaxError → rc=1 → «процесс мёртв».
        helper.write_text("print(1234)\n", encoding="utf-8")
        helper.chmod(0o755)
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
            "  if [ -n \"${ARGUS_TEST_CRONTAB:-}\" ]; then\n"
            "    printf '%s\\n' \"$ARGUS_TEST_CRONTAB\"\n"
            "  else\n"
            "    for i in $(seq 1 20); do printf '* * * * * true\\n'; done\n"
            "  fi\n"
            "fi\n",
            encoding="utf-8",
        )
        (self.bin / "systemctl").write_text(
            "#!/bin/bash\n"
            "case \"$*\" in\n"
            "  *'show -p LoadState --value netdata.service'*) echo \"${TEST_NETDATA_LOAD_STATE:-not-found}\" ;;\n"
            "  *'is-active monitoring-bot-poller.service'*) [ \"${TEST_TG_BOT_ACTIVE:-yes}\" = yes ] ;;\n"
            "  *'is-active netdata.service'*) [ \"${TEST_NETDATA_ACTIVE:-yes}\" = yes ] ;;\n"
            "  *) exit 0 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        (self.bin / "git").write_text(
            "#!/bin/bash\n"
            "printf '%s|%s\\n' \"$PWD\" \"$*\" >> \"$GIT_CALL_LOG\"\n"
            "[ \"$*\" != 'diff --cached --quiet' ]\n",
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
            INTEGRATION_CALL_LOG=str(self.integration_call_log),
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

    def _run_watchdog_health(
        self,
        *,
        analyzer: str = "OFF",
        tg_bot: str = "OFF",
        extra_env: dict[str, str] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        script = self.root / "watchdog-health.sh"
        rendered = WATCHDOG_HEALTH.read_text(encoding="utf-8")
        rendered = rendered.replace("@MODULE_ANALYZER@", analyzer)
        rendered = rendered.replace("@MODULE_TG_BOT@", tg_bot)
        script.write_text(rendered, encoding="utf-8")
        script.chmod(0o755)
        env = os.environ.copy()
        env.update(
            HOME=str(self.home),
            PATH=f"{self.bin}:{env['PATH']}",
            ARGUS_TEST_CRONTAB=(
                "*/5 * * * * $HOME/scripts/hermes-watchdog.sh\n"
                "*/2 * * * * $HOME/.hermes/scripts/gateway-liveness.sh\n"
                "*/5 * * * * $HOME/.hermes/scripts/dashboard-liveness.sh"
            ),
            WATCHDOG_BOT_TOKEN="",
            WATCHDOG_CHAT_ID="",
        )
        env.update(extra_env or {})
        result = subprocess.run(
            ["bash", str(script)], env=env, capture_output=True, text=True, timeout=20
        )
        log = (self.hermes / "logs" / "watchdog-health.log").read_text(encoding="utf-8")
        return result, log

    def _run_heartbeat(self) -> subprocess.CompletedProcess[str]:
        script = self.root / "heartbeat.sh"
        rendered = HEARTBEAT.read_text(encoding="utf-8").replace(
            "@HERMES_DIR@", str(self.hermes)
        )
        script.write_text(rendered, encoding="utf-8")
        script.chmod(0o755)
        env = os.environ.copy()
        env.update(
            HOME=str(self.home),
            PATH=f"{self.bin}:{env['PATH']}",
            GITHUB_REPO="dummy/heartbeat",
            GH_TOKEN="DUMMY_GH_TOKEN",
            GIT_CALL_LOG=str(self.git_call_log),
        )
        for name in ("CRONPING_TOKEN", "DMS_SNITCH"):
            env.pop(name, None)
        return subprocess.run(
            ["bash", str(script)], env=env, capture_output=True, text=True, timeout=20
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

    def test_watchdog_uses_owned_integration_checker_in_quick_mode(self) -> None:
        result = self._run_watchdog()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.home / "scripts" / "check-integrations.sh").exists())
        self.assertEqual(self.integration_call_log.read_text(encoding="utf-8"), "--quick\n")

    def test_disabled_integrations_do_not_create_a_core_incident(self) -> None:
        (self.hermes / "scripts" / "health-check-integrations.sh").unlink()
        self._render_watchdog(integrations="OFF")
        result = self._run_watchdog()
        state = self.hermes / "logs" / "auto-remediate-state" / "watchdog-alerts.state"
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("int:", state.read_text(encoding="utf-8"))

    def test_expected_but_missing_integration_checker_is_explicit(self) -> None:
        (self.hermes / "scripts" / "health-check-integrations.sh").unlink()
        result = self._run_watchdog()
        state = self.hermes / "logs" / "auto-remediate-state" / "watchdog-alerts.state"
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("integration_check_missing", state.read_text(encoding="utf-8"))

    def test_disabled_analyzer_without_state_is_not_a_core_incident(self) -> None:
        health_state = self.hermes / "logs" / "health-state.json"
        health_state.unlink()
        self._render_watchdog(analyzer="OFF")
        result = self._run_watchdog()
        alerts = self.hermes / "logs" / "auto-remediate-state" / "watchdog-alerts.state"
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("health_state_", alerts.read_text(encoding="utf-8"))
        self.assertFalse(health_state.exists())

    def test_enabled_analyzer_missing_state_remains_a_problem(self) -> None:
        (self.hermes / "logs" / "health-state.json").unlink()
        self._render_watchdog(analyzer="ON")
        result = self._run_watchdog()
        alerts = self.hermes / "logs" / "auto-remediate-state" / "watchdog-alerts.state"
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("health_state_missing", alerts.read_text(encoding="utf-8"))

    def test_enabled_analyzer_unreadable_state_is_a_core_incident(self) -> None:
        (self.hermes / "logs" / "health-state.json").write_text("{invalid json\n", encoding="utf-8")
        self._render_watchdog(analyzer="ON")
        result = self._run_watchdog()
        alerts = self.hermes / "logs" / "auto-remediate-state" / "watchdog-alerts.state"
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("health_state_unreadable", alerts.read_text(encoding="utf-8"))

    def test_enabled_analyzer_stale_state_remains_a_core_incident(self) -> None:
        (self.hermes / "logs" / "health-state.json").write_text(
            '{"last_check": "2000-01-01T00:00:00Z"}\n', encoding="utf-8"
        )
        self._render_watchdog(analyzer="ON")
        result = self._run_watchdog()
        alerts = self.hermes / "logs" / "auto-remediate-state" / "watchdog-alerts.state"
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("health_state_stale", alerts.read_text(encoding="utf-8"))

    def test_watchdog_health_skips_analyzer_when_disabled(self) -> None:
        (self.hermes / "logs" / "health-state.json").unlink()
        result, log = self._run_watchdog_health(analyzer="OFF")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("L3 health-state.json", log)

    def test_watchdog_health_reports_enabled_missing_or_unreadable_analyzer_state(self) -> None:
        health_state = self.hermes / "logs" / "health-state.json"
        health_state.unlink()
        result, missing_log = self._run_watchdog_health(analyzer="ON")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("L3 health-state.json: not found", missing_log)

        health_state.write_text("{invalid json\n", encoding="utf-8")
        result, unreadable_log = self._run_watchdog_health(analyzer="ON")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("L3 health-state.json: no last_check", unreadable_log)

        health_state.write_text('{"last_check": "2000-01-01T00:00:00Z"}\n', encoding="utf-8")
        result, stale_log = self._run_watchdog_health(analyzer="ON")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("L3 health-check stale", stale_log)

    def test_disabled_tg_bot_skips_inactive_service(self) -> None:
        result, log = self._run_watchdog_health(
            tg_bot="OFF", extra_env={"TEST_TG_BOT_ACTIVE": "no"}
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("monitoring-bot-poller.service not active", log)

    def test_enabled_tg_bot_inactive_service_remains_reportable(self) -> None:
        result, log = self._run_watchdog_health(
            tg_bot="ON", extra_env={"TEST_TG_BOT_ACTIVE": "no"}
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("monitoring-bot-poller.service not active", log)

    def test_absent_netdata_unit_does_not_fail_self_health(self) -> None:
        result, log = self._run_watchdog_health(
            extra_env={"TEST_NETDATA_LOAD_STATE": "not-found", "TEST_NETDATA_ACTIVE": "no"}
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("netdata.service not active", log)

    def test_installed_inactive_netdata_remains_reportable(self) -> None:
        result, log = self._run_watchdog_health(
            extra_env={"TEST_NETDATA_LOAD_STATE": "loaded", "TEST_NETDATA_ACTIVE": "no"}
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("netdata.service not active", log)

    def test_default_modules_do_not_require_optional_self_health_surfaces(self) -> None:
        (self.hermes / "logs" / "health-state.json").unlink()
        result, log = self._run_watchdog_health(
            analyzer="OFF",
            tg_bot="OFF",
            extra_env={
                "TEST_TG_BOT_ACTIVE": "no",
                "TEST_NETDATA_LOAD_STATE": "not-found",
                "TEST_NETDATA_ACTIVE": "no",
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("PROBLEMS FOUND", log)

    def test_heartbeat_writer_prefers_canonical_directory(self) -> None:
        canonical = self.hermes / "gh-heartbeat"
        legacy = self.hermes / "hermes-infra"
        canonical.mkdir()
        legacy.mkdir()
        legacy_heartbeat = legacy / "heartbeat.txt"
        legacy_heartbeat.write_text("legacy untouched\n", encoding="utf-8")

        result = self._run_heartbeat()

        calls = self.git_call_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(calls)
        self.assertTrue(all(line.startswith(f"{canonical}|") for line in calls), calls)
        self.assertTrue((canonical / "heartbeat.txt").exists())
        self.assertEqual(legacy_heartbeat.read_text(encoding="utf-8"), "legacy untouched\n")

    def test_heartbeat_writer_uses_existing_legacy_directory_as_fallback(self) -> None:
        legacy = self.hermes / "hermes-infra"
        legacy.mkdir()

        result = self._run_heartbeat()

        calls = self.git_call_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(calls)
        self.assertTrue(all(line.startswith(f"{legacy}|") for line in calls), calls)
        self.assertTrue((legacy / "heartbeat.txt").exists())
        self.assertFalse((self.hermes / "gh-heartbeat").exists())

    def test_heartbeat_github_backend_disabled_without_explicit_repo(self) -> None:
        """RR0c B2: GITHUB_REPO — явная настройка оператора; без неё
        GitHub-бекенд остаётся выключенным, даже если каталог репо существует
        и токен задан. Никаких git-вызовов и персонального дефолта."""
        (self.hermes / "gh-heartbeat").mkdir()
        script = self.root / "heartbeat.sh"
        rendered = HEARTBEAT.read_text(encoding="utf-8").replace(
            "@HERMES_DIR@", str(self.hermes)
        )
        script.write_text(rendered, encoding="utf-8")
        script.chmod(0o755)
        env = os.environ.copy()
        env.update(
            HOME=str(self.home),
            PATH=f"{self.bin}:{env['PATH']}",
            GH_TOKEN="DUMMY_GH_TOKEN",
            GIT_CALL_LOG=str(self.git_call_log),
        )
        env.pop("GITHUB_REPO", None)
        for name in ("CRONPING_TOKEN", "DMS_SNITCH"):
            env.pop(name, None)

        result = subprocess.run(
            ["bash", str(script)], env=env, capture_output=True, text=True, timeout=20
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.git_call_log.exists())
        self.assertTrue((self.hermes / "gh-heartbeat").exists())

    def test_heartbeat_writer_does_not_create_legacy_directory(self) -> None:
        result = self._run_heartbeat()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.hermes / "hermes-infra").exists())
        self.assertFalse((self.hermes / "gh-heartbeat").exists())
        self.assertFalse(self.git_call_log.exists())

    def test_watchdog_health_prefers_canonical_heartbeat_directory(self) -> None:
        canonical = self.hermes / "gh-heartbeat"
        legacy = self.hermes / "hermes-infra"
        canonical.mkdir()
        legacy.mkdir()
        canonical_heartbeat = canonical / "heartbeat.txt"
        legacy_heartbeat = legacy / "heartbeat.txt"
        canonical_heartbeat.write_text("canonical\n", encoding="utf-8")
        legacy_heartbeat.write_text("legacy\n", encoding="utf-8")
        os.utime(canonical_heartbeat, (1, 1))
        os.utime(legacy_heartbeat, None)

        result, log = self._run_watchdog_health(analyzer="OFF", tg_bot="OFF")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Heartbeat stale", log)

    def test_watchdog_health_uses_legacy_heartbeat_fallback(self) -> None:
        legacy = self.hermes / "hermes-infra"
        legacy.mkdir()
        heartbeat = legacy / "heartbeat.txt"
        heartbeat.write_text("legacy\n", encoding="utf-8")
        os.utime(heartbeat, (1, 1))

        result, log = self._run_watchdog_health(analyzer="OFF", tg_bot="OFF")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Heartbeat stale", log)

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


    def test_auto_remediate_never_touches_crontab(self) -> None:
        """RR1a: stale full-crontab бэкап не должен триггерить восстановление —
        auto-remediate больше не вызывает crontab ни в какой форме (валидное
        малое расписание — не поломка; writer расписания — только deploy.sh)."""
        cron_fixture = self.root / "crontab-fixture.txt"
        cron_fixture.write_text(
            "# operator job\n"
            "0 9 * * 1-5 /usr/bin/operator-report --quiet\n"
            "30 10 * * * /usr/bin/backup-tool run\n",
            encoding="utf-8")
        crontab_calls = self.root / "crontab-calls.log"
        # flock-шим: среда без util-linux иначе рано выходит на lock-гейте
        (self.bin / "flock").write_text("#!/bin/sh\nexit 0\n",
                                        encoding="utf-8")
        (self.bin / "flock").chmod(0o755)
        (self.bin / "crontab").write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" >> "$CRONTAB_CALLS"\n'
            'case "$1" in\n'
            '  -l) cat "$CRONTAB_FIXTURE";;\n'
            '  -)  cat > "$CRONTAB_FIXTURE";;\n'
            "  *) exit 0;;\n"
            "esac\n",
            encoding="utf-8")
        (self.bin / "crontab").chmod(0o755)
        backup_dir = self.hermes / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "crontab-known-good.txt").write_text(
            "*/5 * * * * /old/scripts/hermes-watchdog.sh\n"
            "*/2 * * * * /old/scripts/network-guard.sh\n",
            encoding="utf-8")

        env_extra = {
            "CRONTAB_FIXTURE": str(cron_fixture),
            "CRONTAB_CALLS": str(crontab_calls),
        }
        saved_env = {k: os.environ.get(k) for k in env_extra}
        os.environ.update(env_extra)
        try:
            result = self._run_auto_remediate()
        finally:
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(crontab_calls.exists(),
                         "auto-remediate не должен вызывать crontab")
        self.assertIn("operator-report", cron_fixture.read_text(encoding="utf-8"))
        self.assertIn("backup-tool", cron_fixture.read_text(encoding="utf-8"))




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

    def test_rr1a_cron_ownership_retirements(self) -> None:
        """RR1a: единственный writer расписания — deploy.sh (managed-блок);
        глобальная «<7 задач»-эвристика и whole-crontab восстановление сняты,
        ручная установка предложенных строк больше не предлагается."""
        deploy = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("# BEGIN HERMES-ARGUS", deploy)
        self.assertIn("reconcile_argus_cron", deploy)
        self.assertNotIn("grep -v '^#' $CRON_FILE) | awk", deploy)
        self.assertNotIn("ожидалось ≥7", (REPO / "scripts" / "health-check-integrations.sh")
                         .read_text(encoding="utf-8"))
        self.assertNotIn("CRON_COUNT", (REPO / "scripts" / "health-check-integrations.sh")
                         .read_text(encoding="utf-8"))
        auto = AUTO_REMEDIATE.read_text(encoding="utf-8")
        # ветка восстановления снята; упоминание файла в provenance-комментарии
        # допустимо — запрещены только исполняемые следы ветки
        self.assertNotIn('crontab "$CRON_BACKUP"', auto)
        self.assertNotIn("восстанавливаю из бэкапа", auto)
        self.assertNotIn("Crontab восстановлен", auto)

if __name__ == "__main__":
    unittest.main(verbosity=2)
