"""Versioned English descriptions at the model boundary; keep game/log data intact."""
from functools import lru_cache
import json
from pathlib import Path
import re

INPUT_LANGUAGE_VERSION = 'en-v1'
_CATALOG = json.loads((Path(__file__).parent/'model-language-en-v1.json').read_text())
_MESSAGES = _CATALOG['messages']
_TEMPLATES = []
for source, target in _CATALOG['templates']:
    ids = []
    parts = []
    for part in re.split(r'(\{\d+\})', source):
        if re.fullmatch(r'\{\d+\}',part):
            ids.append(part[1:-1]);parts.append('(.*?)')
        else:parts.append(re.escape(part))
    literals=[x for x in re.split(r'\{\d+\}',source) if x]
    _TEMPLATES.append((re.compile('^'+''.join(parts)+'$',re.S),target,ids,literals))
_FRAGMENTS = re.compile('|'.join(map(re.escape,sorted(_MESSAGES,key=len,reverse=True))))

@lru_cache(maxsize=2048)
def english_text(text):
    if not re.search(r'[\u3400-\u9fff]',text):return text
    if text in _MESSAGES:return _MESSAGES[text]
    for pattern, template, ids, literals in _TEMPLATES:
        if any(part not in text for part in literals):continue
        match=pattern.fullmatch(text)
        if match:
            args=dict(zip(ids,match.groups()))
            return re.sub(r'\{(\d+)\}',lambda m:english_text(args[m[1]]),template)
    # Actions in event history include the same parenthetical annotations as criteria.
    if '（' in text:
        head,tail=text.split('（',1)
        return english_text(head)+' ('+english_text(tail.rstrip('）'))+')'
    return _FRAGMENTS.sub(lambda m:_MESSAGES[m[0]],text)

def english_data(value):
    if isinstance(value,str):return english_text(value)
    if isinstance(value,dict):return {key:(item if key in ('model', 'actual_model', 'id', 'choice', 'action') else english_data(item)) for key,item in value.items()}
    if isinstance(value,list):return [english_data(item) for item in value]
    if isinstance(value,tuple):return tuple(english_data(item) for item in value)
    return value
