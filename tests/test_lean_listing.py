"""The faster request build (2026-11-28): note forks list without throws (links.LEAN, kitchen.throw_listing) and are
copied with pickle (links._copy), and the clients share one TLS setup (tls_context). None of it may change a request.

The payload switch net (tests/payload_fingerprint.py) checks the release as built; these tests build the same
requests with the speed-ups off and on, and show the check would catch the version that also left throws out of a
throw step (one_press.find), which changed most level-4 requests in which Jeff holds raw beef."""
from __future__ import annotations

import copy
import pickle
import sys
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kitchen  # noqa: E402
import links  # noqa: E402
import one_press  # noqa: E402
import payload_fingerprint as pf  # noqa: E402
import spatial_kitchen  # noqa: E402
import tls_context  # noqa: E402
from kitchen import load_config  # noqa: E402
from levels import level_config  # noqa: E402

# (level, switch set): level 4 with the partner line (release) and with the separate table's partner lines, level 5.
CASES = (('level-4', 'release'), ('level-4', 'release-partner-links'), ('level-5', 'release'))


def build(level, name, lean, pickled):
    """The switch net's requests with throws left out of the note forks (lean) or not, and the forks copied with
    pickle (pickled) or with deepcopy, as before 2026-11-28. (links.FAST stays on: plain forks also carry out walks,
    links-v1, and give walks link lines the release does not.)"""
    pf._PLAYED.clear()
    with patch.object(links, 'LEAN', lean), patch.object(links, '_copy', links._copy if pickled else copy.deepcopy):
        return pf.switch_run(level, name)


class SameRequestsTests(unittest.TestCase):
    def test_the_speed_ups_leave_every_request_as_it_was(self):
        for level, name in CASES:
            with self.subTest(level=level, set=name):
                full = build(level, name, lean=False, pickled=False)
                fast = build(level, name, lean=True, pickled=True)
                for a, b in zip(full['windows'], fast['windows']):
                    self.assertEqual(a['requests'], b['requests'], f"window from {a['start']} s")
                self.assertEqual(full['digest'], fast['digest'])

    def test_a_throw_step_found_without_throws_would_show(self):
        """The net reaches throw_to options with link lines: leaving throws out of one_press.find too changes
        level-4 requests (that is why find lists them for a throw step)."""
        full = build('level-4', 'release', lean=False, pickled=False)
        pf._PLAYED.clear()
        with patch.object(one_press, 'find', one_press._find):
            naive = pf.switch_run('level-4', 'release')
        changed = sum(a != b for wa, wb in zip(full['windows'], naive['windows'])
                      for a, b in zip(wa['requests'], wb['requests']))
        self.assertGreater(changed, 0)


def played(level, seconds):
    k, _ = pf.played(level, seconds)
    return k.fork()


class ListingScopeTests(unittest.TestCase):
    def setUp(self):
        # Level 4 at 1.1 s: Jeff holds raw beef, with throws to every direction and throw_to options.
        self.k = played('level-4', 1.1)
        self.assertIsNotNone(self.k.chefs['jeff'].hand)

    def throws(self):
        return [a.key for a in self.k.actions('jeff') if a.kind == 'throw']

    def test_the_scope_leaves_throws_out_and_puts_them_back(self):
        listed = self.throws()
        self.assertTrue(listed)
        with kitchen.throw_listing(False):
            self.assertEqual(self.throws(), [])
            with kitchen.throw_listing(True):
                self.assertEqual(self.throws(), listed)
            self.assertEqual(self.throws(), [])
        self.assertEqual(self.throws(), listed)
        others = lambda: [a.key for a in self.k.actions('jeff') if a.kind != 'throw']
        before = others()
        with kitchen.throw_listing(False):
            self.assertEqual(others(), before)

    def test_the_scope_is_this_threads_only(self):
        listed, seen = self.throws(), []
        with kitchen.throw_listing(False):
            worker = threading.Thread(target=lambda: seen.append(self.throws()))
            worker.start()
            worker.join()
        self.assertEqual(seen, [listed])

    def test_a_fork_still_throws_without_throws_listed(self):
        throw = next(a for a in self.k.actions('jeff') if a.kind == 'throw')
        with kitchen.throw_listing(False):
            started = self.k.start('jeff', throw)
        self.assertTrue(started[0] if isinstance(started, tuple) else started)

    def test_a_table_leaves_the_game_listing_throws(self):
        actions = self.k.actions('jeff')
        links.table(self.k, 'jeff', actions, [a.key for a in actions], partner=True)
        self.assertTrue(kitchen.throws_listed())
        self.assertTrue(self.throws())


