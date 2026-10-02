"""Read-only supplier-document hash verification; starts no HCL/VM process."""
import argparse
import hashlib
import json
from importlib.resources import files
from pathlib import Path
from mcp_hcl.command_reference import verify_installed_reference


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root',type=Path,default=Path('D:/HCL'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=verify_installed_reference(args.install_root)
    platform=json.loads(files('mcp_hcl').joinpath('data/platform_reference.json').read_text(encoding='utf-8'))
    terminal=json.loads(files('mcp_hcl').joinpath('data/native_terminal_reference.json').read_text(encoding='utf-8'))
    platform['evidence'] += terminal['evidence']
    result['platform_sources']=[]
    for source in platform['evidence']:
        path=args.install_root/source['source']
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
        result['platform_sources'].append({**source,'matches':actual==source['sha256']})
    result['all_match']=result['all_match'] and all(row['matches'] for row in result['platform_sources'])
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'all_match':result['all_match'],'sources':len(result['sources'])+len(result['platform_sources']),
                      'runtime_verified':False}))
    return 0 if result['all_match'] else 1


if __name__=='__main__':
    raise SystemExit(main())
