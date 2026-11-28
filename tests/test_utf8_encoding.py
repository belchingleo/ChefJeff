"""Core modules, scenarios and top-level scripts must not depend on the OS locale codec."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _missing_encoding_calls(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kw = {k.arg for k in node.keywords if k.arg}
        if isinstance(node.func, ast.Attribute) and node.func.attr in ('read_text', 'write_text'):
            needed = 1 if node.func.attr == 'read_text' else 2
            if 'encoding' not in kw and len(node.args) < needed:
                bad.append((node.lineno, node.func.attr))
        elif isinstance(node.func, ast.Name) and node.func.id == 'open':
            mode = _const_str(node, 1, 'mode')
            if not (mode and 'b' in mode) and 'encoding' not in kw and len(node.args) < 4:
                bad.append((node.lineno, 'open'))
        elif (isinstance(node.func, ast.Attribute) and node.func.attr == 'fdopen'
              and isinstance(node.func.value, ast.Name) and node.func.value.id == 'os'):
            mode = _const_str(node, 1, 'mode')
            if not (mode and 'b' in mode) and 'encoding' not in kw and len(node.args) < 5:
                bad.append((node.lineno, 'os.fdopen'))
        elif (isinstance(node.func, ast.Attribute) and node.func.attr in ('NamedTemporaryFile', 'TemporaryFile')
              and isinstance(node.func.value, ast.Name) and node.func.value.id == 'tempfile'):
            mode = _const_str(node, 0, 'mode')
            if mode and 'b' not in mode and 'encoding' not in kw and len(node.args) < 3:
                bad.append((node.lineno, f'tempfile.{node.func.attr}'))
        elif (isinstance(node.func, ast.Attribute) and node.func.attr in ('run', 'Popen', 'check_output')
              and isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess'):
            text_arg = next((k.value for k in node.keywords if k.arg in ('text', 'universal_newlines')), None)
            if isinstance(text_arg, ast.Constant) and text_arg.value is True and 'encoding' not in kw:
                bad.append((node.lineno, f'subprocess.{node.func.attr}'))
    return bad


def _const_str(call, index, name):
    if len(call.args) > index and isinstance(call.args[index], ast.Constant) and isinstance(call.args[index].value, str):
        return call.args[index].value
    for k in call.keywords:
        if k.arg == name and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str):
            return k.value.value
    return None


class Utf8EncodingTests(unittest.TestCase):
    def test_runtime_modules_and_scripts_pass_explicit_encoding(self):
        targets = (
            sorted(ROOT.glob('*.py'))
            + sorted((ROOT / 'scenarios').rglob('*.py'))
            + sorted((ROOT / 'scripts').glob('*.py'))
        )
        violations = []
        for path in targets:
            for lineno, kind in _missing_encoding_calls(path):
                violations.append(f'{path.relative_to(ROOT)}:{lineno}: {kind}() missing encoding')
        self.assertEqual(violations, [])

    def test_core_modules_load_and_run_under_non_utf8_locale(self):
        script = (
            'import importlib, json, os, pathlib, sys, tempfile\n'
            'root = pathlib.Path(sys.argv[1])\n'
            'sys.path.insert(0, str(root))\n'
            'for path in sorted(root.glob("*.py")):\n'
            '    try:\n'
            '        importlib.import_module(path.stem)\n'
            '    except ModuleNotFoundError as exc:\n'
            '        if os.name == "nt" and exc.name in ("fcntl", "pwd", "grp", "termios", "resource"):\n'
            '            continue\n'
            '        raise\n'
            'import config_contract as cc, hosted_server\n'
            'from cooperation_memory import CooperationMemory\n'
            'from environment import AgentPort\n'
            'from spatial_kitchen import SpatialKitchen\n'
            'for lvl in ("level-1", "level-2", "level-3", "level-4", "level-5"):\n'
            '    k = SpatialKitchen(cc.load_level(lvl, seeds={"spawn": 0, "orders": 0}))\n'
            '    obs = AgentPort(k, "jeff").observe()\n'
            '    assert obs["env_api_version"] == "env-v1"\n'
            'rendered = hosted_server.hosted_html((root / "cocos-kitchen/build/web/index.html").read_bytes())\n'
            'assert len(rendered) > 100\n'
            'with tempfile.TemporaryDirectory() as d:\n'
            '    p = pathlib.Path(d) / "mem.json"\n'
            '    m = CooperationMemory(p)\n'
            '    m.save({"version": 1, "enabled": True, "scopes": {"s": [{"round_id": "r1", "outcome": {"note": "\\u4e2d\\u6587"}, "duration": 1.0, "events": []}]}})\n'
            '    reloaded = CooperationMemory(p)\n'
            '    assert reloaded.error is None\n'
            '    assert reloaded.data["scopes"]["s"][0]["outcome"]["note"] == "\\u4e2d\\u6587"\n'
        )
        env = dict(os.environ, PYTHONUTF8='0', PYTHONCOERCECLOCALE='0', LC_ALL='C', LANG='C',
                   PYTHONDONTWRITEBYTECODE='1')
        with tempfile.TemporaryDirectory() as tmp:
            env['CHEFJEFF_LOG_DIR'] = tmp
            proc = subprocess.run(
                [sys.executable, '-X', 'utf8=0', '-c', script, str(ROOT)],
                cwd=tmp, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=30,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)


if __name__ == '__main__':
    unittest.main()
