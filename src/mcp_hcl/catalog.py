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
        for line in text.splitlines():
            heading = re.fullmatch(r'\s*\[([^\[\]]+)\]\s*', line)
            slot = re.fullmatch(r'\s*\[\[(\d+)\]\]\s*', line)
            field = re.fullmatch(r'\s*([\w-]+)\s*=\s*(PHY_[\w]+)\s*', line)
            if heading:
                family, index = heading.group(1), None
                if family != 'PHY_PORT_VALUE':
                    families[family] = []
            elif slot:
                index = int(slot.group(1))
            elif field and family in families and index is not None:
                families[family].append({'index': index, 'kind': field.group(1), 'physical_type': field.group(2)})
        if not families or any(not ports for ports in families.values()):
            raise CatalogError('Malformed deviceInfo.ini port families')
        return self._result('installed_port_family_definitions_only', families=families, evidence=[evidence],
                            limitation='Family indices are not a verified mapping to every model CLI interface.')
