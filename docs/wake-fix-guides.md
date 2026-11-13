# Wake-fix guides (do tomorrow, in order)

Context: 2026-11-13 night showed a broken S3 resume (firmware S3 pair with
no OS resume event) plus update-driven reboots. PC: MSI B650 GAMING PLUS
WIFI (MS-7E26), BIOS 1.G0 (Oct 2024), Fast Startup currently ON, no
BitLocker. Do guide 1 first (5 min, reversible, no reboot needed beyond
a shutdown test); guide 2 second (~20 min, needs care).

## Guide 1 — turn Fast Startup OFF

Why: Fast Startup uses a hibernate-style kernel snapshot on shutdown.
When it misbehaves it produces exactly our symptom class (resume/boot
weirdness, "unexpected shutdown" flags). Turning it off makes every
shutdown a full clean shutdown. Sleep (S3) itself is unaffected.

Steps:

1. Open Control Panel → Power Options → "Choose what the power buttons do".
2. Click "Change settings that are currently unavailable" (admin prompt).
3. Under "Shutdown settings", UNCHECK "Turn on fast startup (recommended)".
4. Click "Save changes".
5. Verify (PowerShell, no admin needed):
   `Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled`
   Expect `HiberbootEnabled : 0`.
6. Test: shut down fully (Start → Shut down, not restart), wait 30s,
   power on. Should boot normally, slightly slower than before.

Revert if undesired: re-check the box in step 3.

Note: this does NOT disable hibernate or sleep, and does not delete
`hiberfil.sys`. If resume problems persist later, the next escalations
are `powercfg -h off` + `powercfg -h on` (rebuilds hiberfil, admin),
then the BIOS track below.

## Guide 2 — update MSI BIOS (B650 GAMING PLUS WIFI, MS-7E26)

Why: BIOS 1.G0 is Oct 2024. Two years of AGESA fixes since then include
sleep/C-state and standby-power behavior — directly in our symptom area.

Preparation (do not skip):

1. Find your current settings: reboot into BIOS (tap `Del` during boot),
   phone-photo every changed screen (especially OC/XMP, Advanced → Power
   Management, Boot order). You need these to restore afterwards.
2. Check current XMP/EXPO state in the same visit (OC → XMP profile).
   Write it down; do NOT change it yet.
3. Ensure stable power: no storm, PSU switched on, do not touch the
   power button during the flash. A UPS is ideal but not required.

Download (on the PC):

1. Go to `https://www.msi.com/Motherboard/B650-GAMING-PLUS-WIFI/support#bios`
   (MSI → B650 GAMING PLUS WIFI → Support → BIOS).
2. Download the latest STABLE BIOS (skip versions marked Beta unless a
   newer stable does not exist). Note the version number.
3. Format a USB stick as FAT32 (any size ≥1 GB; backup its contents first).
4. Extract the downloaded ZIP and copy the BIOS FILE (ends in a versioned
   extension like `.1G2`) to the USB root. Leave any `.txt` instructions
   on the stick too.

Flash via M-FLASH (no OS tools needed):

1. Plug the USB stick into a rear USB 2.0 port (black, most reliable).
2. Reboot into BIOS (`Del`), press F7 for Advanced mode if needed.
3. Go to M-FLASH (usually under the main/tools area), confirm the reboot
   into flash mode.
4. Select the USB stick → select the BIOS file → confirm.
5. WAIT. Progress bar runs several minutes. DO NOT power off, reset, or
   touch anything. The board reboots itself when done.

After the flash:

1. Enter BIOS, check the version shows the new one.
2. MSI typically keeps settings, but VERIFY against your photos: boot
   order, XMP state, and Advanced → Power Management (note ErP / Deep
   Sleep values; do not change them yet — that is a separate experiment).
3. Boot Windows, confirm everything works, then report back: new BIOS
   version + whether XMP was on. Next steps (only if sleep issues
   persist): try Deep Sleep / ErP toggles, then an XMP-off test window.

If anything looks wrong after flashing (no boot): do NOT panic-flash
again; clear CMOS per the MSI manual (JBAT1 jumper, PSU off) and tell
the agent exactly what the board shows (debug LEDs).
