#!/usr/bin/env python3
"""Create separate private backend credentials outside the distributable release."""
import argparse
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_client import SharedClient


def create(directory, remote_url):
    directory = Path(directory).resolve()
    if directory.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('Keep credentials outside the source/release directory')
    tokens = {site: secrets.token_urlsafe(32) for site in ('cn', 'global')}
    cn = {'url': 'http://127.0.0.1:8790', 'site': 'cn', 'token': tokens['cn']}
    overseas = {'url': remote_url, 'site': 'global', 'token': tokens['global']}
    SharedClient(cn);SharedClient(overseas)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    directory.chmod(0o700)
    for name, data in [('data-server.json', {'sites': tokens}), ('cn-client.json', cn), ('global-client.json', overseas)]:
        path = directory/name
        with path.open('x') as output:
            path.chmod(0o600)
            json.dump(data, output)
            output.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--remote-url', required=True)
    args = parser.parse_args()
    create(args.output_dir, args.remote_url)
    print('Private configuration created; transfer/install files through the existing authenticated server connection.')


if __name__ == '__main__':
    main()
