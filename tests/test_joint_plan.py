"""Bilateral shared order focus and commitment (joint_plan trial, joint-plan-v1)."""
import json
import re
import time
import unittest
import uuid

import features
import harness
import hosted_free_models
import hosted_jev
import jev
import joint_plan
from kitchen import Food, load_config
from levels import level_config
from model_output import zhipu_body
from spatial_kitchen import SpatialKitchen
from test_agent_rules_neutral import VALUE_WORDING
from test_one_press import with_features
from test_web import FakeJournal
from web_server import GameSession
from whitebox_server import SpatialJevClient


class ScriptedJointClient(SpatialJevClient):
    """Offline client that inspects each payload and returns scripted next_action + joint_* answers."""

    def __init__(self, config, answers):
        super().__init__(config, key='test-joint-key')
        self.answers = list(answers)
        self.seen = []

    def ask(self, payload):
        self.seen.append(payload)
        step = self.answers.pop(0) if self.answers else {'choice': 'wait'}
        choice = step.get('choice', 'wait')
        if choice not in payload['questions']['next_action']['criteria']:
            choice = 'wait'
        extra = harness.choice_answer(step, payload)
        return {
            'choice': choice,
            'sprint': False,
            'confidence': 1.0,
            'probabilities': {choice: 1.0},
            'model': 'scripted-joint',
            'usage': {'input_tokens': 10, 'output_tokens': 5},
            'latency': 0.01,
            **extra,
        }


