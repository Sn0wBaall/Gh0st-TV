"""
SSDP (Simple Service Discovery Protocol) Module

Handles network discovery of Samsung TVs using SSDP protocol.
Based on work by Dan Krause (2014) and Adam Baxter (2016).

Licensed under the Apache License, Version 2.0
"""

import socket
import http.client
import io
import logging
import time
from typing import List, Optional


class SSDPResponse:
    """Represents an SSDP response from a network device."""
    
    class _FakeSocket(io.BytesIO):
        """Fake socket implementation for HTTP response parsing."""
        def makefile(self, *args, **kw):
            return self

    def __init__(self, response: bytes):
        """
        Initialize SSDP response from raw response data.
        
        Args:
            response: Raw SSDP response bytes
        """
        r = http.client.HTTPResponse(self._FakeSocket(response))
        r.begin()
        
        self.location = r.getheader("location")
        self.usn = r.getheader("usn")
        self.st = r.getheader("st")
        
        cache_control = r.getheader("cache-control")
        self.cache = cache_control.split("=")[1] if cache_control else "0"

    def __repr__(self) -> str:
        return f"<SSDPResponse({self.location}, {self.st}, {self.usn})>"


def discover(service: str, timeout: int = 5, retries: int = 1, mx: int = 3, verbose: bool = False) -> List[SSDPResponse]:
    """
    Discover SSDP services on the network.

    Args:
        service: Service type to search for
        timeout: Socket timeout in seconds
        retries: Number of discovery attempts
        mx: Maximum wait time for responses
        verbose: Log every raw response (useful to debug TVs that answer
            with a different ST)

    Returns:
        List of SSDP responses from discovered devices
    """
    logger = logging.getLogger(__name__)

    group = ("239.255.255.250", 1900)
    message = "\r\n".join([
        'M-SEARCH * HTTP/1.1',
        'HOST: {0}:{1}',
        'MAN: "ns=01; ns=01"',
        'ST: {st}',
        'MX: {mx}',
        '',
        ''
    ])

    responses = {}

    for attempt in range(retries):
        sock = None
        try:
            sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM,
                socket.IPPROTO_UDP
            )
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(timeout)

            message_bytes = message.format(
                *group, st=service, mx=mx
            ).encode('utf-8')

            # Multicast UDP drops packets: instead of a single one-shot
            # M-SEARCH, re-emit every second for the whole window and keep
            # collecting until the deadline. A TV that misses the first packet
            # (or sleeps up to MX seconds before answering) is still caught on
            # a later emission.
            deadline = time.time() + timeout
            next_emit = 0.0
            while True:
                now = time.time()
                if now >= next_emit:
                    try:
                        sock.sendto(message_bytes, group)
                    except OSError as e:
                        logger.warning(f"SSDP send failed (attempt {attempt + 1}): {e}")
                        break
                    next_emit = now + 1.0
                    logger.debug(f"Sent SSDP discovery for {service} (attempt {attempt + 1})")
                remaining = deadline - now
                if remaining <= 0:
                    break
                try:
                    sock.settimeout(min(1.0, remaining))
                    data = sock.recv(8192)
                except socket.timeout:
                    continue  # no reply in this slice, loop and re-emit if due
                except Exception as e:
                    logger.warning(f"Error processing SSDP response: {e}")
                    break
                if verbose:
                    logger.debug(f"RAW SSDP reply: {data[:500]!r}")
                try:
                    response = SSDPResponse(data)
                except Exception as e:
                    logger.debug(f"Ignoring malformed SSDP reply: {e}")
                    continue
                key = (response.location or f"unknown-{len(responses)}").strip()
                # Normalize: same TV may answer with/without trailing slash
                norm = key.lower().rstrip('/') if key.startswith('http') else key
                responses[norm] = response
                logger.debug(f"Received response from {response.location} ST={response.st}")

        except Exception as e:
            logger.error(f"SSDP discovery attempt {attempt + 1} failed: {e}")
        finally:
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass
    
    logger.info(f"SSDP discovery found {len(responses)} devices")
    return list(responses.values())


def scan_network(wait: float = 0.3) -> List[SSDPResponse]:
    """
    Scan network for Samsung TVs using SSDP discovery.
    
    Args:
        wait: Initial timeout for discovery in seconds
        
    Returns:
        List of SSDP responses from discovered Samsung TVs
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.debug(f"Starting network scan with {wait}s timeout")
        
        tvs_found = discover(
            "urn:samsung.com:device:RemoteControlReceiver:1",
            timeout=wait
        )
        
        if not tvs_found:
            logger.debug(f"No TVs found with {wait}s timeout, trying with {wait + 1}s")
            # Try again with higher timeout
            tvs_found = discover(
                "urn:samsung.com:device:RemoteControlReceiver:1",
                timeout=wait + 1
            )
        
        logger.info(f"Network scan completed, found {len(tvs_found)} Samsung TVs")
        return tvs_found

    except KeyboardInterrupt:
        logger.info('Search interrupted by user')
        return []
    except Exception as e:
        logger.error(f"Network scan failed: {e}")
        return []

# Example:
# import ssdp
# ssdp.discover("roku:ecp")
