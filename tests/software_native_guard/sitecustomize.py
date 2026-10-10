"""Acceptance-only subprocess tripwire, also installed in SDK server children."""

import json
import os
import shlex
import sys
from pathlib import Path

audit_root = os.environ.get("MCP_SOFTWARE_NATIVE_AUDIT_ROOT")
if audit_root:

    def observe(event, args):
        if event not in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn"}:
            return
        executable = args[0]
        command = args[1] if event == "subprocess.Popen" else []
        if isinstance(command, str):
            command = [token.strip('"') for token in shlex.split(command, posix=False)]
        sdk = (
            event == "subprocess.Popen"
            and isinstance(command, (list, tuple))
            and len(command) == 3
            and list(command[1:]) == ["-m", "mcp_hcl.server"]
            and Path(command[0]).resolve() == Path(sys.executable).resolve()
            and (executable is None or Path(executable).resolve() == Path(sys.executable).resolve())
        )
        offline_cli = (
            event == "subprocess.Popen"
            and len(command) >= 5
            and list(command[1:4]) == ["-B", "-m", "mcp_hcl.lab_bundle"]
            and command[4] in {"collect", "import", "accept-wireless"}
            and Path(command[0]).resolve() == Path(sys.executable).resolve()
        )
        script_test = (
            event == "subprocess.Popen"
            and command
            and os.environ.get("MCP_SOFTWARE_ALLOW_SCRIPT_TESTS") == "1"
            and os.environ.get("MCP_SOFTWARE_CURRENT_TEST_MODULE")
            in {"test_live_gate_script", "test_lab_account_plan", "test_p0", "test_050_environment"}
            and Path(command[0]).name.lower() == "powershell.exe"
            and "-NoProfile" in command
        )
        allowed = sdk or offline_cli or script_test
        executable = str(executable or (command[0] if command else "unknown"))
        row = {
            "event": event,
            "executable": executable,
            "allowed": allowed,
            "scope": "stdio_server"
            if sdk
            else "offline_cli"
            if offline_cli
            else "software_script_test"
            if script_test
            else "blocked",
        }
        with (Path(audit_root) / ("native-" + str(os.getpid()) + ".jsonl")).open(
            "a", encoding="utf-8"
        ) as log:
            log.write(json.dumps(row) + "\n")
        if not allowed:
            raise AssertionError("Unexpected external process in software acceptance")

    sys.addaudithook(observe)
