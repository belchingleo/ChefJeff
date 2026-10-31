"""Verify the game-side import closure paired with this private-console package."""
import hashlib
import json
from pathlib import Path


def verify_game_release(release, bundle):
    release = Path(release).resolve(strict=True)
    binding = json.loads((Path(bundle) / 'game-binding.json').read_text())
    if binding.get('format') != 'chefjeff-admin-game-binding-v1':
        raise ValueError('Unknown game binding format')
    files = binding['files']
    required = {'scripts/research_export.py', 'research_record.py', 'hosted_records.py',
                'schema_check.py', 'schemas/research-record.schema.json'}
    if not required <= files.keys():
        raise ValueError('Incomplete game binding')
    for name, expected in files.items():
        relative = Path(name)
        path = release / relative
        if (relative.is_absolute() or '..' in relative.parts or path.is_symlink()
                or not path.resolve().is_relative_to(release) or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError('Game binding mismatch: ' + name)
    return release
