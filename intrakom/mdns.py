"""mDNS / Bonjour hub advertise + discovery."""

import logging
import socket
import time
from dataclasses import dataclass
from typing import List

from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_intrakom._tcp.local."


@dataclass
class DiscoveredHub:
    name: str
    address: str
    port: int
    version: str = ""


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def advertise_hub(port: int, version: str) -> Zeroconf:
    hostname = socket.gethostname().split(".")[0]
    ip = _local_ip()
    info = ServiceInfo(
        SERVICE_TYPE,
        f"{hostname}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={"version": version},
        server=f"{hostname}.local.",
    )
    zc = Zeroconf()
    zc.register_service(info)
    zc._intrakom_info = info  # stash for unregister
    logger.info("mDNS advertising %s on %s:%d", hostname, ip, port)
    return zc


def unadvertise(zc: Zeroconf) -> None:
    info = getattr(zc, "_intrakom_info", None)
    try:
        if info is not None:
            zc.unregister_service(info)
    finally:
        zc.close()


class _Collector(ServiceListener):
    def __init__(self) -> None:
        self.found: List[DiscoveredHub] = []

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name, timeout=1500)
        if not info or not info.addresses:
            return
        addr = socket.inet_ntoa(info.addresses[0])
        ver = ""
        if info.properties and b"version" in info.properties:
            ver = info.properties[b"version"].decode("utf-8", errors="replace")
        server = (info.server or "").rstrip(".")
        self.found.append(
            DiscoveredHub(name=server, address=addr, port=info.port, version=ver)
        )

    def remove_service(self, *_): pass
    def update_service(self, *_): pass


def discover_hubs(timeout: float = 2.0) -> List[DiscoveredHub]:
    zc = Zeroconf()
    collector = _Collector()
    ServiceBrowser(zc, SERVICE_TYPE, collector)
    time.sleep(timeout)
    zc.close()
    return collector.found
