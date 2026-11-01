"""Bounded private gateway operational summaries; never player IDs, prompts or keys."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from model_status import clean


class Diagnostics:
    def __init__(self,directory=None):
        self.directory=Path(directory) if directory is not None else None
        self.data={'version':1,'providers':{p:{'upstream_attempts':0,'last_result':{}} for p in ('zhipu','startlux')}}
        if self.directory is not None:
            path=self.directory/'diagnostics.json'
            if path.exists():
                try:
                    if path.is_symlink() or path.stat().st_size>65536 or path.stat().st_mode&0o077:raise ValueError()
                    old=json.loads(path.read_text())
                    for p in self.data['providers']:
                        value=old['providers'][p];n=value['upstream_attempts']
                        if type(n) is not int or not 0<=n<=1000000000:raise ValueError()
                        self.data['providers'][p]={'upstream_attempts':n,'last_result':clean(value['last_result'])}
                except Exception:pass  # Diagnostics never reset the independently locked call budget.

    def record(self,value):
        safe=clean(value);provider=safe.get('provider')
        if provider not in self.data['providers']:return False
        row=self.data['providers'][provider]
        if safe.get('upstream_called') is True:row['upstream_attempts']=min(1000000000,row['upstream_attempts']+1)
        row['last_result']=safe
        if self.directory is None:return True
        temp=None
        try:
            fd,name=tempfile.mkstemp(prefix='.diagnostic-',dir=self.directory);temp=Path(name)
            with os.fdopen(fd,'w') as output:
                os.fchmod(output.fileno(),0o600);json.dump(self.data,output,separators=(',',':'),allow_nan=False)
                output.flush();os.fsync(output.fileno())
            temp.replace(self.directory/'diagnostics.json');return True
        except Exception:return False
        finally:
            if temp is not None:temp.unlink(missing_ok=True)

    def snapshot(self):return deepcopy(self.data)
