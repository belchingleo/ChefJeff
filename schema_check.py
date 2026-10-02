"""Standard-library validator for the JSON Schema subset used in ``schemas/``.

The schema files are the formal contract (Draft 2020-12). This module checks
instances against them without third-party dependencies and never fetches
remote schemas: ``$ref`` resolves only to files in ``schemas/``. A test keeps
the schema files within ``SUPPORTED_KEYWORDS``.
"""
from __future__ import annotations
import json
import math
import re
from functools import lru_cache
from pathlib import Path

SCHEMA_ROOT = Path(__file__).resolve().parent / 'schemas'
ANNOTATIONS = {'$schema', '$id', 'title', 'description', '$defs'}
SUPPORTED_KEYWORDS = ANNOTATIONS | {
    '$ref', 'type', 'const', 'enum', 'required', 'properties', 'additionalProperties', 'propertyNames',
    'minProperties', 'items', 'minItems', 'maxItems', 'minimum', 'maximum', 'exclusiveMinimum',
    'minLength', 'maxLength', 'pattern', 'oneOf'}


@lru_cache(maxsize=None)
def load_schema(name):
    path = (SCHEMA_ROOT / name).resolve()
    if path.parent != SCHEMA_ROOT or not path.is_file():
        raise ValueError(f'unknown schema {name!r}')
    return json.loads(path.read_text(encoding='utf-8'))


def _resolve(ref, base):
    file, _, pointer = ref.partition('#')
    name = file or base
    node = load_schema(name)
    for part in [p for p in pointer.split('/') if p]:
        node = node[part.replace('~1', '/').replace('~0', '~')]
    return node, name


def _type_ok(value, expected):
    if expected == 'null':
        return value is None
    if expected == 'boolean':
        return isinstance(value, bool)
    if expected == 'integer':
        return (isinstance(value, int) and not isinstance(value, bool)) or (
            isinstance(value, float) and math.isfinite(value) and value.is_integer())
    if expected == 'number':
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if expected == 'string':
        return isinstance(value, str)
    if expected == 'array':
        return isinstance(value, list)
    if expected == 'object':
        return isinstance(value, dict)
    raise ValueError(f'unsupported type {expected!r}')


def _path(path):
    return '/' + '/'.join(str(p) for p in path)


def check(value, schema, base, path=()):
    """Yield (field_path, message) for every violation."""
    if schema is True or schema == {}:
        return
    if schema is False:
        yield _path(path), 'not allowed'
        return
    if '$ref' in schema:
        target, name = _resolve(schema['$ref'], base)
        yield from check(value, target, name, path)
    if 'type' in schema:
        types = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
        if not any(_type_ok(value, t) for t in types):
            yield _path(path), f'expected {"/".join(types)}'
            return
    if isinstance(value, float) and not math.isfinite(value):
        yield _path(path), 'non-finite number'
        return
    if 'const' in schema and (value != schema['const'] or (type(value) is bool) != (type(schema['const']) is bool)):
        yield _path(path), f'must be {schema["const"]!r}'
    if 'enum' in schema and not any(value == v and (type(value) is bool) == (type(v) is bool) for v in schema['enum']):
        yield _path(path), f'must be one of {schema["enum"]!r}'
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    if numeric:
        if 'minimum' in schema and value < schema['minimum']:
            yield _path(path), f'must be >= {schema["minimum"]}'
        if 'maximum' in schema and value > schema['maximum']:
            yield _path(path), f'must be <= {schema["maximum"]}'
        if 'exclusiveMinimum' in schema and value <= schema['exclusiveMinimum']:
            yield _path(path), f'must be > {schema["exclusiveMinimum"]}'
    if isinstance(value, str):
        if 'minLength' in schema and len(value) < schema['minLength']:
            yield _path(path), 'too short'
        if 'maxLength' in schema and len(value) > schema['maxLength']:
            yield _path(path), 'too long'
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            yield _path(path), f'does not match {schema["pattern"]}'
    if isinstance(value, list):
        if 'minItems' in schema and len(value) < schema['minItems']:
            yield _path(path), f'needs at least {schema["minItems"]} items'
        if 'maxItems' in schema and len(value) > schema['maxItems']:
            yield _path(path), f'allows at most {schema["maxItems"]} items'
        if 'items' in schema:
            for i, item in enumerate(value):
                yield from check(item, schema['items'], base, path + (i,))
    if isinstance(value, dict):
        for key in schema.get('required', ()):
            if key not in value:
                yield _path(path + (key,)), 'is required'
        if 'minProperties' in schema and len(value) < schema['minProperties']:
            yield _path(path), f'needs at least {schema["minProperties"]} entries'
        properties = schema.get('properties', {})
        for key, item in value.items():
            if 'propertyNames' in schema:
                yield from ((p, 'invalid key: ' + m) for p, m in check(key, schema['propertyNames'], base, path + (key,)))
            if key in properties:
                yield from check(item, properties[key], base, path + (key,))
            elif 'additionalProperties' in schema:
                extra = schema['additionalProperties']
                if extra is False:
                    yield _path(path + (key,)), 'unknown field'
                elif extra is not True:
                    yield from check(item, extra, base, path + (key,))
    if 'oneOf' in schema:
        matches = [list(check(value, option, base, path)) for option in schema['oneOf']]
        valid = sum(not m for m in matches)
        if valid != 1:
            best = min(matches, key=len) if valid == 0 else []
            yield from best if best else [(_path(path), 'must match exactly one alternative')]


def validate(value, schema_name):
    """Return a list of (field_path, message); empty when valid."""
    return list(check(value, load_schema(schema_name), schema_name))


def keywords_used(node=None, found=None):
    """All keywords appearing in schema positions (for the subset guard test)."""
    found = set() if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key in ('properties', '$defs'):
                for sub in value.values():
                    keywords_used(sub, found)
            elif key in ('items', 'additionalProperties', 'propertyNames'):
                keywords_used(value, found)
            elif key == 'oneOf':
                for sub in value:
                    keywords_used(sub, found)
    return found
