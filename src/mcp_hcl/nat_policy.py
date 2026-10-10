"""Single-router NAT transactions with scoped readback and bound recovery."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from ipaddress import IPv4Address
from pathlib import Path
from uuid import uuid4
from pydantic import ValidationError
from mcp_hcl.acl_semantics import configuration_acls, verify_acl
from mcp_hcl.console import ConsoleError
from mcp_hcl.contracts import validation_errors
from mcp_hcl.gui_relay import rejected
from mcp_hcl.nat_models import NatApplication, NatRemoval
from mcp_hcl.nat_semantics import (
    acl_entry, apply_delta, group_ranges, inline_acl, pool_assignment, remove_delta,
)
from mcp_hcl.policy import patch_preserves_unrequested, scopes
from mcp_hcl.deployment import config_text
from mcp_hcl.runtime_binding import unlinked
from mcp_hcl.topology import TopologyPlan


class BudgetConsole:
    """Limit each native exchange to the remaining operation time; never replay."""
    def __init__(self, channel, deadline):
        self.channel = channel
        self.deadline = deadline

    def __getattr__(self, name):
        return getattr(self.channel, name)

    def exchange(self, command, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ConsoleError('NAT operation deadline reached', code='nat_deadline_exceeded')
        previous = getattr(self.channel, 'timeout', None)
        if previous is not None:
            self.channel.timeout = min(previous, remaining)
        try:
            result = self.channel.exchange(command, **kwargs)
        finally:
            if previous is not None:
                self.channel.timeout = previous
        if time.monotonic() >= self.deadline:
            raise ConsoleError('NAT exchange completed after its deadline', code='nat_deadline_exceeded')
        return result


def atomic_json(path, data):
    unlinked(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.new')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def unique_json(path):
    unlinked(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('NAT identity metadata exceeds its read budget')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate NAT identity metadata key')
            result[key] = value
        return result

    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs)


def operation_json(path):
    """Unreadable history is an incomplete record, never replay authority."""
    try:
        record = unique_json(path)
    except (OSError, ValueError, ConsoleError):
        return None
    return record if isinstance(record, dict) else None


def incomplete_operation(operation, directory):
    return {'status': 'unverified', 'operation_id': operation, 'receipt_directory': str(directory),
            'current_state_rechecked': False, 'configuration_verified': False,
            'persistence_verified': False, 'full_live_gate_passed': False,
            'errors': [{'code': 'operation_record_incomplete',
                        'message': 'Prior operation history is missing or invalid; no commands were replayed'}]}


class NatOperations:
    def __init__(self, policy):
        self.policy = policy

    def _stage(self, project_path, parameters):
        document, bindings = self.policy.deployment.bindings(project_path)
        matches = [(identifier, binding) for identifier, binding in bindings.items()
                   if identifier == parameters.router or binding['name'] == parameters.router]
        if len(matches) != 1:
            raise ValueError('Select one exact staged NAT router by plan ID or display name')
        identifier, binding = matches[0]
        plan_file = document.directory / 'MCPArtifacts' / 'plan.json'
        unlinked(plan_file)
        plan = TopologyPlan.model_validate(json.loads(plan_file.read_text(encoding='utf-8')))
        device = next((device for device in plan.devices if device.id == identifier), None)
        if device is None:
            raise ValueError('NAT target is absent from its staged plan')
        models = self.policy.catalog.devices()['devices']
        model = next((model for model in models if model['model'] == device.model), None)
        if model is None:
            raise ValueError('NAT target model is absent from the installed catalog')
        known = set(model.get('default_interfaces', [])) | set(model.get('native_interfaces', []))
        known |= {item.interface for item in plan.subinterfaces if item.device == identifier}
        known |= {f'Vlan-interface{svi.vlan}' for service in plan.services
                  if service.device == identifier and service.feature == 'vlan' for svi in service.parameters.svis}
        for interface in (parameters.inside_interface, parameters.outside_interface):
            if interface == 'NULL0' or interface not in known and interface.split('.', 1)[0] not in known:
                raise ValueError('NAT references an interface absent from the staged model')
        return document, identifier, binding

    def _state(self, document, identifier, identity):
        target = {'project': str(document.net_path), 'device': identifier, 'vm_uuid': identity['vm_uuid']}
        key = hashlib.sha256(json.dumps(target, sort_keys=True).encode('utf-8')).hexdigest()
        folder = '.nat-state' if self.policy.native_dependencies else '.nat-protocol-state'
        path = self.policy.store.output_root / folder / (key + '.json')
        unlinked(path)
        if not path.exists():
            return path, {'schema_version': 1, 'target': target, 'pools': {}, 'acls': {}}
        state = unique_json(path)
        if not isinstance(state, dict) or type(state.get('schema_version')) is not int or state.get('schema_version') != 1 or state.get('target') != target:
            raise ValueError('NAT object metadata has another runtime identity')
        if self.policy.native_dependencies and state.get('native_verified') is not True:
            raise ValueError('Unverified metadata cannot authorize native NAT object reuse')
        if not isinstance(state.get('pools'), dict) or not isinstance(state.get('acls'), dict):
            raise ValueError('NAT object metadata is incomplete')
        for pool in state['pools'].values():
            if not isinstance(pool, dict) or type(pool.get('address_group')) is not int or not 0 <= pool['address_group'] <= 65535:
                raise ValueError('NAT pool object metadata is invalid')
            if any(type(pool.get(key)) is not str for key in ('start', 'end', 'netmask')):
                raise ValueError('NAT pool range metadata is incomplete')
            if any(str(IPv4Address(pool[key])) != pool[key] for key in ('start', 'end', 'netmask')):
                raise ValueError('NAT pool range metadata is not canonical IPv4')
        for record in state['acls'].values():
            if not isinstance(record, dict) or type(record.get('number')) is not int or not 2000 <= record['number'] <= 3999:
                raise ValueError('NAT ACL object metadata is invalid')
        return path, state

    @staticmethod
    def _acl_key(parameters):
        return parameters.acl_namespace + ':' + parameters.acl_number

    def _pool_id(self, before, parameters, state, removal):
        if parameters.mode == 'static' or not removal and not parameters.uses_pool:
            return None
        recorded = state['pools'].get(parameters.pool_name) if parameters.pool_name else None
        if removal:
            identifier = parameters.pool_address_group
            if recorded is not None:
                if identifier is not None and identifier != recorded['address_group']:
                    raise ValueError('Removal pool name and native ID disagree')
                identifier = recorded['address_group']
                view = (f'nat address-group {identifier}',)
                current_views = scopes(before)
                if parameters.pool_address_group is None and view in current_views:
                    recorded_range = [(int(IPv4Address(recorded['start'])), int(IPv4Address(recorded['end'])))]
                    if group_ranges(current_views[view]) != recorded_range:
                        raise ValueError('Named removal pool metadata is stale; pin the reviewed native group explicitly')
            elif parameters.pool_name and identifier is None:
                raise ValueError('Named NAT pool lacks a verified native ID; supply pool_address_group')
            if parameters.mode == 'dynamic' and identifier is None:
                raise ValueError('Dynamic NAT removal needs the pool name or native ID')
        else:
            identifier = pool_assignment(scopes(before), parameters, recorded)
        names = [name for name, pool in state['pools'].items() if pool['address_group'] == identifier]
        if identifier is not None and (len(names) > 1 or parameters.pool_name and any(name != parameters.pool_name for name in names)):
            raise ValueError('The native pool ID also belongs to another recorded pool name')
        return identifier

    def _dry_run(self, identifier, parameters, removal):
        # No VM query, console connection, backup, mapping write, or guest action.
        fake = f'interface {parameters.inside_interface}\n#\ninterface {parameters.outside_interface}\n#\n'
        commands = []
        provisional = False
        group = parameters.pool_address_group
        if removal:
            if parameters.mode != 'static' and parameters.pool_name and group is None:
                return {'status': 'unverified', 'device': identifier, 'commands': None,
                        'requires_current_pool_identity': True, 'full_live_gate_passed': False}
            if parameters.mode == 'static':
                commands = ['undo nat static outbound ' + m.inside_local + ' ' + m.inside_global
                            for m in parameters.static_mappings]
                if parameters.disable_static_interface:
                    commands += ['interface ' + parameters.outside_interface, 'undo nat static enable', 'quit']
            else:
                if parameters.mode == 'dynamic' and group is None:
                    return {'status': 'unverified', 'commands': None, 'requires_current_pool_identity': True,
                            'full_live_gate_passed': False}
                commands = ['interface ' + parameters.outside_interface,
                            'undo nat outbound ' + parameters.acl_reference, 'quit']
                if group is not None and parameters.remove_pool:
                    commands.append('undo nat address-group ' + str(group))
                if parameters.remove_acl:
                    commands.append('undo acl ' + parameters.acl_kind + ' ' + parameters.acl_reference)
        else:
            if parameters.mode != 'static':
                commands, _ = inline_acl(fake, parameters)
            if parameters.uses_pool and group is None:
                group = 0
                provisional = True
            delta = apply_delta(fake, parameters, group)
            commands += delta.commands
        return {'status': 'verified', 'device': identifier, 'commands': ['system-view', *commands, 'return'],
                'native_acl_number': parameters.acl_id if parameters.mode != 'static' else None,
                'native_acl_name': parameters.acl_name if parameters.mode != 'static' else None,
                'address_group': group, 'address_group_assignment_provisional': provisional,
                'requires_current_named_acl_type': parameters.mode != 'static' and parameters.acl_name is not None and parameters.named_acl_type is None,
                'verified_scope': 'offline_nat_command_intent_only', 'runtime_preflight_required': True,
                'configuration_verified': False, 'persistence_verified': False,
                'upstream_behavior_equivalent': False, 'full_live_gate_passed': False}

    def run(self, project_path, topology, parameters, *, removal=False, dry_run=False):
        if not dry_run and not self.policy.writes_enabled:
            return rejected('writes_disabled', 'Native NAT operations require the live write switch')
        try:
            typed = (NatRemoval if removal else NatApplication).model_validate(parameters)
            document, identifier, binding = self._stage(project_path, typed)
        except ValidationError as exc:
            return {'status': 'rejected', 'errors': validation_errors(exc), 'full_live_gate_passed': False}
        except (ValueError, OSError) as exc:
            return rejected('invalid_nat_target', str(exc))
        if dry_run:
            return self._dry_run(identifier, typed, removal)
        operation = typed.operation_key or uuid4().hex
        root = self.policy.store.output_root / '.nat-receipts'
        directory = root / operation
        unlinked(directory)
        request = {'operation': 'remove_nat' if removal else 'apply_nat', 'project': str(document.net_path),
                   'device': identifier, 'topology': topology, 'parameters': typed.model_dump(mode='json')}
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode('utf-8')).hexdigest()
        if directory.exists():
            request_file = directory / 'request.json'
            if not request_file.is_file():
                return {'status': 'unverified', 'operation_id': operation, 'reused_receipt': True,
                        'errors': [{'code': 'nat_operation_record_incomplete',
                                    'message': 'Prior operation has no complete request receipt; no commands were replayed'}],
                        'configuration_verified': False, 'full_live_gate_passed': False}
            previous = operation_json(request_file)
            if not isinstance(previous, dict):
                return incomplete_operation(operation, directory)
            if previous.get('fingerprint') != fingerprint:
                return rejected('operation_key_conflict', 'NAT operation key belongs to another request')
            result_file = directory / 'result.json'
            recorded = operation_json(result_file) if result_file.exists() else None
            if result_file.exists() and recorded is None:
                return incomplete_operation(operation, directory)
            return {'status': 'output_received' if result_file.exists() else 'unverified',
                    'operation_id': operation, 'reused_receipt': True, 'current_state_rechecked': False,
                    'verified_scope': 'recorded_nat_operation_only',
                    'previous_result': recorded,
                    'errors': recorded.get('errors', []) if recorded is not None else
                        [{'code': 'nat_previous_operation_incomplete', 'message': 'Prior NAT state needs reconciliation; no commands were replayed'}],
                    'configuration_verified': False, 'persistence_verified': False,
                    'full_live_gate_passed': False}
        directory.mkdir(parents=True, exist_ok=False)
        atomic_json(directory / 'request.json', {'fingerprint': fingerprint, **request})
        result = {'status': 'unverified', 'operation_id': operation, 'operation': request['operation'],
                  'device': identifier, 'receipt_directory': str(directory), 'steps': [], 'errors': [],
                  'configuration_verified': False, 'protocol_effect_verified': False,
                  'persistence_verified': False, 'protocol_persistence_verified': False,
                  'rollback_verified': False, 'protocol_rollback_verified': False,
                  'upstream_behavior_equivalent': False, 'full_live_gate_passed': False,
                  'inside_interface_effect': 'validated_reference_only_comware_uses_outbound_rules',
                  'pool_netmask_effect_verified': False}
        result['warnings'] = [{'code': 'nat_ingress_role_not_equivalent',
                               'message': 'Comware outbound NAT does not establish an IOS ip nat inside marker'}]
        if not removal and typed.uses_pool:
            result['warnings'].append({'code': 'nat_pool_mask_metadata_only',
                                       'message': 'Pool netmask is validated and recorded; native group readback proves address ranges only'})
        channel = None
        identity = None
        backup = None
        dirty = False
        archived = []
        deadline = time.monotonic() + typed.timeout_seconds
        try:
            raw, identity = self.policy.open(document, binding, topology)
            channel = BudgetConsole(raw, deadline)
            result['target_identity'] = identity
            state_path, state = self._state(document, identifier, identity)

            def saved(record):
                nonlocal backup, dirty
                backup, dirty = record, True

            backup = self.policy.deployment._backup(channel, identifier, directory, operation, on_saved=saved)
            dirty = False
            before = Path(backup['local_file']).read_text(encoding='utf-8')
            result['backup'] = backup
            actual_interfaces = {context[0][10:] for context in scopes(before)
                                 if context and context[0].startswith('interface ')}
            if not {typed.inside_interface, typed.outside_interface} <= actual_interfaces:
                raise ConsoleError('NAT interfaces are absent from the current configuration', code='nat_interface_unverified')
            if typed.mode != 'static' and typed.acl_name is not None and typed.named_acl_type is None:
                named = [entry for entry in configuration_acls(before) if entry['header']['name'] == typed.acl_name]
                if len(named) > 1:
                    raise ValueError('Named NAT ACL identity is ambiguous')
                if named:
                    typed = typed.model_copy(update={'named_acl_type': named[0]['header']['type']})
            group = self._pool_id(before, typed, state, removal)
            entry = acl_entry(before, typed) if typed.mode != 'static' else None
            origin = state['acls'].get(self._acl_key(typed))
            origin_known = origin is not None and origin['number'] == typed.acl_id
            if removal and typed.mode != 'static' and typed.acl_namespace == 'ios' and typed.acl_id is not None and entry is not None and not origin_known:
                raise ValueError('Existing native ACL has no recorded IOS identity; use an explicit Comware namespace')
            acl_commands, effective = ([], None) if removal or typed.mode == 'static' else inline_acl(before, typed, origin_known=origin_known)
            current = before
            if acl_commands:
                dirty = True
                for command in ['system-view', *acl_commands, 'return']:
                    channel.exchange(command)
                    result['steps'].append({'stage': 'acl', 'command': command, 'status': 'accepted'})
                current = config_text(channel.exchange('display current-configuration')['output'])
                if not verify_acl(current, effective) or not patch_preserves_unrequested(before, current, 'acl', effective):
                    raise ConsoleError('Inline ACL readback or preservation mismatch', code='nat_acl_unverified')
            delta = remove_delta(current, typed, group) if removal else apply_delta(current, typed, group)
            if delta.commands:
                dirty = True
                for command in ['system-view', *delta.commands, 'return']:
                    channel.exchange(command)
                    result['steps'].append({'stage': 'nat', 'command': command, 'status': 'accepted'})
                current = config_text(channel.exchange('display current-configuration')['output'])
            if not delta.verified(current):
                raise ConsoleError('NAT readback changed or missed requested configuration scope', code='nat_scope_unverified')
            native = self.policy.native_dependencies and getattr(channel, 'native_channel', False)
            result['native_mapping'] = {'requested_acl': typed.acl_number, 'acl_namespace': typed.acl_namespace,
                                       'native_acl_number': typed.acl_id if typed.mode != 'static' else None,
                                       'native_acl_name': typed.acl_name if typed.mode != 'static' else None,
                                       'pool_name': typed.pool_name, 'address_group': group}
            result['persistence'] = self.policy.deployment.startup.persist(
                channel, backup['startup'], current, f'flash:/mcp_{operation}_{identifier}_after.cfg')
            updated = copy.deepcopy(state)
            if typed.mode != 'static':
                if removal:
                    if typed.remove_acl:
                        updated['acls'].pop(self._acl_key(typed), None)
                    if typed.remove_pool and typed.pool_name:
                        updated['pools'].pop(typed.pool_name, None)
                    elif typed.remove_pool and group is not None:
                        updated['pools'] = {name: record for name, record in updated['pools'].items()
                                            if record['address_group'] != group}
                else:
                    if typed.acl_id is not None:
                        updated['acls'][self._acl_key(typed)] = {'number': typed.acl_id}
                    if typed.uses_pool:
                        updated['pools'][typed.pool_name] = {'address_group': group, 'start': typed.pool_start,
                                                           'end': typed.pool_end, 'netmask': typed.pool_netmask}
            updated['native_verified'] = native
            atomic_json(state_path, updated)
            result.update(status='verified' if native else 'output_received', configuration_verified=native,
                          persistence_verified=native, protocol_effect_verified=True,
                          protocol_persistence_verified=True,
                          verified_scope='bound_native_nat_configuration_and_saved_readback_only' if native
                          else 'synthetic_nat_transaction_only')
        except (ConsoleError, OSError, ValueError) as exc:
            result['errors'] = [exc.as_error() if isinstance(exc, ConsoleError)
                                else {'code': 'nat_operation_failed', 'message': str(exc)}]
            if dirty and backup is not None and identity is not None:
                try:
                    if channel is not None:
                        archived = list(getattr(channel, 'history', []))
                        channel.close()
                        channel = None
                    raw, recovered = self.policy.open(document, binding, topology, identity['vm_uuid'])
                    # Recovery has its own bounded time; never replay the NAT delta.
                    channel = BudgetConsole(raw, time.monotonic() + typed.timeout_seconds)
                    result['recovery_identity'] = recovered
                    result['rollback'] = self.policy.deployment._restore(channel, backup)
                    result['protocol_rollback_verified'] = True
                    result['rollback_verified'] = self.policy.native_dependencies and getattr(channel, 'native_channel', False)
                except (ConsoleError, OSError, ValueError) as recovery:
                    result['rollback'] = {'status': 'unverified', 'error': recovery.as_error()
                                          if isinstance(recovery, ConsoleError) else str(recovery),
                                          'running_snapshot': backup['local_file'], 'startup_snapshot': backup.get('startup')}
        finally:
            result['finished_utc'] = datetime.now(timezone.utc).isoformat()
            history = archived + (getattr(channel, 'history', []) if channel is not None else [])
            receipt_error = None
            try:
                atomic_json(directory / 'transcript.json', history)
            except (OSError, ValueError, ConsoleError) as exc:
                receipt_error = exc
                result['status'] = 'unverified'
                result['errors'].append({'code': 'nat_transcript_io_failed', 'message': str(exc)})
            if channel is not None:
                try:
                    channel.close()
                except (OSError, ConsoleError) as exc:
                    result['status'] = 'unverified'
                    result['errors'].append({'code': 'nat_channel_close_failed', 'message': str(exc)})
            try:
                atomic_json(directory / 'result.json', result)
            except (OSError, ValueError, ConsoleError) as exc:
                receipt_error = exc
            if receipt_error is not None:
                raise ConsoleError('NAT operation receipt is incomplete; do not replay the request',
                                   code='nat_receipt_io_failed', detail={'operation_id': operation,
                                   'receipt_directory': str(directory), 'device_mutation_possible': dirty}) from receipt_error
        return result
