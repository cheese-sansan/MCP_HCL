from __future__ import annotations

import socket
import threading
import unittest
from contextlib import contextmanager

from mcp_hcl.backend import HclBackend


@contextmanager
def responding_backend(replies: list[tuple[str, str]]):
    """A real TCP peer using HCL's captured response framing."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(3)
    failures: list[Exception] = []

    def serve() -> None:
        try:
            for command, response in replies:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(2)
                    request = bytearray()
                    while not request.endswith(b"\n"):
                        chunk = connection.recv(1024)
                        if not chunk:
                            raise AssertionError("Client closed before sending a command")
                        request.extend(chunk)
                    identifier, actual_command = request.decode("ascii").strip().split(" ", 1)
                    if actual_command != command:
                        raise AssertionError(f"Unexpected command: {actual_command}")
                    message = response.replace("{id}", identifier).encode("utf-8")
                    # Force the /end terminator across TCP reads.
                    connection.sendall(message[:-1])
                    connection.sendall(message[-1:])
        except Exception as exc:
            failures.append(exc)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield HclBackend(port=listener.getsockname()[1], timeout=0.5)
    finally:
        thread.join(timeout=4)
        listener.close()
        if failures:
            raise failures[0]
        if thread.is_alive():
            raise AssertionError("Fake backend did not finish")


class BackendProtocolTests(unittest.TestCase):
    def test_real_socket_roundtrip_and_verification_scope(self) -> None:
        with responding_backend([
            ("simwarewrapper version", "{id}-101-1.0.0&6.0.14\r\n/end"),
            ("simwarewrapper system_memory", "{id}-101-14708\r\n/end"),
        ]) as backend:
            result = backend.status()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["backend_version"], "1.0.0&6.0.14")
        self.assertEqual(result["reported_system_memory_mb"], 14708)
        self.assertEqual(result["verified_scope"], "version_and_memory_protocol_readback")
        self.assertFalse(result["full_live_gate_passed"])
        self.assertFalse(result["live_canvas_verified"])
        self.assertEqual(len(result["evidence"]), 2)

    def test_response_for_another_request_is_rejected(self) -> None:
        with responding_backend([
            ("simwarewrapper version", "0-101-1.0.0&6.0.14\r\n/end"),
        ]) as backend:
            result = backend.status()
        self.assertEqual(result["status"], "unverified")
        self.assertIn("different request ID", result["error"])
        self.assertNotIn("backend_version", result)

    def test_valid_version_does_not_mask_invalid_memory(self) -> None:
        with responding_backend([
            ("simwarewrapper version", "{id}-101-1.0.0&6.0.14\r\n/end"),
            ("simwarewrapper system_memory", "{id}-101-not-a-number\r\n/end"),
        ]) as backend:
            result = backend.status()
        self.assertEqual(result["status"], "partial")
        self.assertIn("memory response is invalid", result["error"])
        self.assertFalse(result["full_live_gate_passed"])

    def test_non_loopback_and_mutating_commands_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            HclBackend(host="192.168.1.1")
        with self.assertRaises(ValueError):
            HclBackend()._request("simware create_device")


if __name__ == "__main__":
    unittest.main()
