#!/usr/bin/env python3
"""Regenerate the sample capacity reports in docs/architecture/reports/ (seeds: orders 1, spawn 0)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import capacity_analyzer  # noqa: E402
import config_contract  # noqa: E402

SAMPLES = ('level-1', 'level-2', 'level-3')


def main():
    folder = ROOT / 'docs' / 'architecture' / 'reports'
    folder.mkdir(parents=True, exist_ok=True)
    for level in SAMPLES:
        bundle = config_contract.level_bundle(level, embed=True)
        bundle['level']['seeds'] = {'orders': 1, 'spawn': 0}
        report = capacity_analyzer.analyze_capacity(config_contract.freeze_bundle(bundle))
        (folder / f'{level}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(level, report['I_resource_lb_game_ms'], report['binding_resource'], [d['code'] for d in report['diagnostics']])


if __name__ == '__main__':
    main()
