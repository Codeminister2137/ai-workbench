# Switches the WorkbenchDashboardSupervisor task to a stored-logon principal.
#
# Why: the task currently runs only in an interactive logon session, so after
# any reboot its redeploy/reconcile ticks wait for a login. A stored-logon
# (Password) principal lets its 5-minute time trigger fire whether or not
# anyone is logged on. No trigger changes: the existing repeating time
# trigger already covers boot plus every five minutes.
#
# Owner step (needs the Windows password once):
#   $pw = Read-Host 'Windows password' -AsSecureString
#   .\scripts\register-supervisor-stored-logon.ps1 -UserPassword $pw
# Run both lines in the SAME PowerShell window (SecureString cannot cross
# process boundaries).
#
# The script keeps triggers, action and settings; it only switches the
# principal to stored logon. Safe to re-run (idempotent). The password
# lives in memory for the registration call only and is never written
# anywhere.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter()]
    [SecureString]$UserPassword
)

$ErrorActionPreference = 'Stop'

if (-not $UserPassword) {
    Write-Output 'Usage: register-supervisor-stored-logon.ps1 -UserPassword (SecureString)'
    Write-Output 'Refusing to register without credentials; nothing changed.'
    exit 2
}

$taskName = 'WorkbenchDashboardSupervisor'
[xml]$xml = Export-ScheduledTask -TaskName $taskName
$ns = New-Object Xml.XmlNamespaceManager($xml.NameTable)
$ns.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')

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
$runAs = $userId.InnerText
if ($runAs -match '^S-\d-(\d+-)+$') {
    $runAs = ([System.Security.Principal.SecurityIdentifier]$runAs).Translate(
        [System.Security.Principal.NTAccount]
    ).Value
}

$xmlPath = Join-Path ([IO.Path]::GetTempPath()) 'WorkbenchSupervisor.logon.xml'
$xml.Save($xmlPath)
if ($WhatIfPreference) {
    Write-Output 'pending principal XML:'
    Write-Output $principals.OuterXml
}
try {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($UserPassword)
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    try {
        if ($PSCmdlet.ShouldProcess($taskName, 'Register stored logon')) {
            schtasks /Create /TN $taskName /XML $xmlPath `
                /RU $runAs /RP $plain /F | Out-Null
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
