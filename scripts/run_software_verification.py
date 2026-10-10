"""Run a scoped suite and preserve a new receipt with each source/test manifest."""

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--receipt-root", required=True)
parser.add_argument("--package-root")
parser.add_argument(
    "--allow-software-script-tests",
    action="store_true",
    help="Allow the reviewed PowerShell parsing/Plan/ValidateOnly test modules",
)
parser.add_argument("modules", nargs="+")
args = parser.parse_args()
package_root = Path(args.package_root).resolve() if args.package_root else root / "src"
os.environ["MCP_HCL_ALLOW_LIVE_WRITE"] = "0"
os.environ["MCP_SOFTWARE_ALLOW_SCRIPT_TESTS"] = "1" if args.allow_software_script_tests else "0"
guard = root / "tests/software_native_guard"
os.environ["PYTHONPATH"] = os.pathsep.join((str(guard), str(package_root), str(root / "tests")))
sys.path[:0] = [str(package_root), str(root / "tests")]
import mcp_hcl

assert Path(mcp_hcl.__file__).resolve().is_relative_to(package_root), mcp_hcl.__file__
out = Path(args.receipt_root) / uuid4().hex
out.mkdir(parents=True)
os.environ["MCP_SOFTWARE_NATIVE_AUDIT_ROOT"] = str(out)
# Import the same tripwire now; child interpreters load it at startup.
sys.path.insert(0, str(guard))
import sitecustomize

manifest = {
    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ("src", "tests")
    for p in (root / folder).rglob("*")
    if p.is_file()
    and "__pycache__" not in p.parts
    and not any(x.endswith(".egg-info") for x in p.parts)
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2))
rows = []


class Result(unittest.TextTestResult):
    def startTest(self, test):
        os.environ["MCP_SOFTWARE_CURRENT_TEST_MODULE"] = test.id().split(".")[0]
        super().startTest(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        rows.append({"test": test.id(), "status": "Passed"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        rows.append({"test": test.id(), "status": "Failed"})

    def addError(self, test, err):
        super().addError(test, err)
        rows.append({"test": test.id(), "status": "Failed", "kind": "error"})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        rows.append({"test": test.id(), "status": "Skipped", "reason": reason})

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        rows.append(
            {
                "test": subtest.id(),
                "status": "Passed" if err is None else "Failed",
                "kind": "subtest",
            }
        )


with (
    (out / "tests.log").open("w", encoding="utf-8") as log,
    contextlib.redirect_stdout(log),
    contextlib.redirect_stderr(log),
):
    suite = unittest.defaultTestLoader.loadTestsFromNames(args.modules)
    result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=Result).run(suite)
receipt = {
    "operation_id": out.name,
    "executor": "Codex",
    "modules": args.modules,
    "python": sys.version,
    "import_path": mcp_hcl.__file__,
    "live_write": "0",
    "tests_run": result.testsRun,
    "failures": len(result.failures),
    "errors": len(result.errors),
    "skipped": len(result.skipped),
    "success": result.wasSuccessful(),
    "cases": rows,
    "full_live_gate_passed": False,
    "dependencies": sorted(
        d.metadata["Name"] + "==" + d.version for d in importlib.metadata.distributions()
    ),
    "native_process_audit": [
        json.loads(line) for p in out.glob("native-*.jsonl") for line in p.read_text().splitlines()
    ],
}
receipt["native_process_audit_passed"] = all(
    row["allowed"] for row in receipt["native_process_audit"]
)
receipt["manifest_unchanged"] = all(
    (root / path).is_file() and hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
    for path, digest in manifest.items()
)
receipt["success"] = (
    receipt["success"] and receipt["native_process_audit_passed"] and receipt["manifest_unchanged"]
)
(out / "result.json").write_text(
    json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(
    json.dumps(
        {
            k: v
            for k, v in receipt.items()
            if k not in ("cases", "dependencies", "native_process_audit")
        },
        ensure_ascii=False,
    )
)
print("Evidence:", out)
sys.exit(not receipt["success"])
