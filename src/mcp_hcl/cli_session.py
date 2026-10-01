"""Persistent, leased, bounded Comware console transactions."""
from __future__ import annotations
import hashlib
import base64
import os
import re
import time
import subprocess
from pathlib import Path
from mcp_hcl.console import ConsoleError, ConsoleSession, describe, open_console_pipe, _decode

PROMPT = re.compile(r'(?:^|\n)(<[^<>\r\n]{1,128}>|\[[^\[\]\r\n]{1,160}\])\s*$')
PAGER = re.compile(r'(?:----\s*More\s*----|--More--)\s*$', re.I)
CLI_ERROR = re.compile(r'(?:^|\n)\s*(?:%\s*(?:Unrecognized|Incomplete|Wrong|Error|Too many)|Error:|Invalid command|Permission denied)', re.I)


def clean_text(raw: bytes) -> str:
    text = _decode(raw)[0].replace('\r', '')
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text)
    while '\b' in text: text = re.sub(r'.?\x08', '', text)
    return text


class PipeLease:
    def __init__(self, root: Path, pipe: str):
        describe(pipe)
        root.mkdir(parents=True, exist_ok=True)
        path = root / (hashlib.sha256(pipe.casefold().encode()).hexdigest() + '.lock')
        if path.is_symlink(): raise ConsoleError('Pipe lease cannot be linked')
        self.fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.fstat(self.fd).st_size == 0: os.write(self.fd, b'0')
            os.lseek(self.fd, 0, os.SEEK_SET)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self.fd)
            raise ConsoleError('Console channel is busy; release the other client') from exc

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class PersistentConsole:
    def __init__(self, pipe: str, lease_root: Path, *, session=None, timeout=12.0, max_bytes=1024*1024):
        self.pipe = pipe
        self.native_channel = session is None
        self.lease = PipeLease(lease_root, pipe)
        self.timeout = timeout
        self.max_bytes = max_bytes
        try:
            if session is None and os.name == 'nt':
                # Never close PuTTY or MultiCC automatically. Query only a
                # boolean; do not expose other process command lines.
                needle=pipe.replace("'","''")
                query=("$needle='"+needle+"'; $p=@(Get-CimInstance Win32_Process -ErrorAction Stop | "
                       "Where-Object {$_.Name -in @('putty.exe','SimwareMultiCC.exe')}); "
                       "[bool](@($p | Where-Object {$_.Name -eq 'SimwareMultiCC.exe' -or "
                       "[string]::IsNullOrEmpty($_.CommandLine) -or $_.CommandLine.IndexOf($needle,[StringComparison]::OrdinalIgnoreCase) -ge 0}).Count)")
                checked=subprocess.run(['powershell.exe','-NoProfile','-Command',query],capture_output=True,timeout=10)
                if checked.returncode != 0 or checked.stdout.strip().lower() != b'false':
                    raise ConsoleError('PuTTY/MultiCC may own this console; release it before requesting an exclusive lease')
            self.session = session or ConsoleSession(open_console_pipe(pipe))
        except Exception:
            self.lease.close()
            raise
        self.prompt = None
        self.history = []

    def _receive(self, *, confirmation=False, initial=b''):
        output = bytearray(initial)
        deadline = time.monotonic() + self.timeout
        pager_count = 0
        last_pager_size = -1
        confirmed = False
        while time.monotonic() < deadline:
            if len(output) > self.max_bytes:
                raise ConsoleError('Console output exceeds the evidence limit; truncation is not accepted')
            text = clean_text(bytes(output))
            if confirmation and not confirmed and re.search(r'\[(?:Y/N|y/n)\]:?\s*$', text):
                self.session.send('Y')
                confirmed = True
            if PAGER.search(text) and len(output) != last_pager_size:
                # Space is the documented pager continuation, not a command line.
                try: sent = os.write(self.session._write_fd, b' ')
                except OSError as exc: raise ConsoleError('Pager continuation failed') from exc
                if sent != 1: raise ConsoleError('Pager continuation write failed')
                last_pager_size = len(output)
                pager_count += 1
                if pager_count > 256: raise ConsoleError('Console pagination exceeded the page limit')
            match = PROMPT.search(text)
            if match:
                self.prompt = match[1]
                return bytes(output)
            chunk = self.session._read_available()
            if chunk:
                output.extend(chunk)
                self.partial_output = bytes(output)
            else: time.sleep(0.02)
        raise ConsoleError('No complete console prompt before deadline')

    def exchange(self, command: str, *, confirmation=False) -> dict:
        stale = self.session.drain()
        if len(stale) >= self.max_bytes: raise ConsoleError('Stale stream cannot be drained safely')
        self.session.send(command)
        self.partial_output = b''
        try:
            raw = self._receive(confirmation=confirmation)
        except ConsoleError as exc:
            self.history.append({'command': command, 'output': clean_text(self.partial_output),
                                 'raw_output_b64': base64.b64encode(self.partial_output).decode('ascii'),
                                 'complete': False, 'error': str(exc)})
            raise
        text = clean_text(raw)
        lines = text.splitlines()
        # An idle gap or a previous prompt cannot attribute output to this command.
        echo = any(line.strip() == command or line.strip().endswith('>' + command) or
                   line.strip().endswith(']' + command) for line in lines)
        result = {'command': command, 'output': text, 'prompt': self.prompt,
                  'raw_output_b64': base64.b64encode(raw).decode('ascii'),
                  'output_sha256': hashlib.sha256(raw).hexdigest(),
                  'request_sha256': hashlib.sha256(command.encode('ascii')).hexdigest(),
                  'discarded_stale_bytes': len(stale), 'complete': True}
        self.history.append(result)
        if not echo: raise ConsoleError('Console command echo is missing; response attribution failed')
        if CLI_ERROR.search(text): raise ConsoleError('Device rejected the console command')
        return result

    def close(self):
        try: self.session.close()
        finally: self.lease.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