class JointPlanUnitTests(unittest.TestCase):
    def level2(self):
        return SpatialKitchen(level_config(load_config(), 2))

    def compose(self, k, plan, is_ahead=False):
        client = SpatialJevClient(k.c, key='test')
        feats = with_features(joint_plan={'on': True}, option_links={'on': False})
        opts = features.compose_options(feats)
        opts.pop('joint_plan', None)
        return jev.compose_payload(
            client, k, k.snapshot(), k.actions('jeff'), [], None, jev.NO_MEMORY,
            **opts, joint=joint_plan.snapshot_for_record(plan), is_ahead=is_ahead,
        )

    def test_level2_proposal_is_neutral_english_and_recipe_driven(self):
        k = self.level2()
        plan = joint_plan.start()
        payload = self.compose(k, plan)
        sent = harness.for_model(payload)
        self.assertIn(joint_plan.PROPOSAL_Q, sent['questions'])
        criteria = sent['questions'][joint_plan.PROPOSAL_Q]['criteria']
        self.assertIn('none', criteria)
        self.assertIn('O1:jeff_cook', criteria)
        self.assertIn('O1:jeff_prep', criteria)
        self.assertIn('joint_plan', sent['state']['rules'])
        text = json.dumps({'rule': sent['state']['rules']['joint_plan'], 'q': sent['questions'][joint_plan.PROPOSAL_Q]})
        self.assertIsNone(VALUE_WORDING.search(text), text)
        self.assertIsNone(re.search(r'[\u3400-\u9fff]', text), text)
        # Speculative ask_ahead never attaches a new proposal question when none is active.
        ahead = self.compose(k, plan, is_ahead=True)
        self.assertNotIn(joint_plan.PROPOSAL_Q, ahead['questions'])

    def test_human_click_focus_bilateral_accept_toggle_and_progress(self):
        k = self.level2()
        plan = joint_plan.start()
        ok, err, entry = joint_plan.human_action(plan, k, 'focus', order_id='O1')
        self.assertTrue(ok, err)
        self.assertEqual(plan['status'], 'proposed')
        self.assertEqual(plan['proposer'], 'human')
        self.assertEqual(entry['transition'], 'proposed')

        # Even during ask_ahead, Jeff gets joint_reply to respond promptly to human's click.
        payload = self.compose(k, plan, is_ahead=True)
        self.assertIn(joint_plan.REPLY_Q, payload['questions'])
        reply_keys = set(payload['questions'][joint_plan.REPLY_Q]['criteria'])
        self.assertTrue({'accept:jeff_cook', 'accept:jeff_prep', 'accept:shared', 'decline'} <= reply_keys)

        # Jeff accepts and picks jeff_prep (veg/plating).
        ans_entry = joint_plan.apply_answer(plan, k, {joint_plan.REPLY_Q: 'accept:jeff_prep'}, [joint_plan.REPLY_Q])
        self.assertEqual(ans_entry['transition'], 'accepted')
        self.assertEqual(plan['status'], 'active')
        self.assertEqual(plan['division'], 'jeff_prep')

        # Active commitment appears in state without asking extra questions on normal or ask_ahead turns.
        active_payload = self.compose(k, plan, is_ahead=True)
        self.assertEqual(active_payload['state']['joint_plan']['status'], 'active')
        self.assertEqual(set(active_payload['questions']) & set(joint_plan.QUESTIONS), set())

        # Objective progress updates regardless of who did the work (human fetches beef & chops lettuce).
        k.stations['b1'].food = Food('L1', 'chopped', ingredient='lettuce')
        k.stations['p1'].food = Food('B1', 'ready', ingredient='beef', heated=k.rules.heat_thresholds('beef')[0])
        prog = joint_plan.order_progress(k, k.orders[0])
        by_item = {c['item']: c['status'] for c in prog['components']}
        self.assertEqual(by_item['lettuce'], 'ready')
        self.assertEqual(by_item['beef'], 'ready')
        self.assertEqual(by_item['tomato'], 'needed')

        # Clicking the already-active division chip is a harmless no-op.
        ok, err, noop = joint_plan.human_action(plan, k, 'focus', order_id='O1', division='jeff_prep')
        self.assertTrue(ok, err)
        self.assertIsNone(noop)
        self.assertEqual(plan['status'], 'active')
        self.assertEqual(plan['division'], 'jeff_prep')

        # Clicking the already focused order again releases it.
        ok, err, rel = joint_plan.human_action(plan, k, 'focus', order_id='O1')
        self.assertTrue(ok, err)
        self.assertEqual(plan['status'], 'none')
        self.assertEqual(rel['transition'], 'released')

    def test_jeff_proposal_implicit_human_acceptance_and_explicit_decline(self):
        k = self.level2()
        plan = joint_plan.start()
        entry = joint_plan.apply_answer(plan, k, {joint_plan.PROPOSAL_Q: 'O1:jeff_cook'}, [joint_plan.PROPOSAL_Q])
        self.assertEqual(entry['transition'], 'proposed')
        self.assertEqual(plan['proposer'], 'jeff')
        self.assertEqual(plan['division'], 'jeff_cook')

        # Human starts fetching lettuce (their side of jeff_cook): implicit confirmation!
        k.start('human', next(a for a in k.actions('human') if a.key == 'fetch lettuce'))
        logs = joint_plan.sync(plan, k)
        self.assertEqual(plan['status'], 'active')
        self.assertEqual(plan['accepted_by'], 'human_implicit')
        self.assertEqual(logs[-1]['transition'], 'accepted_implicit')

        # Separate proposal declined by human sets cooldown.
        plan2 = joint_plan.start()
        joint_plan.apply_answer(plan2, k, {joint_plan.PROPOSAL_Q: 'O1:jeff_cook'}, [joint_plan.PROPOSAL_Q])
        ok, err, dec = joint_plan.human_action(plan2, k, 'decline')
        self.assertTrue(ok, err)
        self.assertEqual(plan2['status'], 'none')
        self.assertEqual(dec['transition'], 'declined')
        self.assertGreater(plan2['cooldown_until'], k.time)
        p_cool = self.compose(k, plan2)
        self.assertNotIn(joint_plan.PROPOSAL_Q, p_cool['questions'])

    def test_crisis_suspends_and_omits_joint_plan_from_model_input(self):
        k = self.level2()
        plan = joint_plan.start()
        joint_plan.human_action(plan, k, 'focus', order_id='O1', division='jeff_cook')
        joint_plan.apply_answer(plan, k, {joint_plan.REPLY_Q: 'accept'}, [joint_plan.REPLY_Q])
        self.assertEqual(plan['status'], 'active')

        # Food within 8s of burning suspends commitment and removes it from model input.
        ready_t, burn_t, _ = k.rules.heat_thresholds('beef')
        k.stations['p1'].food = Food('B1', 'ready', ingredient='beef', heated=burn_t - 4.0)
        logs = joint_plan.sync(plan, k)
        self.assertTrue(plan['suspended'])
        self.assertEqual(plan['suspend_reason'], 'burn_risk')
        self.assertEqual(logs[-1]['transition'], 'suspended')

        payload = self.compose(k, plan)
        self.assertNotIn('joint_plan', payload['state'])
        self.assertNotIn('joint_plan', payload['state']['rules'])
        self.assertEqual(set(payload['questions']) & set(joint_plan.QUESTIONS), set())

        # Removing the pan resumes the active commitment cleanly.
        k.stations['p1'].food = None
        logs = joint_plan.sync(plan, k)
        self.assertFalse(plan['suspended'])
        self.assertEqual(logs[-1]['transition'], 'resumed')
        resumed = self.compose(k, plan)
        self.assertEqual(resumed['state']['joint_plan']['status'], 'active')

    def test_stall_triggers_recheck_and_jeff_release(self):
        k = self.level2()
        plan = joint_plan.start()
        joint_plan.human_action(plan, k, 'focus', order_id='O1', division='jeff_cook')
        joint_plan.apply_answer(plan, k, {joint_plan.REPLY_Q: 'accept'}, [joint_plan.REPLY_Q])
        k.advance(joint_plan.STALL_RECHECK_SECONDS + 0.5)
        joint_plan.sync(plan, k)
        payload = self.compose(k, plan)
        self.assertIn(joint_plan.STATUS_Q, payload['questions'])
        entry = joint_plan.apply_answer(plan, k, {joint_plan.STATUS_Q: 'release'}, [joint_plan.STATUS_Q])
        self.assertEqual(entry['transition'], 'released')
        self.assertEqual(plan['status'], 'none')

    def test_wire_parsers_carry_joint_answers_across_decision_and_chat_formats(self):
        k = self.level2()
        plan = joint_plan.start()
        joint_plan.human_action(plan, k, 'focus', order_id='O1')
        payload = harness.for_model(self.compose(k, plan))

        # Decision API (Jev / StartLux)
        raw_decision = json.dumps({
            'answers': {
                'next_action': {'type': 'choice', 'choice': 'wait', 'probabilities': {'wait': 1.0}},
                'sprint': {'type': 'choice', 'choice': 'no'},
                'joint_reply': {'type': 'choice', 'choice': 'accept:jeff_prep'},
            },
            'usage': {'input_tokens': 10, 'output_tokens': 2},
        })
        parsed_dec = hosted_jev.parse_answer(raw_decision, payload)
        self.assertEqual(parsed_dec['answers']['joint_reply'], 'accept:jeff_prep')

        # Chat Completions (Zhipu / Cloudflare schema)
        body = zhipu_body(payload)
        schema = json.loads(body['messages'][0]['content'].split('JSON Schema: ')[1])
        self.assertIn('joint_reply', schema['properties'])
        raw_chat = json.dumps({
            'model': 'glm-4.7-flash',
            'choices': [{'message': {'content': json.dumps({'choice': 'wait', 'sprint': False, 'joint_reply': 'accept:jeff_prep'})}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
        })
        parsed_chat = hosted_free_models.chat_answer(raw_chat, payload, 'zhipu')
        self.assertEqual(parsed_chat['answers']['joint_reply'], 'accept:jeff_prep')

    def test_session_endpoint_and_decision_loop_end_to_end(self):
        cfg = level_config(load_config(), 2)
        client = ScriptedJointClient(cfg, [
            {'choice': 'wait', 'joint_proposal': 'O1:jeff_cook'},
            {'choice': 'wait', 'joint_reply': 'accept:jeff_prep'},
        ])
        session = GameSession(config=cfg, client_factory=lambda c: client, journal_factory=FakeJournal,
                              kitchen_factory=SpatialKitchen)
        self.addCleanup(session.close)
        session.feature_source = lambda: with_features(joint_plan={'on': True}, option_links={'on': False}, ask_ahead={'on': False})
        status, _ = session.command('/api/start', {'game_id': session.game_id, 'request_id': uuid.uuid4().hex})
        self.assertEqual(status, 200)

        # First poll triggers Jeff's bilateral proposal on O1.
        session.ai.poll(enabled=True)
        deadline = time.monotonic() + 2
        while session.ai.q.empty() and time.monotonic() < deadline:
            time.sleep(0.005)
        session.ai.poll(enabled=True)
        pub = session.public_state()['joint_plan']
        self.assertTrue(pub['enabled'])
        self.assertEqual(pub['status'], 'proposed')
        self.assertEqual(pub['proposer'], 'jeff')
        self.assertEqual(pub['order_id'], 'O1')

        # Human clicks O2 via /api/joint-plan -> switches to human proposal on O2.
        status, res = session.command('/api/joint-plan', {
            'game_id': session.game_id, 'request_id': uuid.uuid4().hex,
            'action': 'focus', 'order_id': 'O2',
        })
        self.assertEqual(status, 200, res)
        self.assertEqual(res['joint_plan']['status'], 'proposed')
        self.assertEqual(res['joint_plan']['proposer'], 'human')
        self.assertEqual(res['joint_plan']['order_id'], 'O2')

        # Next poll sends joint_reply and Jeff accepts O2 with jeff_prep.
        session.ai.last_request = -1e9
        session.ai.poll(enabled=True)
        deadline = time.monotonic() + 2
        while session.ai.q.empty() and time.monotonic() < deadline:
            time.sleep(0.005)
        session.ai.poll(enabled=True)
        pub2 = session.public_state()['joint_plan']
        self.assertEqual(pub2['status'], 'active')
        self.assertEqual(pub2['order_id'], 'O2')
        self.assertEqual(pub2['division'], 'jeff_prep')


class JointPlanReplayTests(unittest.TestCase):
    def test_consented_hosted_round_with_joint_plan_replays_exactly(self):
        import research_replay
        from research_record import validate_record
        import test_research_save_paths as paths

        class _ReplayCase(paths.SavePathTests):
            def runTest(self):
                pass

        case = _ReplayCase()
        case.setUp()
        try:
            self.assertEqual(case.command('level', level=2)[0], 200)
            case.game.feature_source = lambda: with_features(joint_plan={'on': True}, option_links={'on': False}, ask_ahead={'on': False})
            receipt = case.begin_manual_relay()
            # Human clicks O1 via hosted /api/joint-plan route!
            status, body = case.command('joint-plan', action='focus', order_id='O1')
            self.assertEqual(status, 200, body)
            self.assertEqual(body['joint_plan']['status'], 'proposed')
            # Jeff receives joint_reply over BrowserRelay and accepts with jeff_prep.
            case.due()
            with case.game.lock:
                case.game.ai.poll()
            deadline = time.monotonic() + 2
            pending = None
            while time.monotonic() < deadline and pending is None:
                pending = case.game.relay.request()
                if pending is None:
                    time.sleep(0.005)
            self.assertIsNotNone(pending)
            self.assertIn(joint_plan.REPLY_Q, pending['payload']['questions'])
            self.assertEqual(case.request('/api/model/result', {
                'id': pending['id'], 'choice': 'wait', 'sprint': False,
                'answers': {joint_plan.REPLY_Q: 'accept:jeff_prep'},
                'usage': {'input_tokens': 10, 'output_tokens': 5},
            }, case.token)[0], 200)
            with case.game.lock:
                case.game.ai.poll()
                self.assertEqual(case.game.ai.joint_plan['status'], 'active')
                self.assertEqual(case.game.ai.joint_plan['division'], 'jeff_prep')
            case.natural_end()
            self.assertEqual(case.contribute()[0], 200)
            record = case.game.store.download(receipt['id'], receipt['deletion_token'])
            validate_record(record)
            self.assertEqual(record['conditions']['features']['joint_plan'], {'on': True, 'version': joint_plan.VERSION})
            rebuilt = list(research_replay.rebuild_requests(record))
            self.assertGreaterEqual(len(rebuilt), 1)
            self.assertEqual({r['status'] for r in rebuilt}, {'verified'})
            self.assertIn(joint_plan.REPLY_Q, rebuilt[0]['rebuilt']['questions'])
        finally:
            case.tearDown()
            case.doCleanups()


if __name__ == '__main__':
    unittest.main()
