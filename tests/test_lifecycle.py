#!/usr/bin/env python3
"""C1-C8: local Git releases and fixture-owned host surfaces, no live services."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parent.parent


@unittest.skipUnless(sys.platform.startswith('linux'), 'isolated Linux lifecycle fixtures')
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='argus-lifecycle-')
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.seed = self.root / 'seed'
        self.remote = self.root / 'remote.git'
        self.checkout = self.home / 'hermes-argus'
        self.shim = self.root / 'bin'
        self.shim.mkdir()
        self.cron = self.root / 'crontab'
        self.cron.write_text('MAILTO=fixture\n# operator\n3 * * * * /operator-job\n')
        self.calls = self.root / 'systemctl-calls'
        self.metadata = self.root / 'release.json'
        self.scheduler = self.root / 'logrotate.d'
        self.scheduler.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'USERPROFILE': str(self.home),
                    'PATH': str(self.shim) + os.pathsep + os.environ['PATH'],
                    'LC_CRON': str(self.cron), 'LC_CALLS': str(self.calls),
                    'LC_METADATA': str(self.metadata), 'LOGROTATE_SCHED_DIR': str(self.scheduler),
                    'CRON_LOCK_FILE': str(self.root / 'cron.lock'),
                    'CRON_FILE': str(self.root / 'cron.proposal'),
                    'ARGUS_SKIP_EDIT': '1', 'GIT_TERMINAL_PROMPT': '0',
                    'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
                    'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
        for name in list(self.env):
            if name.startswith('MODULE_') or name in ('ARGUS_INSTALL_REEXEC', 'ARGUS_INSTALL_SHA'):
                self.env.pop(name)
        self.sh('dpkg', 'exit 0\n')
        self.sh('sudo', 'exit 99\n')
        self.sh('loginctl', "printf 'Linger=yes\\n'\n")
        self.sh('logrotate', 'exit 0\n')
        self.sh('curl', 'cat "$LC_METADATA"\n')
        self.sh('systemctl', '''printf '%s\n' "$*" >> "$LC_CALLS"
[ "${LC_FAIL_UNIT:-0}" != 1 ] || exit 9
[ "${1:-}" != --user ] || shift
case "${1:-}" in
  is-enabled|is-active) exit 1 ;;
  list-unit-files) [ ! -f "$HOME/.config/systemd/user/hermes-argus-config.path" ] || echo 'hermes-argus-config.path enabled enabled' ;;
esac
exit 0
''')
        self.sh('crontab', '''case "${1:-}" in
 -l) cat "$LC_CRON" ;;
 -) [ "${LC_FAIL_CRON:-0}" != 1 ] || exit 9; cat > "$LC_CRON" ;;
 *) exit 9 ;;
esac
''')
        hermes = self.home / '.hermes'
        (hermes / 'logs').mkdir(parents=True)
        (hermes / '.env').write_text('')
        venv = hermes / 'hermes-agent/venv/bin'
        venv.mkdir(parents=True)
        self.executable(venv / 'python', '#!/bin/sh\nexec ' + sys.executable + ' "$@"\n')
        self.executable(venv / 'hermes', '#!/bin/sh\necho Hermes-fixture\n')
        shutil.copytree(REPO, self.seed, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', 'config.env'))
        # Windows mounts may expose every source file as executable. Git's
        # actual config template is 0644; don't manufacture a 0700 config copy.
        (self.seed / 'config/config.env.template').chmod(0o644)
        installer = self.seed / 'install.sh'
        installer.write_text(installer.read_text().replace('https://github.com/upmeister/hermes-argus.git', str(self.remote)))
        # Older legitimate generated content differs from the update target.
        deploy = self.seed / 'deploy.sh'
        deploy.write_text(deploy.read_text().replace('    rotate 7\n', '    rotate 6\n'))
        self.git(self.seed, 'init', '-q', '-b', 'main')
        self.git(self.seed, 'add', '.')
        self.git(self.seed, 'commit', '-qm', 'first lifecycle')
        self.v1 = self.git(self.seed, 'rev-parse', 'HEAD').stdout.strip()
        self.git(self.seed, 'tag', 'v0.1.0')
        deploy.write_text(deploy.read_text().replace('    rotate 6\n', '    rotate 7\n'))
        patterns = self.seed / 'scripts/health_patterns.py'
        patterns.write_text(patterns.read_text() + '\n# selected-tree-v2\n')
        installer.write_text(installer.read_text().replace('cd "$REPO_DIR"\n', 'cd "$REPO_DIR"\necho C_SELECTED_TREE_V2\n'))
        (self.seed / 'new-in-target.txt').write_text('target content\n')
        self.git(self.seed, 'add', '.')
        self.git(self.seed, 'commit', '-qm', 'second lifecycle')
        self.v2 = self.git(self.seed, 'rev-parse', 'HEAD').stdout.strip()
        self.git(self.seed, 'tag', 'v0.2.0-rc.1')
        self.git(self.root, 'clone', '-q', '--bare', str(self.seed), str(self.remote))
        self.release('v0.1.0')

    def tearDown(self):
        self.tmp.cleanup()

    def executable(self, path, text):
        path.write_text(text)
        path.chmod(0o755)

    def sh(self, name, text):
        self.executable(self.shim / name, '#!/bin/bash\n' + text)

    def git(self, cwd, *args, check=True):
        result = subprocess.run(['git', '-C', str(cwd), *args], env=self.env,
                                capture_output=True, text=True, timeout=30)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def release(self, tag):
        self.metadata.write_text(json.dumps({'tag_name': tag, 'draft': False, 'prerelease': False}))

    def config(self, analyzer=True):
        enabled = {'CORE', 'INTEGRATIONS'}
        if analyzer:
            enabled.add('ANALYZER')
        cfg = ''.join(f'MODULE_{m}={"ON" if m in enabled else "OFF"}\n' for m in
                      ['CORE', 'INTEGRATIONS', 'ANALYZER', 'TG_BOT', 'HEARTBEAT',
                       'GH_HEARTBEAT', 'DISCORD_BOT', 'LOCAL_SERVICES', 'NETWORK_GUARD'])
        cfg += 'WATCHDOG_BOT_TOKEN=ARGUS_C_CANARY\nWATCHDOG_CHAT_ID=fixture\n'
        path = self.checkout / 'config.env'
        path.write_text(cfg)
        path.chmod(0o600)
        return path

    def install(self, *args, env=None):
        return subprocess.run(['bash', str(self.seed / 'install.sh'), *args], env=env or self.env,
                              capture_output=True, text=True, timeout=180)

    def bootstrap(self, *args, analyzer=True):
        first = self.install(*args)
        self.assertNotEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertTrue((self.checkout / 'config.env').is_file(), first.stdout + first.stderr)
        self.assertEqual((self.checkout / 'config.env').stat().st_mode & 0o777, 0o600)
        self.config(analyzer)
        result = self.install(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def uninstall(self, apply=False, env=None):
        return subprocess.run(['bash', str(self.checkout / 'uninstall.sh'), *(['--apply'] if apply else [])],
                              env=env or self.env, capture_output=True, text=True, timeout=120)

    def runtime(self):
        result = {'cron': self.cron.read_bytes()}
        for root in [self.home / 'scripts', self.home / '.hermes/scripts',
                     self.home / '.config/systemd/user', self.scheduler]:
            if root.exists():
                for p in root.rglob('*'):
                    if p.is_file():
                        result[str(p)] = (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode & 0o777)
        return result

    def test_c1_stable_rc_edge_exact_tree(self):
        result = self.bootstrap()
        self.assertEqual(self.git(self.checkout, 'rev-parse', 'HEAD').stdout.strip(), self.v1)
        self.assertNotIn('C_SELECTED_TREE_V2', result.stdout)
        result = self.install('--version', 'v0.2.0-rc.1')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('C_SELECTED_TREE_V2', result.stdout)
        self.assertEqual(self.git(self.checkout, 'rev-parse', 'HEAD').stdout.strip(), self.v2)
        self.assertIn('selected-tree-v2', (self.home / '.hermes/scripts/health_patterns.py').read_text())
        result = self.install('--channel', 'edge')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(self.v2, result.stdout)

    def test_c2_bad_release_and_tag_no_runtime_writes(self):
        before = self.runtime()
        for metadata in ['{}', '{bad', json.dumps({'tag_name': 'v0.2.0-rc.1', 'draft': False, 'prerelease': True})]:
            self.metadata.write_text(metadata)
            self.assertNotEqual(self.install().returncode, 0)
            self.assertEqual(self.runtime(), before)
        self.sh('curl', 'exit 7\n')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.runtime(), before)
        self.sh('curl', 'cat "$LC_METADATA"\n')
        self.release('no-such-tag')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.runtime(), before)
        self.assertNotEqual(self.install('--version', '../bad').returncode, 0)
        self.assertNotEqual(self.install('--channel', 'edge', '--version', 'v0.1.0').returncode, 0)

    def test_c3_rerun_upgrade_old_source_ownership(self):
        self.bootstrap()
        operator = self.cron.read_bytes().split(b'# BEGIN HERMES-ARGUS')[0]
        config = (self.checkout / 'config.env').read_bytes()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.cron.read_text().count('# BEGIN HERMES-ARGUS'), 1)
        self.assertEqual((self.checkout / 'config.env').read_bytes(), config)
        result = self.install('--channel', 'edge')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.cron.read_bytes().split(b'# BEGIN HERMES-ARGUS')[0], operator)
        self.assertIn('rotate 7', (self.scheduler / 'argus').read_text())
        self.assertIn('selected-tree-v2', (self.home / '.hermes/scripts/health_patterns.py').read_text())

    def test_c3_nondefault_modules(self):
        self.bootstrap('--channel', 'edge', analyzer=False)
        self.assertFalse((self.home / '.hermes/scripts/health-analyzer.py').exists())
        result = self.install('--channel', 'edge')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_c4_dirty_collision_remote_and_divergence(self):
        self.bootstrap()
        before = self.runtime()
        readme = self.checkout / 'README.md'
        original = readme.read_text()
        readme.write_text(original + '\nuser edit\n')
        self.assertNotEqual(self.install('--channel', 'edge').returncode, 0)
        self.assertEqual(self.runtime(), before)
        readme.write_text(original)
        collision = self.checkout / 'new-in-target.txt'
        collision.write_text('user data\n')
        self.assertNotEqual(self.install('--channel', 'edge').returncode, 0)
        self.assertEqual(collision.read_text(), 'user data\n')
        self.assertEqual(self.runtime(), before)
        collision.unlink()
        self.git(self.checkout, 'remote', 'set-url', 'origin', str(self.seed))
        self.assertNotEqual(self.install('--channel', 'edge').returncode, 0)
        self.assertEqual(self.runtime(), before)
        self.git(self.checkout, 'remote', 'set-url', 'origin', str(self.remote))
        self.git(self.checkout, 'checkout', '-qb', 'local-work')
        (self.checkout / 'operator.txt').write_text('user branch\n')
        self.git(self.checkout, 'add', 'operator.txt')
        self.git(self.checkout, 'commit', '-qm', 'user commit')
        self.assertNotEqual(self.install('--channel', 'edge').returncode, 0)
        self.assertEqual(self.runtime(), before)
        self.git(self.checkout, 'checkout', '--detach')
        self.assertNotEqual(self.install('--channel', 'edge').returncode, 0)
        self.assertEqual(self.runtime(), before)

    def test_c6_fresh_install_preserves_foreign_runtime(self):
        script = self.home / 'scripts/hermes-watchdog.sh'
        script.parent.mkdir()
        self.executable(script, '#!/bin/sh\necho operator-owned\n')
        before = self.runtime()
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual(self.runtime(), before)

    def test_c4_implicit_and_explicit_downgrade(self):
        self.bootstrap('--version', 'v0.2.0-rc.1')
        before = self.runtime()
        refused = self.install()
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.runtime(), before)
        result = self.install('--version', 'v0.1.0')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Intentional downgrade', result.stdout)
        self.assertEqual(self.git(self.checkout, 'rev-parse', 'HEAD').stdout.strip(), self.v1)

    def test_c5_plan_apply_repeat_preserves_hermes_and_external(self):
        units = self.home / '.config/systemd/user'
        units.mkdir(parents=True)
        for name in ['hermes-gateway.service', 'hermes-dashboard.service']:
            (units / name).write_text('operator-owned Hermes base\n')
        self.bootstrap()
        foreign = self.home / 'scripts/foreign-sentinel'
        foreign.write_text('keep\n')
        state = self.home / '.hermes/state/foreign.json'
        state.write_text('{"keep":true}\n')
        before = self.runtime()
        calls_before = self.calls.read_bytes()
        plan = self.uninstall()
        self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
        self.assertEqual(self.runtime(), before)
        self.assertEqual(self.calls.read_bytes(), calls_before)
        result = self.uninstall(True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.cron.read_text(), 'MAILTO=fixture\n# operator\n3 * * * * /operator-job\n')
        self.assertTrue(foreign.exists() and state.exists())
        self.assertTrue((self.checkout / 'config.env').exists())
        self.assertTrue((self.home / '.hermes/scripts/health-check-integrations.sh').exists())
        for name in ['hermes-gateway.service', 'hermes-dashboard.service']:
            self.assertEqual((units / name).read_text(), 'operator-owned Hermes base\n')
        self.assertNotIn('disable --now hermes-gateway', self.calls.read_text())
        self.assertNotIn('disable --now hermes-dashboard', self.calls.read_text())
        self.assertFalse((units / 'hermes-gateway.service.d/memory-limits.conf').exists())
        self.assertFalse((self.scheduler / 'argus').exists())
        once = self.runtime()
        self.assertEqual(self.uninstall(True).returncode, 0)
        self.assertEqual(self.runtime(), once)

    def test_c6_custom_files_disabled_old_module_stop_without_clobber(self):
        self.bootstrap()
        custom = self.home / '.hermes/scripts/health-analyzer.py'
        custom.write_text(custom.read_text() + '\n# operator custom\n')
        self.config(analyzer=False)
        before = self.runtime()
        plan = self.uninstall()
        self.assertNotEqual(plan.returncode, 0)
        self.assertIn(str(custom), plan.stdout)
        self.assertIn('RETAIN changed/ambiguous', plan.stdout)
        self.assertNotEqual(self.uninstall(True).returncode, 0)
        self.assertEqual(self.runtime(), before)
        # Disabled custom payload is preserved during an update, not overwritten.
        self.assertEqual(self.install('--channel', 'edge').returncode, 0)
        self.assertIn('# operator custom', custom.read_text())

    def test_c6_changed_enabled_payload_refuses_update_before_checkout(self):
        self.bootstrap()
        custom = self.home / '.hermes/scripts/health-check-integrations.sh'
        custom.write_text(custom.read_text() + '\n# operator custom\n')
        before = self.runtime()
        result = self.install('--channel', 'edge')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.runtime(), before)
        self.assertEqual(self.git(self.checkout, 'rev-parse', 'HEAD').stdout.strip(), self.v1)

    def test_c6_modified_unit_policy_and_executable_permissions(self):
        self.bootstrap()
        paths = [self.home / '.config/systemd/user/hermes-argus-config.path',
                 self.scheduler / 'argus']
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b'\n# operator customization\n')
                before = self.runtime()
                self.assertNotEqual(self.uninstall(True).returncode, 0)
                self.assertEqual(self.runtime(), before)
                path.write_bytes(original)
        script = self.home / '.hermes/scripts/health-analyzer.py'
        mode = script.stat().st_mode & 0o777
        script.chmod(0o600)
        before = self.runtime()
        self.assertNotEqual(self.uninstall(True).returncode, 0)
        self.assertEqual(self.runtime(), before)
        script.chmod(mode)

    def test_c7_malformed_block_no_partial_mutation(self):
        self.bootstrap()
        self.cron.write_text(self.cron.read_text() + '# BEGIN HERMES-ARGUS\n')
        before = self.runtime()
        self.assertNotEqual(self.uninstall(True).returncode, 0)
        self.assertEqual(self.runtime(), before)

    def test_c7_legacy_schedule_adoption_and_legacy_unit_retention(self):
        self.bootstrap()
        operator = 'MAILTO=fixture\n# operator\n3 * * * * /operator-job\n'
        legacy_job = f'*/5 * * * * python3 {self.home}/scripts/fallback-tracker-v2.py >> {self.home}/.hermes/logs/fallback-tracker-v2.log 2>&1\n'
        self.cron.write_text(operator + legacy_job)
        before = self.runtime()
        self.assertNotEqual(self.uninstall(True).returncode, 0)
        self.assertEqual(self.runtime(), before)
        adopted = self.install('--version', 'v0.1.0')
        self.assertEqual(adopted.returncode, 0, adopted.stdout + adopted.stderr)
        self.assertTrue(self.cron.read_text().startswith(operator + '# BEGIN HERMES-ARGUS\n'))
        legacy_unit = self.home / '.config/systemd/user/hermes-vps-kit-config.path'
        legacy_unit.write_text('legacy operator unit\n')
        before = self.runtime()
        self.assertNotEqual(self.uninstall(True).returncode, 0)
        self.assertEqual(self.runtime(), before)

    def test_c8_failed_uninstall_reports_partial_not_completion(self):
        self.bootstrap()
        before = self.runtime()
        result = self.uninstall(True, env={**self.env, 'LC_FAIL_UNIT': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Uninstall complete', result.stdout)
        self.assertEqual(self.runtime(), before)
        result = self.uninstall(True, env={**self.env, 'LC_FAIL_CRON': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Uninstall complete', result.stdout)
        self.assertEqual(self.runtime(), before)

    def test_c8_checkout_and_deploy_failure_are_not_completion(self):
        self.bootstrap()
        before = self.runtime()
        real_git = shutil.which('git')
        self.sh('git', 'for arg in "$@"; do [ "$arg" != checkout ] || exit 71; done\nexec ' + real_git + ' "$@"\n')
        failed = self.install('--channel', 'edge')
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(self.runtime(), before)
        (self.shim / 'git').unlink()
        (self.seed / 'scripts/health-check-v2.py').write_text('if invalid syntax\n')
        self.git(self.seed, 'add', '.')
        self.git(self.seed, 'commit', '-qm', 'broken deploy fixture')
        self.git(self.seed, 'push', '-q', str(self.remote), 'main')
        failed = self.install('--channel', 'edge')
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('runtime may be partial', failed.stderr)
        self.assertNotIn('payload: проверен', failed.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
