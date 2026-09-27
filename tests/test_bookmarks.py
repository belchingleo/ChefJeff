"""Bookmarks annotate logs without becoming gameplay or model input."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
from player_api import PlayerGameSession
from spatial_kitchen import SpatialKitchen
from test_web import FakeJournal
from test_jev import NoKeyClient

class BookmarkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.g=PlayerGameSession(credential_path=Path(self.tmp.name)/'settings.json',
            kitchen_factory=SpatialKitchen,journal_factory=FakeJournal,
            connector=lambda c,s:NoKeyClient(c))
        self.addCleanup(self.g.close)
        self.g.setting={'provider':'compatible','model':'SECRET_SENTINEL','api_key':'SECRET_SENTINEL'}
    def cmd(self,path,**data):
        return self.g.command('/api/'+path,{'game_id':self.g.game_id,'request_id':uuid.uuid4().hex,**data})
    def start(self):self.assertEqual(self.cmd('start')[0],200)
    def mark(self,clock,game_time):
        self.g.k.time=game_time
        with patch('web_server.time.monotonic',return_value=clock):return self.cmd('bookmark')
    def test_rolling_merge_real_clock_and_log_snapshots(self):
        self.start();log=self.g.journal
        a=self.mark(100,1)[1];b=self.mark(105,3)[1];c=self.mark(110,4)[1];d=self.mark(115.001,5)[1]
        self.assertFalse(a['merged']);self.assertTrue(b['merged']);self.assertTrue(c['merged']);self.assertFalse(d['merged'])
        self.assertEqual([v['press_count'] for v in self.g.bookmarks],[3,1])
        self.assertEqual(self.g.bookmarks[0]['start_game_time'],1)
        self.assertEqual(self.g.bookmarks[0]['end_game_time'],4)
        self.assertIsNotNone(datetime.fromisoformat(a['bookmark']['start_wall_time']).tzinfo)
        rows=[v for k,v in log.rows if k=='bookmark']
        self.assertEqual([r['operation'] for r in rows],['create','extend','extend','create'])
        self.assertEqual(rows[0]['bookmark']['press_count'],1)
        folded={r['bookmark']['id']:r['bookmark'] for r in rows}
        self.assertEqual(list(folded.values()),self.g.bookmarks)
    def test_annotation_does_not_interrupt_or_change_model_observation(self):
        self.start();g=self.g
        action=next(a for a in g.k.actions('human') if a.key=='fetch')
        g.k.start('human',action)
        before=deepcopy(g.k.snapshot());events=deepcopy(g.k.events);epoch=g.ai.epoch
        timing=(g.last_tick,g.last_seen,g.move_until,g.speed)
        with patch.object(g.ai,'poll') as poll,patch.object(g.ai,'invalidate') as invalidate:
            self.assertEqual(self.cmd('bookmark')[0],200)
            poll.assert_not_called();invalidate.assert_not_called()
        self.assertEqual(g.k.snapshot(),before);self.assertEqual(g.k.events,events)
        self.assertEqual(g.ai.epoch,epoch);self.assertEqual(g.phase,'running')
        self.assertEqual((g.last_tick,g.last_seen,g.move_until,g.speed),timing)
        with patch.object(g.ai,'poll'):g.tick(g.last_tick+.1)
        self.assertGreater(g.k.time,before['time'])
    def test_request_dedup_and_stale_round(self):
        self.start();body={'game_id':self.g.game_id,'request_id':'same'}
        first=self.g.command('/api/bookmark',body)
        self.assertEqual(self.g.command('/api/bookmark',body),first)
        self.assertEqual(self.g.bookmarks[0]['press_count'],1)
        self.assertEqual(self.cmd('bookmark',game_id='old')[0],409)
        self.assertEqual(self.cmd('bookmark',request_id='')[0],400)
    def test_lifecycle_export_retains_all_marks_and_reset_isolates(self):
        self.assertEqual(self.cmd('bookmark')[0],409);self.start();self.mark(10,1)
        for _ in range(100):self.g.k.emit('private note',kind='action_done',actor='human',action='fetch')
        self.cmd('pause');self.assertEqual(self.cmd('bookmark')[0],409)
        log=self.g.journal;self.cmd('end');self.assertEqual(self.cmd('bookmark')[0],409)
        report=self.cmd('export-run')[1]['report']
        self.assertEqual(len(report['recent_events']),80);self.assertEqual(report['bookmarks'],self.g.bookmarks)
        self.assertNotIn('SECRET_SENTINEL',json.dumps(report));self.assertNotIn('private note',json.dumps(report))
        self.assertEqual(report['bookmarks'],[r for k,r in log.rows if k=='end'][0]['bookmarks'])
        report['bookmarks'].clear();self.assertEqual(len(self.g.bookmarks),1)
        self.cmd('reset');self.assertEqual(self.g.bookmarks,[]);self.assertIsNone(self.g.last_bookmark_at)
    def test_failed_log_write_reports_failure_and_does_not_commit(self):
        self.start();log=self.g.journal
        def broken(*args):raise OSError('disk unavailable')
        self.g.journal=broken
        try:
            self.assertEqual(self.cmd('bookmark')[0],503)
            self.assertEqual(self.g.bookmarks,[]);self.assertEqual(self.g.phase,'running')
        finally:self.g.journal=log
