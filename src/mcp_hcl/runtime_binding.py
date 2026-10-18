"""Read-only binding of a staged device to a running HCL VM and pipe server."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import UUID

from mcp_hcl.console import ConsoleError, endpoint


def fail(message):
    raise ConsoleError(
        message, code="runtime_binding_unverified", detail={"stage": "runtime_identity"}
    )


def unlinked(path: Path):
    if any(
        item.is_symlink() or getattr(item, "is_junction", lambda: False)()
        for item in (path, *path.parents)
    ):
        fail("Runtime identity paths cannot contain links")


def machine_values(text):
    result = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in result:
            fail("Duplicate machine observation field")
        try:
            result[key] = json.loads(value) if value.startswith('"') else value
        except ValueError:
            fail("Unreadable machine observation field")
    return result


class _DescriptorTreeBuilder(ET.TreeBuilder):
    def doctype(self, *args):
        # Parser-level rejection also covers UTF-16 declarations, for which
        # an ASCII byte scan alone cannot enforce the no-DTD contract.
        fail("Unsafe VM descriptor declarations")


def _descriptor_tree(data):
    return ET.fromstring(data, parser=ET.XMLParser(target=_DescriptorTreeBuilder()))


def identity_descriptor(data):
    """Parse identity XML, tolerating only observed ETX in ignored HCL DMI metadata.

    VirtualBox accepts HCL's literal ETX board serial, which XML 1.0 rejects.
    The on-disk bytes and their identity hash are never changed. UUID/storage/
    UART fields and all other invalid controls retain strict parsing.
    """
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        fail("Unsafe VM descriptor declarations")
    try:
        return _descriptor_tree(data)
    except ET.ParseError:
        if b"\x03" not in data:
            raise
    # Never treat tag-looking text inside comments, CDATA or PIs as metadata.
    for block in re.finditer(rb"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>", data, re.S):
        if b"\x03" in block[0]:
            fail("Unsupported control bytes outside HCL board-serial metadata")
    key = b"VBoxInternal/Devices/pcbios/0/Config/DmiBoardSerial"
    pattern = rb'<ExtraDataItem\s+name="' + re.escape(key) + rb'"\s+value="[^"<>&]*"\s*/>'
    parsed_data = re.sub(pattern, lambda match: match[0].replace(b"\x03", b" "), data)
    if b"\x03" in parsed_data:
        fail("Unsupported control bytes outside HCL board-serial metadata")
    root = _descriptor_tree(parsed_data)
    parents = {child: parent for parent in root.iter() for child in parent}
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] != "ExtraDataItem" or item.get("name") != key.decode():
            continue
        parent = parents.get(item)
        grandparent = parents.get(parent)
        if (
            parent is None
            or grandparent is None
            or parent.tag.rsplit("}", 1)[-1] != "ExtraData"
            or grandparent.tag.rsplit("}", 1)[-1] != "Machine"
            or set(item.attrib) != {"name", "value"}
        ):
            fail("HCL board-serial metadata is outside its expected view")
    return root


class RuntimeBinding:
    def __init__(self, *, runner=subprocess.run):
        self.runner = runner

    def facts(self, query):
        query = (
            "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false);$ErrorActionPreference='Stop';"
            + query
        )
        try:
            result = self.runner(
                ["powershell.exe", "-NoProfile", "-Command", query], capture_output=True, timeout=12
            )
            if result.returncode:
                fail("Windows runtime observation failed")
            return json.loads(result.stdout.decode("utf-8-sig"))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise ConsoleError(
                "Windows runtime identity is unknown",
                code="runtime_binding_unverified",
                detail={"stage": "runtime_identity"},
            ) from exc

    def resolve(self, document, binding, topology):
        if os.name != "nt":
            fail("Native runtime binding requires Windows")
        device_id = binding["device_id"]
        pipe = endpoint(topology, device_id)
        facts = self.facts(
            "$v=Get-ItemProperty 'HKLM:\\SOFTWARE\\Oracle\\VirtualBox';@{profile=[Environment]::GetFolderPath('UserProfile');sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;vbox=$v.InstallDir}|ConvertTo-Json -Compress"
        )
        if (
            not isinstance(facts, dict)
            or not re.fullmatch(r"S-\d+(?:-\d+)+", str(facts.get("sid", "")))
            or not isinstance(facts.get("profile"), str)
            or not isinstance(facts.get("vbox"), str)
        ):
            fail("Current Windows principal was not observed")
        profile = Path(facts["profile"])
        if not profile.is_absolute():
            fail("Windows profile is not absolute")
        name = f"{topology}-device{device_id}"
        config = profile / "HCL VMs" / topology / f"device{device_id}" / (name + ".vbox")
        unlinked(config)
        if not config.is_file() or config.stat().st_size > 1024 * 1024:
            fail("The expected current-user VM descriptor is missing or oversized")
        data = config.read_bytes()
        try:
            root = identity_descriptor(data)
            machines = [item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "Machine"]
            if len(machines) != 1:
                fail("VM descriptor has no unique machine")
            machine = machines[0]
            uuid = str(UUID(machine.attrib["uuid"].strip("{}")))
        except (ET.ParseError, KeyError, ValueError) as exc:
            raise ConsoleError(
                "VM descriptor identity is unreadable", code="runtime_binding_unverified"
            ) from exc
        if machine.get("name") != name:
            fail("VM descriptor name does not match staged device")
        ports = [
            item
            for item in machine.iter()
            if item.tag.rsplit("}", 1)[-1] == "Port" and item.get("hostMode") == "HostPipe"
        ]
        if (
            len(ports) != 1
            or ports[0].get("path", "").casefold() != pipe.casefold()
            or ports[0].get("server") != "true"
        ):
            fail("VM UART server does not match the requested HCL pipe")
        expected_disk = document.directory / "ConfigDisk" / f"device{device_id}.vdi"
        unlinked(expected_disk)
        config_disk_uuids = set()
        for disk in machine.iter():
            if disk.tag.rsplit("}", 1)[-1] == "HardDisk" and disk.get("location"):
                location = Path(disk.get("location"))
                if (
                    location if location.is_absolute() else config.parent / location
                ).resolve() == expected_disk.resolve():
                    config_disk_uuids.add(disk.get("uuid", "").strip("{}").lower())
        controllers = [
            item for item in machine if item.tag.rsplit("}", 1)[-1] == "StorageControllers"
        ]
        attached = {
            item.get("uuid", "").strip("{}").lower()
            for controller in controllers
            for item in controller.iter()
            if item.tag.rsplit("}", 1)[-1] == "Image"
        }
        if (
            len(config_disk_uuids) != 1
            or not config_disk_uuids.issubset(attached)
            or not expected_disk.is_file()
        ):
            fail("Running VM has no configuration disk bound to this staged project")
        executable = Path(facts["vbox"]) / "VBoxManage.exe"
        try:
            observed = self.runner(
                [str(executable), "showvminfo", name, "--machinereadable"],
                capture_output=True,
                timeout=12,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ConsoleError(
                "Registered VM observation is unknown", code="runtime_binding_unverified"
            ) from exc
        if observed.returncode:
            fail("Registered VM identity observation failed")
        values = machine_values(observed.stdout.decode("utf-8-sig"))
        if (
            values.get("name") != name
            or values.get("UUID") != uuid
            or values.get("VMState") != "running"
            or Path(values.get("CfgFile", "")).resolve() != config.resolve()
        ):
            fail("Registered running VM does not match its current-user descriptor")
        if not any(
            isinstance(value, str)
            and Path(value).is_absolute()
            and Path(value).resolve() == expected_disk.resolve()
            for value in values.values()
        ):
            fail("Registered VM storage does not mount the staged configuration disk")
        return {
            "pipe": pipe,
            "topology": topology,
            "device_id": device_id,
            "vm_name": name,
            "vm_uuid": uuid,
            "owner_sid": facts["sid"],
            "vm_descriptor": str(config),
            "descriptor_sha256": hashlib.sha256(data).hexdigest(),
            "project_file": str(document.net_path),
            "project_sha256": hashlib.sha256(document.net_path.read_bytes()).hexdigest(),
            "configuration_disk": str(expected_disk),
            "verified_scope": "running_vm_descriptor_and_staged_config_disk_only",
            "runtime_isolation_verified": False,
        }

    def verify_pipe(self, channel, target):
        """Verify the actual handle's server PID, principal and VM start identity."""
        import msvcrt

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetNamedPipeServerProcessId.argtypes = [wt.HANDLE, ctypes.POINTER(wt.ULONG)]
        kernel.GetNamedPipeServerProcessId.restype = wt.BOOL
        pid = wt.ULONG()
        handle = msvcrt.get_osfhandle(channel.session._read_fd)
        if not kernel.GetNamedPipeServerProcessId(handle, ctypes.byref(pid)):
            fail("Console server PID is unknown")
        observed = self.facts(
            "$p=Get-CimInstance Win32_Process -Filter 'ProcessId="
            + str(pid.value)
            + "';if(-not $p){throw 'Console process missing'};$s=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid;@{name=$p.Name;command=$p.CommandLine;sid=$s.Sid;owner_result=$s.ReturnValue}|ConvertTo-Json -Compress"
        )
        if (
            not isinstance(observed, dict)
            or observed.get("name")
            not in {"VBoxHeadless.exe", "VirtualBoxVM.exe", "VirtualBox.exe"}
            or type(observed.get("owner_result")) is not int
            or observed.get("owner_result") != 0
            or observed.get("sid") != target["owner_sid"]
        ):
            fail("Console server is not the expected current-user VirtualBox process")
        command = observed.get("command")
        if not isinstance(command, str) or not re.search(
            r'--startvm\s+"?' + re.escape(target["vm_uuid"]) + r'"?(?:\s|$)', command, re.I
        ):
            fail("Console server command line does not bind the expected VM UUID")
        return {
            **target,
            "console_server_pid": pid.value,
            "verified_scope": "running_vm_staged_config_disk_and_native_pipe_server_identity_only",
        }
