"""Private installation state and immutable source verification; no player data operations."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, data, mode=0o600):
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('Unexpected installation path')
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), mode); output.write(data); output.flush(); os.fsync(output.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def public_release(release, manifest_sha):
    release = Path(release).resolve(strict=True)
    if (not re.fullmatch(r'/opt/chefjeff/releases/[a-z0-9-]+/chefjeff-web-demo', str(release))
            or not re.fullmatch(r'[0-9a-f]{64}', manifest_sha)
            or digest(release/'release-manifest.json') != manifest_sha):
        raise ValueError('Pinned release manifest does not match')
    manifest = json.loads((release/'release-manifest.json').read_text())
    if not isinstance(manifest.get('files'), dict) or not 500 <= len(manifest['files']) <= 1000:
        raise ValueError('Unexpected release manifest')
    for name, expected in manifest['files'].items():
        relative = Path(name)
        if (relative.is_absolute() or any(p.startswith('.') or p == '..' for p in relative.parts)
                or relative.suffix.lower() in ('.sqlite3', '.sqlite', '.db', '.pem', '.key', '.env')):
            raise ValueError('Release may contain only public application files')
        path = release/relative
        if not path.resolve().is_relative_to(release) or path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError('Immutable release file verification failed')
    return release, manifest


def property_of(unit, name):
    return subprocess.check_output(['systemctl','show',unit,'--property='+name,'--value'], text=True).strip()


def work_path(kind, manifest_sha):
    path = Path('/root')/('chefjeff-free-'+kind+'-'+manifest_sha[:12])
    if path.is_symlink(): raise ValueError('Unexpected work directory')
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def save(work, state):
    atomic(work/'state.json', (json.dumps(state, indent=2)+'\n').encode())


def load(work):
    return json.loads((work/'state.json').read_text())
