# Gh0st-TV

<p align="center">
  <img src="banner.png" alt="Gh0st-TV banner" width="100%">
</p>

Samsung Smart TV remote controller and network scanner for local networks. Discover Samsung TVs via SSDP, identify model and connection method, and send remote keys over WebSocket (Tizen) using `samsungtvws`.

> [!IMPORTANT]
> **For educational and personal use only.** Use only with TVs you own or are explicitly authorized to control.
>
> - Do not use this tool to access or control devices you don't own or don't have explicit permission to operate.
> - Unauthorized access to other people's devices may be illegal in your jurisdiction and can have legal consequences.
> - The authors are not responsible for any misuse, damage, or legal issues arising from the use of this software.

By [**Sn0wBaall**](https://github.com/Sn0wBaall)

---

## Features

- **Network discovery (SSDP multicast)** for Samsung TVs
- **Combined scan** (`-s`): SSDP multicast and the TCP subnet sweep run together and results are merged by IP — a TV that misses multicast (blocked, AP isolation, standby, one-shot UDP drop) is still found via TCP
- **Direct IP check** (`--check`) without multicast — ideal for VLANs / AP isolation
- **Subnet fallback sweep** (`--range`) via `http://IP:8001/api/v2/`
- **TV fingerprinting**: friendly name, model, IP and method (`websocket` vs `legacy`)
- **Key sender** over encrypted WebSocket (`port 8002`)
- **Key lister** (`--keys`) extracted from the installed `samsungtvws` package
- Persistent pairing token (`samsung_token.txt`)

## Project structure

```
Gh0st-TV/
├── Gh0st-TV.py        # CLI entry point
├── helpers/
│   ├── ssdp.py        # discovery: targeted M-SEARCH + netdisco + subnet sweep
│   ├── ssdp_custom.py # raw SSDP M-SEARCH implementation
│   ├── tvinfo.py      # api/v2 + XML fingerprinting, legacy detection
│   ├── tvcon.py       # legacy samsungctl sender
│   └── macro.py       # CSV macro executor
├── requirements.txt
└── samsung_token.txt  # auto-created on first pairing
```

> [!NOTE]
> The `helpers/` modules (`ssdp.py`, `ssdp_custom.py`, `tvinfo.py`, `tvcon.py`, `macro.py`) are based on code taken from [pedrinho/samsung_remote](https://github.com/pedrinho/samsung_remote) (public domain, Unlicense), adapted and extended for this project.

## Requirements

- Python 3.10+
- Samsung TV and computer on the same LAN (first pairing)
- Tested packages:

```
samsungtvws==3.0.6
samsungctl==0.7.1
pwntools==4.15.0
termcolor==3.3.0
rich==15.0.0
netdisco==3.0.0
```

Install:

```bash
pip install -r requirements.txt
# or individually:
pip install samsungtvws samsungctl pwntools termcolor rich netdisco
```

## Usage

```bash
python3 Gh0st-TV.py --help
python3 Gh0st-TV.py -s
python3 Gh0st-TV.py --check 192.168.1.50,192.168.1.51
python3 Gh0st-TV.py --range 192.168.1.0/24
python3 Gh0st-TV.py -s --timeout 8 --verbose
python3 Gh0st-TV.py -i 192.168.1.50
python3 Gh0st-TV.py -k
```

### Options

| Flag | Description |
|------|-------------|
| `-h, --help` | Show help and exit |
| `-i, --ip IP` | Target TV IP, sends `KEY_HOME` as connection test |
| `-k, --keys` | List all available `KEY_*` codes |
| `-s, --scan` | All-in-one: SSDP multicast + TCP subnet sweep, results merged per IP (add `--no-fallback` for SSDP only) |
| `--check IPS` | Comma-separated IPs checked directly, no SSDP |
| `--range CIDR` | CIDR for TCP fallback (default: local `/24`) |
| `--timeout SEC` | SSDP timeout in seconds (default: `5`) |
| `--verbose` | Debug SSDP / HTTP traffic |
| `--no-fallback` | Disable TCP subnet fallback |

## Pairing

1. Run `python3 Gh0st-TV.py -i <TV-IP>`.
2. Accept the connection popup on the TV.
3. Run the command again. The token is saved in `samsung_token.txt` and bound to the client name `Cyb3rGh0st` — do not rename it or you will need to re-pair.

## How discovery works

1. Targeted `M-SEARCH` for `urn:samsung.com:device:RemoteControlReceiver:1` (reliable path — the packet is re-emitted every second, because one-shot UDP drops replies).
2. Generic `netdisco` scan filtered by Samsung manufacturer/model strings.
3. TCP sweep: direct `GET http://IP:8001/api/v2/` over the `/24` (Tizen 2016+), with legacy XML fallback (`/ssdp/device-desc.xml`, `/dm.xml`) for pre-2016 models.

`-s` always runs steps 1–3 and shows one merged, deduped list (per IP) with the methods that found each TV. That is why a second TV that misses multicast but answers on port 8001 still shows up.

Model method heuristic (`helpers/tvinfo.py:getMethod`): series `C/D/E/F` → `legacy` (port `55000`), otherwise `websocket` (port `8002`).

## Troubleshooting

- **SSDP finds nothing**: router blocks multicast, TV on another VLAN, or AP isolation enabled. Use `--check` or `--range`.
- **Only one of two TVs shows up**: multicast is unreliable UDP — one TV can miss the `M-SEARCH`. `-s` merges SSDP + TCP sweep, so the missed TV is caught on port 8001. You can also probe the known IPs directly: `--check <ip-of-.11>,<ip-of-.13>`.
- **TV off / standby**: first `/api/v2` request often times out. The scanner already retries, but try `--check` twice.
- **Unauthorized / token error**: accept the popup on the TV, do not delete `samsung_token.txt`, keep client name `Cyb3rGh0st`.
- **Wrong TV on port 8001**: the code validates `type` contains `samsung/smarttv/dtv` to avoid false positives from other UPnP devices.

## Disclaimer

> [!WARNING]
> This tool sends network commands to Samsung TVs, including power control and network activity. Only use it on **your own devices and networks** or those you are explicitly authorized to test. The author is not responsible for any misuse, damage, or legal consequences.