"""Run Home Assistant for the sandbox, with the system's nameservers.

Run by scripts/sandbox.py with the sandbox's Python, in place of `hass`.
On macOS, c-ares (HA's DNS resolver) can find no nameservers and falls
back to 127.0.0.1, so nothing online resolves: the Marketplace's catalog,
HACS, the weather. This hands it the ones in /etc/resolv.conf, which
macOS keeps up to date.
"""

import sys
from pathlib import Path

import aiodns
from homeassistant.__main__ import main

RESOLV_CONF = Path("/etc/resolv.conf")
SERVERS = [
    line.split()[1]
    for line in (RESOLV_CONF.read_text().splitlines() if RESOLV_CONF.exists() else [])
    if line.startswith("nameserver") and len(line.split()) > 1
]

if SERVERS:
    _init = aiodns.DNSResolver.__init__

    def _with_servers(self, nameservers=None, *args, **kwargs):
        _init(self, nameservers or SERVERS, *args, **kwargs)

    aiodns.DNSResolver.__init__ = _with_servers

if __name__ == "__main__":
    sys.argv[0] = "hass"
    sys.exit(main())
