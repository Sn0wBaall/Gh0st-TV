"""
SSDP (Simple Service Discovery Protocol) Module - Simple Library-based Implementation

Simple replacement for the custom SSDP implementation using the netdisco library.
This provides the same interface as the original custom implementation.
"""

import logging
from typing import List
from dataclasses import dataclass

try:
    from netdisco import ssdp as netdisco_ssdp
    NETDISCO_AVAILABLE = True
except ImportError:
    NETDISCO_AVAILABLE = False
    logging.warning("netdisco library not available. Install with: pip install netdisco")


@dataclass
class SSDPResponse:
    """Represents an SSDP response from a network device."""
    location: str
    usn: str
    st: str
    cache: str = "0"

    def __repr__(self) -> str:
        return f"<SSDPResponse({self.location}, {self.st}, {self.usn})>"


def _get_usn(device) -> str:
    """UPNPEntry has no .usn attribute, it lives in .values['usn}."""
    try:
        values = getattr(device, 'values', None)
        if isinstance(values, dict) and values.get('usn'):
            return str(values.get('usn'))
    except Exception:
        pass
    return str(getattr(device, 'usn', '') or '')


def _to_response(device) -> "SSDPResponse":
    return SSDPResponse(
        location=str(getattr(device, 'location', '') or ''),
        usn=_get_usn(device),
        st=str(getattr(device, 'st', '') or ''),
        cache='0',
    )


def _is_samsung(device) -> bool:
    """netdisco always queries upnp:rootdevice, so ST is never samsung-specific.
    Check ST/USN/location strings first, then the device description."""
    st = str(getattr(device, 'st', '') or '').lower()
    usn = _get_usn(device).lower()
    location = str(getattr(device, 'location', '') or '').lower()
    if 'samsung' in st or 'samsung' in usn or 'samsung' in location:
        return True
    try:
        desc = getattr(device, 'description', None)
        if isinstance(desc, dict):
            dev = desc.get('device', {}) if isinstance(desc.get('device', {}), dict) else {}
            for key in ('manufacturer', 'manufacturerURL', 'modelName',
                        'modelDescription', 'friendlyName'):
                if 'samsung' in str(dev.get(key, '') or '').lower():
                    return True
    except Exception:
        pass
    return False


def _dedupe_key(location: str) -> str:
    """Normalize SSDP location for dedup: same TV can advertise
    different paths (/api/v2/ vs /ssdp/device-desc.xml) or trailing
    slashes. Key by IP when possible, else normalized URL."""
    import re as _re
    loc = (location or '').strip()
    m = _re.search(r'[0-9]+(?:\.[0-9]+){3}', loc)
    if m:
        return m.group(0)
    return loc.lower().rstrip('/')


def discover(service: str, timeout: int = 5, retries: int = 1, mx: int = 3) -> List[SSDPResponse]:
    """
    Discover SSDP services on the network using netdisco.
    
    Args:
        service: Service type to search for
        timeout: Socket timeout in seconds (not used by netdisco)
        retries: Number of discovery attempts (not used by netdisco)
        mx: Maximum wait time for responses (not used by netdisco)
        
    Returns:
        List of SSDP responses from discovered devices
    """
    logger = logging.getLogger(__name__)
    
    if not NETDISCO_AVAILABLE:
        logger.error("netdisco library not available")
        return []
    
    try:
        logger.debug(f"Starting SSDP discovery for {service}")

        # Respect the timeout parameter (netdisco default is 2s)
        try:
            scan_timeout = max(2, int(timeout))
        except Exception:
            scan_timeout = 5
        devices = netdisco_ssdp.scan(timeout=scan_timeout)

        # Filter for the requested service (match ST or USN), deduped by IP
        # (same TV can answer with different paths, e.g. /api/v2/ vs xml)
        seen = {}
        for device in devices:
            st = str(getattr(device, 'st', '') or '')
            if service.lower() in st.lower() or service.lower() in _get_usn(device).lower():
                resp = _to_response(device)
                key = _dedupe_key(resp.location)
                if key and key not in seen:
                    seen[key] = resp
        matching_devices = list(seen.values())

        # Samsung-specific ST never matches a generic upnp:rootdevice scan,
        # fall back to the targeted M-SEARCH implementation.
        if not matching_devices and 'samsung' in service.lower():
            try:
                from . import ssdp_custom as custom_ssdp
                for r in custom_ssdp.discover(service, timeout=timeout, retries=max(1, retries), mx=mx):
                    matching_devices.append(SSDPResponse(
                        location=str(getattr(r, 'location', '') or ''),
                        usn=str(getattr(r, 'usn', '') or ''),
                        st=str(getattr(r, 'st', '') or ''),
                        cache=str(getattr(r, 'cache', '0') or '0'),
                    ))
            except Exception as e:
                logger.debug(f"Custom SSDP fallback failed: {e}")

        logger.info(f"SSDP discovery found {len(matching_devices)} devices for {service}")
        return matching_devices
        
    except Exception as e:
        logger.error(f"SSDP discovery failed: {e}")
        return []


