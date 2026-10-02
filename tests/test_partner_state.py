import unittest
from kitchen import Food, load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient


class PartnerStateTests(unittest.TestCase):
    def test_jev_receives_players_real_position_hand_job_and_remaining_time(self):
        k=SpatialKitchen(load_config());client=SpatialJevClient(k.c,key='test-only')
        k.chefs['human'].hand=Food('player-meat','chopped',6,0)
        k.command('human','put p1');k.advance(min(.1,k.chefs['human'].job.travel/2))
        p=client.payload(k.snapshot(),k.actions('jeff'))['state']
        h=p['kitchen']['chefs']['human']
        self.assertEqual(h['holding']['id'],'player-meat')
        self.assertEqual(h['target'],'p1');self.assertIn('Put chopped beef into the frying pan',h['task'])
        self.assertGreater(h['travel_remaining'],0);self.assertGreater(h['work_remaining'],0)
        self.assertNotEqual(h['position'],[2.,2.])
        self.assertIn('position',p['rules']['partner'])
        before=h['position'];k.command('human','go b2');k.advance(min(.1,k.chefs['human'].job.travel/2))
        changed=client.payload(k.snapshot(),k.actions('jeff'))['state']['kitchen']['chefs']['human']
        self.assertNotEqual(changed['position'],before);self.assertEqual(changed['target'],'b2')
        self.assertEqual(changed['holding']['id'],'player-meat')
