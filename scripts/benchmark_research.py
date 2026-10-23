#!/usr/bin/env python3
"""Synthetic instrumentation benchmark; no providers, keys or real player records.
Uses the test-only reference trajectory solely to exercise engine/logging coverage.
It is not a teammate in the shipped game and is not an evaluation of cooperation.
"""
import argparse
import gc
import json
from pathlib import Path
import sys
import time
import tracemalloc

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import config_contract as cc
import reference_policy
from hosted_server import HostedSession
from research_record import record, validate_record
from spatial_kitchen import SpatialKitchen


def trajectory(k, session=None, dense=False):
    steps=0
    while not k.ended:
        if dense:
            at=list(k.positions['human']);base=k.resync['human']
            if session:
                session.command('/api/position', {'game_id':session.game_id,'seq':steps,'base':base,'at':at,'press':False})
            else:
                k.report_position('human',at[0],at[1],base,False,False)
        if steps%10==0:
            for who,role in (('human','assembler'),('jeff','cook')):
                a=reference_policy.choose(k,who,role)
                if a:k.start(who,a)
        k.advance(.05);steps+=1
    return steps


def run(level, dense=False):
    frozen=cc.load_level('level-'+str(level),seeds={'orders':1,'spawn':0})
    base=SpatialKitchen(frozen)
    began=time.perf_counter();trajectory(base,dense=dense);baseline=time.perf_counter()-began
    del base;gc.collect()
    measured=HostedSession();measured.k=SpatialKitchen(frozen);measured.c=measured.k.c;measured.connected=True
    measured.research_armed={'decision_telemetry':False};measured._command('/api/start',{})
    began=time.perf_counter();trajectory(measured.k,measured,dense);instrumented=time.perf_counter()-began
    measured.phase='ended';measured._finish();measured.close();del measured;gc.collect()
    s=HostedSession();s.k=SpatialKitchen(frozen);s.c=s.k.c;s.connected=True;s.research_armed={'decision_telemetry':False};s._command('/api/start',{})
    # No session tick / model poll: this is an offline engine trajectory.
    gc.collect();tracemalloc.start();began=time.perf_counter()
    steps=trajectory(s.k,s,dense);elapsed=time.perf_counter()-began
    s.phase='ended';s._finish();data=record(s)
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    began=time.perf_counter();raw=json.dumps(data,separators=(',',':'),ensure_ascii=False).encode();serialization=time.perf_counter()-began
    began=time.perf_counter();validate_record(data);validation=time.perf_counter()-began
    counts={kind:sum(e['type']==kind for e in data['events']) for kind in ('state_checkpoint','state_delta','served','expired','ready','burn','fire','shared_work_join')}
    result={'level':level,'synthetic':True,'input_reports_per_game_second':20 if dense else 0,'game_seconds':s.k.time,'ticks':steps,'baseline_elapsed_seconds':round(baseline,4),
            'instrumented_elapsed_seconds':round(instrumented,4),'instrumented_seconds_with_tracemalloc':round(elapsed,4),'peak_traced_bytes':peak,'record_bytes':len(raw),
            'records':len(data['events']),'counts':counts,'dropped':data['quality']['dropped'],
            'serialization_ms':round(serialization*1000,3),'validation_ms':round(validation*1000,3)}
    s.close();return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--level',type=int,choices=[1,2,3]);p.add_argument('--dense-inputs',action='store_true');args=p.parse_args()
    for level in ([args.level] if args.level else [1,2,3]):print(json.dumps(run(level,args.dense_inputs)),flush=True)

if __name__=='__main__':main()
