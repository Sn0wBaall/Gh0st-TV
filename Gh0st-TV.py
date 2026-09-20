#!/usr/bin/env python3

import os, sys, re, argparse, signal
from helpers import tvcon, macro, ssdp, tvinfo

try:
    import samsungtvws
    from samsungtvws import SamsungTVWS
    from pwn import *
    from termcolor import colored
    from rich.console import Console
    from rich.table import Table
    from rich import box
except ImportError as e:
    print(f"Error importing...\n {e}")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "samsung_token.txt")

BANNER = r"""
   █████████  █████         █████             █████               ███████████ █████   █████
  ███▒▒▒▒▒███▒▒███        ███▒▒▒███          ▒▒███               ▒█▒▒▒███▒▒▒█▒▒███   ▒▒███ 
 ███     ▒▒▒  ▒███████   ███   ▒▒███  █████  ███████             ▒   ▒███  ▒  ▒███    ▒███ 
▒███          ▒███▒▒███ ▒███    ▒███ ███▒▒  ▒▒▒███▒    ██████████    ▒███     ▒███    ▒███ 
▒███    █████ ▒███ ▒███ ▒███    ▒███▒▒█████   ▒███    ▒▒▒▒▒▒▒▒▒▒     ▒███     ▒▒███   ███  
▒▒███  ▒▒███  ▒███ ▒███ ▒▒███   ███  ▒▒▒▒███  ▒███ ███               ▒███      ▒▒▒█████▒   
 ▒▒█████████  ████ █████ ▒▒▒█████▒   ██████   ▒▒█████                █████       ▒▒███     
  ▒▒▒▒▒▒▒▒▒  ▒▒▒▒ ▒▒▒▒▒    ▒▒▒▒▒▒   ▒▒▒▒▒▒     ▒▒▒▒▒                ▒▒▒▒▒         ▒▒▒      
"""

INFO_TABLE = Table(border_style="white", box=box.ROUNDED, show_header=False, width=50)

INFO_TABLE.add_column("Key", style="bold red", width=12)
INFO_TABLE.add_column("Value", style="cyan")

INFO_TABLE.add_row('Author', 'Sn0wBaall')
INFO_TABLE.add_row('Github', 'https://github.com/Sn0wBaall')

VERSION = "1.0.0"

def about():
    console = Console()
    table = Table(title="About Gh0st-TV", border_style="cyan", box=box.DOUBLE,
                  show_header=False, width=62)
    table.add_column("Field", style="bold red", width=14)
    table.add_column("Value", style="white")

    table.add_row('Name', 'Gh0st-TV')
    table.add_row('Version', VERSION)
    table.add_row('Author', 'Sn0wBaall')
    table.add_row('GitHub', 'https://github.com/Sn0wBaall')
    table.add_row('Language', 'Python 3')
    table.add_row('Requires', 'Python 3.10+, samsungtvws, pwntools, termcolor, rich')
    table.add_row('Description',
                  'Samsung Smart TV remote controller and network scanner for local networks.')
    table.add_row('Features',
                  '· SSDP discovery of Samsung TVs\n'
                  '· Direct IP check (--check) without multicast\n'
                  '· Subnet fallback sweep (--range)\n'
                  '· TV fingerprinting (name, model, method)\n'
                  '· Key sender over WebSocket (port 8002)\n'
                  '· Key lister (--keys)')
    table.add_row('Disclaimer',
                  'For educational and personal use only. Use only with TVs you own '
                  'or are explicitly authorized to control.')

    console.print(table)
    console.print(f"[bold cyan]Gh0st-TV[/bold cyan] [dim]- Samsung TV remote "
                  f"controller by [/dim][bold magenta]Sn0wBaall[/bold magenta]")

def signal_handler(key, frame):
    print()
    log.failure(f"{colored('Exit...\n', 'white')}")
    sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)

