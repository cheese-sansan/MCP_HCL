"""Compile a validated plan into an isolated HCL project, using real templates.

No guessed VM positional arguments, port-order inference, GUI, or guest writes.
The caller must supply an explicit CLI-to-scene mapping for every linked port.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
from pathlib import Path

from mcp_hcl.generation import generate_configs
from mcp_hcl.project import ProjectError, _PORT


def safe_filename(name: str) -> None:
    """Display names become config filenames; enforce Windows basename rules."""
    if (not name or name[-1] in ' .' or any(c in name for c in '<>:"/\\|?*') or
            re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name)):
        raise ProjectError('Device name is not a safe Windows config filename')


def note_blocks(lines: list[str]) -> list[tuple[int, int]]:
    blocks = []
    for start, line in enumerate(lines):
        if re.fullmatch(r'\s{4}\[\[NOTE \d+\]\]\s*', line.rstrip('\r\n')):
            end = next((i for i in range(start + 1, len(lines))
                        if lines[i].startswith('    [[') or lines[i].startswith('[')), len(lines))
            blocks.append((start, end))
    return blocks


def render_notes(lines: list[str], annotations: list[dict], newline: str) -> list[str]:
    """Replace only known NOTE blocks; retain unrelated Non-vBox fields."""
    result = list(lines)
    font = '"Arial,14,-1,5,75,0,0,0,0,0"'
    blocks = note_blocks(result)
    if blocks:
        for line in result[blocks[0][0]:blocks[0][1]]:
            if line.strip().startswith('font = '):
                font = line.strip().split('=', 1)[1].strip()
                break
    for start, end in reversed(blocks):
        del result[start:end]
    if annotations and not any(line.startswith('[Non-vBox-DATA]') for line in result):
        result.append('[Non-vBox-DATA]' + newline)
    insertion = next((i + 1 for i, line in enumerate(result) if line.startswith('[Non-vBox-DATA]')), len(result))
    while insertion < len(result) and not result[insertion].startswith('['):
        insertion += 1
    encoded = []
    for index, annotation in enumerate(annotations, 1):
        text = annotation['text']
        # Newlines have an observed \n representation. Quote/backslash escape
        # semantics have not been verified in HCL, so do not fabricate them.
        if '"' in text or '\\' in text:
            raise ProjectError('HCL note quote/backslash escaping is unverified')
        if any(not c.isprintable() and c not in '\r\n' for c in text):
            raise ProjectError('HCL note contains an unsupported control character')
        text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n')
        encoded.extend([f'    [[NOTE {index}]]{newline}', f'        text = "{text}"{newline}',
                        f'        font = {font}{newline}', f"        x = {annotation['x']}{newline}",
                        f"        y = {annotation['y']}{newline}", f'        z = 6.0{newline}'])
    result[insertion:insertion] = encoded
    return result


def stage_plan(store, catalog, project_path: str, stage_name: str, plan: dict,
               port_map: dict[str, dict[str, str]]) -> dict:
    generated = generate_configs(plan, catalog)
    if generated['status'] != 'verified':
        return generated
    normalized = generated['plan']
    doc = store._open(project_path)
    devices = {device['id']: device for device in normalized['devices']}
    by_model = {}
    for section in doc.sections.values():
        by_model.setdefault(section.model, section)
    missing = sorted({device['model'] for device in devices.values()} - set(by_model))
    if missing:
        raise ProjectError('Source project has no real template for models: ' + ', '.join(missing))
    names = [device['name'] for device in devices.values()]
    if len({name.casefold() for name in names}) != len(names):
        raise ProjectError('Device filenames collide on Windows')
    for name in names:
        safe_filename(name)
        if any(name != other and name.endswith(' ' + other) for other in names):
            raise ProjectError('Device names are ambiguous in the HCL section grammar')
    if any(abs(device[axis]) > 10000 for device in devices.values() for axis in ('x', 'y')):
        raise ProjectError('Device coordinates exceed the supported staging range')
    families = catalog.ports()
    allowed = {}
    for model in {device['model'] for device in devices.values()}:
        allowed[model] = {}
        for key, value in by_model[model].fields.items():
            match = re.fullmatch(r'slot(\d+)', key)
            if match:
                if not value.split():
                    raise ProjectError('Source slot profile is empty')
                family = value.split()[0]
                for port in families['families'].get(family, []):
                    allowed[model][f"{port['kind']}_{int(match[1])}/{port['index']}"] = port['physical_type']
    installed = {row['model']: row for row in catalog.devices()['devices']}
    if set(port_map) - set(allowed):
        raise ProjectError('Port map contains models outside this plan')
    for model, mapping in port_map.items():
        if len(set(mapping.values())) != len(mapping):
            raise ProjectError('CLI ports must map to distinct scene ports')
        for cli, scene in mapping.items():
            if cli not in installed[model]['default_interfaces'] or cli == 'NULL0' or scene not in allowed[model]:
                raise ProjectError('Port map is not present in installed CLI defaults and source slot profiles')
    connections = {identifier: {} for identifier in devices}
    for link in normalized['links']:
        resolved = {}
        for side in ('a', 'b'):
            endpoint = link[side]
            device = devices[endpoint['device']]
            scene = port_map.get(device['model'], {}).get(endpoint['interface'])
            if scene is None:
                raise ProjectError(f"Explicit port map required: {device['model']}/{endpoint['interface']}")
            physical = allowed[device['model']][scene]
            ethernet = physical.startswith('PHY_ETH_')
            serial = physical in {'PHY_SYNC', 'PHY_ASYNC', 'PHY_SERIAL'}
            if not (ethernet if link['medium'] == 'ethernet' else serial):
                raise ProjectError('Scene physical type disagrees with link medium')
            resolved[side] = scene
        a, b = link['a']['device'], link['b']['device']
        connections[a][resolved['a']] = f"{devices[b]['name']} {resolved['b']}"
        connections[b][resolved['b']] = f"{devices[a]['name']} {resolved['a']}"
    first_id = max(int(section.fields['device_id']) for section in doc.sections.values()) + 1
    if first_id + len(devices) - 1 > 1024:
        raise ProjectError('Fresh device IDs exceed the observed backend range')
    prefix_end = min(section.start for section in doc.sections.values())
    lines = list(doc.lines[:prefix_end])
    metadata = copy.deepcopy(doc.metadata)
    metadata['deviceInfoList'] = []
    files = {}
    bindings = []
    macs = {section.fields.get('bridge_mac', '').lower() for section in doc.sections.values()}
    for offset, device in enumerate(devices.values()):
        template = by_model[device['model']]
        identifier = first_id + offset
        while True:
            mac = '64-52-' + '-'.join(f'{value:02x}' for value in secrets.token_bytes(4))
            if mac not in macs:
                macs.add(mac)
                break
        lines.extend([f"    [[{template.model} {device['name']}]]{doc.newline}",
                      f'        device_id = {identifier}{doc.newline}',
                      f'        bridge_mac = {mac}{doc.newline}'])
        for key, value in template.fields.items():
            if key not in {'device_id', 'bridge_mac', 'x', 'y', 'z'} and not _PORT.fullmatch(key):
                lines.append(f'        {key} = {value}{doc.newline}')
        for scene, peer in connections[device['id']].items():
            lines.append(f'        {scene} = {peer}{doc.newline}')
        lines.extend([f"        x = {device['x']}{doc.newline}", f"        y = {device['y']}{doc.newline}", f'        z = 5.0{doc.newline}'])
        original = next(row for row in doc.metadata['deviceInfoList'] if row['resourceName'] == template.name)
        cloned = copy.deepcopy(original)
        cloned.update(resourceName=device['name'], configPath=f"DeviceConfig\\{device['name']}.cfg")
        metadata['deviceInfoList'].append(cloned)
        # CLI command transcripts are NOT HCL startup .cfg files. Keep them
        # separate, with an empty startup placeholder, until CLI deployment.
        files[f"DeviceConfig/{device['name']}.cfg"] = b''
        files[f"MCPArtifacts/commands/{device['id']}.txt"] = generated['configs'][device['id']].encode('utf-8')
        bindings.append({'plan_id': device['id'], 'name': device['name'], 'model': device['model'],
                         'device_id': identifier, 'template_device': template.name})
    lines.extend(render_notes(doc.lines[doc.vbox_end:], normalized['annotations'], doc.newline))
    files['MCPArtifacts/plan.json'] = (json.dumps(normalized, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    files['MCPArtifacts/bindings.json'] = (json.dumps({'devices': bindings, 'port_map': port_map,
                                                    'port_mapping_provenance': 'caller_supplied',
                                                    'runtime_verified': False}, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    result = store._commit(doc, stage_name, lines, metadata, additional_files=files)
    result.update(verified_scope='isolated_project_files_and_caller_mapping_only',
                  device_bindings=bindings, port_mapping_provenance='caller_supplied',
                  port_mapping_verified=False, configuration_verified=False, guest_boot_verified=False,
                  live_canvas_verified=False, connectivity_verified=False, full_live_gate_passed=False,
                  commands_directory=str(Path(result['project_directory']) / 'MCPArtifacts/commands'),
                  warnings=generated['warnings'],
                  evidence=[{'source': str(doc.net_path), 'sha256': hashlib.sha256(doc.net_path.read_bytes()).hexdigest(),
                             'layer': 'source_project_template'}, *families['evidence']])
    return result
