"""Owner-only, in-memory password delivery to the reviewed account helper.

Passwords are never command arguments or files. --test checks the transport
without invoking any account mutation. Windows elevation remains an OS action.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import ctypes.wintypes as wt
import getpass
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pywintypes
import win32api
import win32con
import win32crypt
import win32event
import win32file
import win32pipe
import win32security


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.ConvertSidToStringSid(
            win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        )
    finally:
        token.Close()
    if (
        plan.get("owner_sid") != sid
        or plan.get("kind") != "lab_account_plan"
        or plan.get("status") != "prepared"
    ):
        raise ValueError("Only the same owner can execute a prepared account plan")
    if plan.get("account_name") != "MCPHCLLab":
        raise ValueError("Broker is scoped to the reviewed MCPHCLLab account")
    operation = uuid4().hex
    directory = args.output_root.resolve() / operation
    directory.mkdir(parents=True, exist_ok=False)
    helper = Path(__file__).with_name("hcl_lab_account.ps1").resolve()
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    name = "mcphcl-account-" + operation
    record = {
        "operation_id": operation,
        "owner_sid": sid,
        "account_name": "MCPHCLLab",
        "scope": "password_transport_test" if args.test else "authorized_standard_account_creation",
        "credential_transport": "owner_only_named_pipe_with_current_user_dpapi",
        "password_in_argv": False,
        "password_in_files": False,
        "phase": "preparing",
    }

    def save():
        (directory / "broker.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    def progress(phase):
        record["phase"] = phase
        save()
        print(json.dumps({"phase": phase, "operation_id": operation}), flush=True)

    pipe = None
    launcher = None
    try:
        password = "IPC-transport-test" if args.test else getpass.getpass("Secure password input: ")
        protected = win32crypt.CryptProtectData(password.encode("utf-8"), None, None, None, None, 1)
        del password
        payload = base64.b64encode(protected) + b"\n"
        attributes = pywintypes.SECURITY_ATTRIBUTES()
        attributes.SECURITY_DESCRIPTOR = (
            win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
                f"D:P(A;;GA;;;{sid})(A;;GA;;;SY)", win32security.SDDL_REVISION_1
            )
        )
        pipe = win32pipe.CreateNamedPipe(
            r"\\.\pipe" + "\\" + name,
            win32pipe.PIPE_ACCESS_OUTBOUND | win32file.FILE_FLAG_OVERLAPPED,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1,
            16384,
            16384,
            0,
            attributes,
        )
        connection = pywintypes.OVERLAPPED()
        connection.hEvent = win32event.CreateEvent(None, True, False, None)
        try:
            win32pipe.ConnectNamedPipe(pipe, connection)
        except pywintypes.error as exc:
            if exc.winerror != 997:
                raise

        def quoted(value):
            return "'" + str(value).replace("'", "''") + "'"

        if args.test:
            worker = directory / "transport-test.ps1"
            worker.write_text(
                "$ErrorActionPreference='Stop';$t=$null;$e=$null;"
                " $ast=[Management.Automation.Language.Parser]::ParseFile("
                + quoted(helper)
                + ",[ref]$t,[ref]$e);"
                " $function=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Receive-Lab-Password'},$true);"
                " . ([ScriptBlock]::Create($function.Extent.Text));$PasswordPipe="
                + quoted(name)
                + ";"
                " $secret=Receive-Lab-Password;try{if($secret.Length -ne 18 -or -not $secret.IsReadOnly()){throw 'Transport integrity failed'};"
                " @{status='verified';scope='protected_password_transport_only'}|ConvertTo-Json}finally{$secret.Dispose()}",
                encoding="utf-8-sig",
            )
            launcher = subprocess.Popen(
                [str(shell), "-NoProfile", "-File", str(worker)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            helper_pid = launcher.pid
        else:
            # Only paths, the public nonce and the account name enter argv.
            arguments = [
                "-NoProfile",
                "-File",
                '"' + str(helper) + '"',
                "-Action",
                "Create",
                "-AccountName",
                "MCPHCLLab",
                "-RecordFile",
                '"' + str(args.plan.resolve()) + '"',
                "-OutputRoot",
                '"' + str(directory / "account-receipts") + '"',
                "-PasswordPipe",
                name,
            ]
            command = (
                "$p=Start-Process -FilePath "
                + quoted(shell)
                + " -Verb RunAs -WindowStyle Hidden -PassThru -ArgumentList @("
                + ",".join(quoted(argument) for argument in arguments)
                + ");$p.Id"
            )
            progress("windows_elevation_pending")
            launcher = subprocess.Popen(
                [str(shell), "-NoProfile", "-Command", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            while launcher.poll() is None:
                time.sleep(0.2)
            stdout, stderr = launcher.communicate()
            if launcher.returncode or not stdout.strip().isdigit():
                raise RuntimeError("Windows elevation did not return a helper PID")
            helper_pid = int(stdout.strip())
        record["helper_pid"] = helper_pid
        progress("waiting_for_owner_helper_connection")
        if win32event.WaitForSingleObject(connection.hEvent, 15000) != win32event.WAIT_OBJECT_0:
            raise TimeoutError("Owner helper did not connect")
        win32file.GetOverlappedResult(pipe, connection, True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetNamedPipeClientProcessId.argtypes = [wt.HANDLE, ctypes.POINTER(wt.ULONG)]
        kernel.GetNamedPipeClientProcessId.restype = wt.BOOL
        actual_pid = wt.ULONG()
        if (
            not kernel.GetNamedPipeClientProcessId(int(pipe), ctypes.byref(actual_pid))
            or actual_pid.value != helper_pid
        ):
            raise RuntimeError("Password recipient process identity mismatch")
        write = pywintypes.OVERLAPPED()
        write.hEvent = win32event.CreateEvent(None, True, False, None)
        win32file.WriteFile(pipe, payload, write)
        if win32event.WaitForSingleObject(write.hEvent, 10000) != win32event.WAIT_OBJECT_0:
            raise TimeoutError("Protected password delivery did not finish")
        if win32file.GetOverlappedResult(pipe, write, True) != len(payload):
            raise RuntimeError("Partial protected password delivery")
        del payload, protected
        progress("password_delivered_without_persistence")
        if args.test:
            stdout, stderr = launcher.communicate(timeout=15)
            if launcher.returncode:
                raise RuntimeError("Transport receiver did not pass its checks")
            record["test_result"] = json.loads(stdout)
            record["status"] = "verified"
        else:
            # Poll the specific elevated process and its request-local receipt.
            # Do not replay Create after timeout or partial completion.
            process = win32api.OpenProcess(
                win32con.SYNCHRONIZE | win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, helper_pid
            )
            try:
                deadline = time.monotonic() + 45
                while win32event.WaitForSingleObject(process, 200) == win32event.WAIT_TIMEOUT:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "Account helper has no terminal result yet; reconcile its existing receipt"
                        )
            finally:
                process.Close()
            receipts = list((directory / "account-receipts").glob("*/result.json"))
            if len(receipts) != 1:
                raise RuntimeError("No unique creation receipt")
            creation = json.loads(receipts[0].read_text(encoding="utf-8-sig"))
            record["creation_receipt"] = str(receipts[0])
            record["account_sid"] = creation.get("account_sid")
            record["status"] = creation["status"]
        save()
        print(json.dumps(record, indent=2), flush=True)
    except Exception as exc:
        record.update(status="unverified", error_type=type(exc).__name__)
        if args.test:
            record["test_error"] = str(exc)
        save()
        print(json.dumps(record, indent=2), flush=True)
        raise SystemExit(2)
    finally:
        if pipe is not None:
            pipe.Close()


if __name__ == "__main__":
    main()
