"""Read local HCL model defaults without distributing vendor files.

Default interfaces and firmware strings are installation evidence. They are
not proof that a guest booted or that a command is accepted by its firmware.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from uuid import uuid4
from mcp_hcl.templates import TEMPLATES

# These two board names are observed in HCL .net slot0 records; do not guess
# a board for other models by truncating their names.
MODEL_FAMILIES = {'MSR36-20': 'MSR36', 'S5820V2-54QS-GE': 'S5800',
                  'F1060': 'F1060', 'AC': 'AC', 'AP': 'AP', 'PC': 'PC'}


class CatalogError(ValueError):
    pass


class HclCatalog:
    def __init__(self, installation: Path):
        self.installation = installation.resolve()

    def _read(self, path: Path) -> tuple[str, dict[str, str]]:
        if not path.resolve().is_relative_to(self.installation):
            raise CatalogError('Catalog file escaped the installation directory')
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise CatalogError(f'Catalog file missing, linked or oversized: {path.name}')
        data = path.read_bytes()
        return data.decode('utf-8-sig'), {'source': str(path), 'sha256': hashlib.sha256(data).hexdigest()}

    def _models(self) -> list[dict[str, Any]]:
        models = []
        for path in sorted((self.installation / 'devicecfgs').glob('*.cfg')):
            text, evidence = self._read(path)
            version = re.search(r'^\s*version\s+(.+)$', text, re.MULTILINE)
            interfaces = re.findall(r'^interface\s+([A-Za-z][\w/-]*)\s*$', text, re.MULTILINE)
            models.append({
                'model': path.stem,
                'default_firmware': version.group(1).strip() if version else None,
                'default_interfaces': interfaces,
                'runtime_verified': False,
                'evidence': evidence,
            })
        if not models:
            raise CatalogError('No device defaults found; configure MCP_HCL_INSTALL_ROOT')
        ini = self.installation / 'deviceInfo.ini'
        if ini.is_file():
            ports = self.ports()
            for name in ('AC', 'AP'):
                image = self.installation / 'version' / (name.lower() + '.vmdk')
                if name in ports['families'] and image.is_file() and not image.is_symlink():
                    models.append({'model': name, 'default_firmware': None, 'default_interfaces': [],
                                   'runtime_verified': False, 'default_configuration_available': False,
                                   'evidence': ports['evidence'][0],
                                   'limitation': 'Installed port family and image presence only; CLI interface mapping and guest firmware unverified.'})
            for model in models:
                family = MODEL_FAMILIES.get(model['model'], model['model'])
                model['port_family'] = family if family in ports['families'] else None
                model['scene_ports'] = []
                for port in ports['families'].get(family, []):
                    row = {**port, 'scene_port': f"{port['kind']}_0/{port['index']}", 'cli_interface': None}
                    prefix = {'GE': 'GigabitEthernet', 'XGE': 'Ten-GigabitEthernet', 'FGE': 'FortyGigE',
                              'M-GE': 'M-GigabitEthernet', 'FE': 'FastEthernet'}.get(str(port['kind']))
                    matches = [i for i in model['default_interfaces'] if prefix and
                               i.startswith(prefix) and int(i.rsplit('/', 1)[-1]) == port['index']]
                    if len(matches) == 1:
                        row['cli_interface'] = matches[0]
                    row['mapping_verified'] = row['cli_interface'] is not None
                    model['scene_ports'].append(row)
                model['port_evidence'] = ports['evidence']
                # Match complete physical groups in natural CLI order. This is
                # a derived candidate mapping, not an observed guest mapping.
                for kind, prefix in {'GE':'GigabitEthernet', 'XGE':'Ten-GigabitEthernet',
                                     'FGE':'FortyGigE', 'M-GE':'M-GigabitEthernet', 'Ser':'Serial'}.items():
                    scene = [p for p in model['scene_ports'] if p['kind'] == kind]
                    cli = [i for i in model['default_interfaces'] if i.startswith(prefix)]
                    cli.sort(key=lambda v: tuple(int(n) for n in re.findall(r'\d+', v)))
                    if len(scene) == len(cli):
                        for row, interface in zip(scene, cli):
                            row.update(cli_interface=interface, mapping_verified=False,
                                       mapping_method='paired_installed_port_order_unverified')
        return models

    def _result(self, scope: str, **payload: Any) -> dict[str, Any]:
        return {'status': 'verified', 'operation_id': uuid4().hex, 'target_project': None,
                'verified_scope': scope, 'runtime_verified': False, **payload}

    def devices(self) -> dict[str, Any]:
        models = self._models()
        return self._result('installed_model_defaults_only', devices=models,
                            evidence=[row['evidence'] for row in models])

    def device_details(self, model: str) -> dict[str, Any]:
        # Lookup by discovered name; a model parameter is never a filesystem path.
        matches = [row for row in self._models() if row['model'] == model]
        if len(matches) != 1:
            raise CatalogError(f'Unknown installed model: {model}')
        return self._result('installed_model_defaults_only', device=matches[0], evidence=[matches[0]['evidence']])

    def ports(self) -> dict[str, Any]:
        text, evidence = self._read(self.installation / 'deviceInfo.ini')
        families: dict[str, list[dict[str, str | int]]] = {}
        family = None
        index = None
        physical_types: dict[str, int] = {}
        for line in text.splitlines():
            heading = re.fullmatch(r'\s*\[([^\[\]]+)\]\s*', line)
            slot = re.fullmatch(r'\s*\[\[(\d+)\]\]\s*', line)
            field = re.fullmatch(r'\s*([\w-]+)\s*=\s*(PHY_[\w]+)\s*', line)
            value = re.fullmatch(r'\s*(PHY_\w+)\s*=\s*(\d+)\s*', line)
            if heading:
                family, index = heading.group(1), None
                if family != 'PHY_PORT_VALUE':
                    families[family] = []
            elif slot:
                index = int(slot.group(1))
            elif value and family == 'PHY_PORT_VALUE':
                physical_types[value.group(1)] = int(value.group(2))
            elif field and family in families and index is not None:
                families[family].append({'index': index, 'kind': field.group(1), 'physical_type': field.group(2)})
        if not families or any(not ports for ports in families.values()):
            raise CatalogError('Malformed deviceInfo.ini port families')
        for entries in families.values():
            for entry in entries:
                entry['physical_type_id'] = physical_types.get(str(entry['physical_type']))
        return self._result('installed_port_family_definitions_only', families=families, physical_types=physical_types, evidence=[evidence],
                            limitation='Family indices are not a verified mapping to every model CLI interface.')

    def aliases(self) -> dict[str, Any]:
        models = self._models()
        names = {row['model'] for row in models}
        # Case-insensitive exact aliases only, not arbitrary vendor-model substitutions.
        return self._result('installed_model_aliases_only', aliases={name.lower(): name for name in sorted(names)},
                            evidence=[row['evidence'] for row in models])

    def cables(self) -> dict[str, Any]:
        ports = self.ports()
        return self._result('installed_physical_media_only', cables=[
            {'medium': 'ethernet', 'physical_types': sorted(p for p in ports['physical_types'] if p.startswith('PHY_ETH_'))},
            {'medium': 'serial', 'physical_types': sorted(p for p in ports['physical_types'] if p in {'PHY_SYNC','PHY_ASYNC'})}],
            evidence=ports['evidence'])

    def templates(self) -> dict[str, Any]:
        source = Path(__file__).with_name('templates.py')
        return self._result('offline_template_graphs_only', templates=TEMPLATES,
                            evidence=[{'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}])

    def modules(self, model: str | None = None) -> dict[str, Any]:
        models = self._models()
        if model is not None:
            models = [row for row in models if row['model'] == model]
            if not models:
                raise CatalogError('Unknown installed model')
        return self._result('installed_fixed_port_profiles_only', modules=[],
                            fixed_port_profiles=[{'model': row['model'], 'family': row.get('port_family'),
                                                  'ports': row.get('scene_ports', [])} for row in models],
                            expansion_modules_verified=False,
                            warnings=[{'code': 'module_catalog_unverified', 'message': 'No evidence-backed expansion module catalog is available; fixed interfaces are not modules.'}],
                            evidence=[row['evidence'] for row in models])