def connection(ip):
    
    tv = None
    try:
        # Sanitize token: the lib uses readline() without strip(), a trailing "\n" invalidates it and forces re-auth every time
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r", encoding="utf-8", errors="ignore") as f:
                clean = f.read().strip()
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(clean)
            log.info(f"{colored('Using token:', 'white')} {colored(clean[:4], 'magenta')}{colored('****', 'magenta', attrs=['bold'])}")
        else:
            log.info("No token file found, first pairing required")

        log.info(f"{colored('Trying to connect...', 'white')}")
        tv = SamsungTVWS(
                host=ip,
                port=8002,
                timeout=30,
                name="Cyb3rGh0st",  # Do not change: the token is bound to this name
                token_file=TOKEN_FILE,
            )
        tv.open()
        import time as _time; _time.sleep(1)  # Give the TV time to authorize
        # Check connection before entering the key loop
        if not tv.is_alive():
            log.failure(f"{colored('Connection check failed: websocket is not alive', 'red')}")
            return
        log.success(f"{colored('Connected to ' + ip, 'white')}")
        print(f"{colored('Enter', 'white')} {colored('"M"', 'green', attrs=['bold'])} {colored('list available keys...', 'white')}")
        print(f"{colored('Type exit/quit/q or Ctrl+C to disconnect.', 'white')}")
        while True:
            try:
                key = input(f"{colored('[Enter KEY]', 'magenta', attrs=['bold'])} {colored('>', 'blue')} ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                log.info("Disconnecting...")
                break
            if not key:
                continue
            if key.lower() in ("exit", "quit", "q"):
                log.info("Disconnecting...")
                break
            if key == "M":
                keys()
                continue
            # Verify connection is still alive before sending; try one reconnect
            if not tv.is_alive():
                log.failure(f"{colored('Connection lost, reconnecting...', 'red')}")
                try:
                    tv.open()
                    _time.sleep(1)
                except Exception as e:
                    log.failure(f"{colored(f'Reconnect failed: {e}', 'red')}")
                    continue
                if not tv.is_alive():
                    log.failure(f"{colored('Still not connected, skipping key', 'red')}")
                    continue
            try:
                tv.send_key(key)
                log.success(f"{colored('Key sent successfully', 'white')} {colored(key, 'magenta')}")
            except (EOFError, KeyboardInterrupt):
                raise
            except Exception as e:
                # Send failed: connection may have dropped, try one reconnect + retry
                log.failure(f"{colored(f'Send failed for {key}: {e}', 'red')}")
                try:
                    tv.open()
                    _time.sleep(1)
                    if tv.is_alive():
                        tv.send_key(key)
                        log.success(f"{colored('Key sent successfully on retry', 'white')} {colored(key, 'magenta')}")
                    else:
                        log.failure(f"{colored('Reconnect failed: websocket not alive', 'red')}")
                except Exception as e2:
                    log.failure(f"{colored(f'Retry failed: {e2}', 'red')}")
    except TimeoutError:
        log.failure(f"{colored('Timeout - IP is not responding', 'red')}")
    except Exception as e:
        if "nothorized" in str(e).lower() or "token" in str(e).lower():
            log.failure("Unauthorized: accept the popup on the TV and run again (do not delete the token)")
        log.failure(f"{colored(f'Connection failed: {e}', 'red')}")
    finally:
        if tv is not None:
            try:
                tv.close()
            except Exception:
                pass

def keys():
    # Locate the installed samsungtvws package
    path = os.path.dirname(samsungtvws.__file__)

    found = set()

    # Walk through all package files and extract KEY_* constants
    for root, _, files in os.walk(path):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file), errors="ignore") as f:
                    found.update(re.findall(r"KEY_[A-Z0-9_]+", f.read()))

    # Ensure numeric keys are always included
    found.update(f"KEY_{i}" for i in range(10))

    if not found:
        log.failure("No keys found")
        return

    sorted_keys = sorted(found)

    # Render keys as a colored table with rich
    console = Console()
    table = Table(title="Available Keys", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Key", style="bold magenta")
    table.add_column("Category", style="green")

    for idx, key in enumerate(sorted_keys, 1):
        table.add_row(str(idx), key, _key_category(key))

    console.print(table)
    console.print(f"[bold]Total: {len(sorted_keys)} keys[/bold]")

def _key_category(key: str) -> str:
    # Classify keys by prefix for the Category column
    if re.match(r"KEY_[0-9]$", key):
        return "Numeric"
    if any(x in key for x in ("VOL", "MUTE", "CH")):
        return "Audio/Channel"
    if any(x in key for x in ("UP", "DOWN", "LEFT", "RIGHT", "ENTER", "RETURN")):
        return "Navigation"
    if any(x in key for x in ("RED", "GREEN", "YELLOW", "BLUE")):
        return "Color"
    if any(x in key for x in ("POWER", "SOURCE", "MENU", "HOME", "GUIDE", "INFO", "TOOLS")):
        return "System"
    return "Other"

def _show_tv(location: str, via: str = "", endpoint: str = ""):
    import re as _re
    try:
        # Fast path first: api/v2 JSON (standby Tizen hangs on device-desc.xml).
        info = None
        m = _re.search(r'[0-9]+(?:\.[0-9]+){3}', location or '')
        if m:
            try:
                if endpoint:
                    # Discovery already recorded the exact endpoint (TCP/Direct).
                    info = tvinfo.get_by_ip(m.group(0))
                else:
                    # SSDP: report the endpoint that actually answered the info call.
                    info, endpoint = tvinfo.get_by_ip_full(m.group(0))
            except Exception:
                info = None
        if info is None:
            info = tvinfo.get(location)
            if not endpoint and location:
                endpoint = location
        method = tvinfo.getMethod(info.get('model', ''))
        name = info.get('fn', 'Unknown')
        model = info.get('model', '?')
        ip = info.get('ip', '?')
        suffix = (' ' + colored('via ' + via, 'white', attrs=['dark'])) if via else ''
        if endpoint:
            suffix += ' ' + colored('·', 'white') + ' ' \
                + colored('endpoint', 'white', attrs=['dark']) + ' ' \
                + colored(str(endpoint), 'yellow')
        log.success(
            colored(name, 'magenta') + ' '
            + colored('(' + str(model) + ')', 'white') + ' - '
            + colored(str(ip), 'cyan') + ' '
            + '[' + colored(str(method), 'green') + ']'
            + suffix
        )
        return True
    except Exception as e:
        log.failure(colored(str(location) + ' - could not get info: ' + str(e), 'red'))
        return False


def scan(check_ips=None, cidr=None, timeout=5, verbose=False, no_fallback=False, combined=False):
    import logging as _logging
    import re as _re
    if verbose:
        _logging.basicConfig(level=_logging.DEBUG)

    # Every method feeds the same pool, deduped by IP, so a TV that misses
    # multicast but answers TCP (or vice versa) is still found and shown once.
    found = {}      # key(ip) -> SSDPResponse
    methods = {}    # key(ip) -> set of discovery method names

    def add_result(tv, method):
        loc = getattr(tv, 'location', '') or ''
        m = _re.search(r'[0-9]+(?:\.[0-9]+){3}', loc)
        key = m.group(0) if m else loc.strip().lower().rstrip('/')
        if not key:
            return
        if key not in found:
            found[key] = tv
        methods.setdefault(key, set()).add(method)

    # 0) Direct check of known IPs (no multicast needed)
    if check_ips:
        # Dedupe user input preserving order (same IP twice -> one probe)
        seen_in = set()
        uniq_ips = []
        for _ip in check_ips:
            _ip = _ip.strip()
            if _ip and _ip not in seen_in:
                seen_in.add(_ip)
                uniq_ips.append(_ip)
        log.info(colored('Checking ' + str(len(uniq_ips)) + ' given IP(s) directly...', 'white'))
        for ip in uniq_ips:
            ip = ip.strip()
            if not ip:
                continue
            r = ssdp.probe_ip(ip, timeout=timeout)
            if r is None:
                log.failure(colored(ip + ': no Samsung ports/info (8001/8002/55000). TV off, other VLAN or AP ISOLATION?', 'red'))
                continue
            add_result(r, 'Direct')
        if not combined:
            # --check mode: those IPs are the whole job
            if not found:
                log.failure(colored('None of the given IPs respond as Samsung. Check they are powered on and on the same network.', 'red'))
            else:
                for key, tv in found.items():
                    _show_tv(getattr(tv, 'location', '') or '', via='Direct',
                             endpoint=getattr(tv, 'endpoint', '') or '')
            return
        if not found:
            log.failure(colored('None of the given IPs respond as Samsung, continuing with the network scan...', 'red'))

    # 1) SSDP multicast (catches TVs that answer M-SEARCH)
    print()
    log.info(f"{colored('Scanning network', 'white')} {colored('(', 'white', attrs=['bold'])}{colored('SSDP multicast', 'black', 'on_blue')}{colored(')', 'white', attrs=['bold'])}{colored('...', 'white')}")
    for tv in ssdp.scan_network(wait=timeout):
        add_result(tv, 'SSDP')

    # 2) TCP sweep of the subnet (catches TVs that ignore/block multicast,
    #    e.g. standby models, AP isolation, one-shot UDP drops)
    if not no_fallback:
        target = cidr or ssdp.local_subnet()
        log.info(f"{colored('Probing', 'white')} {colored(target, 'green')} {colored('via TCP', 'blue')} {colored('(', 'white', attrs=['bold'])}{colored('ports 8001/8002/55000', 'black', 'on_blue')}{colored(')', 'white', attrs=['bold'])}{colored('...', 'white')}")
        for tv in ssdp.scan_subnet(target, timeout=1.5):
            add_result(tv, 'TCP')

    if not found:
        log.failure(colored('Nothing found. Try: --range YOUR_NET/24 (e.g. 192.168.0.0/24) or --check IP1,IP2', 'red'))
        return

    total = len(found)
    counts = {}
    for mset in methods.values():
        for m in mset:
            counts[m] = counts.get(m, 0) + 1
    summary = '  '.join(colored(m + ': ' + str(counts[m]), 'cyan')
                        for m in ('SSDP', 'TCP', 'Direct') if counts.get(m))
    log.success(colored('Found ' + str(total) + ' Samsung TV(s)', 'green', attrs=['bold']) + '  ' + summary)
    for key, tv in found.items():
        via = '+'.join(sorted(methods.get(key, [])))
        _show_tv(getattr(tv, 'location', '') or '', via=via,
                 endpoint=getattr(tv, 'endpoint', '') or '')

def main():

    parser = argparse.ArgumentParser(description=f"{colored('Samsung TV', 'white', attrs=['bold'])} {colored('controller', 'white')}")

    parser.add_argument('-i', "--ip", help="Target TV IP address")
    parser.add_argument('-a', "--about", action="store_true", help="Show information about the tool")
    parser.add_argument('-k', "--keys", action="store_true", help="Show available keys")
    parser.add_argument('-s', "--scan", action="store_true", help="Network scan")
    parser.add_argument('--check', help="Check known TV IPs directly, comma-separated (no SSDP): --check 192.168.1.50,192.168.1.51")
    parser.add_argument('--range', dest="cidr", help="CIDR for TCP fallback scan (default: local /24): --range 192.168.1.0/24")
    parser.add_argument('--timeout', type=float, default=5, help="SSDP timeout in seconds (default: 5)")
    parser.add_argument('--verbose', action="store_true", help="Debug SSDP traffic")
    parser.add_argument('--no-fallback', action="store_true", help="Disable TCP subnet fallback")

    args = parser.parse_args()

    if args.about:
        about()
    elif args.keys:
        keys()
    elif args.scan or args.check or args.cidr:
        check_ips = [x.strip() for x in args.check.split(',')] if args.check else None
        scan(check_ips=check_ips, cidr=args.cidr, timeout=args.timeout,
             verbose=args.verbose, no_fallback=args.no_fallback,
             combined=bool(args.scan or args.cidr))
    elif args.ip:
        connection(args.ip)
    else:
        parser.print_help()

if __name__ == '__main__':

    print(f"{colored(BANNER, 'cyan', attrs=['bold'])}")
    Console().print(INFO_TABLE)
    main()