"""Verify failed deployments restore the running release and proxy configuration."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from deploy import update_hetzner as update
from deploy import set_kitchen_capacity as capacity


class UpdateTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        old, new = root / 'old', root / 'new'
        old.mkdir()
        (new / 'deploy').mkdir(parents=True)
        (new / 'deploy/nginx-https.conf').write_text('new proxy')
        current = root / 'current'
        current.symlink_to(old)
        site = root / 'chefjeff.conf'
        site.write_text('old proxy')
        return old, new, current, site

    def test_health_failure_rolls_back_release_and_proxy(self):
        old, new, current, site = self.fixture()
        with patch.object(update, 'run') as run, patch.object(update, 'health', side_effect=RuntimeError('Unhealthy')):
            with self.assertRaisesRegex(RuntimeError, 'Unhealthy'):
                update.install(new, current, site)
        self.assertEqual(current.resolve(), old)
        self.assertEqual(site.read_text(), 'old proxy')
        self.assertEqual(sum(c.args == ('systemctl', 'restart', 'chefjeff.service') for c in run.call_args_list), 2)

    def test_invalid_proxy_never_restarts_backend(self):
        old, new, current, site = self.fixture()
        with patch.object(update, 'run', side_effect=[subprocess.CalledProcessError(1, 'nginx'), None, None]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                update.install(new, current, site)
        self.assertEqual(current.resolve(), old)
        self.assertEqual(site.read_text(), 'old proxy')
        self.assertFalse(any(c.args[:2] == ('systemctl', 'restart') for c in run.call_args_list))

    def test_success_keeps_old_release_for_rollback(self):
        old, new, current, site = self.fixture()
        with patch.object(update, 'run') as run, patch.object(update, 'health') as health:
            update.install(new, current, site)
        health.assert_called_once()
        self.assertEqual(current.resolve(), new)
        self.assertTrue(old.is_dir())
        self.assertEqual(site.read_text(), 'new proxy')
        self.assertEqual(run.call_args_list[-1].args, ('systemctl', 'reload', 'nginx'))


class CapacityUpdateTests(unittest.TestCase):
    unit = '/usr/bin/python3 /opt/chefjeff/current/hosted_server.py --port 8780 --origin https://chefjeff.belchingleo.online --max-sessions 2 --data-dir /var/lib/chefjeff'

    def test_verified_change_preserves_other_unit_settings(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);old=root/'hetzner.conf';old.write_text('MemoryMax=512M\n')
            dropin=root/'zz-chefjeff-capacity.conf'
            states=[{'capacity':{'limit':2,'session_limit':34}},{'capacity':{'limit':8,'session_limit':40}}]
            with patch.object(capacity,'read_metrics',side_effect=states),patch.object(capacity,'run') as run,patch.object(capacity.subprocess,'check_output',return_value=self.unit):
                capacity.apply(8,dropin)
            self.assertEqual(old.read_text(),'MemoryMax=512M\n')
            self.assertIn('--max-sessions 8 --max-waiting 32',dropin.read_text())
            self.assertEqual(run.call_args_list[-1].args,('systemctl','restart','chefjeff.service'))

    def test_waiting_pages_can_change_with_the_same_limit(self):
        with tempfile.TemporaryDirectory() as td:
            dropin=Path(td)/'zz-chefjeff-capacity.conf'
            states=[{'capacity':{'limit':8,'session_limit':24}},{'capacity':{'limit':8,'session_limit':40}}]
            with patch.object(capacity,'read_metrics',side_effect=states),patch.object(capacity,'run'),patch.object(capacity.subprocess,'check_output',return_value=self.unit):
                capacity.apply(8,dropin,waiting=32)
            self.assertIn('--max-sessions 8 --max-waiting 32',dropin.read_text())
            with patch.object(capacity,'read_metrics',return_value={'capacity':{'limit':8,'session_limit':40}}),patch.object(capacity,'run') as run:
                capacity.apply(8,dropin,waiting=32)
            run.assert_not_called()
            with self.assertRaises(ValueError):capacity.apply(8,dropin,waiting=33)

    def test_failed_change_restores_exact_previous_override(self):
        with tempfile.TemporaryDirectory() as td:
            dropin=Path(td)/'capacity.conf';dropin.write_bytes(b'old reviewed command\n')
            states=[{'capacity':{'limit':2,'session_limit':34}}]
            states.extend([OSError('not ready')]*30)
            with patch.object(capacity,'read_metrics',side_effect=states),patch.object(capacity,'run') as run,patch.object(capacity.subprocess,'check_output',return_value=self.unit),patch.object(capacity.time,'sleep'):
                with self.assertRaisesRegex(RuntimeError,'does not match'):capacity.apply(8,dropin)
            self.assertEqual(dropin.read_bytes(),b'old reviewed command\n')
            self.assertEqual(sum(c.args==('systemctl','restart','chefjeff.service') for c in run.call_args_list),2)
