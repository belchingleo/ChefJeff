#!/usr/bin/env python3
"""Check research records: coverage, gaps, sequence continuity and exact replay.

Read-only. Takes record JSON files (a player's own download) or, with --database, every active
v2 row of a private contributions database. Prints one JSON report per round; never calls a model.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_record import SCHEMA
import research_replay


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('records', nargs='*', type=Path, help='Record JSON files, as downloaded with a receipt.')
    p.add_argument('--database', type=Path, help='Private contributions.sqlite3, opened read-only.')
    args = p.parse_args(argv)
    if not args.records and not args.database:
        p.error('Give record files or --database.')
    sources = []
    for path in args.records:
        data = json.loads(path.read_text())
        sources.append(data.get('record', data))  # the download reply wraps the record
    if args.database:
        from scripts.research_export import rows
        sources += [data for _, _, data in rows(args.database) if data.get('schema') == SCHEMA]
    failed = False
    for record in sources:
        try:
            report = research_replay.check(record)
        except (ValueError, KeyError, TypeError) as error:
            report = {'round_id': record.get('round_id'), 'error': type(error).__name__ + ': ' + str(error)[:200]}
        failed = failed or 'error' in report or report.get('replay') == 'diverged'
        print(json.dumps(report, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