def scan_network(wait: float = 5) -> List[SSDPResponse]:
    """
    Scan network for Samsung TVs using SSDP discovery.

    Strategy: targeted Samsung M-SEARCH (reliable) + generic netdisco
    scan filtered by Samsung indicators (catches models that ignore
    the targeted ST). Results are deduplicated by location.

    Args:
        wait: timeout for discovery in seconds

    Returns:
        List of SSDP responses from discovered Samsung TVs
    """
    logger = logging.getLogger(__name__)

    try:
        logger.debug(f"Starting network scan for Samsung TVs")
        try:
            timeout = max(2, int(wait))
        except Exception:
            timeout = 5

        found = {}
        # 1) Targeted Samsung M-SEARCH (the reliable path)
        try:
            from . import ssdp_custom as custom_ssdp
            for r in custom_ssdp.discover(
                "urn:samsung.com:device:RemoteControlReceiver:1",
                timeout=timeout,
            ):
                loc = str(getattr(r, 'location', '') or '')
                key = _dedupe_key(loc)
                if key and key not in found:
                    found[key] = SSDPResponse(
                        location=loc,
                        usn=str(getattr(r, 'usn', '') or ''),
                        st=str(getattr(r, 'st', '') or ''),
                        cache=str(getattr(r, 'cache', '0') or '0'),
                    )
        except Exception as e:
            logger.debug(f"Targeted Samsung scan failed: {e}")

        # 2) Generic netdisco scan + Samsung filter
        if NETDISCO_AVAILABLE:
            try:
                devices = netdisco_ssdp.scan(timeout=timeout)
                for device in devices:
                    if _is_samsung(device):
                        resp = _to_response(device)
                        key = _dedupe_key(resp.location)
                        if key and key not in found:
                            found[key] = resp
            except Exception as e:
                logger.debug(f"Generic netdisco scan failed: {e}")
        else:
            logger.debug("netdisco not available, only targeted scan used")

        samsung_devices = list(found.values())
        logger.info(f"Network scan completed, found {len(samsung_devices)} Samsung TVs")
        return samsung_devices

    except KeyboardInterrupt:
        logger.info('Search interrupted by user')
        return []
    except Exception as e:
        logger.error(f"Network scan failed: {e}")
        return []


def probe_ip(ip: str, timeout: float = 3.0) -> "SSDPResponse | None":
    """Direct probe of one IP via /api/v2 (no multicast needed).

    Fast path: single GET to http://IP:8001/api/v2/. Only if that fails
    AND a Samsung port is open, fall back to the full get_by_ip()
    (retries + legacy XML) for pre-2016 models without api/v2.

    Returns an SSDPResponse if the host answers like a Samsung TV,
    else None.
    """
    logger = logging.getLogger(__name__)
    ip = ip.strip()
    try:
        from . import tvinfo as _tvinfo
        for _ in range(2):  # standby TVs drop the first request sometimes
            try:
                _tvinfo.identify_api_v2(ip, timeout=min(2.0, timeout))
                return SSDPResponse(location=f"http://{ip}:8001/api/v2/",
                                    usn="", st="urn:samsung.com:device:RemoteControlReceiver:1", cache="0")
            except Exception as e:
                logger.debug(f"probe {ip}: api/v2 attempt failed ({e})")
                last = e
        logger.debug(f"probe {ip}: api/v2 fast path failed ({last})")
        # Slow path (legacy models): ports open but no api/v2?
        if not any(_tvinfo.is_port_open(ip, p, timeout=min(2.0, timeout))
                   for p in (8001, 8002, 55000, 9197)):
            return None
        try:
            _tvinfo.get_by_ip(ip, timeout=max(4.0, timeout))
            return SSDPResponse(location=f"http://{ip}:8001/ssdp/device-desc.xml",
                                usn="", st="urn:samsung.com:device:RemoteControlReceiver:1", cache="0")
        except Exception as e:
            logger.debug(f"probe {ip}: ports open but not Samsung ({e})")
            return None
    except Exception as e:
        logger.debug(f"probe {ip} failed: {e}")
        return None


