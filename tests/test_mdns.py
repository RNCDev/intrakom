import os
import time

import pytest

from intrakom import mdns


@pytest.mark.skipif(
    not os.environ.get("INTRAKOM_TEST_MDNS"),
    reason="mDNS multicast test is slow (~minutes on macOS); set INTRAKOM_TEST_MDNS=1 to run",
)
def test_advertise_and_discover_roundtrip():
    zc = mdns.advertise_hub(port=18000, version="9.9.9-test")
    try:
        time.sleep(0.3)
        hubs = mdns.discover_hubs(timeout=2.0)
    finally:
        mdns.unadvertise(zc)
    assert any(h.port == 18000 and h.version == "9.9.9-test" for h in hubs), (
        f"Expected a hub on port 18000 in {hubs}"
    )