class PickleCopyTests(unittest.TestCase):
    """links._copy makes what deepcopy makes, and does not fall back to deepcopy on the game's kitchens."""

    def test_pickle_and_deepcopy_forks_play_on_alike(self):
        for level, seconds in (('level-1', 20), ('level-2', 50), ('level-3', 40), ('level-4', 31), ('level-5', 110)):
            with self.subTest(level=level):
                k = played(level, seconds)
                with patch.object(copy, 'deepcopy', side_effect=AssertionError('fell back to deepcopy')):
                    fast = k.fork(copy=links._copy)
                plain = k.fork()
                self.assertEqual(fast.snapshot(), plain.snapshot())
                for twin in (fast, plain):
                    for _ in range(100):
                        twin.advance(.05)
                self.assertEqual(fast.snapshot(), plain.snapshot())
                self.assertEqual([e for e in fast.events], [e for e in plain.events])
                self.assertEqual(k.snapshot(), played(level, seconds).snapshot())    # the kitchen is untouched

    def test_a_value_pickle_cannot_write_falls_back(self):
        k = spatial_kitchen.SpatialKitchen(level_config(load_config(), 'level-1'))
        k.unpicklable = lambda: None
        twin = links._copy(k)
        self.assertIs(twin.unpicklable, k.unpicklable)      # deepcopy keeps functions as they are


def urllib_own_context():
    """The context urllib's default HTTPS handler made for each opener before, on this Python."""
    import http.client
    made = urllib.request.HTTPSHandler()._context              # 3.12+ makes it here
    if made is None:                                            # 3.10/3.11: HTTPSConnection makes it
        made = http.client.HTTPSConnection('example.invalid')._context
    return made


class SharedTlsTests(unittest.TestCase):
    def setUp(self):
        tls_context.forget()

    def test_one_context_each_made_as_before(self):
        self.assertIs(tls_context.context(), tls_context.context())
        self.assertIs(tls_context.urllib_context(), tls_context.urllib_context())
        import ssl
        for shared, own in ((tls_context.urllib_context(), urllib_own_context()),
                            (tls_context.context(), ssl.create_default_context())):
            for name in ('verify_mode', 'check_hostname', 'options', 'minimum_version', 'maximum_version',
                         'post_handshake_auth', 'verify_flags', 'protocol'):
                self.assertEqual(getattr(shared, name), getattr(own, name), name)
            self.assertEqual(shared.cert_store_stats(), own.cert_store_stats())
        self.assertIs(tls_context.https_handler()._context, tls_context.urllib_context())

    def test_the_store_is_read_again_after_a_lifetime_or_a_failed_verification(self):
        import ssl
        import urllib.error
        first = tls_context.urllib_context()
        with patch.object(tls_context.time, 'monotonic', lambda: tls_context._made['urllib'][1] + tls_context.LIFETIME):
            later = tls_context.urllib_context()
        self.assertIsNot(later, first)
        failure = urllib.error.URLError(ssl.SSLCertVerificationError(1, 'certificate verify failed'))
        handler = tls_context.https_handler()
        with patch.object(urllib.request.HTTPSHandler, 'https_open', side_effect=failure):
            with self.assertRaises(urllib.error.URLError):
                handler.https_open(urllib.request.Request('https://example.invalid/'))
        self.assertIsNot(tls_context.urllib_context(), later)
        kept = tls_context.urllib_context()
        with patch.object(urllib.request.HTTPSHandler, 'https_open',
                          side_effect=urllib.error.URLError(ConnectionRefusedError())):
            with self.assertRaises(urllib.error.URLError):
                tls_context.https_handler().https_open(urllib.request.Request('https://example.invalid/'))
        self.assertIs(tls_context.urllib_context(), kept)        # other failures keep it

    def test_the_openers_use_the_shared_handler(self):
        """Every opener built per request gets the shared HTTPS handler in place of a new default one."""
        handler = tls_context.https_handler()
        opener = urllib.request.build_opener(pf.hosted_jev.NoRedirect(), handler)
        https = [h for h in opener.handlers if isinstance(h, urllib.request.HTTPSHandler)]
        self.assertEqual(https, [handler])

    def test_each_client_passes_it(self):
        import inspect
        import free_model_client
        import hosted_cloudflare
        import hosted_free_models
        import hosted_jev
        import player_api
        import shared_client
        for module in (player_api, hosted_jev, hosted_cloudflare, hosted_free_models):
            source = inspect.getsource(module)
            self.assertNotIn('build_opener(NoRedirect)', source.replace('build_opener(NoRedirect,', ''))
            self.assertEqual(source.count('build_opener('), source.count('tls_context.https_handler()'), module.__name__)
        for module in (free_model_client, shared_client):
            source = inspect.getsource(module)
            self.assertNotIn('create_default_context', source)
            self.assertIn("options['context'] = tls_context.context()", source)


if __name__ == '__main__':
    unittest.main()
