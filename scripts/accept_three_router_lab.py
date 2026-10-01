"""Run only after the user boots and starts the isolated HCL lab in the GUI."""
import argparse
import json
from pathlib import Path
from mcp_hcl.server import create_store,live_writes_enabled
from mcp_hcl.catalog import HclCatalog
from mcp_hcl.deployment import Deployment
from mcp_hcl.live_acceptance import accept_lab
import os


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-directory',required=True)
    parser.add_argument('--topology',required=True)
    parser.add_argument('--gui-receipt',required=True)
    args=parser.parse_args()
    engine=Deployment(create_store(),catalog=HclCatalog(Path(os.environ.get('MCP_HCL_INSTALL_ROOT','D:/HCL'))),writes_enabled=live_writes_enabled())
    result=accept_lab(engine,args.project_directory,args.topology,args.gui_receipt)
    print(json.dumps({'status':result['status'],'operation_id':result['operation_id'],'full_live_gate_passed':result['full_live_gate_passed']}))
    return 0 if result.get('network_gate_passed') else 1


if __name__=='__main__': raise SystemExit(main())
