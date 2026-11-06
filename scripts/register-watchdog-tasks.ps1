# Register the workbench watchdog scheduled tasks. MUST run elevated
# (task registration writes the machine task store).
#
# Tasks:
#   WorkbenchDashboard - every 5 min: restart the dashboard when :8766 is down.
#   MsiUdpWatchdog     - every 5 min, elevated: restart MSI_Center_Service when
#                        MSI.CentralServer holds >2000 UDP endpoints; records
#                        every incident in .tmp/msi-watchdog/incidents.log.
# Idempotent: existing tasks with these names are replaced.
# Remove: Unregister-ScheduledTask -TaskName WorkbenchDashboard,MsiUdpWatchdog -Confirm:$false

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\Jakub\PycharmProjects\ai-workbench'

function New-FiveMinuteLogonTrigger {
    $trigger = New-ScheduledTaskTrigger -AtLogon -RandomDelay (New-TimeSpan -Minutes 1)
    $trigger.Repetition = $(
        New-ScheduledTaskTrigger -Once -At (Get-Date) `
            -RepetitionInterval (New-TimeSpan -Minutes 5) `
            -RepetitionDuration (New-TimeSpan -Days 1)
    ).Repetition
    return $trigger
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden

$tasks = @(
    @{
        Name = 'WorkbenchDashboard'
        Script = 'scripts\dashboard-keepalive.ps1'
        Description = 'Restart the workbench dashboard when its status probe fails.'
        RunLevel = 'Limited'
    },
    @{
        Name = 'MsiUdpWatchdog'
        Script = 'scripts\msi-udp-watchdog.ps1'
        Description = 'Restart MSI Center service on UDP leak; record incidents.'
        RunLevel = 'Highest'
    }
)

foreach ($task in $tasks) {
    $scriptPath = Join-Path $repo $task.Script
    if (-not (Test-Path -LiteralPath $scriptPath)) { throw "missing script: $scriptPath" }
    Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false -ErrorAction SilentlyContinue
    $action = New-ScheduledTaskAction -Execute 'powershell' `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ' + $scriptPath)
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive -RunLevel $task.RunLevel
    Register-ScheduledTask -TaskName $task.Name -Trigger (New-FiveMinuteLogonTrigger) `
        -Action $action -Settings $settings -Principal $principal `
        -Description $task.Description | Out-Null
    "registered: $($task.Name) ($($task.RunLevel))"
}
