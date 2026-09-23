"""Choose one checked network route for a child process."""

from __future__ import annotations

from finesub_bootstrap.http_client import NetworkRoute


_PROXY_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


def apply_network_route(environment: dict[str, str], route: NetworkRoute) -> None:
    """Replace inherited proxy settings instead of letting stale ones survive."""

    for key in _PROXY_KEYS:
        environment.pop(key, None)
    if route.proxy is not None:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            environment[key] = route.proxy
