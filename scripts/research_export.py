#!/usr/bin/env python3
"""Private, read-only SQLite research export. No game HTTP endpoint or credentials."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_record import SCHEMA, validate_record
import schema_check
import config_contract as cc

FORMAT = 'chefjeff-research-package-v1'


def rows(database, schema=None, level=None, since=None, until=None, now=None):
    """Read active rows only; never construct a store or prune the source database."""
    uri = Path(database).resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        identifiers = db.execute('SELECT id FROM records WHERE expires>? ORDER BY expires,id',
                                 (time.time() if now is None else now,)).fetchall()
        def timestamp(value):
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None: raise ValueError('Filter timestamps need a timezone')
            return parsed.timestamp()
        for (identifier,) in identifiers:
            cursor = db.execute('SELECT expires,record FROM records WHERE id=? AND expires>?',
                                (identifier, time.time() if now is None else now))
            row = cursor.fetchone()
            cursor.close()  # release the read lock before compression/projection of a large row
            if row is None: continue
            expiry, encoded = row
            data = json.loads(encoded)
            if schema and data.get('schema') != schema: continue
            if level is not None and data.get('level') != level: continue
            started = data.get('started_at')
            if since and (not started or timestamp(started) < timestamp(since)): continue
            if until and (not started or timestamp(started) >= timestamp(until)): continue
            yield identifier, expiry, data


def legacy_quality(data):
    return {'source_schema': data.get('schema'), 'status': 'legacy_read_only',
            'missing': ['round_id', 'seq', 'object_relations', 'resolved_config', 'state_observations',
                        'confirmed_close_reason', 'model_decision_linkage'],
            'interpretation': 'not_collected; absence of fields is not absence of events'}


def export_package(database, destination, **filters):
    destination = Path(destination)
    if destination.exists(): raise ValueError('Export destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    selected = []
    fd, temp = tempfile.mkstemp(prefix='.research-', dir=destination.parent)
    artifacts = []
    try:
        with os.fdopen(fd, 'wb') as output, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            def write(name, raw):
                if not isinstance(raw, bytes): raw = json.dumps(raw, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
                archive.writestr(name, raw)
                artifacts.append({'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
            for identifier, expiry, data in rows(database, **filters):
                # SQLite IDs are not trusted filesystem/ZIP path components.
                prefix = hashlib.sha256(identifier.encode()).hexdigest()[:24] + '/'
                selected.append({'source_ref': prefix[:-1], 'expires': expiry,
                                 'record_sha256': cc.sha256(data)})
                if data.get('schema') == SCHEMA:
                    validate_record(data)
                    metadata = {k: v for k, v in data.items() if k not in ('events','resolved_config')}
                    metadata['artifacts'] = {'config': prefix + 'resolved-config.json', 'events': prefix + 'events.jsonl',
                                             'state_records': 'state_checkpoint/state_delta in the same events.jsonl'}
                    metadata['source_expires_at'] = datetime.fromtimestamp(expiry, timezone.utc).isoformat()
                    write(prefix + 'metadata.json', metadata)
                    write(prefix + 'resolved-config.json', data['resolved_config'])
                    write(prefix + 'events.jsonl', ''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n' for r in data['events']).encode())
                elif data.get('schema') == 'chefjeff-pilot-session-v1':
                    if schema_check.validate(data, 'research-legacy-v1.schema.json'): raise ValueError('Unknown legacy fields; inspect privately before export')
                    write(prefix + 'legacy-v1.json', data)
                    write(prefix + 'quality.json', legacy_quality(data))
                else:
                    raise ValueError('Unsupported source schema')
            if not selected: raise ValueError('No active matching contributions')
            manifest = {'format': FORMAT, 'created_at': datetime.now(timezone.utc).isoformat(),
                        'expires': min(source['expires'] for source in selected),
                        'source': 'private_sqlite_read_only', 'rounds': len(selected), 'artifacts': artifacts, 'sources': selected, 'authenticated': False,
                        'annotations': 'separate research layer; never engine facts',
                        'deletion': 'private derived copy; remove package on any included withdrawal or earliest source expiry'}
            archive.writestr('manifest.json', json.dumps(manifest, separators=(',', ':')))
        os.chmod(temp, 0o600)
        # No overwrite even if another process creates the destination meanwhile.
        os.link(temp, destination)
        return manifest
    finally:
        Path(temp).unlink(missing_ok=True)


def verify_package(path, now=None, database=None):
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo('manifest.json').file_size > 2_000_000: raise ValueError('Oversized manifest')
        manifest = json.loads(archive.read('manifest.json'))
        if schema_check.validate(manifest, 'research-package.schema.json'): raise ValueError('Invalid manifest schema')
        if manifest.get('format') != FORMAT: raise ValueError('Unknown package format')
        if manifest['expires'] <= (time.time() if now is None else now): raise ValueError('Package expired; remove the derived copy')
        if manifest['rounds'] != len(manifest['sources']) or manifest['expires'] != min(s['expires'] for s in manifest['sources']):
            raise ValueError('Invalid source count or retention boundary')
        if len({s['source_ref'] for s in manifest['sources']}) != manifest['rounds']: raise ValueError('Duplicate source')
        names = [a['path'] for a in manifest['artifacts']]
        if len(archive.namelist()) != len(set(archive.namelist())): raise ValueError('Duplicate ZIP entries')
        if len(names) != len(set(names)) or set(archive.namelist()) != set(names) | {'manifest.json'}:
            raise ValueError('Unexpected or duplicate package entries')
        for artifact in manifest['artifacts']:
            if archive.getinfo(artifact['path']).file_size > 13_000_000: raise ValueError('Oversized artifact')
            raw = archive.read(artifact['path'])
            if len(raw) != artifact['bytes'] or hashlib.sha256(raw).hexdigest() != artifact['sha256']:
                raise ValueError('Artifact digest mismatch')
        for source in manifest['sources']:
            prefix=source['source_ref']+'/'
            if prefix+'metadata.json' in names:
                metadata=json.loads(archive.read(prefix+'metadata.json'))
                if schema_check.validate(metadata,'research-metadata.schema.json'): raise ValueError('Invalid metadata schema')
                if metadata['artifacts']['config'] != prefix+'resolved-config.json' or metadata['artifacts']['events'] != prefix+'events.jsonl':
                    raise ValueError('Invalid artifact reference')
                config=json.loads(archive.read(prefix+'resolved-config.json'))
                events=[json.loads(line) for line in archive.read(prefix+'events.jsonl').splitlines() if line]
                restored={k:v for k,v in metadata.items() if k not in ('artifacts','source_expires_at')}
                restored.update(resolved_config=config,events=events)
                validate_record(restored)
                if cc.sha256(restored)!=source['record_sha256']: raise ValueError('Source digest mismatch')
            else:
                legacy=json.loads(archive.read(prefix+'legacy-v1.json'))
                if schema_check.validate(legacy,'research-legacy-v1.schema.json'): raise ValueError('Invalid legacy schema')
                if cc.sha256(legacy)!=source['record_sha256']: raise ValueError('Legacy source digest mismatch')
        if database is not None:
            current = {hashlib.sha256(i.encode()).hexdigest()[:24]: (cc.sha256(r), expiry)
                       for i, expiry, r in rows(database, now=now)}
            for source in manifest['sources']:
                if current.get(source['source_ref']) != (source['record_sha256'], source['expires']):
                    raise ValueError('Source changed, expired or withdrawn; remove the derived package')
        return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--schema', choices=['chefjeff-pilot-session-v1', SCHEMA])
    parser.add_argument('--level', type=int, choices=[1,2,3])
    parser.add_argument('--since', help='inclusive ISO 8601 UTC start time; v1 without date excluded')
    parser.add_argument('--until', help='exclusive ISO 8601 UTC start time; v1 without date excluded')
    parser.add_argument('command', choices=['list','export','verify'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'verify':
            if not args.output: parser.error('--output package is required')
            result = verify_package(args.output, database=args.database)
        else:
            if not args.database: parser.error('--database is required')
            filters = {k: getattr(args,k) for k in ('schema','level','since','until')}
            if args.command == 'export':
                if not args.output: parser.error('--output destination is required')
                result = export_package(args.database, args.output, **filters)
            else:
                result = [{'id': i, 'schema': r.get('schema'), 'level': r.get('level'),
                           'round_id': r.get('round_id'), 'started_at': r.get('started_at'),
                           'expires': exp, 'quality': r.get('quality', legacy_quality(r))}
                          for i, exp, r in rows(args.database, **filters)]
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, TypeError, KeyError, sqlite3.Error, OSError, zipfile.BadZipFile):
        parser.exit(1, 'Research export failed: check file permissions, schema, integrity and expiry.\n')


if __name__ == '__main__':
    main()
