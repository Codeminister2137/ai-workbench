# Adds a boot trigger + stored-logon principal to the WorkbenchDashboard task.
#
# Why: the task currently triggers only at user logon, so after any reboot
# nothing serves the dashboard until an interactive login. A boot trigger with
# S4U stored logon lets the keepalive run whether or not anyone is logged on.
#
# Owner step on return (needs the Windows password once):
#   $pw = Read-Host 'Windows password' -AsSecureString
#   .\scripts\register-dashboard-boot-task.ps1 -UserPassword $pw
# Run both lines in the SAME PowerShell window (SecureString cannot cross
# process boundaries).
#
# The script keeps the existing logon trigger, 5-minute repetition, action and
# settings; it only adds the boot trigger and switches the principal to
# stored-logon. Safe to re-run (idempotent). The password lives in memory for
# the registration call only and is never written anywhere.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter()]
    [SecureString]$UserPassword
)

$ErrorActionPreference = 'Stop'

if (-not $UserPassword) {
    Write-Output 'Usage: register-dashboard-boot-task.ps1 -UserPassword (SecureString)'
    Write-Output 'Refusing to register without credentials; nothing changed.'
    exit 2
}

$taskName = 'WorkbenchDashboard'
[xml]$xml = Export-ScheduledTask -TaskName $taskName
$ns = New-Object Xml.XmlNamespaceManager($xml.NameTable)
$ns.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')

$triggers = $xml.SelectSingleNode('/t:Task/t:Triggers', $ns)
if (-not $triggers.SelectSingleNode('t:BootTrigger', $ns)) {
    $boot = $xml.CreateElement('BootTrigger', $ns.LookupNamespace('t'))
    $enabled = $xml.CreateElement('Enabled', $ns.LookupNamespace('t'))
    $enabled.InnerText = 'true'
    $repetition = $xml.CreateElement('Repetition', $ns.LookupNamespace('t'))
    foreach ($pair in @(
        @('Interval', 'PT5M'), @('Duration', 'P1D'), @('StopAtDurationEnd', 'true')
    )) {
        $node = $xml.CreateElement($pair[0], $ns.LookupNamespace('t'))
        $node.InnerText = $pair[1]
        $repetition.AppendChild($node) | Out-Null
    }
    $boot.AppendChild($enabled) | Out-Null
    $boot.AppendChild($repetition) | Out-Null
    $triggers.AppendChild($boot) | Out-Null
}

$principals = $xml.SelectSingleNode('/t:Task/t:Principals/t:Principal', $ns)
$logonType = $principals.SelectSingleNode('t:LogonType', $ns)
if ($logonType) {
    $logonType.InnerText = 'Password'
} else {
    $node = $xml.CreateElement('LogonType', $ns.LookupNamespace('t'))
    $node.InnerText = 'Password'
    $principals.AppendChild($node) | Out-Null
}
$userId = $principals.SelectSingleNode('t:UserId', $ns)
if (-not $userId) {
    throw 'Task principal has no UserId; refusing to guess.'
}

$xmlPath = Join-Path ([IO.Path]::GetTempPath()) 'WorkbenchDashboard.boot.xml'
$xml.Save($xmlPath)
if ($WhatIfPreference) {
    Write-Output 'pending boot trigger XML:'
    Write-Output $triggers.SelectSingleNode('t:BootTrigger', $ns).OuterXml
}
try {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($UserPassword)
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    try {
        if ($PSCmdlet.ShouldProcess($taskName, 'Register boot trigger with stored logon')) {
            schtasks /Create /TN $taskName /XML $xmlPath `
                /RU $userId.InnerText /RP $plain /F | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "schtasks registration failed with exit $LASTEXITCODE."
            }
        }
    } finally {
        $plain = $null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
} finally {
    Remove-Item $xmlPath -ErrorAction SilentlyContinue
}

$updated = Get-ScheduledTask -TaskName $taskName
$triggerKinds = @($updated.Triggers) | ForEach-Object { $_.CimClass.CimClassName }
Write-Output "task: $taskName registered"
Write-Output "principal: $($updated.Principal.UserId) logon=$($updated.Principal.LogonType)"
Write-Output "triggers: $($triggerKinds -join ', ')"
