# Remote-wake runbook (Wake-on-LAN ladder)

Owner-infra doc. No access material here — this file is public, so it
carries placeholders only. Real values live in the local-only `.env`
(`WAKE_DDNS_HOSTNAME`, `WAKE_MAC`, `WAKE_WOL_PORT`, `WAKE_LAN_IP`); a reader
following this doc sets their own and can only ever reach their own machine.
The public IP rotates (see below), so it is never written down either.

## The chain

```text
phone WoL app ──Internet──▶ home public IP : UDP 9 ──router port-forward──▶ LAN ──▶ PC NIC (WoL)
```

`scripts/wake_on_lan.py` is the LAN-side sender for testing from any awake
machine on the home LAN. There is no repo-hosted wake relay: the packet
sender is the owner's phone app, delivery depends on the router + ISP.

## PC side (verified 2026-11-06, healthy)

- NIC wake-armed (example: `Realtek Gaming 2.5GbE`), MAC `AA:BB:CC:DD:EE:FF`
  (placeholder — the real MAC is the shared secret and lives only in
  local `.env` as `WAKE_MAC`).
- Advanced: Wake on Magic Packet = Enabled, pattern match = Enabled.
- Sleep state S3 available; sleeps and stays asleep (26 min proven).
- Power-Troubleshooter is the source of truth for wake cause
  (`powercfg /lastwake`, System log 42/107/1).

## Known failure modes

1. **ISP rotates the public IP** (observed ~Nov 3→6). The phone app keeps
   sending to the stale IP and fails silently. This is the 2026-11-06 cause.
2. **DHCP drift**: the router port-forward targets a LAN IP (e.g.
   `192.168.1.50`) that DHCP may reassign. Same silent symptom.
3. **Router reboot** losing forward/ARP entries (not yet observed here).

## Recover now (5 min, owner phone + this PC awake)

1. Get the current public IP: newest `public_ip` in
   `.tmp/loop-*/notifications/*.json`, or from the home PC:
   `Invoke-RestMethod https://api.ipify.org`.
2. In the phone app set host = that IP, port 9, MAC = your `WAKE_MAC`.
3. E2E test: sleep the PC, turn OFF home Wi-Fi on the phone (mobile data
   only), send the packet, confirm wake. If it fails, the router forward
   (mode 2/3) is the next suspect, not the PC.

## Durable router fixes (owner decision C, 2026-11-06)

Security analysis (2026-11-06 night, loop-3): both changes are SAFE.

- **DHCP reservation** (pin the PC's LAN IP to its MAC) is LAN-only
  admin state. It opens no ports, publishes nothing, and cannot be
  abused remotely. It kills failure mode 2 permanently.
- **Router DDNS** (stable hostname -> rotating WAN IP) publishes only a
  hostname-to-IP mapping - scanners already enumerate the IP range and
  the UDP forward regardless. It opens no new ports and does not weaken
  WoL authentication (magic packets are unauthenticated by design; the
  MAC stays the shared secret and must never be posted publicly).
  Requirements: a RANDOM hostname (no name/company - avoid a privacy
  leak via public DNS), set up on the ROUTER (a PC-side updater cannot
  run while the PC is asleep, which is exactly when wake matters).
  If the FunBox has no usable DDNS client, keep the mail-IP flow:
  every loop mail carries the current IP plus a rotation NOTE.

Steps (router admin UI; exact menu labels vary by firmware):
1. DHCP/static-lease section -> reserve your PC's LAN IP (`WAKE_LAN_IP`)
   for its MAC (`WAKE_MAC`) -> reboot router -> confirm the PC keeps it.
   Fallback 2026-11-07 (static-DHCP UI broken, no factory reset): the UDP
   forward (WAN `WAKE_WOL_PORT` -> LAN IP port 9) pins the target; the
   weekly self-test `lan_ip` check mails on drift.
2. DDNS section -> provider account -> random hostname -> confirm it
   resolves to the current WAN IP -> point the phone app at the
   hostname -> re-run the E2E test above.
3. Record the hostname ONLY in local `.env` (`WAKE_DDNS_HOSTNAME`) and
   local-only notes — never in this public doc, even when random.

## Durable fixes (owner decision, all router-side)

- **Router DDNS** (recommended): enable the router's built-in dynamic-DNS
  client (most vendors: No-IP / DuckDNS / DynDNS / vendor cloud) and point
  the phone app at the hostname instead of the IP. Must be router-side — a
  PC updater cannot run while the PC sleeps.
- **DHCP reservation**: pin the PC's LAN IP (`WAKE_LAN_IP`) to its MAC
  (`WAKE_MAC`) so the port-forward target never drifts.
- Optional: static public IP from the ISP (usually paid) removes mode 1.

Decided 2026-11-07: provider NO-IP (free tier, 1 hostname, 30-day one-click confirm),
random hostname, router-side client. WAN IP confirmed at setup (NO-IP prefill
== loop-mail IP); the router keeps it updated — no PC updater (it cannot run
while asleep). E2E PASS 2026-11-07: PC slept, Termux wake via hostname succeeded.
Off-LAN wake (Termux; substitute your own `.env` values — the example below
reaches nothing real):
python -c "import socket,os; m=bytes.fromhex(os.environ['WAKE_MAC_HEX']); s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'\xff'*6+m*16,(os.environ['WAKE_DDNS_HOSTNAME'],int(os.environ['WAKE_WOL_PORT']))); print('sent')"
Weekly WakeSelfTest monitors resolution via WAKE_DDNS_HOSTNAME (repo .env).

## Automated monitoring (2026-11-07)

`WakeSelfTest` weekly task (Sundays 06:30, Limited) runs `scripts/wake-self-test.py`: dashboard probe, NIC wake-armed check, public-IP lookup, DDNS resolution when `WAKE_DDNS_HOSTNAME` is configured, and Gmail SMTP login (no mail sent). Silent on success (one line in `artifacts/wake-self-test/runs.log`); a single owner mail on any failure. Registered via `scripts/register-watchdog-tasks.ps1` (elevated). Run manually any time: `.venv\Scripts\python.exe scripts/wake-self-test.py --dry-run`.
