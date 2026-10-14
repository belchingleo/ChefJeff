"""Verify failed deployments restore the running release and proxy configuration."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from deploy import update_hetzner as update


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
