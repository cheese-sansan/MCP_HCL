"""Acceptance-only subprocess tripwire, also installed in SDK server children."""
import json
import os
from pathlib import Path
import sys
import shlex

audit_root=os.environ.get('MCP_SOFTWARE_NATIVE_AUDIT_ROOT')
if audit_root:
    def observe(event,args):
        if event not in {'subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn'}:
            return
        executable=args[0];command=args[1] if event=='subprocess.Popen' else []
        if isinstance(command,str):
            command=[token.strip('"') for token in shlex.split(command,posix=False)]
        allowed=(event=='subprocess.Popen' and isinstance(command,(list,tuple))
            and len(command)==3 and list(command[1:])==['-m','mcp_hcl.server']
            and Path(command[0]).resolve()==Path(sys.executable).resolve()
            and (executable is None or Path(executable).resolve()==Path(sys.executable).resolve()))
        executable=str(executable or (command[0] if command else 'unknown'))
        row={'event':event,'executable':executable,'allowed':allowed}
        with (Path(audit_root)/('native-'+str(os.getpid())+'.jsonl')).open('a',encoding='utf-8') as log:
            log.write(json.dumps(row)+'\n')
        if not allowed:raise AssertionError('Unexpected external process in software acceptance')
    sys.addaudithook(observe)
