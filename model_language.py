"""Versioned English descriptions at the model boundary; keep game/log data intact."""
from functools import lru_cache
import json
from pathlib import Path
import re

INPUT_LANGUAGE_VERSION = 'en-v2'
_CATALOG = json.loads((Path(__file__).parent/'model-language-en-v2.json').read_text())
_MESSAGES = _CATALOG['messages']
# Chefs are named by their state keys (human, jeff) so "you" in the rules only ever means the model's own chef.
_ACTORS = _CATALOG['actors']
# Model input is plain ASCII English: remaining CJK punctuation and symbols are spelled out.
_ASCII = _CATALOG['ascii']
_ASCII_CHARS = re.compile('|'.join(map(re.escape, _ASCII)))
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

def _ascii(text):
    text=re.sub(r'¥\s*(-?\d+(?:\.\d+)?)',r'\1 yuan',text)
    return re.sub(r'  +',' ',_ASCII_CHARS.sub(lambda m:_ASCII[m[0]],text)).replace(' )',')')


@lru_cache(maxsize=2048)
def english_text(text):
    return _ascii(_english(text))


def _english(text):
    if not re.search(r'[\u3400-\u9fff]',text):return text
    if text in _MESSAGES:return _MESSAGES[text]
    for pattern, template, ids, literals in _TEMPLATES:
        if any(part not in text for part in literals):continue
        match=pattern.fullmatch(text)
        if match:
            args=dict(zip(ids,match.groups()))
            return re.sub(r'\{(\d+)\}',lambda m:_ACTORS.get(args[m[1]]) or _english(args[m[1]]),template)
    # Actions in event history include the same parenthetical annotations as criteria.
    if '（' in text:
        head,tail=text.split('（',1)
        return _english(head)+' ('+_english(tail.rstrip('）'))+')'
    return _FRAGMENTS.sub(lambda m:_MESSAGES[m[0]],text)

def english_data(value):
    if isinstance(value,str):return english_text(value)
    if isinstance(value,dict):return {key:(item if key in ('model', 'actual_model', 'id', 'choice', 'action') else english_data(item)) for key,item in value.items()}
    if isinstance(value,list):return [english_data(item) for item in value]
    if isinstance(value,tuple):return tuple(english_data(item) for item in value)
    return value
