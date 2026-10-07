"""Use IPv4 only. On some home/office networks Telegram hangs over IPv6 but works over IPv4."""
import socket

_orig = socket.getaddrinfo


def _ipv4_only(host, port, family=0, *a, **k):
    return _orig(host, port, socket.AF_INET, *a, **k)


socket.getaddrinfo = _ipv4_only
