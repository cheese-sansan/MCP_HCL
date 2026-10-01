"""Immutable command-help fingerprints. No vendor manuals are redistributed."""
import hashlib
import json
from importlib.resources import files
from pathlib import Path


def reference() -> dict:
    return json.loads(files('mcp_hcl').joinpath('data/command_reference.json').read_text(encoding='utf-8'))


def feature_evidence(feature: str) -> list[dict]:
    return [{**source, 'layer': 'documented_command_syntax', 'runtime_verified': False}
            for source in reference()['features'][feature]['sources']]


def verify_installed_reference(root: Path) -> dict:
    checked = []
    for feature, entry in reference()['features'].items():
        for source in entry['sources']:
            path = root / source['relative_path']
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
            checked.append({'feature': feature, **source, 'matches': actual == source['sha256']})
    return {'verified_scope': 'installed_command_help_hashes_only', 'sources': checked,
            'all_match': all(row['matches'] for row in checked), 'runtime_verified': False}
