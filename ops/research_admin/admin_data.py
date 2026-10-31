"""Read-only, allowlisted research projections. No model/game commands or store constructors."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from types import FunctionType
import zipfile

SCHEMAS = ('chefjeff-pilot-session-v1', 'chefjeff-pilot-session-v2')
FIELDS = ('started_at', 'ended_at', 'level', 'schema', 'duration', 'quality.complete',
          'conditions.model_identity.provider', 'conditions.model_identity.model_id',
          'result.served', 'result.money', 'result.won', 'termination.session_close.reason')
GROUPS = {'day': '日期 · UTC', 'level': '关卡', 'model': '模型（浏览器上报）',
          'quality': '记录完整性', 'end_reason': '结束原因', 'site': '游戏入口站点'}
SITES = {'cn':'国内站 · 上海', 'global':'海外站 · 德国', 'unknown':'来源未知'}
REGION_COUNTERS = ('page_views','started_sessions','started_rounds','completed_rounds','manual_ends',
                   'estimated_visitor_browsers','estimated_player_browsers')
METRICS = {'records': ('贡献记录数', '条'), 'avg_duration': ('平均记录时长', '秒'),
           'avg_served': ('平均出餐数', '份'), 'avg_money': ('平均金额', '游戏内金额'),
           'win_rate': ('已结束贡献胜率', '%'), 'complete_rate': ('完整记录率', '%')}


class RecordGone(Exception):
    pass


def reference(identifier):
    return hashlib.sha256(identifier.encode()).hexdigest()[:24]


def connection(database):
    db = sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro', uri=True, timeout=2)
    db.execute('PRAGMA query_only=ON')
    return db


def clause(selected):
    conditions = ["expires>?", "json_extract(record,'$.schema') IN (?,?)"]
    args = [time.time(), *SCHEMAS]
    for key in ('level', 'schema'):
        if key in selected:
            conditions.append(f"json_extract(record,'$.{key}')=?")
            args.append(selected[key])
    for key, operator in (('since', '>='), ('until', '<')):
        if key in selected:
            conditions.append(f"julianday(json_extract(record,'$.started_at')) {operator} julianday(?)")
            args.append(selected[key])
    return ' AND '.join(conditions), args


def metadata(database, selected, page=None):
    where, args = clause(selected)
    projection = ','.join("json_extract(record,'$."+field+"')" for field in FIELDS)
    query = 'SELECT id,expires,'+projection+",json_type(record,'$.result.won'),json_type(record,'$.quality.complete') FROM records WHERE "+where
    query += " ORDER BY json_extract(record,'$.started_at') DESC,id DESC"
    query += ' LIMIT 5001'
    db = connection(database)
    try:
        raw = db.execute(query, args).fetchall()
    finally:
        db.close()
    if len(raw)>5000:
        raise ValueError('记录过多，请缩短日期范围。')
    result = []
    sites = source_index(database)['sources']
    for identifier, expiry, *values in raw:
        row = dict(zip(FIELDS, values[:len(FIELDS)]))
        row.update(ref=reference(identifier), expires=expiry,
                   won_known=values[-2] in ('true', 'false'), complete_known=values[-1] in ('true', 'false'))
        row['site'] = sites.get(row['ref'],'unknown')
        row['site_label'] = SITES[row['site']]
        if selected.get('site') and row['site']!=selected['site']:
            continue
        result.append(row)
    return result if page is None else result[(page-1)*50:page*50]


def index(database, selected, page):
    rows = metadata(database,selected)
    return {'total': len(rows), 'page': page, 'page_size': 50, 'records': rows[(page-1)*50:page*50]}


def source_index(database):
    path = Path(database).parent/'record-sources.sqlite3'
    if not path.exists():
        return {'tracking_since':None, 'sources':{}}
    db = connection(path)
    try:
        tracking = db.execute('SELECT tracking_since FROM meta WHERE id=1').fetchone()
        sources = {ref:site for ref,site in db.execute('SELECT ref,site FROM sources WHERE expires>?',(time.time(),)) if site in ('cn','global')}
    finally:
        db.close()
    return {'tracking_since':tracking[0] if tracking else None, 'sources':sources}


def regional_usage(database):
    db = connection(Path(database).parent/'usage.sqlite3')
    try:
        db.execute('BEGIN')  # Totals and stream checkpoints must come from one snapshot.
        row = db.execute('SELECT tracking_since,'+','.join(REGION_COUNTERS)+' FROM totals WHERE id=1').fetchone()
        if row is None:
            raise ValueError('统计尚不可用。')
        tracking, *values = row
        totals = dict(zip(REGION_COUNTERS,values))
        sites = {site:dict.fromkeys(REGION_COUNTERS,0) for site in ('cn','global')}
        for site, raw in db.execute('SELECT site,aggregate FROM shared_streams'):
            if site not in sites:
                continue
            aggregate = json.loads(raw)['counts']
            for key in REGION_COUNTERS:
                value = aggregate[key]
                if type(value) is not int or value<0:
                    raise ValueError('分站累计值无效。')
                sites[site][key] += value
        unknown = {key:totals[key]-sum(v[key] for v in sites.values()) for key in REGION_COUNTERS}
        if any(type(value) is not int or value<0 for value in unknown.values()):
            raise ValueError('分站统计与总量不一致，请稍后核对。')
    finally:
        db.close()
    return {'tracking_since':tracking,'totals':totals,'sites':[{'site':site,'label':SITES[site],**counts} for site,counts in [*sites.items(),('unknown',unknown)]],
            'note':'按现存共享累计检查点拆分；迁移前无法归属的历史总量单列。这里的国内/海外指游戏入口，不是玩家所在地。'}


def available_levels(database):
    db = connection(database)
    try:
        rows = db.execute("SELECT DISTINCT json_extract(record,'$.level') FROM records WHERE expires>? "
                          "AND json_extract(record,'$.schema') IN (?,?) AND json_type(record,'$.level')='integer' "
                          "ORDER BY 1", (time.time(), *SCHEMAS)).fetchall()
    finally:
        db.close()
    return [r[0] for r in rows if 1 <= r[0] <= 999999]


def references(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 50 or
            any(not isinstance(r, str) or not re.fullmatch(r'[a-f0-9]{24}', r) for r in value) or
            len(set(value)) != len(value)):
        raise ValueError('请勾选1至50条不同的记录。')
    return value


def selected_rows(database, refs, **unused):
    """Look up pseudonymous references without selecting deletion hashes or credentials."""
    refs = references(refs)
    db = connection(database)
    try:
        identifiers = db.execute('SELECT id FROM records WHERE expires>?', (time.time(),)).fetchall()
        mapped = {}
        for (identifier,) in identifiers:
            ref = reference(identifier)
            if ref in mapped:
                raise ValueError('记录引用不唯一。')
            mapped[ref] = identifier
        if any(ref not in mapped for ref in refs):
            raise RecordGone()
        for ref in refs:
            row = db.execute('SELECT expires,record FROM records WHERE id=? AND expires>?',
                             (mapped[ref], time.time())).fetchone()
            if row is None:
                raise RecordGone()
            expiry, raw = row
            if len(raw.encode()) > 13_000_000:
                raise ValueError('记录过大。')
            yield mapped[ref], expiry, json.loads(raw)
    finally:
        db.close()


def selected_exporter(exporter, refs=None, site=None):
    # Copy only the function's globals for this request. Never monkeypatch shared modules
    # or change the trusted export/validation logic in the installed game release.
    def projected_rows(database, **kw):
        sources = source_index(database)['sources'] if site else {}
        iterator = selected_rows(database, refs, **kw) if refs is not None else exporter.__globals__['rows'](database,**kw)
        for identifier,expiry,record in iterator:
            if site is None or sources.get(reference(identifier),'unknown')==site:
                yield identifier,expiry,record
    environment = {**exporter.__globals__, 'rows': projected_rows}
    return FunctionType(exporter.__code__, environment, exporter.__name__, exporter.__defaults__, exporter.__closure__)


def preview(database, ref, exporter, offset=0, event_type=''):
    identifier, expiry, record = list(selected_rows(database, [ref]))[0]
    environment = exporter.__globals__
    if record.get('schema') == environment['SCHEMA']:
        environment['validate_record'](record)
    elif record.get('schema') == SCHEMAS[0]:
        if environment['schema_check'].validate(record, 'research-legacy-v1.schema.json'):
            raise ValueError('旧记录未通过字段校验。')
    else:
        raise ValueError('记录版本尚不兼容。')
    events = record.get('events', [])
    types = sorted({event.get('type', 'unknown') for event in events if isinstance(event, dict)})
    filtered = [event for event in events if not event_type or event.get('type') == event_type]
    origin=source_index(database)
    site=origin['sources'].get(ref,'unknown')
    return {'ref': ref, 'expires': expiry, 'site':site, 'site_label':SITES[site], 'source_tracking_since':origin['tracking_since'],
            'metadata': {k:v for k,v in record.items() if k not in ('events','resolved_config')},
            'config': record.get('resolved_config'), 'events': filtered[offset:offset+50], 'event_total': len(filtered),
            'event_types': types, 'offset': offset, 'page_size': 50, 'legacy': record.get('schema') == SCHEMAS[0]}


def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) else None


def group_label(row, group):
    if group == 'site':
        return row['site_label']
    if group == 'day':
        try:
            stamp = datetime.fromisoformat((row.get('started_at') or '').replace('Z','+00:00'))
            return stamp.astimezone(timezone.utc).date().isoformat() if stamp.tzinfo else '未知日期'
        except ValueError:
            return '未知日期'
    if group == 'level':
        return '第 '+str(row['level'])+' 关' if row['level'] is not None else '未知关卡'
    if group == 'model':
        return ' / '.join(str(row.get(k) or '') for k in ('conditions.model_identity.provider','conditions.model_identity.model_id')).strip(' /') or '未知模型'
    if group == 'quality':
        return ('完整' if row['quality.complete'] else '不完整快照') if row['complete_known'] else '旧版或未知'
    return row['termination.session_close.reason'] or '未知结束原因'


def add_source_artifact(package, database, manifest):
    origin=source_index(database)
    source={'format':'chefjeff-record-source-index-v1','meaning':'authenticated_game_entry_not_player_location',
            'tracking_since':origin['tracking_since'], 'expires':manifest['expires'],
            'records':[{'source_ref':s['source_ref'],'site':origin['sources'].get(s['source_ref'],'unknown')} for s in manifest['sources']]}
    raw=json.dumps(source,ensure_ascii=False,separators=(',',':')).encode()
    replacement=Path(package).with_suffix('.with-sites.zip')
    artifact={'path':'source-sites.json','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    manifest={**manifest,'artifacts':[*manifest['artifacts'],artifact]}
    try:
        with zipfile.ZipFile(package) as old, zipfile.ZipFile(replacement,'w',zipfile.ZIP_DEFLATED) as new:
            for info in old.infolist():
                if info.filename!='manifest.json':
                    new.writestr(info,old.read(info.filename))
            new.writestr('source-sites.json',raw)
            new.writestr('manifest.json',json.dumps(manifest,separators=(',',':')))
        replacement.chmod(0o600)
        replacement.replace(package)
    finally:
        replacement.unlink(missing_ok=True)
    return manifest


def analysis(database, selected, group, metric, refs=None):
    if group not in GROUPS or metric not in METRICS:
        raise ValueError('请使用支持的分组和指标。')
    rows = metadata(database, selected)
    if refs is not None:
        refs = references(refs)
        rows = [row for row in rows if row['ref'] in refs]
        if set(row['ref'] for row in rows) != set(refs):
            raise RecordGone()
    grouped = defaultdict(list)
    for row in rows:
        if metric == 'records':
            value = 1
        elif metric == 'win_rate':
            value = 100*row['result.won'] if row['won_known'] and row['ended_at'] else None
        elif metric == 'complete_rate':
            value = 100*row['quality.complete'] if row['complete_known'] else None
        else:
            value = number(row[{'avg_duration':'duration','avg_served':'result.served','avg_money':'result.money'}[metric]])
        grouped[group_label(row, group)].append(value)
    groups = []
    for label, values in sorted(grouped.items()):
        valid = [v for v in values if v is not None]
        groups.append({'label': label, 'records': len(values), 'eligible': len(valid), 'excluded': len(values)-len(valid),
                       'value': (sum(valid) if metric=='records' else sum(valid)/len(valid)) if valid else None})
    description=[SITES.get(selected.get('site'),'全部站点')]
    if 'level' in selected:description.append('第 '+str(selected['level'])+' 关')
    if 'since' in selected or 'until' in selected:
        description.append('UTC ['+selected.get('since','不限')[:10]+', '+selected.get('until','不限')[:10]+')')
    return {'group': group, 'metric': metric, 'group_label': GROUPS[group], 'metric_label': METRICS[metric][0],
            'unit': METRICS[metric][1], 'records': len(rows), 'eligible': sum(g['eligible'] for g in groups),
            'filters':dict(selected),'filter_label':' · '.join(description),
            'groups': groups, 'population': '已选贡献记录' if refs is not None else '筛选范围内的全部有效贡献记录',
            'scope_note': '仅代表玩家同意且仍有效的贡献记录，不代表所有访问或所有对局；未知值不按0计。'}
