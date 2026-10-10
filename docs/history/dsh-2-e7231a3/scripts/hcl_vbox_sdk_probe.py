"""Compare verified Oracle SDK declarations without installing or invoking COM."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HASHES = {'6.0.14': 'c7b848034939fa65be095752109009ad0c3733e5d10c09fd26b5addaf58ba159',
          '6.1.50': 'fb4ed0430f044016711e9727440fcc22c75e1d3b95f2f4d3f144832627553997'}
MEMBERS = {
    'IVirtualBox': ['findMachine', 'createMachine', 'openMachine', 'registerMachine', 'createMedium'],
    'IMachine': ['cloneTo', 'saveSettings', 'lockMachine', 'launchVMProcess', 'attachDevice',
                 'getNetworkAdapter', 'getSerialPort', 'chipsetType', 'memorySize', 'name', 'settingsFilePath'],
    'INetworkAdapter': ['enabled', 'adapterType', 'attachmentType', 'MACAddress', 'cableConnected',
                        'hostOnlyInterface', 'internalNetwork', 'NATNetwork'],
    'ISerialPort': ['enabled', 'path', 'hostMode', 'server'],
    'ISession': ['unlockMachine', 'machine'],
}
ENUMS = ['CloneMode', 'CloneOptions', 'ChipsetType', 'NetworkAdapterType', 'NetworkAttachmentType',
         'PortMode', 'LockType', 'MachineState', 'DeviceType', 'AccessMode', 'StorageBus', 'CPUPropertyType']


def read_sdk(path: Path, version: str) -> dict:
    if path.is_symlink() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('SDK is missing, linked or oversized')
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != HASHES[version]: raise ValueError('Official SDK SHA256 mismatch')
    with zipfile.ZipFile(path) as archive:
        xml = archive.read('sdk/bindings/VirtualBox.xidl')
        python = archive.read('sdk/installer/vboxapi/__init__.py').decode('utf-8-sig')
        constants = archive.read('sdk/installer/vboxapi/VirtualBox_constants.py').decode('utf-8-sig')
    document = ET.fromstring(xml)
    # Coclass references also use <interface name=...>, but have no UUID or
    # members. They are not interface declarations and must not shadow them.
    interfaces = {row.attrib['name']: row for row in document.iter('interface') if 'uuid' in row.attrib}
    declarations = {}
    for name, names in MEMBERS.items():
        interface = interfaces.get(name)
        if interface is None: raise ValueError('Expected SDK interface is absent: ' + name)
        declaration = {'uuid':interface.attrib.get('uuid'), 'members':{}}
        for member in interface:
            if member.tag in {'method','attribute'} and member.attrib.get('name') in names:
                declaration['members'][member.attrib['name']] = {
                    'kind':member.tag,
                    'type':member.attrib.get('type'),
                    'readonly':member.attrib.get('readonly','no'),
                    'params':[{k:p.attrib.get(k) for k in ('name','type','dir','safearray','optional')}
                              for p in member if p.tag=='param']}
        declarations[name] = declaration
    enumerations = {}
    for enum in document.iter('enum'):
        if enum.attrib.get('name') in ENUMS:
            enumerations[enum.attrib['name']] = {v.attrib['name']:v.attrib.get('value')
                                               for v in enum if v.tag=='const'}
    # Parse, never import/execute vendor Python. HCL's bundled interpreter is 3.8.
    ast.parse(python, feature_version=(3,8)); ast.parse(constants, feature_version=(3,8))
    return {'version':version,'sha256':actual,'interfaces':declarations,'enums':enumerations,
            'python38_syntax_valid':True,'sdk_python_executed':False}


def compare(before: dict, after: dict) -> dict:
    members=[]; ids=[]; enums=[]
    for interface, names in MEMBERS.items():
        old,new=before['interfaces'][interface],after['interfaces'][interface]
        if old['uuid']!=new['uuid']: ids.append({'interface':interface,'before':old['uuid'],'after':new['uuid']})
        for name in names:
            a,b=old['members'].get(name),new['members'].get(name)
            state='same' if a is not None and a==b else 'changed' if a and b else 'missing'
            members.append({'interface':interface,'member':name,'state':state, 'before':a,'after':b})
    for name in ENUMS:
        a,b=before['enums'].get(name,{}),after['enums'].get(name,{})
        changed={key:{'before':value,'after':b.get(key)} for key,value in a.items() if key not in b or b[key]!=value}
        enums.append({'enum':name,'existing_values_unchanged':bool(a) and not changed,
                      'changed_or_removed':changed,'added':{key:value for key,value in b.items() if key not in a}})
    return {'status':'observed','verified_scope':'selected_official_sdk_declarations_only',
            'before_version':before['version'],'after_version':after['version'],
            'members':members,'changed_interface_ids':ids,'enums':enums,
            'selected_declarations_compatible':all(row['state']=='same' for row in members) and all(row['existing_values_unchanged'] for row in enums),
            'hcl_embedded_sdk_identity_confirmed':False,'hcl_runtime_compatible':None,
            'guest_boot_verified':False,'rollback_verified':False,'full_live_gate_passed':False,
            'installer_executed':False,'com_instantiated':False,'machine_changes_applied':False,
            'limitations':['Selected members are based on observed HCL use, not exhaustive binary analysis',
                           'Equal declarations do not prove the embedded HCL binding uses them correctly',
                           'COM registration, cached wrappers, Windows driver and WHPX guest execution remain untested']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-sdk',type=Path,required=True)
    parser.add_argument('--after-sdk',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Never overwrite a prior probe receipt')
    before=read_sdk(args.before_sdk,'6.0.14');after=read_sdk(args.after_sdk,'6.1.50')
    result=compare(before,after)
    result['sources']=[{'path':str(p),'version':v,'sha256':HASHES[v]} for p,v in [(args.before_sdk,'6.0.14'),(args.after_sdk,'6.1.50')]]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'selected_members':len(result['members']),
        'member_differences':[f"{r['interface']}.{r['member']} ({r['state']})" for r in result['members'] if r['state']!='same'],
        'enum_differences':[r['enum'] for r in result['enums'] if not r['existing_values_unchanged']],
        'changed_interface_ids':len(result['changed_interface_ids']), 'hcl_runtime_compatible':None,
        'machine_changes_applied':False},indent=2))


if __name__=='__main__':main()
