"""Standard tests may connect only to ephemeral listeners created by this test process."""

import socket

import pytest


@pytest.fixture(autouse=True)
def no_generation_connections(monkeypatch):
    owned = set()
    original_bind = socket.socket.bind
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def bind(sock, address):
        result = original_bind(sock, address)
        if isinstance(address, tuple) and address[1] == 0:
            owned.add(sock.getsockname()[:2])
        return result

    def connect(sock, address):
        if isinstance(address, tuple) and address[:2] not in owned:
            raise AssertionError(f"Generation/external connection forbidden in tests: {address}")
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if isinstance(address, tuple) and address[:2] not in owned:
            raise AssertionError(f"Generation/external connection forbidden in tests: {address}")
        return original_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "bind", bind)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
