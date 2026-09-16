"""
TV Information Module

Handles retrieving and parsing TV information from Samsung TVs.
"""

import re
import json
import socket
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
import logging
from typing import Dict, Optional


def getMethod(model: str) -> str:
    """
    Determine the connection method based on TV model.
    
    Args:
        model: TV model string (e.g., 'UN55F8000')
        
    Returns:
        Connection method: 'legacy' for older models (C, D, E, F), 'websocket' for newer
    """
    logger = logging.getLogger(__name__)
    
    # Legacy models (C, D, E, F series)
    legacy_models = {'C', 'D', 'E', 'F'}
    
    if len(model) < 5:
        logger.warning(f"Invalid model format: {model}")
        return 'websocket'
    
    model_series = model[4]
    method = 'legacy' if model_series in legacy_models else 'websocket'
    
    logger.debug(f"Model: {model_series} returns method: {method}")
    return method


def identify_api_v2(ip: str, timeout: float = 2.0) -> Dict[str, str]:
    """Single GET to http://IP:8001/api/v2/ (JSON, Tizen 2016+).

    This is the fastest reliable Samsung check: one HTTP request, no
    port pre-scan, no XML fallbacks. Raises on any failure so callers
    can decide to retry or fall back to legacy endpoints.
    """
    logger = logging.getLogger(__name__)
    ip = ip.strip()
    if not re.match(r'^[0-9]+(?:\.[0-9]+){3}$', ip):
        raise ValueError(f"Invalid IP: {ip}")
    url = f"http://{ip}:8001/api/v2/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode('utf-8', errors='ignore'))
    dev = data.get('device', data)
    if not isinstance(dev, dict):
        raise ValueError("unexpected api/v2 payload")
    # Confirm it really is a Samsung TV, not another UPnP gadget on :8001
    blob = (str(dev.get('type', '')) + ' ' + str(data.get('type', ''))).lower()
    if 'samsung' not in blob and 'smarttv' not in blob and 'dtv' not in str(dev.get('description', '')).lower():
        raise ValueError("api/v2 answered but not a Samsung TV")
    name = dev.get('name') or data.get('name') or 'Samsung TV'
    model = (dev.get('modelNumber') or dev.get('modelName')
             or data.get('modelNumber') or data.get('modelName') or '?')
    logger.debug(f"api/v2 OK for {ip}: {name} ({model})")
    return {'fn': str(name), 'ip': ip, 'model': str(model)}


def get_by_ip(ip: str, timeout: float = 4) -> Dict[str, str]:
    """Probe a known IP directly without SSDP multicast.

    Tries (in order):
      1. http://IP:8001/api/v2/ (JSON, newer Tizen)
      2. http://IP:8001/ssdp/device-desc.xml (XML)
      3. http://IP:8001/dm.xml / msf endpoints (XML, older models)

    Raises the last error if nothing answers like a Samsung TV.
    """
    logger = logging.getLogger(__name__)
    ip = ip.strip()
    if not re.match(r'^[0-9]+(?:\.[0-9]+){3}$', ip):
        raise ValueError(f"Invalid IP: {ip}")

    last_err = Exception("no Samsung endpoint answered")

    # 1) JSON API (Tizen 2016+), with retries: standby TVs are flaky
    # (first request often times out, second answers).
    for attempt in range(3):
        try:
            return identify_api_v2(ip, timeout=timeout)
        except Exception as e:
            last_err = e
            logger.debug(f"api/v2 attempt {attempt + 1} failed for {ip}: {e}")

    # 2) XML endpoints (legacy models; on standby Tizen these hang/404)
    for path in ("/ssdp/device-desc.xml", "/dm.xml", "/msf/1.0/", "/ssdp/dd.xml"):
        url = f"http://{ip}:8001{path}"
        try:
            return get(url, timeout=timeout)
        except Exception as e:
            last_err = e
            logger.debug(f"{path} failed for {ip}: {e}")
            continue

    raise last_err


def is_port_open(ip: str, port: int, timeout: float = 1.0) -> bool:
    """Quick TCP check for Samsung ports: 8001 (HTTP), 8002 (WSS), 55000 (legacy), 9197."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def namespace(element) -> str:
    """
    Extract XML namespace from element tag.

    Args:
        element: XML element

    Returns:
        Namespace string or empty string if no namespace
    """
    m = re.match(r'\{.*\}', element.tag)
    return m.group(0) if m else ''


def get(url: str, timeout: float = 5) -> Dict[str, str]:
    """
    Retrieve TV information from a Samsung TV's XML endpoint.
    
    Args:
        url: URL to the TV's XML information endpoint
        
    Returns:
        Dictionary containing TV information (friendly_name, ip, model)
        
    Raises:
        ValueError: If IP address cannot be extracted from URL
        urllib.error.URLError: If URL cannot be accessed
        xml.etree.ElementTree.ParseError: If XML cannot be parsed
    """
    logger = logging.getLogger(__name__)
    
    # Extract IP address from URL
    ip_match = re.search(r'[0-9]+(?:\.[0-9]+){3}', url)
    if not ip_match:
        raise ValueError(f"Could not extract IP address from URL: {url}")
    
    ip = ip_match.group(0)
    
    try:
        # Fetch XML data
        with urllib.request.urlopen(url, timeout=timeout) as response:
            xmlstr = response.read().decode('utf-8')
        
        # Parse XML
        root = ET.fromstring(xmlstr)
        ns = namespace(root)
        
        # Extract TV information
        friendly_name_elem = root.find(f'.//{ns}friendlyName')
        model_name_elem = root.find(f'.//{ns}modelName')
        
        if friendly_name_elem is None or model_name_elem is None:
            raise ValueError("Required XML elements not found")
        
        friendly_name = friendly_name_elem.text
        model = model_name_elem.text
        
        if not friendly_name or not model:
            raise ValueError("TV information is incomplete")
        
        logger.debug(f"Retrieved TV info: {friendly_name} ({model}) at {ip}")
        
        return {
            'fn': friendly_name,
            'ip': ip,
            'model': model
        }
        
    except urllib.error.URLError as e:
        logger.error(f"Failed to access URL {url}: {e}")
        raise
    except ET.ParseError as e:
        logger.error(f"Failed to parse XML from {url}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting TV info from {url}: {e}")
        raise
