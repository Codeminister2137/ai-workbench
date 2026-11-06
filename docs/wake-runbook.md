# Remote-wake runbook (Wake-on-LAN ladder)

Owner-infra doc. No secrets here — the public IP rotates (see below), so it
is intentionally never written down; fetch it fresh each time.

## The chain

```text
phone WoL app ──Internet──▶ home public IP : UDP 9 ──router port-forward──▶ LAN ──▶ PC NIC (WoL)
```

`scripts/wake_on_lan.py` is the LAN-side sender for testing from any awake
machine on the home LAN. There is no repo-hosted wake relay: the packet
sender is the owner's phone app, delivery depends on the router + ISP.

## PC side (verified 2026-11-06, healthy)

- NIC `Realtek Gaming 2.5GbE`, MAC `34:5A:60:38:44:C8`, wake-armed.
- Advanced: Wake on Magic Packet = Enabled, pattern match = Enabled.
- Sleep state S3 available; sleeps and stays asleep (26 min proven).
- Power-Troubleshooter is the source of truth for wake cause
  (`powercfg /lastwake`, System log 42/107/1).

## Known failure modes

1. **ISP rotates the public IP** (observed ~Nov 3→6). The phone app keeps
   sending to the stale IP and fails silently. This is the 2026-11-06 cause.
2. **DHCP drift**: the router port-forward targets a LAN IP (e.g.
   `192.168.1.12`) that DHCP may reassign. Same silent symptom.
3. **Router reboot** losing forward/ARP entries (not yet observed here).

## Recover now (5 min, owner phone + this PC awake)

1. Get the current public IP: newest `public_ip` in
   `.tmp/loop-*/notifications/*.json`, or from the home PC:
   `Invoke-RestMethod https://api.ipify.org`.
2. In the phone app set host = that IP, port 9, MAC `34:5A:60:38:44:C8`.
3. E2E test: sleep the PC, turn OFF home Wi-Fi on the phone (mobile data
   only), send the packet, confirm wake. If it fails, the router forward
   (mode 2/3) is the next suspect, not the PC.

## Durable fixes (owner decision, all router-side)

- **Router DDNS** (recommended): enable the router's built-in dynamic-DNS
  client (most vendors: No-IP / DuckDNS / DynDNS / vendor cloud) and point
  the phone app at the hostname instead of the IP. Must be router-side — a
  PC updater cannot run while the PC sleeps.
- **DHCP reservation**: pin the PC's LAN IP to MAC `34:5A:60:38:44:C8` so
  the port-forward target never drifts.
- Optional: static public IP from the ISP (usually paid) removes mode 1.

Record the chosen DDNS hostname shape here once decided (hostname only if
it does not leak identity beyond what the repo already carries).
