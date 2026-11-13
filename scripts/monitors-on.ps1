# Turn all monitors on (restore after monitors-off, or before sleep).
#
# The sleep path calls this first: suspending with forced-off monitors
# breaks resume on this machine (proven 2026-11-13: aborted suspend +
# headless resume + power-off). Safe anytime; a no-op when already on.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts/monitors-on.ps1
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
$ON = [IntPtr]-1
[DisplayPower]::SendMessage($HWND_BROADCAST, $WM_SYSCOMMAND, [IntPtr]$SC_MONITORPOWER, $ON) | Out-Null
Write-Output "monitors: on"
