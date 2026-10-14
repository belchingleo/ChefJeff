"""Result card to next round in one step, without clearing the player configuration."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from hosted_server import FIELDS
from player_api import PlayerGameSession
from spatial_kitchen import SpatialKitchen
from test_web import FakeJournal
from test_jev import NoKeyClient


class PlayFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.g=PlayerGameSession(credential_path=Path(self.tmp.name)/'settings.json',
            kitchen_factory=SpatialKitchen,journal_factory=FakeJournal,
            connector=lambda c,s:NoKeyClient(c))
        self.addCleanup(self.g.close)
        self.g.setting={'provider':'compatible','model':'SECRET_SENTINEL','api_key':'SECRET_SENTINEL'}
    def cmd(self,path,**data):
        return self.g.command('/api/'+path,{'game_id':self.g.game_id,'request_id':uuid.uuid4().hex,**data})
    def close_round(self,money):
        """What the tick does at closing time."""
        self.g.k.money=money;self.g.k.ended=True;self.g.phase='ended';self.g._finish()

    def test_next_needs_a_finished_round_and_starts_the_chosen_level_at_the_same_speed(self):
        self.assertEqual(self.cmd('next',level='level-2')[0],409)
        self.assertEqual(self.cmd('start',speed=.5)[0],200)
        self.assertEqual(self.cmd('next',level='level-2')[0],409)
        self.close_round(999);first=self.g.game_id
        self.assertEqual(self.cmd('next',level='level-9')[0],400)
        self.assertEqual((self.g.phase,self.g.game_id),('ended',first))
        self.assertEqual(self.cmd('next',level='level-2')[0],200)
        self.assertEqual((self.g.phase,self.g.c['level_id'],self.g.speed),('running','level-2',.5))
        self.assertNotEqual(self.g.game_id,first);self.assertIsNotNone(self.g.journal)

    def test_next_without_a_connection_keeps_the_result_card(self):
        self.cmd('start');self.close_round(0);self.g.setting=None
        self.assertEqual(self.cmd('next',level='level-1')[0],428)
        self.assertEqual(self.g.phase,'ended')

    def test_hosted_allows_next_with_only_a_level(self):
        self.assertEqual(FIELDS['/api/next'],{'level'})


if __name__ == '__main__':
    unittest.main()