def _api_v2_sweep(hosts, timeout: float, workers: int):
    """One GET /api/v2 per host. Returns list of (ip, info)."""
    import urllib.request as _url
    import json as _json
    from concurrent.futures import ThreadPoolExecutor as _Pool

    def check(h: str):
        # Two attempts: standby TVs often drop the first request.
        for _ in range(2):
            try:
                req = _url.Request(f"http://{h}:8001/api/v2/",
                                   headers={"User-Agent": "Mozilla/5.0"})
                with _url.urlopen(req, timeout=timeout) as r:
                    data = _json.loads(r.read().decode('utf-8', errors='ignore'))
                dev = data.get('device', data)
                if not isinstance(dev, dict):
                    return None  # definitive: answers but not a TV payload
                blob = (str(dev.get('type', '')) + ' ' + str(data.get('type', ''))).lower()
                if 'samsung' not in blob and 'smarttv' not in blob:
                    return None  # definitive: another device on :8001
                name = dev.get('name') or data.get('name') or 'Samsung TV'
                model = (dev.get('modelNumber') or dev.get('modelName')
                         or data.get('modelNumber') or data.get('modelName') or '?')
                return (h, {'fn': str(name), 'ip': h, 'model': str(model)})
            except Exception:
                continue  # timeout/connection: retry once
        return None

    hits = []
    with _Pool(max_workers=workers) as ex:
        for res in ex.map(check, hosts):
            if res is not None:
                hits.append(res)
    return hits


def scan_subnet(cidr: str, timeout: float = 1.5, workers: int = 128) -> List[SSDPResponse]:
    """Sweep a CIDR via GET /api/v2 (e.g. 192.168.1.0/24).

    One HTTP request per host, no port pre-scan: fast enough for a /24
    (~10-20 s). Hosts with pre-2016 firmware (no api/v2) are checked
    afterwards via probe_ip() legacy fallback.
    """
    import ipaddress
    from concurrent.futures import ThreadPoolExecutor, as_completed
    logger = logging.getLogger(__name__)
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except Exception as e:
        logger.error(f"Invalid CIDR {cidr}: {e}")
        return []
    hosts = [str(h) for h in net.hosts()]
    if len(hosts) > 1024:
        logger.error(f"Subnet too large ({len(hosts)} hosts), refusing")
        return []
    logger.info(f"Probing {len(hosts)} hosts in {cidr} via /api/v2...")
    found = {}
    for h, _info in _api_v2_sweep(hosts, timeout=timeout, workers=workers):
        loc = f"http://{h}:8001/api/v2/"
        key = _dedupe_key(loc)
        if key not in found:
            found[key] = SSDPResponse(location=loc, usn="",
                                      st="urn:samsung.com:device:RemoteControlReceiver:1", cache="0")
            logger.info(f"Samsung TV at {loc}")
    # Legacy second pass only for hosts with Samsung ports open but no api/v2
    if found:
        return list(found.values())
    logger.debug("api/v2 sweep found nothing, trying legacy probe on open ports...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(probe_ip, h, timeout): h for h in hosts}
        for f in as_completed(futs):
            try:
                r = f.result()
                if r is not None:
                    key = _dedupe_key(r.location)
                    if key not in found:
                        logger.info(f"Samsung TV at {r.location}")
                        found[key] = r
            except Exception:
                pass
    return list(found.values())


def local_subnet() -> str:
    """Best-effort local /24 (e.g. 192.168.1.0/24) for the auto-fallback."""
    import socket as _socket
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local = s.getsockname()[0]
        s.close()
        base = ".".join(local.split(".")[:3]) + ".0/24"
        return base
    except Exception:
        return "192.168.1.0/24"


# Fallback to custom implementation if netdisco is not available
if not NETDISCO_AVAILABLE:
    try:
        from . import ssdp_custom as custom_ssdp
        discover = custom_ssdp.discover
        scan_network = custom_ssdp.scan_network
        SSDPResponse = custom_ssdp.SSDPResponse
        logging.info("Using custom SSDP implementation as fallback")
    except ImportError:
        logging.error("No SSDP implementation available")
