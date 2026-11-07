# Register the workbench watchdog scheduled tasks. MUST run elevated
# (task registration writes the machine task store).
#
# Tasks:
#   WorkbenchDashboard - every 5 min: restart the dashboard when :8766 is down.
#   MsiUdpWatchdog     - every 5 min, elevated: restart MSI_Center_Service when
#                        MSI.CentralServer holds >2000 UDP endpoints; records
#                        every incident in .tmp/msi-watchdog/incidents.log.
#   CloneScan          - weekly Sunday 06:00: duplication scan, inbox brief
#                        only when new clone groups appear.
#   WakeSelfTest       - weekly Sunday 06:30: wake-path self-test, mail
#                        only on failure.
# Idempotent: existing tasks with these names are replaced.
# Remove: Unregister-ScheduledTask -TaskName WorkbenchDashboard,MsiUdpWatchdog,CloneScan,WakeSelfTest -Confirm:$false

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

function New-WeeklyTrigger {
    param([string]$At = '06:00')
    return New-ScheduledTaskTrigger -Weekly -At $At -DaysOfWeek Sunday
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
    },
    @{
        Name = 'CloneScan'
        Script = 'scripts\clone-scan-scheduled.ps1'
        Description = 'Weekly duplication scan; inbox brief only on new groups.'
        RunLevel = 'Limited'
        Trigger = 'Weekly'
        At = '06:00'
    },
    @{
        Name = 'WakeSelfTest'
        Script = 'scripts\wake-self-test.ps1'
        Description = 'Weekly wake-path self-test; mail only on failure.'
        RunLevel = 'Limited'
        Trigger = 'Weekly'
        At = '06:30'
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
    $trigger = if ($task.Trigger -eq 'Weekly') { New-WeeklyTrigger -At $task.At } else { New-FiveMinuteLogonTrigger }
    Register-ScheduledTask -TaskName $task.Name -Trigger $trigger `
        -Action $action -Settings $settings -Principal $principal `
        -Description $task.Description | Out-Null
    "registered: $($task.Name) ($($task.RunLevel))"
}
