"""Run style checks and the complete software suite, preserving run receipts."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-root", type=Path, default=root / "work" / "checks")
    args = parser.parse_args()
    environment = dict(os.environ, MCP_HCL_ALLOW_LIVE_WRITE="0", PYTHONIOENCODING="utf-8")
    for operation in ("check", "format"):
        command = [sys.executable, "-m", "ruff", operation]
        if operation == "format":
            command.append("--check")
        command.extend(("src", "tests", "scripts"))
        result = subprocess.run(command, cwd=root, env=environment, check=False)
        if result.returncode:
            return result.returncode
    modules = sorted(path.stem for path in (root / "tests").glob("test_*.py"))
    command = [
        sys.executable,
        str(root / "scripts" / "run_software_verification.py"),
        "--receipt-root",
        str(args.receipt_root.resolve()),
        "--allow-software-script-tests",
        *modules,
    ]
    return subprocess.run(command, cwd=root, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
