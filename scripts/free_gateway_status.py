#!/usr/bin/env python3
"""Read safe operational summaries through the private gateway; zero model API calls."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from free_model_client import FreeGatewayClient
from shared_client import SharedClient
from shared_server import read_private_json


def main():
    client=FreeGatewayClient(SharedClient(read_private_json('/etc/chefjeff/shared-client.json')))
    result=client.request('status',{})
    print(json.dumps({'diagnostics_version':result['catalog']['diagnostics_version'],
        'capacity':result['catalog']['global_capacity'],'diagnostics':result['diagnostics'],
        'model_calls':0,'player_databases_opened':False,'credentials_printed':False},ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'gateway-status-unavailable','error_type':type(error).__name__,
            'credentials_printed':False}));raise SystemExit(1) from None
