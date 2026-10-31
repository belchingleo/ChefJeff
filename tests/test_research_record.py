"""Synthetic engine trajectories only. Never use production contributions or paid APIs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import config_contract as cc
from hosted_records import ContributionStore, CONSENT_VERSION, pilot_record
from hosted_server import HostedSession, Sessions
from kitchen import Food
from research_record import (record, restored_states, validate_record, validate_telemetry, config)
from scripts.research_export import export_package, verify_package, rows, legacy_quality
from spatial_kitchen import SpatialKitchen

ROOT = Path(__file__).resolve().parents[1]


def start(s, consent=False, telemetry=False):
    s.connected = True
    if consent:
        assert s._command('/api/contribution/consent', {'consent': True, 'consent_version': CONSENT_VERSION,
                                                       'decision_telemetry': telemetry})[0] == 200
    assert s._command('/api/start', {})[0] == 200


class ResearchTests(unittest.TestCase):
    def game(self):
        s = HostedSession();self.addCleanup(s.close)
        return s

    def test_projection_and_state_references_restore_engine_facts(self):
        s=self.game();start(s)
        self.assertTrue(s.k.command('human','fetch')[0]);s.k.advance(12)
        s._command('/api/end',{})
        r=record(s)
        self.assertTrue(validate_record(r))
        states=dict(restored_states(r))
        self.assertEqual(states[r['termination']['final_state_seq']]['chefs']['human']['hand']['id'],s.k.chefs['human'].hand.id)
        self.assertEqual(states[r['termination']['final_state_seq']]['orders'][0]['status'],'unresolved_at_close')
        self.assertTrue(any(e['type']=='order' and e['order_id']=='O1' for e in r['events']))
        starts=[e for e in r['events'] if e['type']=='action_start']
        dones=[e for e in r['events'] if e['type']=='action_done']
        self.assertEqual(starts[0]['action_id'],dones[0]['action_id'])
        self.assertEqual(starts[0]['payload']['action']['target'],'fridge')
        self.assertEqual([e['seq'] for e in r['events']],sorted({e['seq'] for e in r['events']}))
        self.assertEqual(s.session_log.projection_errors,0)

    def test_observer_does_not_change_rules_revision_choices_or_engine_events(self):
        s=self.game();start(s)
        again=SpatialKitchen(deepcopy(s.k.resolved))
        for k in (s.k,again):
            k.command('human','fetch');k.advance(12);k.command('human','put b1');k.advance(12)
            k.command('human','chop b1');k.advance(15)
        self.assertEqual(s.k.events,again.events)
        self.assertEqual(s.k.revision,again.revision)
        self.assertEqual([a.key for a in s.k.actions('jeff')],[a.key for a in again.actions('jeff')])

    def test_items_transform_handoff_and_real_receiver_are_linked(self):
        s=self.game();start(s)
        # Synthetic fixture setup; explicitly observable new object lifecycle, no invented order assignment.
        s.k.chefs['human'].hand=Food('F9','raw')
        s.k.positions.update(human=(4.,6.),jeff=(8.,6.))
        self.assertTrue(s.k.start('human',s.k.throw_action('human',s.k.positions['jeff'],'throw partner'))[0])
        s.k.advance(2)
        plate=Food('D1','clean_plate');ingredient=Food('F20','ready')
        result=s.k.merge_plate(plate,ingredient)
        s._command('/api/end',{})
        r=record(s);validate_record(r)
        thrown=next(e for e in r['events'] if e['type']=='thrown')
        caught=next(e for e in r['events'] if e['type'] in ('caught','landed') and e['item_id']=='F9')
        self.assertEqual(thrown['handoff_id'],caught['handoff_id'])
        self.assertEqual(caught['item_id'],'F9')
        if caught['type']=='caught':self.assertEqual(caught['receiver_id'],'jeff')
        transform=next(e for e in r['events'] if e['type']=='item_transform')
        self.assertEqual(transform['payload']['input_item_ids'],['D1','F20'])
        self.assertEqual(transform['payload']['output_item_ids'],[result.id])
        self.assertIsNone(transform['order_id'])

    def test_decision_choice_and_engine_execution_share_request_action_links(self):
        from test_jev import NoKeyClient
        s=self.game();start(s)
        s.ai.client=NoKeyClient(s.c,'fetch')
        s.ai.poll()
        deadline=time.monotonic()+2
        while s.ai.q.empty() and time.monotonic()<deadline:time.sleep(.001)
        s.ai.poll();s._events();s.k.advance(12);s._command('/api/end',{})
        r=record(s);validate_record(r)
        req=next(e for e in r['events'] if e['type']=='ai_request')
        response=next(e for e in r['events'] if e['type']=='ai_response')
        self.assertEqual(req['request_id'],response['request_id'])
        self.assertIn(response['payload']['choice']['key'],req['payload']['candidates'])
        self.assertTrue(any(e['action_id']==response['action_id'] and e['type']=='action_done' for e in r['events']))
        self.assertFalse(response['payload']['provider_verified'])
        self.assertIsNone(r['conditions']['model_identity'])

    def test_pause_disconnect_speed_and_wall_clocks(self):
        s=self.game();start(s)
        s._command('/api/pause',{'reason':'hidden'});s._command('/api/resume',{})
        s.last_seen=time.monotonic()-10;s.tick()
        pauses=[r for r in s.session_log.records if r['type']=='pause']
        self.assertEqual([e['payload']['reason'] for e in pauses],['hidden','connection_timeout'])
        self.assertEqual(s.phase,'paused')
        self.assertTrue(all(e['clock_id']=='server_monotonic' for e in s.session_log.records))
        # Speed is immutable within a round; a different start makes a new round ID/config condition.
        old=s.game_id;s._command('/api/restart',{});self.assertNotEqual(old,s.game_id)
        self.assertEqual(s.session_log.records[0]['payload']['speed'],s.speed)

    def test_termination_reasons_are_observed_not_inferred(self):
        for close_reason,want in [('disconnected','idle_timeout'),('shutdown','server_shutdown'),('page_close','page_close_request')]:
            with self.subTest(close_reason=close_reason):
                s=self.game();start(s);s.usage_close_reason=close_reason;s.close()
                r=record(s);validate_record(r)
                self.assertEqual(r['termination']['session_close']['reason'],want)
                self.assertEqual(r['termination']['game_condition'],'none_observed')
        s=self.game();start(s);s._command('/api/end',{})
        self.assertEqual(record(s)['termination']['session_close']['reason'],'manual_end')
        s=self.game();start(s);s.k.advance(200);s.phase='ended';s._finish()
        self.assertEqual(record(s)['termination']['game_condition'],'round_limit')
        self.assertIsNone(record(s)['termination']['session_close'])

    def test_no_consent_no_disk_old_consent_rejected_and_early_close_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            s=self.game();s.store=ContributionStore(folder);start(s);s.close()
            with s.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM records').fetchone()[0],0)
            s=self.game();s.store=ContributionStore(folder)
            self.assertEqual(s._command('/api/contribution/consent',{'consent':True,'consent_version':'pilot-session-2026-10-v3'})[0],400)
            start(s,consent=True);receipt=deepcopy(s.receipt)
            initial=s.store.download(receipt['id'],receipt['deletion_token'])
            self.assertFalse(initial['quality']['complete']);self.assertFalse(initial['termination']['confirmed'])
            s.k.advance(2);s.usage_close_reason='shutdown';s.close()
            final=s.store.download(receipt['id'],receipt['deletion_token'])
            self.assertTrue(final['quality']['complete']);self.assertEqual(final['duration'],2)
            self.assertEqual(final['termination']['session_close']['reason'],'server_shutdown')
            self.assertIsNone(s.store.download(receipt['id'],'wrong'))
            self.assertTrue(s.store.delete(receipt['id'],receipt['deletion_token']))
            s._persist_research();self.assertIsNone(s.store.download(receipt['id'],receipt['deletion_token']))

    def test_withdraw_during_round_stops_retention_and_future_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            s=self.game();s.store=ContributionStore(folder);start(s,True)
            receipt=s.receipt
            self.assertEqual(s._command('/api/contribution/consent',{'consent':False,'consent_version':CONSENT_VERSION})[0],200)
            s._command('/api/end',{})
            self.assertIsNone(s.store.download(receipt['id'],receipt['deletion_token']))

    def test_cap_is_reported_with_ranges_and_final_checkpoint_survives(self):
        s=self.game();start(s)
        with patch('research_record.MAX_RECORDS',15):
            for _ in range(30):s.k.emit('not stored',kind='arrival_conflict',actor='human',action_id=1)
            s._command('/api/end',{})
        r=record(s)
        self.assertTrue(r['quality']['truncated']);self.assertFalse(r['quality']['complete'])
        self.assertGreater(r['quality']['dropped'],0)
        lost=sum(x['last_seq']-x['first_seq']+1 for x in r['quality']['loss_ranges'])
        self.assertEqual(lost,r['quality']['dropped'])
        self.assertEqual(r['events'][-1]['type'],'state_checkpoint')
        self.assertEqual(r['events'][-1]['payload']['trigger'],'final')
        validate_record(r)

    def test_sensitive_fields_errors_and_spoofed_metadata(self):
        s=self.game();start(s)
        secret='SECRET_SENTINEL/https://private.example/token'
        for kind in ('ai_error','engine_error','player_message','bookmark'):
            s.session_log(kind,{'error':secret,'trace':secret,'text':secret,'model':secret,'provider':secret,'request_id':1})
        s.k.resolved['overrides']['api_key']=secret
        s.k.resolved['map']['equipment'][0]['params']={'api_key':secret}
        s.k.emit(secret,kind='arrival_conflict',actor='human',error=secret,api_key=secret)
        s._command('/api/end',{})
        r=record(s);validate_record(r)
        self.assertNotIn(secret,json.dumps(r));self.assertNotIn(secret,json.dumps(config(s.k)))
        bad=deepcopy(r);bad['api_key']=secret
        with self.assertRaises(ValueError):validate_record(bad)
        for value in ({'duration_ms':1,'error_type':None,'model':'private'}, {'duration_ms':float('nan'),'error_type':None}, {'duration_ms':1,'error_type':'raw error'}):
            with self.assertRaises(ValueError):validate_telemetry(value)
        self.assertEqual(validate_telemetry({'duration_ms':30,'error_type':None})['duration_ms'],30)

    def test_read_only_cli_mixed_versions_hashes_filters_and_expiry(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ContributionStore(folder);s=self.game();start(s);s._command('/api/end',{})
            store.save(record(s));store.save({'schema':'chefjeff-pilot-session-v1','level':2,'events':[]})
            before=store.path.read_bytes()
            self.assertEqual(len(list(rows(store.path,level=2))),1)
            target=Path(folder)/'private.cjresearch.zip'
            export_package(store.path,target);self.assertEqual(verify_package(target)['rounds'],2)
            self.assertEqual(before,store.path.read_bytes())
            self.assertEqual(target.stat().st_mode&0o777,0o600)
            self.assertIn('not_collected',legacy_quality({})['interpretation'])
            self.assertEqual(verify_package(target,now=time.time()+31*86400)['rounds'],2)  # six-month terms
            with self.assertRaises(ValueError):verify_package(target,now=time.time()+181*86400)
            store.prune(time.time()+181*86400)
            self.assertEqual(list(rows(store.path)),[])

    def test_consented_full_round_orders_work_and_state_gap_are_measured(self):
        import reference_policy
        with tempfile.TemporaryDirectory() as folder:
            s=self.game();s.store=ContributionStore(folder);start(s,True)
            steps=0
            while not s.k.ended:
                if steps%10==0:
                    for who,role in (('human','assembler'),('jeff','cook')):
                        a=reference_policy.choose(s.k,who,role)
                        if a:s.k.start(who,a)
                s.k.advance(.05);steps+=1
            s.phase='ended';s._finish();r=record(s);validate_record(r)
            self.assertTrue(r['quality']['complete']);self.assertEqual(r['quality']['dropped'],0)
            self.assertLessEqual(r['quality']['observed_max_state_gap_game_ms'],1000)
            appeared={e['order_id'] for e in r['events'] if e['type']=='order'}
            served=[e for e in r['events'] if e['type']=='served']
            self.assertTrue(served);self.assertTrue(all(e['order_id'] in appeared and e['item_id'] for e in served))
            self.assertTrue(any(e['type']=='shared_work_join' and e['station_id'] for e in r['events']))
            restored=dict(restored_states(r))[r['termination']['final_state_seq']]
            self.assertEqual(restored['served'],s.k.served)
            self.assertIsNone(r['termination']['session_close'])
            old_id=s.game_id;receipt=s.receipt
            self.assertEqual(s._command('/api/next',{'level':99})[0],400)
            self.assertIsNone(record(s)['termination']['session_close'])
            self.assertEqual(s._command('/api/next',{'level':2})[0],200)
            saved=s.store.download(receipt['id'],receipt['deletion_token'])
            self.assertEqual(saved['round_id'],old_id)
            self.assertEqual(saved['termination']['session_close']['reason'],'next_level');validate_record(saved)

    def test_expired_orders_and_fire_failure_keep_observed_causes(self):
        s=self.game();start(s);s.k.advance(180);s.phase='ended';s._finish();r=record(s)
        appeared={e['order_id'] for e in r['events'] if e['type']=='order'}
        expired=[e for e in r['events'] if e['type']=='expired']
        self.assertTrue(expired);self.assertTrue(all(e['order_id'] in appeared for e in expired));validate_record(r)
        s=self.game();start(s)
        for key in list(s.k.stations)[:s.k.rules.fire_loss]:s.k.ignite(key)
        s.k.advance(.05);s.phase='ended';s._finish();r=record(s)
        self.assertEqual(r['termination']['game_condition'],'fire_loss');validate_record(r)

    def test_store_byte_capacity_keeps_previous_record_and_source_verification_detects_withdrawal(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ContributionStore(folder,byte_limit=100)
            with self.assertRaises(ValueError):store.save({'schema':'legacy','content':'x'*200})
            store=ContributionStore(folder);s=self.game();start(s);s._command('/api/end',{})
            receipt=store.save(record(s));target=Path(folder)/'test.cjresearch.zip'
            export_package(store.path,target);verify_package(target,database=store.path)
            store.delete(receipt['id'],receipt['deletion_token'])
            with self.assertRaises(ValueError):verify_package(target,database=store.path)

    def test_duplicate_archive_entries_are_not_hidden_by_manifest_sets(self):
        import zipfile,warnings
        with tempfile.TemporaryDirectory() as folder:
            store=ContributionStore(folder);data=json.loads((ROOT/'tests/fixtures/research-v2-short.json').read_text());store.save(data)
            target=Path(folder)/'duplicate.cjresearch.zip';export_package(store.path,target)
            with zipfile.ZipFile(target,'a') as archive,warnings.catch_warnings():
                warnings.simplefilter('ignore');archive.writestr('manifest.json',archive.read('manifest.json'))
            with self.assertRaises(ValueError):verify_package(target)

    def test_synthetic_fixture_is_versioned_and_valid(self):
        data=json.loads((ROOT/'tests/fixtures/research-v2-short.json').read_text())
        validate_record(data)


if __name__=='__main__':unittest.main()
