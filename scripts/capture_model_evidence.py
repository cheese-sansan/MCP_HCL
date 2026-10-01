"""Capture read-only model/port facts, never infer a verified port mapping."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from mcp_hcl.project import ProjectStore


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-directory',type=Path,required=True)
    parser.add_argument('--configuration-file',type=Path,required=True)
    parser.add_argument('--model',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    directory=args.project_directory.resolve();configuration=args.configuration_file.resolve()
    if configuration.is_symlink() or configuration.stat().st_size>1024*1024: raise ValueError('Configuration must be a bounded regular file')
    store=ProjectStore([directory],args.output.parent/'unused-stage-output')
    document=store._open(str(directory))
    sections=[s for s in document.sections.values() if s.model==args.model]
    if not sections: raise ValueError('Model is not present in the supplied real project template')
    text=configuration.read_text(encoding='utf-8-sig')
    interfaces=re.findall(r'^interface\s+([A-Za-z][\w/.-]*)\s*$',text,re.M)
    version=re.search(r'^\s*version\s+(.+)$',text,re.M)
    result={'schema_version':1,'model':args.model,'firmware':version[1] if version else None,
            'interfaces':interfaces,'source_templates':[{'name':s.name,'slots':{k:v for k,v in s.fields.items() if k.startswith('slot')}} for s in sections],
            'evidence':[{'source':str(document.net_path),'sha256':hashlib.sha256(document.net_path.read_bytes()).hexdigest()},
                        {'source':str(configuration),'sha256':hashlib.sha256(configuration.read_bytes()).hexdigest()}],
            'mapping_verified':False,'factory_defaults_verified':False,'runtime_verified':False,
            'remaining':['Independent model identity, scene/CLI mapping and wireless association command evidence']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists(): raise ValueError('Evidence outputs are immutable; choose a new filename')
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'model':args.model,'interfaces':len(interfaces),'mapping_verified':False}))


if __name__=='__main__': main()
