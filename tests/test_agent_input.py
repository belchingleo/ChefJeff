"""What Jeff receives: plain ASCII English, chefs named by state key, no duplicate candidates."""
import json
import unittest
from unittest.mock import patch

import config_contract as cc
from cooperation_memory import episode, round_scope
from jev import DecisionLoop
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient, model_candidates

LEVELS = (1, 2, 3, 4)


def kitchen(level):
    return SpatialKitchen(level_config(load_config(), level))


def request(k, memory=None):
    rows = []
    ai = DecisionLoop(k, SpatialJevClient(k.c, key='test'), lambda kind, data: rows.append((kind, data)), lambda text: None)
    if memory is not None:
        ai.cooperation_memory = memory
    with patch('jev.threading.Thread'):
        ai.poll()
    return next(d['payload'] for kind, d in rows if kind == 'ai_request')


class AgentInputTests(unittest.TestCase):
    def test_payload_is_ascii_english_for_every_level(self):
        memory = {'enabled': True, 'version': 1, 'episodes': [{'events': [
            {'message': '你完成动作：去地面(2,5)捡起 D1（干净餐盘；自动换手）', 'actor': 'human'}]}],
            'description': '同一本地玩家与当前接口/模型的过往已结束对局。事件为按时间抽样的事实，非完整录像、非玩家偏好结论；物品编号和坐标仅属于各自旧局。'}
        for level in LEVELS:
            with self.subTest(level=level):
                k = kitchen(level)
                k.advance(20)
                payload = request(k, memory)
                payload.pop('model', None)
                text = json.dumps(payload, ensure_ascii=False)
                self.assertEqual([c for c in text if ord(c) > 127], [])

    def test_chefs_are_named_human_and_jeff_in_events(self):
        k = kitchen(2)
        k.emit('你完成动作：切菜', kind='action_done', actor='human')
        k.emit('Jeff完成动作：切菜', kind='action_done', actor='jeff')
        messages = [e['message'] for e in request(k)['state']['recent_events']]
        self.assertIn('human completed: Chop', messages)
        self.assertIn('jeff completed: Chop', messages)
        self.assertFalse([m for m in messages if m.startswith('You ')])

    def test_manual_walking_is_not_an_event_for_the_model(self):
        k = kitchen(2)
        for _ in range(25):
            k.emit('你手动移动', kind='manual_move', actor='human')
        k.emit('你完成动作：切菜', kind='action_done', actor='human')
        events = request(k)['state']['recent_events']
        self.assertTrue(events)
        self.assertNotIn('manual_move', {e.get('kind') for e in events})
        self.assertEqual(events[-1]['message'], 'human completed: Chop')

    def test_candidates_drop_duplicates_and_spare_empty_counters_only(self):
        for level in LEVELS:
            with self.subTest(level=level):
                k = kitchen(level)
                k.advance(20)
                state, actions = k.snapshot(), k.actions('jeff')
                listed = model_candidates(state, actions, 2)
                self.assertLess(len(listed), len(actions))
                keys = {a.key for a in listed}
                acted = {a.target for a in listed if a.kind not in ('go', 'throw')}
                self.assertFalse([a.key for a in listed if a.kind == 'go' and a.target in acted])
                # Throws and every action at an occupied place stay listed.
                for a in actions:
                    if a.kind == 'throw' or (a.target in state['stations'] and state['stations'][a.target].get('food')):
                        if a.kind != 'go':
                            self.assertIn(a.key, keys)
                empty = [a.target for a in listed if a.kind in ('go', 'put_counter')
                         and state['stations'].get(a.target, {}).get('counter') and not state['stations'][a.target].get('food')]
                per_area = {}
                for key in set(empty):
                    per_area[state['stations'][key]['area']] = per_area.get(state['stations'][key]['area'], 0) + 1
                self.assertTrue(all(n <= 2 for n in per_area.values()), per_area)
                payload = SpatialJevClient(k.c, key='test').payload(state, actions)
                self.assertEqual(set(payload['questions']['next_action']['criteria']), keys)

    def test_rounds_have_a_money_goal_and_name_every_servable_dish(self):
        k = kitchen(2)
        payload = SpatialJevClient(k.c, key='test').payload(k.snapshot(), k.actions('jeff'))
        state = payload['state']['kitchen']
        for key in ('bad_reviews', 'settlement'):
            self.assertNotIn(key, state)
        self.assertEqual(state['goals'], {'target_money': 150})
        self.assertNotIn('time_bonus_per_second', state['scoring'])
        self.assertEqual([d['id'] for d in state['dishes']], ['steak', 'burger'])
        rules = payload['state']['rules']
        self.assertIn('steak 50 yuan', rules['score'])
        self.assertNotIn('incomplete food cannot be served', rules['score'])
        self.assertNotIn('pass through each other', json.dumps(rules))

    def test_client_display_fields_stay_out_of_the_model_input(self):
        k = kitchen(2)
        state = k.snapshot()
        self.assertEqual(state['items']['beef']['color'], '#846144')
        self.assertEqual([p['layer'] for p in next(d for d in state['dishes'] if d['id'] == 'burger')['plating']],
                         ['bun_bottom', 'beef', 'lettuce', 'tomato', 'bun_top'])
        self.assertTrue(any(e.get('item') == 'beef' for e in state['map']['equipment'].values()))
        model = SpatialJevClient(k.c, key='test').payload(state, k.actions('jeff'))['state']['kitchen']
        self.assertNotIn('items', model)
        self.assertFalse(any('plating' in d for d in model['menu'] + model['dishes']))
        self.assertFalse(any('item' in e for e in model['map']['equipment'].values()))

    def test_memory_is_kept_per_level_and_rule_set(self):
        setting = {'provider': 'jev', 'base_url': 'https://example.test/v1', 'model': 'm'}
        scopes = {round_scope(setting, kitchen(level)) for level in LEVELS}
        self.assertEqual(len(scopes), len(LEVELS))
        outcome = episode(kitchen(2), 'g', 'm')['outcome']
        self.assertEqual(set(outcome), {'served', 'money', 'target_money', 'reached_target'})
        self.assertEqual(episode(kitchen(2), 'g', 'm')['level_id'], 'level-2')


if __name__ == '__main__':
    unittest.main()
