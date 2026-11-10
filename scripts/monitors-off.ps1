# Turn all monitors off immediately (power saving for unattended runs).
#
# Any mouse/keyboard input turns them back on instantly; nothing is locked,
# slept, or closed. Safe to run while the owner is away; if they return
# mid-session, one mouse move restores the picture (no watchdog needed).
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts/monitors-off.ps1
$signature = @"
using System;
using System.Runtime.InteropServices;
public static class DisplayPower {
    [DllImport("user32.dll")]
    public static extern IntPtr SendMessage(
        IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
}
"@
Add-Type -TypeDefinition $signature
$HWND_BROADCAST = [IntPtr]0xffff
$WM_SYSCOMMAND = 0x0112
$SC_MONITORPOWER = 0xF170
$OFF = [IntPtr]2
[DisplayPower]::SendMessage($HWND_BROADCAST, $WM_SYSCOMMAND, [IntPtr]$SC_MONITORPOWER, $OFF) | Out-Null
Write-Output "monitors: off (any input wakes)"
